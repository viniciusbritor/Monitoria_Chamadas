"""
Modulo de Monitoria de Chamadas - API Backend
============================================

OBJETIVO PRINCIPAL:
  1. Upload de chamada (audio file)
  2. Transcricao audio -> texto (Whisper)
  3. Separar audio atendente e cliente (diarizacao)
  4. Avaliar nota QA do atendente e nota NPS do cliente (LLM)
  5. Categorizar motivos principais da chamada

STACK:
  - FastAPI (web framework)
  - Firestore (database - source of truth)
  - Google Cloud Pub/Sub (job queue async)
  - faster-whisper (transcricao local)
  - MiniMax M3 (LLM para avaliacao)
  - Firebase Auth (SSO via Portal)

DEPLOY:
  - Cloud Run: monitoria-test-env
  - URL: https://monitoria-test-env-894828119087.us-central1.run.app
"""
import os
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uuid
import shutil
from datetime import datetime
import json
import jwt

# Firebase Admin (substitui Google OAuth direto - agora validamos tokens emitidos pelo Portal)
try:
    import firebase_admin
    from firebase_admin import credentials, auth as fb_auth
    if not firebase_admin._apps:
        _fb_project = os.getenv("FIRESTORE_PROJECT_ID", "coherence-ominichannel-fs")
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": _fb_project})
except Exception as _e:
    print(f"Aviso: firebase-admin nao inicializado: {_e}")
    fb_auth = None

from core.transcriber import Transcriber, preload_model
from core.evaluator import Evaluator
from core.portal_auth import is_authorized_for_module, get_user_role_and_admin, require_admin_user
from core.masker import mask_pii
from core import pubsub_admin
from core.db import (
    get_db, get_call, list_calls, update_call_status, cleanup_orphans as cleanup_orphans_db,
    get_user_settings, upsert_user_settings,
)

MODULE_ID = "monitoria-chamadas"

app = FastAPI(title="Monitoria de Chamadas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# GUARDRAIL: Acesso exclusivo via Portal Coherence (Regra #0 do GUARDRAILS.md)
# ============================================================================
# A URL do modulo NAO e' publica. O unico caminho de acesso legitimo e' via
# Portal: window.open(module.url + '?token=' + firebase_id_token).
# Requests ao SPA root (/) sem Referer do Portal sao logadas como alerta
# de seguranca. O frontend ja exibe a pagina "Acesso via Portal Coherence"
# nesses casos; este middleware adiciona telemetria para auditoria.
ALLOWED_PORTAL_REFERERS = frozenset([
    u.strip().lower().rstrip("/")
    for u in os.getenv(
        "ALLOWED_PORTAL_REFERERS",
        "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app,"
        "https://monitoria.coherenceai.com.br,"
        "https://coherence-portal-prod-c5nbfc5meq-uc.a.run.app,"
        "http://localhost:5173,"  # dev local (Vite)
        "http://localhost:8001,"  # dev local (FastAPI)
    ).split(",")
    if u.strip()
])


@app.middleware("http")
async def enforce_portal_only_access(request, call_next):
    """Telemetria para tentativas de acesso direto a URL do modulo.

    Comportamento:
      - SPA entry point (/, /index.html): se Referer NAO for do Portal OU
        ausente (acesso direto/curl), loga alerta de seguranca. NAO bloqueia
        para nao quebrar testes de QA / load balancer health probe.
      - API calls seguem auth normal via Depends(get_current_user).
      - Endpoints publicos intencionais (/api/auth/portal-sso, /api/internal/*)
        sao isentos pois o fluxo legitimo exige token de qualquer forma.
    """
    path = request.url.path
    referer = (request.headers.get("referer") or "").lower().rstrip("/")
    user_agent = request.headers.get("user-agent", "")
    client_ip = request.client.host if request.client else "?"

    # SPA entry point: checa Referer contra lista de Portals permitidos
    if path in ("/", "/index.html"):
        if referer and not any(referer.startswith(p) for p in ALLOWED_PORTAL_REFERERS):
            print(
                f"[Security] direct-access attempt: path={path} "
                f"referer={referer!r} ua={user_agent[:80]!r} ip={client_ip}",
                flush=True,
            )
        elif not referer and user_agent:
            print(
                f"[Security] direct-access attempt (no-referer): path={path} "
                f"ua={user_agent[:80]!r} ip={client_ip}",
                flush=True,
            )

    return await call_next(request)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def init_db():
    """No-op mantido para compat. Firestore nao precisa de schema initialization
    (collections sao criadas lazily). Indices sao provisionados via terraform/gcloud.

    Historico:
    - Pre-06/07/2026: criava tabelas SQLite (users, access_requests, chamadas, user_settings)
    - 06/07/2026 (Plano A++): migracao completa para Firestore. Tabelas users e
      access_requests removidas (mortas desde migracao SSO Portal em 03/07/2026).
    """
    pass


@app.on_event("startup")
def startup_event():
    init_db()
    if fb_auth is None:
        print("ERRO CRITICO: firebase-admin nao foi inicializado. Verifique FIRESTORE_PROJECT_ID.", flush=True)
    # Otimizacao C: pre-carregar modelo Whisper no startup
    # Salva ~33s no primeiro upload
    try:
        get_transcriber()
        print("Transcriber pre-carregado no startup", flush=True)
    except Exception as e:
        print(f"AVISO: Falha ao pre-carregar Transcriber: {e}", flush=True)

def get_current_user(authorization: str = Header(None)):
    """Valida Firebase token, valida permissao no Portal via /api/auth/me, retorna user info.

    Fluxo (Fase 8 - 03/07/2026):
      1. Extrai Bearer token do header Authorization
      2. Valida Firebase token LOCALMENTE (firebase_admin.verify_id_token)
      3. Consulta Portal: GET /api/auth/me?module_id=monitoria-chamadas com Bearer
         - 200 = user tem permissao (payload completo da sessao)
         - 403 = user NAO tem (Portal ja gravou ACCESS_DENIED automatico)
         - 401/503 = tratar como falha transitoria
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        token = authorization.split("Bearer ")[1]
        if fb_auth is None:
            raise HTTPException(status_code=503, detail="firebase-admin nao disponivel no servidor")
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token sem email")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")

    # Valida permissao no Portal via /api/auth/me?module_id=... (1 chamada).
    # O Portal grava ACCESS_DENIED automaticamente no audit log quando retorna 403,
    # entao NAO precisamos chamar log_access_denied aqui (era redundante ate a Fase 8).
    # is_authorized_for_module retorna False quando Portal retorna 403; nunca re-raise.
    if not is_authorized_for_module(email, MODULE_ID, token):
        raise HTTPException(
            status_code=403,
            detail=f"Acesso negado: {email} nao tem permissao para '{MODULE_ID}'",
        )

    # Decora user com role info vinda do payload /api/auth/me
    role_info = get_user_role_and_admin(email, token)
    decoded["is_super_admin"] = role_info["is_super_admin"]
    decoded["client_id"] = role_info["client_id"]
    decoded["role"] = "admin" if role_info["is_super_admin"] else "user"
    return decoded

def save_user(user_info):
    pass # Usuários agora são salvos no banco global do SSO

# SSO handoff: Portal abre Monitoria com ?token=<jwt> e Monitoria valida + cria sessao
@app.post("/api/auth/portal-sso")
def portal_sso(token: str = Form(...)):
    """Valida Firebase token vindo do Portal e cria sessao local."""
    if fb_auth is None:
        raise HTTPException(status_code=503, detail="firebase-admin nao disponivel")
    try:
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token sem email")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")

    # Verifica permissao via /api/auth/me?module_id=... (1 chamada, Portal ja grava ACCESS_DENIED).
    # Nao chamamos log_access_denied aqui - Portal ja fez isso no 403.
    if not is_authorized_for_module(email, MODULE_ID, token):
        raise HTTPException(status_code=403, detail=f"Acesso negado: {email} sem permissao para '{MODULE_ID}'")

    role_info = get_user_role_and_admin(email, token)
    return {
        "email": email,
        "name": decoded.get("name"),
        "picture": decoded.get("picture"),
        "role": "admin" if role_info["is_super_admin"] else "user",
        "is_super_admin": role_info["is_super_admin"],
        "token": token,
    }

transcriber = None
evaluator = None

def get_transcriber():
    """Retorna Transcriber pre-carregado no startup."""
    global transcriber
    if transcriber is None:
        transcriber = Transcriber()
    return transcriber

def get_evaluator():
    """Retorna Evaluator (carga lazy para nao atrasar startup)."""
    global evaluator
    if evaluator is None:
        evaluator = Evaluator()
    return evaluator

def process_call_task(call_id: str, file_path: str, user_id: str, diretrizes_qualidade: str):
    def update_status(status_text):
        get_db().update(call_id, {"status": status_text})

    def update_progress(pct: float):
        """Atualiza apenas progress_pct (mantem status atual)."""
        get_db().update(call_id, {"progress_pct": pct})

    def read_audio_duration() -> float | None:
        """Le audio_duration_sec salvo no INSERT inicial."""
        try:
            call = get_call(call_id)
            if call and call.get("audio_duration_sec") is not None:
                return float(call["audio_duration_sec"])
            return None
        except Exception:
            return None

    try:
        # Busca configurações do usuário (Firestore collection user_settings)
        settings_doc = get_user_settings(user_id) or {}
        # Remove campos de controle interno antes de passar pro evaluator
        user_settings = {k: v for k, v in settings_doc.items()
                         if k not in ("user_id", "updated_at")}

        # Etapa 1: Transcricao Bruta com callback de progresso throttled
        update_status("Transcrevendo Audio (Whisper)...")
        last_progress_ts = [0.0]
        PROGRESS_THROTTLE_SEC = 2.0
        audio_duration_sec = read_audio_duration()

        def on_progress(segment_end: float, audio_total: float):
            now_ts = time.time()
            if now_ts - last_progress_ts[0] < PROGRESS_THROTTLE_SEC:
                return
            if audio_total <= 0:
                return
            pct = max(0.0, min(99.0, (segment_end / audio_total) * 100.0))
            last_progress_ts[0] = now_ts
            try:
                update_progress(pct)
            except Exception as e:
                print(f"[InProcess] update_progress falhou: {e}", flush=True)

        raw_transcript, segments = get_transcriber().transcribe(
            file_path,
            on_progress=on_progress,
            audio_duration_sec=audio_duration_sec,
        )
        update_progress(100.0)

        # Etapa 2: Diarizacao IA
        eval_ = get_evaluator()
        update_status(f"Separando falas (Diarizacao {eval_.client.last_provider_used or 'IA'})...")
        diarized_transcript = eval_.diarize(raw_transcript)

        # Etapa 3: Avaliacao IA
        update_status(f"Analisando Qualidade e Sentimento ({eval_.client.last_provider_used or 'IA'})...")
        checklist_str = user_settings.get("checklist_items", "[]")
        estrategia_vendas = user_settings.get("estrategia_vendas", "")
        estrategia_retencao = user_settings.get("estrategia_retencao", "")
        pop_context = f"Checklist: {checklist_str}. "
        if estrategia_vendas:
            pop_context += f"Vendas: {estrategia_vendas}. "
        if estrategia_retencao:
            pop_context += f"Retencao: {estrategia_retencao}. "
        pop_context += f"Diretrizes: {diretrizes_qualidade}" if diretrizes_qualidade else "Diretrizes: Cordialidade, Resolucao, Empatia, Clareza."
        evaluation = eval_.evaluate(diarized_transcript, user_settings=user_settings, pop_context=pop_context, quality_form=diretrizes_qualidade)

        # Etapa 4: Conclusão
        nota = evaluation.get("nota_geral")
        if isinstance(nota, str) and "%" in nota:
            nota = int(nota.replace("%", "").strip())
        elif isinstance(nota, (int, float)):
            nota = int(nota)
        else:
            nota = 0

        nota_sentimento_cliente = evaluation.get("nota_sentimento_cliente", 5)
        nota_qualidade_operador = evaluation.get("nota_qualidade_operador", nota)

        # Persiste resultado final via Firestore (Firestore sanitiza dicts/lists)
        get_db().update(call_id, {
            "status": "Concluído",
            "nota": nota,
            "transcricao": mask_pii(" ".join(seg.get("text", "") for seg in segments)),
            "sentimentos_cliente": evaluation.get("sentimentos_cliente", []),
            "sentimentos_operador": evaluation.get("sentimentos_operador", []),
            "erros_fatais": evaluation.get("erros_fatais_identificados", []),
            "raw_evaluation": evaluation,
            "transcricao_diarizada": mask_pii(diarized_transcript),
            "nota_sentimento_cliente": nota_sentimento_cliente,
            "nota_qualidade_operador": nota_qualidade_operador,
        })

    except Exception as e:
        update_status(f"Erro: {str(e)}")

@app.get("/api/auth/me")
def get_me(user = Depends(get_current_user)):
    save_user(user)
    return user

@app.post("/api/request-access")
async def request_access(email: str = Form(...)):
    """Endpoint legado removido em 06/07/2026 (Plano A++).

    Substituido pelo fluxo SSO Portal: admin gerencia permissoes direto no Firestore
    via Portal Coherence (que e' source of truth de sessoes). Para solicitar acesso
    ao modulo, o usuario deve pedir ao admin do Portal — nao ha mais self-service aqui.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint removido. Solicite acesso ao admin do Portal Coherence.",
    )


@app.get("/api/approve-access")
async def approve_access(token: str):
    """Endpoint legado removido em 06/07/2026 (Plano A++).

    Substituido pelo Portal Coherence: admin aprova/revoga permissoes direto
    no Firestore via /admin/permissions do Portal.
    """
    raise HTTPException(
        status_code=410,
        detail="Endpoint removido. Gerencie permissoes no Portal Coherence.",
    )


class UserSettings(BaseModel):
    checklist_items: str
    estrategia_vendas: str
    estrategia_retencao: str


@app.get("/api/settings")
def get_settings(user = Depends(get_current_user)):
    """Retorna settings de QA do usuario logado (Firestore user_settings)."""
    doc = get_user_settings(user.get("sub"))
    if doc:
        # Remove chaves internas
        return {
            "checklist_items": doc.get("checklist_items", "[]"),
            "estrategia_vendas": doc.get("estrategia_vendas", ""),
            "estrategia_retencao": doc.get("estrategia_retencao", ""),
        }
    return {
        "checklist_items": "[]",
        "estrategia_vendas": "",
        "estrategia_retencao": ""
    }


@app.post("/api/settings")
def save_settings(settings: UserSettings, user = Depends(get_current_user)):
    """Persiste settings de QA do usuario (Firestore upsert)."""
    upsert_user_settings(user.get("sub"), {
        "checklist_items": settings.checklist_items,
        "estrategia_vendas": settings.estrategia_vendas,
        "estrategia_retencao": settings.estrategia_retencao,
    })
    return {"message": "Configurações salvas com sucesso"}


@app.get("/api/calls")
def get_calls(user = Depends(get_current_user)):
    """Lista chamadas do usuario (Firestore list_all com filtro user_id)."""
    calls = list_calls(limit=100, user_id_filter=user.get("sub"))
    # Firestore retorna dicts; mantem shape compativel com frontend atual.
    # O frontend espera camelCase/snake_case misto; mantemos snake_case (original).
    return calls


@app.get("/api/calls/{call_id}")
def get_call_endpoint(call_id: str, user = Depends(get_current_user)):
    """Retorna detalhes de 1 chamada (Firestore get).

    Ownership:
    - User normal so ve suas proprias chamadas (user_id == sub).
    - Super-admin (is_super_admin=True) pode ver qualquer chamada.
      Util para investigar orfaos, debug de upload, etc.
    """
    call_data = get_call(call_id)
    if not call_data:
        raise HTTPException(status_code=404, detail="Chamada não encontrada")
    # Validar ownership: user so ve suas proprias chamadas, EXCETO super-admin
    if call_data.get("user_id") != user.get("sub"):
        is_super = user.get("is_super_admin", False)
        if not is_super:
            raise HTTPException(status_code=403, detail="Sem permissão para esta chamada")
        # Super-admin override: log para auditoria
        print(
            f"[AdminBypass] super-admin={user.get('email')} sub={user.get('sub')} "
            f"acessando chamada {call_id[:8]}... de outro user "
            f"(owner_sub={call_data.get('user_id')})",
            flush=True,
        )
    # Firestore ja serializa dicts/lists via _sanitize; campos JSON ja vem como dict/list.
    # Mantem shape original (Firestore retorna datetime objects para timestamps — converter pra ISO).
    for ts_field in ("uploaded_at", "created_at", "updated_at"):
        if ts_field in call_data and hasattr(call_data[ts_field], "isoformat"):
            call_data[ts_field] = call_data[ts_field].isoformat()
    return call_data

@app.get("/api/calls/{call_id}/audio")
def get_call_audio_endpoint(call_id: str, user = Depends(get_current_user)):
    """Gera Signed URL para o audio salvo no GCS (playback no frontend)."""
    call_data = get_call(call_id)
    if not call_data or "gcs_uri" not in call_data or not call_data["gcs_uri"]:
        raise HTTPException(status_code=404, detail="Áudio não encontrado ou já deletado")
        
    if call_data.get("user_id") != user.get("sub"):
        is_super = user.get("is_super_admin", False)
        if not is_super:
            raise HTTPException(status_code=403, detail="Sem permissão para esta chamada")
            
    gcs_uri = call_data["gcs_uri"]
    try:
        bucket_name = gcs_uri.split("/")[2]
        blob_name = "/".join(gcs_uri.split("/")[3:])
        
        from google.cloud import storage as gcs_storage
        gcs_client = gcs_storage.Client()
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Arquivo deletado do storage")
            
        import datetime
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=120),
            method="GET"
        )
        return {"audio_url": url}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API] Erro gerando signed_url para {gcs_uri}: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar link do áudio")


@app.delete("/api/calls/{call_id}")
def delete_call_endpoint(call_id: str, user = Depends(get_current_user)):
    """Deleta uma chamada e seus dados associados (LGPD Art. 18, IV).

    Remove documento do Firestore e audio do GCS. Apenas owner ou
    super-admin pode deletar. Acao e' irreversivel.
    """
    call_data = get_call(call_id)
    if not call_data:
        raise HTTPException(status_code=404, detail="Chamada nao encontrada")

    if call_data.get("user_id") != user.get("sub"):
        if not user.get("is_super_admin", False):
            raise HTTPException(status_code=403, detail="Sem permissao para deletar esta chamada")
        print(
            f"[AdminBypass] super-admin={user.get('email')} DELETANDO chamada {call_id[:8]}... "
            f"de outro user (owner_sub={call_data.get('user_id')})",
            flush=True,
        )

    gcs_uri = call_data.get("gcs_uri")
    gcs_deleted = False
    if gcs_uri:
        try:
            from google.cloud import storage as gcs_storage
            bucket_name = gcs_uri.replace("gs://", "").split("/")[0]
            blob_name = gcs_uri.replace(f"gs://{bucket_name}/", "")
            gcs_client = gcs_storage.Client()
            blob = gcs_client.bucket(bucket_name).blob(blob_name)
            if blob.exists():
                blob.delete()
                gcs_deleted = True
                print(f"[Delete] Audio deletado do GCS: {gcs_uri}", flush=True)
        except Exception as e:
            print(f"[Delete] Falha ao deletar audio do GCS: {e}", flush=True)

    get_db().delete(call_id)
    print(f"[Delete] call_id={call_id[:8]}... deletado do Firestore por {user.get('email')}", flush=True)
    return {"deleted": True, "call_id": call_id, "gcs_deleted": gcs_deleted}

@app.post("/api/upload")
async def upload_audio(
    background_tasks_fallback: BackgroundTasks,
    file: UploadFile = File(...),
    diretrizes: str = Form(""),
    user = Depends(get_current_user)
):
    """
    Fase C+ (05/07/2026): Hibrido Pub/Primary, fallback BackgroundTasks.

    SEMPRE salva audio no GCS primeiro (durabilidade). Decide o worker:
      - Worker saudavel E audio <= 50MB: Pub/Sub (worker dedicado).
      - Caso contrario: BackgroundTasks in-process como degradacao
        imediata (latencia de producao, zero espera de fila).

    In-process fallback agora tambem:
      - Mantem arquivo em GCS (ja' salvo no passo 1).
      - Persiste gcs_uri no DB.
      - BackgroundTask processa localmente MAS, se morrer (SIGTERM),
        o endpoint /api/internal/recover-stale detecta e re-enfileira
        no Pub/Sub para o worker retomar.
    """
    call_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{call_id}_{file.filename}")

    # 1. Salva audio local temporariamente
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"[Upload] call_id={call_id} arquivo={file.filename} tamanho={file_size_mb:.2f}MB", flush=True)

    # 2. Upload para GCS (SEMPRE - garante durabilidade)
    gcs_bucket = os.getenv("AUDIO_BUCKET", "coherence-monitoria-audios-tmp")
    gcs_path = f"{call_id}_{file.filename}"
    gcs_uri = None
    gcs_ok = False
    try:
        from google.cloud import storage as gcs_storage
        gcs_client = gcs_storage.Client()
        bucket = gcs_client.bucket(gcs_bucket)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(file_path)
        gcs_uri = f"gs://{gcs_bucket}/{gcs_path}"
        gcs_ok = True
        print(f"[Upload] Audio salvo em {gcs_uri}", flush=True)
    except Exception as e:
        print(f"[Upload] FALHA ao subir para GCS: {e}. Fallback total.", flush=True)

    # 3. Decide path (hibrido)
    worker_ok = _worker_healthy()
    use_pubsub = worker_ok and file_size_mb <= 50.0 and gcs_ok

    if not use_pubsub:
        if not gcs_ok:
            reason = "gcs_fail"
            initial_status = "Erro: falha no upload GCS - reenvie"
        elif not worker_ok:
            reason = "worker_unhealthy"
            initial_status = "Transcrevendo Audio (Whisper)..."
        else:
            reason = f"audio_grande ({file_size_mb:.1f}MB > 50MB)"
            initial_status = "Transcrevendo Audio (Whisper)..."
        print(f"[Upload] fallback in-process: reason={reason}", flush=True)

        # Probe duracao do audio via ffprobe para UI mostrar progresso real
        audio_duration_sec = _probe_audio_duration(file_path)

        # Persiste com gcs_uri (se disponivel) para permitir recover posterior
        now = datetime.now().isoformat()
        get_db().create(call_id, {
            "filename": file.filename,
            "uploaded_at": now,
            "status": initial_status,
            "user_id": user.get("sub"),
            "diretrizes_qualidade": diretrizes,
            "gcs_uri": gcs_uri,
            "audio_duration_sec": audio_duration_sec,
            "progress_pct": 0.0,
        })

        if not gcs_ok:
            # Sem GCS, nao ha como recuperar. Retorna erro.
            return {"message": "Falha no upload do audio", "id": call_id, "mode": "error", "reason": reason}

        # BackgroundTask processa localmente. Se morrer (SIGTERM),
        # o endpoint recover-stale re-enfileira no Pub/Sub.
        background_tasks_fallback.add_task(process_call_task, call_id, file_path, user.get("sub"), diretrizes)
        return {"message": "Processamento iniciado (in-process)", "id": call_id, "mode": "local", "reason": reason}

    # 4. Path Pub/Sub (primario)
    # Probe duracao do audio via ffprobe para UI mostrar progresso real
    audio_duration_sec = _probe_audio_duration(file_path)

    now = datetime.now().isoformat()
    get_db().create(call_id, {
        "filename": file.filename,
        "uploaded_at": now,
        "status": "Na Fila de Processamento...",
        "user_id": user.get("sub"),
        "diretrizes_qualidade": diretrizes,
        "gcs_uri": gcs_uri,
        "audio_duration_sec": audio_duration_sec,
        "progress_pct": 0.0,
    })

    # 5. Publica job no Pub/Sub
    try:
        from google.cloud import pubsub_v1
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(
            os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"),
            os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs"),
        )
        message_data = json.dumps({
            "call_id": call_id,
            "gcs_uri": gcs_uri,
            "filename": file.filename,
            "user_id": user.get("sub"),
            "diretrizes": diretrizes,
            "uploaded_at": now,
            "audio_duration_sec": audio_duration_sec,
        }).encode("utf-8")
        future = publisher.publish(topic_path, message_data)
        message_id = future.result(timeout=10)
        print(f"[Upload] Job publicado no Pub/Sub: {message_id}", flush=True)
    except Exception as e:
        print(f"[Upload] FALHA ao publicar no Pub/Sub: {e}. Marcando para recover.", flush=True)

    # 6. Cleanup arquivo local
    try:
        os.remove(file_path)
    except OSError:
        pass

    return {"message": "Processamento iniciado", "id": call_id, "mode": "pubsub"}


# ============================================================================
# NEW (08/07/2026 - Plano Ultra-Economico): Upload em BATCH
# ============================================================================
# Habilita dropar varios arquivos de uma vez. Cada arquivo vira 1 chamada
# independente (Firestore row + Pub/Sub message). Worker processa em paralelo
# ate max-instances=2 instancias.
#
# Limitacoes (GUARDRAILS):
# - MAX_FILES = 50 por request
# - MAX_FILE_SIZE = 20MB por arquivo (worker tem 4 GiB)
#
# Comportamento:
# - Para cada arquivo valido: upload GCS + INSERT Firestore + publish Pub/Sub
# - Arquivos rejeitados (muito grandes) retornam error no resultado individual
# - Request inteiro retorna 200 mesmo com erros parciais (cliente checa results[])
# ============================================================================
@app.post("/api/upload-batch")
async def upload_batch(
    files: list[UploadFile] = File(..., description="Max 50 arquivos por batch"),
    diretrizes: str = Form(""),
    user = Depends(get_current_user),
):
    """Upload em batch. Cada arquivo vira 1 chamada independente."""
    MAX_FILES = 50
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB (worker 4 GiB - GUARDRAILS Regra #11)

    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximo {MAX_FILES} arquivos por batch (recebido: {len(files)})",
        )
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado")

    from google.cloud import pubsub_v1, storage as gcs_storage

    gcs_bucket_name = os.getenv("AUDIO_BUCKET", "coherence-monitoria-audios-tmp")
    gcs_client = gcs_storage.Client()
    bucket = gcs_client.bucket(gcs_bucket_name)

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"),
        os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs"),
    )

    results = []
    publish_futures = []

    for f in files:
        filename = f.filename or "audio.mp3"
        try:
            contents = await f.read()
        except Exception as e:
            results.append({
                "filename": filename,
                "call_id": None,
                "status": "error",
                "error": f"Falha ao ler arquivo: {e}",
            })
            continue

        if len(contents) > MAX_FILE_SIZE:
            results.append({
                "filename": filename,
                "call_id": None,
                "status": "error",
                "error": f"Arquivo excede {MAX_FILE_SIZE // (1024*1024)}MB",
            })
            continue

        call_id = str(uuid.uuid4())
        gcs_path = f"uploads/{user.get('sub')}/{call_id}_{filename}"
        gcs_uri = None

        # Upload GCS
        try:
            blob = bucket.blob(gcs_path)
            blob.upload_from_string(contents, content_type=f.content_type or "audio/mpeg")
            gcs_uri = f"gs://{gcs_bucket_name}/{gcs_path}"
        except Exception as e:
            print(f"[BatchUpload] GCS falhou {call_id}: {e}", flush=True)
            results.append({
                "filename": filename,
                "call_id": call_id,
                "status": "error",
                "error": f"Falha GCS: {e}",
            })
            continue

        # INSERT Firestore
        now = datetime.now().isoformat()
        try:
            get_db().create(call_id, {
                "filename": filename,
                "uploaded_at": now,
                "status": "Na Fila de Processamento...",
                "user_id": user.get("sub"),
                "diretrizes_qualidade": diretrizes,
                "gcs_uri": gcs_uri,
                "audio_duration_sec": None,
                "progress_pct": 0.0,
            })
        except Exception as e:
            print(f"[BatchUpload] Firestore create falhou {call_id}: {e}", flush=True)
            results.append({
                "filename": filename,
                "call_id": call_id,
                "status": "error",
                "error": f"Falha Firestore: {e}",
            })
            continue

        # Publish Pub/Sub
        try:
            payload = json.dumps({
                "call_id": call_id,
                "gcs_uri": gcs_uri,
                "filename": filename,
                "user_id": user.get("sub"),
                "diretrizes": diretrizes,
                "uploaded_at": now,
                "audio_duration_sec": None,
            }).encode("utf-8")
            publish_futures.append((
                call_id, filename, publisher.publish(topic_path, payload)
            ))
            results.append({
                "filename": filename,
                "call_id": call_id,
                "status": "queued",
            })
        except Exception as e:
            print(f"[BatchUpload] publish falhou {call_id}: {e}", flush=True)
            results.append({
                "filename": filename,
                "call_id": call_id,
                "status": "error",
                "error": f"Falha publish: {e}",
            })

    # Espera todos os publishes
    for call_id, filename, future in publish_futures:
        try:
            future.result(timeout=10)
        except Exception as e:
            print(f"[BatchUpload] publish result falhou {call_id}: {e}", flush=True)

    queued = sum(1 for r in results if r["status"] == "queued")
    errors = sum(1 for r in results if r["status"] == "error")
    print(
        f"[BatchUpload] user={user.get('email')} total={len(results)} "
        f"queued={queued} errors={errors}",
        flush=True,
    )

    return {
        "calls": results,
        "total": len(results),
        "queued": queued,
        "errors": errors,
    }

# ============================================================================
# Internal Worker Callback (service-to-service, OIDC)
# ============================================================================
# O worker dedicado (monitoria-whisper-worker) chama este endpoint para
# atualizar o status das chamadas que esta processando. Como worker e test-env
# estao em Cloud Run no mesmo projeto, a autenticacao usa Google Cloud
# identity tokens (OIDC). Nao requer secret compartilhado.

from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

# Audience esperada no identity token: o proprio URL do test-env.
# Cloud Run injeta esse valor automaticamente quando o worker chama o
# metadata server com audience=<nosso URL>.
TEST_ENV_AUDIENCE = os.getenv("TEST_ENV_AUDIENCE", "https://monitoria-test-env-894828119087.us-central1.run.app")


class InternalStatusUpdate(BaseModel):
    status: str  # processing | transcrevendo | analisando | concluido | erro
    transcript: str | None = None
    transcricao_diarizada: str | None = None
    qa_score: int | None = None
    qa_details: dict | None = None  # {nota_qualidade_operador, nota_sentimento_cliente, ...}
    error: str | None = None
    progress_pct: float | None = None  # 0-100, usado na fase Whisper (audio processado / total)


def _verify_cloud_run_identity(auth_header: str, request_url: str) -> dict:
    """Valida identity token do Cloud Run.

    Retorna o dict do token decodificado se valido (com 'sub', 'email', etc.).
    Levanta HTTPException 401 caso contrario.
    """
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        idinfo = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=TEST_ENV_AUDIENCE,
        )
        # Verifica que o emissor e o Google (nao terceiros)
        if idinfo.get("iss") not in ("https://accounts.google.com", "accounts.google.com"):
            raise HTTPException(status_code=401, detail="Invalid issuer")
        return idinfo
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid identity token: {e}")


# NEW (07/07/2026): normalizar variantes de status para forma canonica.
# Defende contra typos futuros ("Concluido" vs "Concluído") sem quebrar
# workers antigos em producao durante a janela de deploy.
# Tambem protege o idempotency check em worker.py:363 que compara com acento.
# Erro: variantes NAO sao normalizadas (sao livres e significativas).
STATUS_NORMALIZATION = {
    "Concluido": "Concluído",       # sem acento (typo historico pre-07/07/2026)
    "concluido": "Concluído",       # lowercase
    "concluído": "Concluído",       # lowercase com acento
    "CONCLUIDO": "Concluído",       # uppercase
    "CONCLUÍDO": "Concluído",       # uppercase com acento
}


@app.post("/api/internal/calls/{call_id}/status")
async def internal_update_call_status(
    call_id: str,
    body: InternalStatusUpdate,
    request: Request,
):
    """Callback do worker dedicado para atualizar status de uma chamada.

    Autenticado via Google Cloud identity token (OIDC). O worker obtem seu
    proprio token do metadata server e envia como Authorization: Bearer.

    Body:
      {
        "status": "transcrevendo",
        "transcript": "...",
        "qa_score": 85,
        "qa_details": {...},
        "error": null
      }

    Substitui o padrao anterior (worker escreve em SQLite GCS, test-env le
    local) que resultava em UI sempre mostrando 'Na Fila de Processamento...'.
    """
    auth_header = request.headers.get("Authorization", "")
    _verify_cloud_run_identity(auth_header, str(request.base_url))

    # Verifica que chamada existe (Firestore)
    call = get_call(call_id)
    if not call:
        raise HTTPException(status_code=404, detail=f"Chamada {call_id} nao encontrada")

    # NEW (07/07/2026): normalizar variantes de status (defesa contra typos).
    # Garante que Firestore sempre grava forma canonica "Concluído" (com acento),
    # independente do que o worker envia. Veja STATUS_NORMALIZATION acima.
    normalized_status = STATUS_NORMALIZATION.get(body.status, body.status)
    if normalized_status != body.status:
        print(
            f"[InternalCallback] call_id={call_id} status NORMALIZADO: "
            f"{body.status!r} -> {normalized_status!r}",
            flush=True,
        )

    # Monta update_fields para Firestore (last-write-wins; nao ha COALESCE,
    # entao so atualizamos campos explicitamente enviados)
    update_fields = {"status": normalized_status}

    if body.qa_score is not None:
        update_fields["nota"] = body.qa_score

    if body.transcript is not None:
        update_fields["transcricao"] = body.transcript

    if body.transcricao_diarizada is not None:
        update_fields["transcricao_diarizada"] = body.transcricao_diarizada

    if body.qa_details:
        if "nota_qualidade_operador" in body.qa_details:
            update_fields["nota_qualidade_operador"] = body.qa_details["nota_qualidade_operador"]
        if "nota_sentimento_cliente" in body.qa_details:
            update_fields["nota_sentimento_cliente"] = body.qa_details["nota_sentimento_cliente"]
        if "raw_evaluation" in body.qa_details:
            update_fields["raw_evaluation"] = body.qa_details["raw_evaluation"]
        if "sentimentos_cliente" in body.qa_details:
            update_fields["sentimentos_cliente"] = body.qa_details["sentimentos_cliente"]
        if "sentimentos_operador" in body.qa_details:
            update_fields["sentimentos_operador"] = body.qa_details["sentimentos_operador"]
        if "erros_fatais_identificados" in body.qa_details:
            update_fields["erros_fatais"] = body.qa_details["erros_fatais_identificados"]

    if body.progress_pct is not None:
        pct = max(0.0, min(100.0, float(body.progress_pct)))
        update_fields["progress_pct"] = pct

    get_db().update(call_id, update_fields)

    print(f"[InternalCallback] call_id={call_id} status={normalized_status} qa_score={body.qa_score}", flush=True)
    return {"updated": True, "call_id": call_id, "status": normalized_status}


# ============================================================================
# Recovery: detecta jobs orfaos (BackgroundTask morto por SIGTERM/deploy)
# ============================================================================
# Chamadas em status inicial (Transcrevendo/Na Fila) ha mais de STALE_MIN
# minutos E com gcs_uri presente = SIGTERM matou o BackgroundTask.
# Solucao: republicar job no Pub/Sub para o worker retomar do GCS.
STALE_MINUTES = int(os.getenv("STALE_RECOVERY_MIN", "12"))


@app.post("/api/internal/recover-stale")
async def recover_stale_jobs(request: Request):
    """Detecta jobs orfaos (in-process SIGTERM) e re-enfileira no Pub/Sub.

    Autenticado via OIDC (mesmo padrao do callback do worker). Chamado
    por cron externo ou manualmente quando o owner detecta travamento.

    Criterio: status comeca com 'Transcrevendo' OU 'Na Fila' E
    uploaded_at < now() - STALE_MINUTES E gcs_uri IS NOT NULL.
    """
    auth_header = request.headers.get("Authorization", "")
    _verify_cloud_run_identity(auth_header, str(request.base_url))

    # Firestore: lista chamadas orfas via list_stale (ja implementado no core/db.py)
    # Filtra adicionalmente por gcs_uri presente (worker so' pode retomar do GCS)
    all_stale = get_db().list_stale(older_than_seconds=STALE_MINUTES * 60)
    stale_jobs = [j for j in all_stale if j.get("gcs_uri")][:20]

    if not stale_jobs:
        return {"recovered": 0, "stale_jobs": []}

    recovered = []
    for job in stale_jobs:
        try:
            from google.cloud import pubsub_v1
            publisher = pubsub_v1.PublisherClient()
            topic_path = publisher.topic_path(
                os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"),
                os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs"),
            )
            message_data = json.dumps({
                "call_id": job["call_id"],
                "gcs_uri": job["gcs_uri"],
                "filename": job.get("filename"),
                "user_id": job.get("user_id"),
                "diretrizes": job.get("diretrizes_qualidade") or "",
                "uploaded_at": job.get("uploaded_at").isoformat() if hasattr(job.get("uploaded_at"), "isoformat") else job.get("uploaded_at"),
                "recovered": True,
            }).encode("utf-8")
            future = publisher.publish(topic_path, message_data)
            message_id = future.result(timeout=10)
            recovered.append({
                "call_id": job["call_id"],
                "gcs_uri": job["gcs_uri"],
                "pubsub_message_id": message_id,
                "stale_status": job.get("status"),
            })
            print(
                f"[Recover] call_id={job['call_id']} re-enfileirado (msg={message_id}) "
                f"stale_status={job.get('status')!r}",
                flush=True,
            )
        except Exception as e:
            print(f"[Recover] FALHA call_id={job.get('call_id')}: {e}", flush=True)

    return {"recovered": len(recovered), "stale_jobs": recovered}


# ============================================================================
# NEW (08/07/2026 - Plano Ultra-Economico): Re-enfileira TODAS as chamadas em "Na Fila"
# Independente da idade. Util quando worker ACKou mensagens mas falhou em salvar
# no Firestore (causa: 403 permission denied pre-fix). Acao manual via admin.
# ============================================================================
@app.post("/api/internal/reprocess-na-fila")
async def reprocess_na_fila(request: Request):
    """Re-enfileira TODAS as chamadas em status 'Na Fila de Processamento...'.

    Autenticado via OIDC. Util quando worker perdeu mensagens (ACK + 403 Firestore).
    Sem restricao de idade (reprocessa qualquer chamada em 'Na Fila' que tenha gcs_uri).
    """
    auth_header = request.headers.get("Authorization", "")
    _verify_cloud_run_identity(auth_header, str(request.base_url))

    all_na_fila = (
        get_db().collection
        .where("status", ">=", "Na Fila")
        .where("status", "<", "Na Fila" + "\uf8ff")
        .stream()
    )
    na_fila = [d for d in all_na_fila if d.to_dict().get("gcs_uri")]

    if not na_fila:
        return {"reprocessed": 0, "calls": []}

    from google.cloud import pubsub_v1
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(
        os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"),
        os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs"),
    )

    results = []
    for doc in na_fila:
        d = doc.to_dict()
        call_id = doc.id
        try:
            payload = json.dumps({
                "call_id": call_id,
                "gcs_uri": d.get("gcs_uri"),
                "filename": d.get("filename"),
                "user_id": d.get("user_id"),
                "diretrizes": d.get("diretrizes_qualidade") or "",
                "uploaded_at": d.get("uploaded_at"),
                "reprocessed": True,
            }).encode("utf-8")
            future = publisher.publish(topic_path, payload)
            msg_id = future.result(timeout=10)
            results.append({
                "call_id": call_id,
                "filename": d.get("filename"),
                "pubsub_message_id": msg_id,
            })
            print(f"[Reprocess] call_id={call_id[:8]}... re-enfileirado (msg={msg_id})", flush=True)
        except Exception as e:
            print(f"[Reprocess] FALHA call_id={call_id[:8]}...: {e}", flush=True)
            results.append({"call_id": call_id, "error": str(e)})

    return {"reprocessed": len([r for r in results if "pubsub_message_id" in r]), "calls": results}


# ============================================================================
# Queue Manager (Admin-only): visualizar e gerenciar fila Pub/Sub
# Implementa as Tasks 2.1-2.5 do backlog docs/goals/queue-manager.md
# ============================================================================

WORKER_URL = os.getenv("WORKER_URL", "https://monitoria-whisper-worker-c5nbfc5meq-uc.a.run.app")


def _probe_audio_duration(file_path: str) -> float | None:
    """Extrai duracao do audio em segundos via ffprobe. Retorna None se falhar."""
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, Exception):
        pass
    return None


def _worker_healthy() -> bool:
    """Checa saude do worker via GET /healthz.

    Worker responde:
      - 200 = saudavel (ready ou processing < 15min)
      - 503 = travado (stuck: ready+sem msg >5min OU processing >15min)
      - 403 = no-auth (worker requer IAM, mas servidor esta' vivo)

    200 e 403 = saudavel. 503 = unhealthy (fallback in-process).
    """
    try:
        import httpx
        # Worker so' expoe /healthz (nao /health). Mas helper historico usa /health.
        # /health retorna 404 (Cloud Run quando no-auth) ou 200/403 quando auth.
        # Estrategia: tentar /healthz primeiro; fallback /health.
        for path in ("/healthz", "/health"):
            try:
                r = httpx.get(WORKER_URL.rstrip("/") + path, timeout=3.0)
                if r.status_code in (200, 403):
                    # 200 = saudavel, 403 = autenticado requer IAM mas servidor up
                    return True
                if r.status_code == 503:
                    # Worker explicitamente reporta stuck
                    return False
                # 404 ou outros: tentar proximo path
            except httpx.HTTPError:
                continue
        # Todos paths retornaram 404 (Cloud Run com no-auth) -> servidor up
        return True
    except Exception:
        return False


@app.get("/api/queue/stats")
def queue_stats(user: dict = Depends(require_admin_user)):
    """Metricas da subscription Pub/Sub + saude do worker."""
    try:
        stats = pubsub_admin.get_stats()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha ao ler subscription: {e}")
    stats["worker_healthy"] = _worker_healthy()
    stats["subscription"] = pubsub_admin.PUBSUB_SUBSCRIPTION
    stats["topic"] = pubsub_admin.PUBSUB_TOPIC
    stats["project"] = pubsub_admin.GCP_PROJECT
    return stats


@app.get("/api/queue/messages")
def queue_messages(limit: int = 50, user: dict = Depends(require_admin_user)):
    """Lista mensagens pendentes (peek sem consumir). Max 50 por chamada."""
    limit = max(1, min(limit, 50))
    try:
        return pubsub_admin.list_pending(limit=limit)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Falha ao listar mensagens: {e}")


@app.post("/api/queue/messages/{message_id}/ack")
def queue_ack(message_id: str, ack_id: str, user: dict = Depends(require_admin_user)):
    """Descarta 1 mensagem orfa (acknowledge)."""
    n = pubsub_admin.acknowledge([ack_id])
    print(f"[Queue] user={user.get('email')} ACK message_id={message_id} -> {n}", flush=True)
    return {"acked": n, "message_id": message_id}


class RetryPayload(BaseModel):
    payload: str = ""
    attributes: dict = {}


@app.post("/api/queue/messages/{message_id}/retry")
def queue_retry(message_id: str, body: RetryPayload, user: dict = Depends(require_admin_user)):
    """Republica mensagem no topico com novo message_id."""
    new_id = pubsub_admin.retry_message(
        message_id,
        payload=body.payload,
        attributes=body.attributes,
    )
    print(f"[Queue] user={user.get('email')} RETRY {message_id} -> {new_id}", flush=True)
    return {"new_message_id": new_id, "original_message_id": message_id}


@app.post("/api/queue/purge")
def queue_purge(confirm: bool = False, user: dict = Depends(require_admin_user)):
    """Ack em massa: descarta TODAS mensagens pendentes (EXIGE confirm=true)."""
    if not confirm:
        raise HTTPException(status_code=400, detail="Passe confirm=true para confirmar purge")
    n = pubsub_admin.purge_all()
    print(f"[Queue] user={user.get('email')} PURGE -> {n} mensagens", flush=True)
    return {"purged": n}


# ============================================================================
# Cleanup de orfaos (Fase 1 / Fix #3)
# ============================================================================
# Marca como 'Erro' chamadas que ficaram presas em status inicial (Na Fila /
# Transcrevendo / Separando / Analisando) ha mais de STALE_MIN minutos.
# Libera a UI do owner (sai do loop "ficou travado").
#
# Autenticado via OIDC (mesmo padrao do callback do worker / recover-stale)
# para que possa ser chamado por cron externo alem do admin UI.
@app.post("/api/internal/cleanup-orphans")
async def cleanup_orphans(request: Request):
    auth_header = request.headers.get("Authorization", "")
    _verify_cloud_run_identity(auth_header, str(request.base_url))

    # Firestore: wrapper cleanup_orphans ja' marca status como erro e retorna IDs
    new_status = "Erro: processamento interrompido (orphaned >30min). Reenvie o audio."
    cleaned_ids = cleanup_orphans_db(older_than_seconds=30 * 60, new_status=new_status)

    print(f"[Cleanup] {len(cleaned_ids)} orfaos marcados como erro", flush=True)
    return {"cleaned": len(cleaned_ids), "orphans": cleaned_ids}


# Listagem de chamadas "stuck" (read-only) para o admin UI
@app.get("/api/admin/stuck-calls")
def stuck_calls(user: dict = Depends(require_admin_user)):
    """Lista chamadas em estado inicial >15min. Apenas visualizacao."""
    # Firestore: list_stale faz o filtro (status prefix + idade >15min)
    rows = get_db().list_stale(older_than_seconds=15 * 60)
    return {"stuck_count": len(rows), "stuck_calls": rows}


# REMOVIDO (07/07/2026 - refactor): endpoints de migracao de status.
# Função cumprida - 1 doc migrado (230e22e4-...). Bug do accent ja foi
# corrigido em commits anteriores (worker.py:303, api.py STATUS_NORMALIZATION).
# Mantemos apenas o normalizer no callback (defesa em profundidade).

# Frontend estático (Vite Build) - DEVE FICAR NO FINAL PARA NÃO SOBRESCREVER ROTAS /API
FRONTEND_DIR = os.path.join("frontend", "dist")
ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

from fastapi.responses import FileResponse

@app.get("/")
@app.get("/index.html")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        response = FileResponse(index_path)
        # Força o navegador a nunca fazer cache do index.html para garantir atualizações automáticas de UI
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return {"message": "Index HTML not found"}

@app.get("/{file_name}")
async def serve_root_file(file_name: str):
    file_path = os.path.join(FRONTEND_DIR, file_name)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")
