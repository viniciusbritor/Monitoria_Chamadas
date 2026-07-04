import os
import sqlite3
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
from core.portal_audit import log_access_denied
from core import pubsub_admin

MODULE_ID = "monitoria-chamadas"

app = FastAPI(title="Monitoria de Chamadas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DB_PATH = "/mnt/db/monitoria_ia.db" if os.path.exists("/mnt/db") else "monitoria_ia.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            name TEXT,
            picture TEXT,
            is_approved BOOLEAN DEFAULT 0,
            role TEXT DEFAULT 'user'
        )
    ''')
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except sqlite3.OperationalError:
        pass
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_requests (
            token TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            created_at DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chamadas (
            id TEXT PRIMARY KEY,
            filename TEXT,
            uploaded_at DATETIME,
            status TEXT,
            nota INTEGER,
            transcricao TEXT,
            sentimentos_cliente TEXT,
            sentimentos_operador TEXT,
            erros_fatais TEXT,
            raw_evaluation TEXT,
            user_id TEXT,
            diretrizes_qualidade TEXT,
            nota_sentimento_cliente INTEGER,
            nota_qualidade_operador INTEGER,
            transcricao_diarizada TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            checklist_items TEXT,
            estrategia_vendas TEXT,
            estrategia_retencao TEXT
        )
    ''')
    conn.commit()
    conn.close()

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

    # Valida permissao no Portal via /api/auth/me?module_id=... (1 chamada)
    # is_authorized_for_module ja levanta 403 quando Portal bloqueia.
    if not is_authorized_for_module(email, MODULE_ID, token):
        # 403 ja foi levantado por is_authorized_for_module via Portal.
        # Chegamos aqui so se is_authorized_for_module retornou False sem HTTPException,
        # o que nao acontece mais (helper propaga 403). Defesa em profundidade:
        log_access_denied(MODULE_ID, token, f"Tentativa de acesso ao modulo '{MODULE_ID}' negada")
        raise HTTPException(status_code=403, detail=f"Acesso negado: {email} nao tem permissao para '{MODULE_ID}'")

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

    # Verifica permissao via /api/auth/me?module_id=... (1 chamada, Portal ja grava ACCESS_DENIED)
    if not is_authorized_for_module(email, MODULE_ID, token):
        log_access_denied(MODULE_ID, token, "Tentativa de SSO Portal sem permissao")
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE chamadas SET status = ? WHERE id = ?", (status_text, call_id))
        conn.commit()
        conn.close()

    try:
        # Busca configurações do usuário
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
        settings_row = cursor.fetchone()
        conn.close()
        
        user_settings = {}
        if settings_row:
            user_settings = dict(settings_row)

        # Etapa 1: Transcrição Bruta
        update_status("Transcrevendo Áudio (Whisper)...")
        raw_transcript, segments = get_transcriber().transcribe(file_path)
        
        # Etapa 2: Diarização IA
        update_status("Separando falas (Diarização MiniMax)...")
        diarized_transcript = get_evaluator().diarize(raw_transcript)
        
        # Etapa 3: Avaliação IA
        update_status("Analisando Qualidade e Sentimento (MiniMax M3)...")
        evaluation = get_evaluator().evaluate(diarized_transcript, user_settings=user_settings, pop_context="", quality_form=diretrizes_qualidade)
        
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
            
        sentimentos_cliente = json.dumps(evaluation.get("sentimentos_cliente", []))
        sentimentos_operador = json.dumps(evaluation.get("sentimentos_operador", []))
        erros_fatais = json.dumps(evaluation.get("erros_fatais_identificados", []))
        raw_evaluation = json.dumps(evaluation)
        transcricao = json.dumps(segments)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE chamadas
            SET status = ?, nota = ?, transcricao = ?, sentimentos_cliente = ?, sentimentos_operador = ?, erros_fatais = ?, raw_evaluation = ?, transcricao_diarizada = ?, nota_sentimento_cliente = ?, nota_qualidade_operador = ?
            WHERE id = ?
        ''', ("Concluído", nota, transcricao, sentimentos_cliente, sentimentos_operador, erros_fatais, raw_evaluation, diarized_transcript, nota_sentimento_cliente, nota_qualidade_operador, call_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        update_status(f"Erro: {str(e)}")

@app.get("/api/auth/me")
def get_me(user = Depends(get_current_user)):
    save_user(user)
    return user

@app.post("/api/request-access")
async def request_access(email: str = Form(...)):
    token = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO access_requests (token, email, created_at) VALUES (?, ?, ?)", (token, email, now))
    conn.commit()
    conn.close()
    
    # Simula envio de e-mail por enquanto (MOCK)
    approve_url = f"https://monitoria-cx-4105010761.us-central1.run.app/api/approve-access?token={token}"
    print(f"\n============================================\n[NOVO PEDIDO DE ACESSO] De: {email}\n[CLIQUE AQUI PARA APROVAR]: {approve_url}\n============================================\n", flush=True)
    return {"message": "Solicitação enviada. O administrador foi notificado!"}

@app.get("/api/approve-access")
async def approve_access(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM access_requests WHERE token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"message": "Token inválido ou expirado."}
    
    email = row[0]
    cursor.execute("INSERT OR IGNORE INTO users (id, email, is_approved) VALUES (?, ?, 1)", (str(uuid.uuid4()), email))
    cursor.execute("UPDATE users SET is_approved = 1 WHERE email = ?", (email,))
    cursor.execute("DELETE FROM access_requests WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return {"message": f"Acesso aprovado para {email} com sucesso!"}

class UserSettings(BaseModel):
    checklist_items: str
    estrategia_vendas: str
    estrategia_retencao: str

@app.get("/api/settings")
def get_settings(user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user.get("sub"),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "checklist_items": "[]",
        "estrategia_vendas": "",
        "estrategia_retencao": ""
    }

@app.post("/api/settings")
def save_settings(settings: UserSettings, user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO user_settings (user_id, checklist_items, estrategia_vendas, estrategia_retencao)
        VALUES (?, ?, ?, ?)
    ''', (user.get("sub"), settings.checklist_items, settings.estrategia_vendas, settings.estrategia_retencao))
    conn.commit()
    conn.close()
    return {"message": "Configurações salvas com sucesso"}

@app.get("/api/calls")
def get_calls(user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, uploaded_at, status, nota, nota_sentimento_cliente, nota_qualidade_operador, raw_evaluation FROM chamadas WHERE user_id = ? ORDER BY uploaded_at DESC", (user.get("sub"),))
    calls = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return calls

@app.get("/api/calls/{call_id}")
def get_call(call_id: str, user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chamadas WHERE id = ? AND user_id = ?", (call_id, user.get("sub")))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Chamada não encontrada ou sem permissão")
    
    call_data = dict(row)
    for field in ["transcricao", "sentimentos_cliente", "sentimentos_operador", "erros_fatais", "raw_evaluation"]:
        if call_data.get(field):
            try:
                call_data[field] = json.loads(call_data[field])
            except:
                pass
    return call_data

@app.post("/api/upload")
async def upload_audio(
    background_tasks_fallback: BackgroundTasks,
    file: UploadFile = File(...),
    diretrizes: str = Form(""),
    user = Depends(get_current_user)
):
    """
    Fase B: agora enfileira job no Pub/Sub em vez de processar via BackgroundTasks.
    Vantagens:
    - Backend principal nao trava durante transcricao
    - Worker escala independentemente (0-10 instancias)
    - Persistencia: audio no GCS, nao em disco local volatil
    """
    call_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{call_id}_{file.filename}")

    # 1. Salva audio local temporariamente (sera uploadado para GCS)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Upload para GCS (bucket dedicado para arquivos temporarios do worker)
    gcs_bucket = os.getenv("AUDIO_BUCKET", "coherence-monitoria-audios-tmp")
    gcs_path = f"{call_id}_{file.filename}"

    try:
        from google.cloud import storage as gcs_storage
        gcs_client = gcs_storage.Client()
        bucket = gcs_client.bucket(gcs_bucket)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(file_path)
        gcs_uri = f"gs://{gcs_bucket}/{gcs_path}"
        print(f"[Upload] Audio salvo em {gcs_uri}", flush=True)
    except Exception as e:
        # Se GCS falhar, faz fallback para BackgroundTasks local (modo degradado)
        print(f"[Upload] FALHA ao subir para GCS: {e}. Fallback: BackgroundTasks local.", flush=True)
        gcs_uri = None

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO chamadas (id, filename, uploaded_at, status, user_id, diretrizes_qualidade)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (call_id, file.filename, now, "Na Fila de Processamento...", user.get("sub"), diretrizes))
        conn.commit()
        conn.close()

        background_tasks_fallback.add_task(process_call_task, call_id, file_path, user.get("sub"), diretrizes)
        return {"message": "Processamento iniciado (modo degradado)", "id": call_id, "mode": "local"}

    # 3. INSERT no SQLite com status "Na Fila de Processamento..."
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO chamadas (id, filename, uploaded_at, status, user_id, diretrizes_qualidade)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (call_id, file.filename, now, "Na Fila de Processamento...", user.get("sub"), diretrizes))
    conn.commit()
    conn.close()

    # 4. Publica job no Pub/Sub para o worker dedicado processar
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
        }).encode("utf-8")
        future = publisher.publish(topic_path, message_data)
        message_id = future.result(timeout=10)
        print(f"[Upload] Job publicado no Pub/Sub: {message_id}", flush=True)
    except Exception as e:
        print(f"[Upload] FALHA ao publicar no Pub/Sub: {e}", flush=True)
        # Continua mesmo assim — o usuario vera "Na Fila de Processamento..." para sempre.
        # Em prod, considere alerta admin aqui.

    # 5. Cleanup arquivo local (foi copiado para GCS)
    try:
        os.remove(file_path)
    except OSError:
        pass

    return {"message": "Processamento iniciado", "id": call_id, "mode": "pubsub"}

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
TEST_ENV_AUDIENCE = os.getenv("TEST_ENV_AUDIENCE", "https://monitoria-test-env-c5nbfc5meq-uc.a.run.app")


class InternalStatusUpdate(BaseModel):
    status: str  # processing | transcrevendo | analisando | concluido | erro
    transcript: str | None = None
    qa_score: int | None = None
    qa_details: dict | None = None  # {nota_qualidade_operador, nota_sentimento_cliente, ...}
    error: str | None = None


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

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Verifica que chamada existe
    cursor.execute("SELECT id, user_id, status FROM chamadas WHERE id = ?", (call_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Chamada {call_id} nao encontrada")

    # Monta UPDATE dinamico baseado nos campos fornecidos
    fields_to_update = ["status = ?", "nota = COALESCE(?, nota)"]
    params = [body.status, body.qa_score]

    if body.transcript is not None:
        fields_to_update.append("transcricao = ?")
        params.append(body.transcript)

    if body.qa_details:
        if "nota_qualidade_operador" in body.qa_details:
            fields_to_update.append("nota_qualidade_operador = ?")
            params.append(body.qa_details["nota_qualidade_operador"])
        if "nota_sentimento_cliente" in body.qa_details:
            fields_to_update.append("nota_sentimento_cliente = ?")
            params.append(body.qa_details["nota_sentimento_cliente"])
        if "raw_evaluation" in body.qa_details:
            fields_to_update.append("raw_evaluation = ?")
            params.append(body.qa_details["raw_evaluation"])

    params.append(call_id)
    cursor.execute(
        f"UPDATE chamadas SET {', '.join(fields_to_update)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()

    print(f"[InternalCallback] call_id={call_id} status={body.status} qa_score={body.qa_score}", flush=True)
    return {"updated": True, "call_id": call_id, "status": body.status}


# ============================================================================
# Queue Manager (Admin-only): visualizar e gerenciar fila Pub/Sub
# Implementa as Tasks 2.1-2.5 do backlog docs/goals/queue-manager.md
# ============================================================================

WORKER_URL = os.getenv("WORKER_URL", "https://monitoria-whisper-worker-c5nbfc5meq-uc.a.run.app")


def _worker_healthy() -> bool:
    """Checa saude do worker via GET /health. 403 (sem auth) tambem indica vivo."""
    try:
        import httpx
        r = httpx.get(WORKER_URL.rstrip("/") + "/health", timeout=3.0)
        return r.status_code in (200, 403, 404)  # 404 = rota nao existe mas server up
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


# Endpoints administrativos migrados para o Coherence Portal (SSO Global).

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
