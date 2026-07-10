"""
Worker dedicado - Monitoria de Chamadas
====================================

OBJETIVO PRINCIPAL (parte 2 do pipeline):
  Recebe audio uploaded, transcreve com Whisper, diariza (separa
  atendente vs cliente), e avalia com LLM (MiniMax M3) para gerar
  nota QA + nota NPS + analise de 3 fases + motivos.

O OBJETIVO PRINCIPAL completo (frontend + backend + worker):
  1. Upload de chamada (audio file) - frontend + api.py
  2. Transcricao audio -> texto - ESTE WORKER (Whisper)
  3. Separar audio atendente e cliente - ESTE WORKER (LLM diarize)
  4. Avaliar nota QA do atendente e nota NPS do cliente - ESTE WORKER (LLM evaluate)
  5. Categorizar motivos principais da chamada - ESTE WORKER (LLM evaluate)

Deploy: Cloud Run service monitoria-whisper-worker
- 4 CPU, 8Gi RAM
- min-instances=0 (scale to zero)
- max-instances=3
- timeout=900s
- concurrency=1
"""
import os
import json
import time
import tempfile
import shutil
import urllib.request
from datetime import datetime
import concurrent.futures
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1, storage as gcs_storage

# Firestore (substituiu SQLite em 06/07/2026 — Plano A++)
from core.db import get_call, get_db, get_user_settings

# PII masker (LGPD Art. 46)
from core.masker import mask_pii

# Logger
import sys
print(f"[Worker {os.getenv('K_SERVICE', 'local')}] Iniciando...", flush=True)


# ============================================================================
# Configuracao
# ============================================================================
GCP_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs")
PUBSUB_SUBSCRIPTION = os.getenv("PUBSUB_SUBSCRIPTION", "monitoria-whisper-jobs-worker")
AUDIO_BUCKET = os.getenv("AUDIO_BUCKET", "coherence-monitoria-audios-tmp")
WORKER_ID = os.getenv("K_REVISION", f"local-{os.getpid()}")


# ============================================================================
# Inicializacao lazy dos recursos pesados (Whisper, Evaluator)
# ============================================================================
_transcriber = None
_evaluator = None

# ============================================================================
# Estado do worker (para watchdog e /healthz)
# ============================================================================
WORKER_STATE = {
    "started_at": time.time(),
    "last_msg_received_at": None,    # timestamp da ultima mensagem recebida
    "last_msg_id": None,
    "last_msg_call_id": None,
    "current_state": "initializing",  # initializing | ready | processing | stuck
    "messages_processed": 0,
    "consecutive_errors": 0,
}

# NEW (09/07/2026 - Batch/Standalone): fila interna para acumular mensagens
# e processar em batch. Aproveita o concurrency=4 configurado no Cloud Run.
BATCH_SIZE = 4
BATCH_TIMEOUT_SEC = 5  # max espera para encher batch (reduzido 09/07/2026: baixo volume)
_batch_buffer = []        # lista de (message, data) aguardando
_batch_buffer_lock = __import__("threading").Lock()
_batch_buffer_first_at = None  # timestamp da primeira msg no buffer atual
_batch_timer = None           # referencia ao timer ativo
_last_restart_at = 0.0        # timestamp do ultimo restart (debounce watchdog)

HEALTHZ_LOCK = __import__("threading").Lock()


def get_transcriber():
    global _transcriber
    if _transcriber is None:
        from core.transcriber import Transcriber
        _transcriber = Transcriber()
        print(f"[Worker {WORKER_ID}] Transcriber inicializado", flush=True)
    return _transcriber


def get_evaluator():
    global _evaluator
    if _evaluator is None:
        from core.evaluator import Evaluator
        _evaluator = Evaluator()
        print(f"[Worker {WORKER_ID}] Evaluator inicializado", flush=True)
    return _evaluator


def update_status(call_id: str, status_text: str, **extra):
    """Atualiza status da chamada. Escrita DIRETA no Firestore.

    Historico:
    - Pre-06/07/2026: escrevia em SQLite (GCS FUSE mount) E chamava callback OIDC.
    - 06/07/2026 (Plano A++): SQLite removido. Apenas callback OIDC permanece.
    - 08/07/2026 (Plano Ultra-Economico): Worker grava DIRETO no Firestore,
      eliminando 7 callbacks OIDC por chamada (-3-5s latencia). Callback OIDC
      fica disponivel como fallback via env var LEGACY_CALLBACK=true.

    Args:
        call_id: UUID da chamada
        status_text: status canonico (ex: "Concluido", "Transcrevendo...")
        **extra: campos extras para gravar (ex: progress_pct=42.5)
    """
    payload = {"status": status_text, **extra}
    try:
        get_db().update_or_create(call_id, payload)
        with HEALTHZ_LOCK:
            WORKER_STATE["last_callback_ok"] = time.time()
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Firestore write FALHOU: {e}", flush=True)
        # Fallback: callback OIDC legado (defesa em profundidade)
        if LEGACY_CALLBACK:
            _notify_test_env_callback(call_id, payload)


def _notify_test_env_callback(call_id: str, payload: dict):
    """Envia update de status para test-env via HTTP + OIDC identity token.

    Necessario porque test-env NAO tem volume mount GCS, entao nao le o
    SQLite compartilhado do worker. Sem este callback, a UI do test-env
    sempre mostra 'Na Fila de Processamento...'.

    NEW (05/07/2026): detecta orphan (callback 404 = call_id nao existe no DB
    test-env). Marca flag global; o callback() do Pub/Sub checa essa flag e
    faz ack forcado (poison message) em vez de nack.
    """
    global _ORPHAN_DETECTED
    callback_url = os.getenv("WORKER_CALLBACK_URL")
    if not callback_url:
        # Callback desabilitado (worker legado ou config minima)
        return

    try:
        # Obtem identity token do Cloud Run metadata server
        # audience = URL do test-env (o token so vale para esse servico)
        token = _get_cloud_run_identity_token(callback_url)
        if not token:
            return  # rodando fora do Cloud Run

        import requests as _requests
        resp = _requests.post(
            f"{callback_url.rstrip('/')}/api/internal/calls/{call_id}/status",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=5,
        )
        if resp.status_code != 200:
            print(f"[Worker {WORKER_ID}] callback falhou: HTTP {resp.status_code} - {resp.text[:200]}", flush=True)
            # 404 = chamada nao existe no DB do test-env = orphan. Sinaliza
            # para o callback() do Pub/Sub fazer ack forcado (poison message).
            if resp.status_code == 404:
                with HEALTHZ_LOCK:
                    _ORPHAN_DETECTED = True
                print(
                    f"[Worker {WORKER_ID}] ORPHAN detectado: call_id={call_id} "
                    f"ausente no DB do test-env. Marcando para poison-ack.",
                    flush=True,
                )
    except Exception as e:
        # Falha no callback NAO bloqueia processamento (ja escrevemos no SQLite)
        print(f"[Worker {WORKER_ID}] callback falhou (continuando): {e}", flush=True)


# Flag global: quando setado, a proxima mensagem COM O MESMO call_id
# sera ack'ada sem reprocessar (poison message). Detecta-se orfao quando
# callback do test-env retorna 404 (call_id nao existe no DB).
_ORPHAN_CALL_ID = None

# NEW (08/07/2026 - Plano Ultra-Economico): Flag de rollback para callback OIDC legado.
# Quando true, worker cai de volta no callback HTTP via test-env em vez de gravar
# direto no Firestore. Util se o item 1.1 (worker direto Firestore) causar regressao.
LEGACY_CALLBACK = os.getenv("LEGACY_CALLBACK", "false").lower() == "true"


def _get_cloud_run_identity_token(audience: str) -> str | None:
    """Obtem identity token do Cloud Run metadata server para o audience dado.

    Retorna None se rodando fora do Cloud Run (metadata server nao disponivel).
    """
    try:
        metadata_url = (
            "http://metadata/computeMetadata/v1/"
            f"instance/service-accounts/default/identity?audience={audience}"
        )
        req = urllib.request.Request(metadata_url, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def process_call(call_id: str, gcs_uri: str, user_id: str, diretrizes: str, audio_duration_sec: float = None):
    """
    Processa uma chamada: baixa do GCS, transcreve, diariza, avalia.
    Atualiza SQLite com progresso e resultado final.

    Args:
        audio_duration_sec: duracao do audio (segundos). Usada para calcular
            progress_pct durante transcricao Whisper. Se None, usa info.duration
            retornado pelo Whisper (fallback).
    """
    print(f"[Worker {WORKER_ID}] Processando {call_id} de {gcs_uri}", flush=True)
    start_time = time.time()

    # 1. Baixa audio do GCS
    update_status(call_id, "Baixando audio do storage...")
    tmp_dir = tempfile.mkdtemp(prefix=f"worker_{call_id}_")
    local_audio_path = os.path.join(tmp_dir, os.path.basename(gcs_uri))

    try:
        bucket_name = gcs_uri.replace("gs://", "").split("/")[0]
        blob_name = gcs_uri.replace(f"gs://{bucket_name}/", "")
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_audio_path)
        print(f"[Worker {WORKER_ID}] Audio baixado: {local_audio_path}", flush=True)
    except Exception as e:
        update_status(call_id, f"Erro: falha ao baixar audio do GCS: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # 2. Busca user_settings (Firestore collection user_settings)
    try:
        settings_doc = get_user_settings(user_id) or {}
        user_settings = {k: v for k, v in settings_doc.items()
                         if k not in ("user_id", "updated_at")}
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha ao ler user_settings: {e}", flush=True)
        user_settings = {}

    # Prepara contexto POP a partir dos settings do usuario
    checklist_str = user_settings.get("checklist_items", "[]")
    estrategia_vendas = user_settings.get("estrategia_vendas", "")
    estrategia_retencao = user_settings.get("estrategia_retencao", "")
    pop_context = f"Checklist: {checklist_str}. "
    if estrategia_vendas:
        pop_context += f"Vendas: {estrategia_vendas}. "
    if estrategia_retencao:
        pop_context += f"Retencao: {estrategia_retencao}. "
    pop_context += f"Diretrizes: {diretrizes}" if diretrizes else "Diretrizes: Cordialidade, Resolucao, Empatia, Clareza."

    # 3. Transcricao com callback de progresso throttled
    update_status(call_id, "Transcrevendo Audio (Whisper)...")
    last_progress_ts = [0.0]  # list para mutabilidade dentro do closure
    PROGRESS_THROTTLE_SEC = 2.0

    def on_whisper_progress(segment_end: float, audio_total: float):
        """Callback por segmento. Grava progress_pct no Firestore no maximo a cada 2s."""
        now = time.time()
        if now - last_progress_ts[0] < PROGRESS_THROTTLE_SEC:
            return
        if audio_total <= 0:
            return
        pct = max(0.0, min(99.0, (segment_end / audio_total) * 100.0))
        last_progress_ts[0] = now
        # NEW (08/07/2026): escrita direta no Firestore (sem callback OIDC)
        update_status(
            call_id,
            "Transcrevendo Audio (Whisper)...",
            progress_pct=pct,
        )

    try:
        raw_transcript, segments = get_transcriber().transcribe(
            local_audio_path,
            on_progress=on_whisper_progress,
            audio_duration_sec=audio_duration_sec,
        )
        print(f"[Worker {WORKER_ID}] Transcricao OK: {len(segments)} segmentos", flush=True)
    except Exception as e:
        update_status(call_id, f"Erro: transcricao falhou: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        # Cleanup GCS
        try:
            blob.delete()
        except Exception:
            pass
        return

    # Marca Whisper como 100% ao terminar (NEW 08/07/2026: escrita direta)
    update_status(
        call_id,
        "Transcrevendo Audio (Whisper)...",
        progress_pct=100.0,
    )

    # 4. Diarizacao + Avaliacao em 1 chamada LLM (NEW 08/07/2026)
    eval_ = get_evaluator()
    update_status(call_id, f"Processando IA ({eval_.client.last_provider_used or 'IA'}) - diarize + evaluate batch...")
    try:
        result = eval_.diarize_and_evaluate(
            raw_transcript,
            user_settings=user_settings,
            pop_context=pop_context,
            quality_form=diretrizes,
        )
        diarized_transcript = result["diarized_transcript"]
        evaluation = result["evaluation"]
        print(f"[Worker {WORKER_ID}] Batch LLM OK ({eval_.client.last_provider_used or 'IA'}): nota={evaluation.get('nota_geral')}", flush=True)
    except Exception as e:
        update_status(call_id, f"Erro: avaliacao LLM falhou: {e}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            blob.delete()
        except Exception:
            pass
        return

    # 6. Parse nota
    nota = evaluation.get("nota_geral")
    if isinstance(nota, str) and "%" in nota:
        nota = int(nota.replace("%", "").strip())
    elif isinstance(nota, (int, float)):
        nota = int(nota)
    else:
        nota = 0

    nota_sentimento_cliente = evaluation.get("nota_sentimento_cliente", 5)
    nota_qualidade_operador = evaluation.get("nota_qualidade_operador", nota)

    elapsed = time.time() - start_time
    print(f"[Worker {WORKER_ID}] {call_id} CONCLUIDO em {elapsed:.1f}s (nota={nota})", flush=True)
    # Persistencia: feita pelo test-env via callback OIDC abaixo (api.py refatora para Firestore).

    # 7b. Callback final com resultado completo (transcript + qa + diarizacao + sentimentos)
    # NEW (08/07/2026): escrita DIRETA no Firestore via update_or_create.
    # Substitui _notify_test_env_callback (callback OIDC). Veja Fase 1 do plano.
    raw_text = "\n".join(seg.get("text", "") for seg in segments)
    final_payload = {
        "status": "Concluído",
        "nota": nota,
        "transcricao": mask_pii(raw_text),
        "transcricao_diarizada": mask_pii(diarized_transcript),
        "nota_qualidade_operador": nota_qualidade_operador,
        "nota_sentimento_cliente": nota_sentimento_cliente,
        "raw_evaluation": evaluation,
        "sentimentos_cliente": evaluation.get("sentimentos_cliente", []),
        "sentimentos_operador": evaluation.get("sentimentos_operador", []),
        "erros_fatais": evaluation.get("erros_fatais_identificados", []),
        "progress_pct": 100.0,
    }
    try:
        get_db().update_or_create(call_id, final_payload)
        print(f"[Worker {WORKER_ID}] Firestore write OK: {call_id[:8]}... status=Concluido", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Firestore write FALHOU (final): {e}", flush=True)
        # NEW (08/07/2026 - A1): Re-raise para que callback() faca NACK
        # e a mensagem seja reprocessada por outra instancia.
        # Isso evita perda de trabalho quando Firestore tem permissao
        # negada, network blip, etc. Veja DIARIO_BORDO.md A1.
        if LEGACY_CALLBACK:
            # Fallback OIDC: monta payload no formato esperado pelo callback handler
            try:
                _notify_test_env_callback(call_id, {
                    "status": "Concluído",
                    "transcript": final_payload["transcricao"],
                    "transcricao_diarizada": final_payload["transcricao_diarizada"],
                    "qa_score": final_payload["nota"],
                    "qa_details": {
                        "nota_qualidade_operador": nota_qualidade_operador,
                        "nota_sentimento_cliente": nota_sentimento_cliente,
                        "raw_evaluation": evaluation,
                        "sentimentos_cliente": evaluation.get("sentimentos_cliente", []),
                        "sentimentos_operador": evaluation.get("sentimentos_operador", []),
                        "erros_fatais_identificados": evaluation.get("erros_fatais_identificados", []),
                    },
                })
                # Fallback OIDC deu certo - mensagem pode ser ack
                print(f"[Worker {WORKER_ID}] Firestore falhou mas OIDC fallback OK: {call_id[:8]}...", flush=True)
            except Exception as e2:
                # Fallback OIDC TAMBEM falhou - re-raise para NACK
                print(f"[Worker {WORKER_ID}] Firestore + OIDC fallback ambos falharam: {e2}", flush=True)
                raise RuntimeError(f"Firestore write failed and OIDC fallback also failed: {e2}") from e
        else:
            # Sem fallback: re-raise para NACK
            raise

    # 8. Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)
    # try:
    #     blob.delete()
    #     print(f"[Worker {WORKER_ID}] Audio deletado do GCS: {gcs_uri}", flush=True)
    # except Exception as e:
    #     print(f"[Worker {WORKER_ID}] Falha ao deletar audio do GCS: {e}", flush=True)



def _flush_batch():
    """NEW (09/07/2026 - Batch/Standalone): drena buffer e processa todas as mensagens em paralelo.
    Aproveita o concurrency=4 do Cloud Run para paralelismo real."""
    global _batch_buffer, _batch_buffer_first_at, _batch_timer
    with _batch_buffer_lock:
        if not _batch_buffer:
            return
        items = list(_batch_buffer)
        _batch_buffer = []
        _batch_buffer_first_at = None
        _batch_timer = None

    print(f"[Worker {WORKER_ID}] BATCH: processando {len(items)} mensagens em paralelo", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(items)) as executor:
        futures = {
            executor.submit(_process_single_message, msg, data): (msg, data)
            for msg, data in items
        }
        for future in concurrent.futures.as_completed(futures, timeout=900):
            msg, _ = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[Worker {WORKER_ID}] BATCH erro: {e}", flush=True)
                msg.nack()


def _process_single_message(message, data):
    """Processa uma unica mensagem (chamado pelo _flush_batch em paralelo).
    Faz ack/nack + idempotency + process_call.
    """
    global _ORPHAN_DETECTED
    try:
        call_id = data["call_id"]
        gcs_uri = data.get("gcs_uri") or data.get("audio_gcs_uri")
        if not gcs_uri:
            print(f"[Worker {WORKER_ID}] ERRO: payload sem audio URI. keys={list(data.keys())}", flush=True)
            raise KeyError("gcs_uri (ou audio_gcs_uri) ausente no payload")
        user_id = data["user_id"]
        diretrizes = data.get("diretrizes", "")
        audio_duration_sec = data.get("audio_duration_sec")

        # NEW (05/07/2026 - Fase 1 / Fix #2): idempotency check ANTES de processar.
        try:
            call_doc = get_call(call_id)
            if call_doc is None:
                print(
                    f"[Worker {WORKER_ID}] ORPHAN: call_id={call_id} ausente. Ack (poison-ack).",
                    flush=True,
                )
                message.ack()
                with HEALTHZ_LOCK:
                    WORKER_STATE["messages_processed"] += 1
                    WORKER_STATE["consecutive_errors"] = 0
                    WORKER_STATE["current_state"] = "ready"
                return
            existing_status = call_doc.get("status", "")
            if existing_status == "Concluído" or existing_status.startswith("Erro"):
                print(
                    f"[Worker {WORKER_ID}] JÁ PROCESSADO: call_id={call_id}. Ack (idempotente).",
                    flush=True,
                )
                message.ack()
                with HEALTHZ_LOCK:
                    WORKER_STATE["messages_processed"] += 1
                    WORKER_STATE["consecutive_errors"] = 0
                    WORKER_STATE["current_state"] = "ready"
                return
            print(
                f"[Worker {WORKER_ID}] RETOMANDO: call_id={call_id} status_anterior={existing_status!r}",
                flush=True,
            )
        except Exception as e:
            print(f"[Worker {WORKER_ID}] idempotency check falhou: {e}", flush=True)

        with HEALTHZ_LOCK:
            WORKER_STATE["last_msg_received_at"] = time.time()
            WORKER_STATE["last_msg_id"] = message.message_id
            WORKER_STATE["last_msg_call_id"] = call_id
            WORKER_STATE["current_state"] = "processing"

        # NEW (07/07/2026): timeout explicito em process_call.
        PROCESSING_TIMEOUT_SEC = int(os.getenv("PROCESSING_TIMEOUT_SEC", "840"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                process_call, call_id, gcs_uri, user_id, diretrizes, audio_duration_sec
            )
            try:
                future.result(timeout=PROCESSING_TIMEOUT_SEC)
            except concurrent.futures.TimeoutError:
                _notify_test_env_callback(
                    call_id,
                    {"status": f"Erro: processamento excedeu {PROCESSING_TIMEOUT_SEC}s timeout"},
                )
                print(f"[Worker {WORKER_ID}] TIMEOUT em process_call. Nack para redelivery.", flush=True)
                raise

        message.ack()
        print(f"[Worker {WORKER_ID}] Message {message.message_id} ACKed", flush=True)

        with HEALTHZ_LOCK:
            WORKER_STATE["messages_processed"] += 1
            WORKER_STATE["consecutive_errors"] = 0
            WORKER_STATE["current_state"] = "ready"
            WORKER_STATE["last_msg_received_at"] = time.time()  # FIX: watchdog nao dispara falso STUCK
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO processando message {message.message_id}: {e}", flush=True)
        with HEALTHZ_LOCK:
            WORKER_STATE["consecutive_errors"] += 1
        POISON_THRESHOLD = 20
        if WORKER_STATE["consecutive_errors"] >= POISON_THRESHOLD:
            print(
                f"[Worker {WORKER_ID}] POISON: Ack forcado para {message.message_id}",
                flush=True,
            )
            message.ack()
            with HEALTHZ_LOCK:
                WORKER_STATE["consecutive_errors"] = 0
                WORKER_STATE["current_state"] = "ready"
            return
        message.nack()


def callback(message):
    """Callback para mensagens do Pub/Sub. Acumula em batch para processar em paralelo."""
    global _batch_buffer, _batch_buffer_first_at, _batch_timer
    try:
        data = json.loads(message.data.decode("utf-8"))
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO parse JSON: {e}", flush=True)
        message.nack()
        return

    # Acumula no buffer para batch
    should_flush = False
    with _batch_buffer_lock:
        _batch_buffer.append((message, data))
        if _batch_buffer_first_at is None:
            _batch_buffer_first_at = time.time()
        if len(_batch_buffer) >= BATCH_SIZE:
            should_flush = True
        else:
            # Agenda timer para flush se buffer nao encher
            if _batch_timer is None:
                _batch_timer = __import__("threading").Timer(
                    BATCH_TIMEOUT_SEC, _flush_batch
                )
                _batch_timer.daemon = True
                _batch_timer.start()

    if should_flush:
        _flush_batch()


# Mantido para compatibilidade com testes
def _callback_legacy_unused(message):
    """Callback legacy. Substituido por callback() + batch processing."""
    raise NotImplementedError("Use callback() instead")


# ============================================================================
# Auto-restart do streaming_pull (quando trava)
# ============================================================================
# O watchdog_loop() monitora estado e, se detectar travamento, chama
# _restart_streaming_pull() para cancelar e recriar a conexao Pub/Sub.
# Variaveis globais (mutaveis pelo watchdog):
#   _subscriber_client: cliente Pub/Sub (reusado entre restarts)
#   _streaming_pull_future: future ativo (cancelado + recriado pelo watchdog)
# ============================================================================
_subscriber_client = None
_streaming_pull_future = None
_STREAMING_LOCK = __import__("threading").Lock()


def _restart_streaming_pull():
    """Cancela streaming_pull atual e recria. Usado pelo watchdog quando trava."""
    global _streaming_pull_future, _last_restart_at
    # Debounce: nao reiniciar mais de uma vez a cada 120s
    now = time.time()
    if now - _last_restart_at < 120:
        return
    _last_restart_at = now
    # Descarrega buffer pendente antes de reiniciar
    _flush_batch()
    with _STREAMING_LOCK:
        if _streaming_pull_future is not None:
            try:
                _streaming_pull_future.cancel()
            except Exception:
                pass
        if _subscriber_client is None:
            return  # nao inicializado ainda, nao pode recriar
        try:
            # Nack das msgs pendentes no buffer (do subscriber antigo)
            with _batch_buffer_lock:
                for msg, _ in _batch_buffer:
                    try:
                        msg.nack()
                    except Exception:
                        pass
                _batch_buffer = []
                _batch_buffer_first_at = None
                _batch_timer = None
            subscription_path = _subscriber_client.subscription_path(GCP_PROJECT, PUBSUB_SUBSCRIPTION)
            flow_control = pubsub_v1.types.FlowControl(max_messages=2)
            new_future = _subscriber_client.subscribe(
                subscription_path,
                callback=callback,
                flow_control=flow_control,
            )
            _streaming_pull_future = new_future
            with HEALTHZ_LOCK:
                WORKER_STATE["consecutive_errors"] = 0
                WORKER_STATE["current_state"] = "ready"
            print(f"[WATCHDOG] streaming_pull recriado com sucesso", flush=True)
        except Exception as e:
            print(f"[WATCHDOG] FALHA ao recriar streaming_pull: {e}", flush=True)


def health_check_server():
    """
    Cloud Run exige que o container escute em PORT (default 8080).
    Este servidor HTTP minimo responde health checks com JSON detalhado do estado.
    Roda em thread separada para nao bloquear o consumer Pub/Sub.

    FIX (06/07/2026 - load test Fase 3): health check SEMPRE retorna 200.
    A diferenca de "200 vs 503" causava liveness probe failure -> Cloud Run
    matava o container worker -> orphan no Pub/Sub. Agora:
      - 200 OK se worker esta vivo (sempre que o processo esta rodando)
      - JSON inclui state="stuck" mas isso e' SO INFORMATIVO, nao bloqueia
      - test-env agora decide se faz fallback in-process via _worker_healthy()
        que checa state via metadata ao inves de liveness probe
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    STUCK_THRESHOLD_SEC = 300  # 5min sem mensagem = warning
    PROCESSING_STUCK_SEC = 900  # 15min processando = claramente travado (05/07/2026)

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/healthz"):
                with HEALTHZ_LOCK:
                    now = time.time()
                    uptime = now - WORKER_STATE["started_at"]
                    last_msg_at = WORKER_STATE["last_msg_received_at"]
                    last_msg_age = (now - last_msg_at) if last_msg_at else None

                    # Marca state=stuck internamente para observabilidade,
                    # mas SEMPRE retorna 200 para nao matar o container via
                    # liveness probe. Workers ainda vivos podem recuperar
                    # quando novas mensagens chegarem.
                    if last_msg_age is not None and last_msg_age > STUCK_THRESHOLD_SEC and WORKER_STATE["current_state"] != "processing":
                        WORKER_STATE["current_state"] = "stuck"
                    elif WORKER_STATE["current_state"] == "processing" and last_msg_age is not None and last_msg_age > PROCESSING_STUCK_SEC:
                        WORKER_STATE["current_state"] = "stuck"
                    status_code = 200  # FIX: sempre saudavel para o liveness probe

                    payload = {
                        "status": "ok" if WORKER_STATE["current_state"] != "stuck" else "idle",
                        "worker_id": WORKER_ID,
                        "state": WORKER_STATE["current_state"],
                        "uptime_sec": round(uptime, 1),
                        "last_msg_age_sec": round(last_msg_age, 1) if last_msg_age is not None else None,
                        "last_msg_id": WORKER_STATE["last_msg_id"],
                        "last_msg_call_id": WORKER_STATE["last_msg_call_id"],
                        "messages_processed": WORKER_STATE["messages_processed"],
                        "consecutive_errors": WORKER_STATE["consecutive_errors"],
                    }

                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Silencia log padrao (muito verbose)
            pass

    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[Worker {WORKER_ID}] Health check server listening on :{port}", flush=True)
    server.serve_forever()


def watchdog_loop():
    """
    Watchdog: monitora o estado do worker a cada 30s e loga.
    Se worker ficar 'stuck' (sem processar ha > 5min) ou 'consecutive_errors' crescer,
    loga alerta critico. Cloud Run nao mata container baseado nisso; apenas para
    visibilidade operacional.
    """
    import threading
    INTERVAL_SEC = 30
    ERROR_THRESHOLD = 5

    while True:
        time.sleep(INTERVAL_SEC)
        with HEALTHZ_LOCK:
            now = time.time()
            uptime = now - WORKER_STATE["started_at"]
            last_msg_age = (now - WORKER_STATE["last_msg_received_at"]) if WORKER_STATE["last_msg_received_at"] else None
            state = WORKER_STATE["current_state"]
            errs = WORKER_STATE["consecutive_errors"]
            msgs = WORKER_STATE["messages_processed"]

        # Log periodico de saude
        age_str = f"{last_msg_age:.0f}s" if last_msg_age is not None else "nunca"
        print(
            f"[WATCHDOG] worker={WORKER_ID} uptime={uptime:.0f}s state={state} "
            f"msgs={msgs} last_msg_age={age_str} errors={errs}",
            flush=True,
        )

        # Alerta: muitos erros consecutivos
        if errs >= ERROR_THRESHOLD:
            print(
                f"[WATCHDOG] ALERTA: {errs} erros consecutivos no callback",
                flush=True,
            )

        # Auto-restart: detecta trava do streaming_pull.
        # Criterios para considerar travado:
        #  - Worker esta em estado "ready" (nao processando)
        #  - Ja passou do startup (uptime > 3min)
        #  - OU ha mais de 5min sem receber mensagem
        #  - OU nunca recebeu mensagem (initial connect falha)
        #
        # FIX (06/07/2026 - rev 2): removido check `sub_info.message_count`
        # que nao existe no proto Subscription (Unknown field error).
        # Agora detecta STUCK via last_msg_age/uptime apenas.
        if (
            state == "ready"
            and uptime > 180
            and _subscriber_client is not None
        ):
            # Caso A: nunca recebeu msg E ja passou do startup (initial connect falha)
            stuck_initial = last_msg_age is None and uptime > 240
            # Caso B: idle > 5min sem receber
            stuck_idle = last_msg_age is not None and last_msg_age > 300
            if stuck_initial or stuck_idle:
                motivo = (
                    f"last_msg_age=nunca, uptime={uptime:.0f}s"
                    if stuck_initial
                    else f"last_msg_age={last_msg_age:.0f}s, uptime={uptime:.0f}s"
                )
                print(
                    f"[WATCHDOG] STUCK detectado ({motivo}). "
                    f"Reiniciando streaming_pull...",
                    flush=True,
                )
                _restart_streaming_pull()

        # NEW (05/07/2026): detecta processing travado (msg recebida mas
        # process_call() nunca retornou). Cancela streaming_pull para que o
        # Pub/Sub reentregue a mensagem para outra instancia.
        # Critério: state=processing ha mais de 15min sem conclusao.
        PROCESSING_STUCK_SEC = 900  # 15min processando = claramente travado
        if state == "processing" and last_msg_age is not None and last_msg_age > PROCESSING_STUCK_SEC:
            print(
                f"[WATCHDOG] STUCK-PROCESSING detectado: state=processing ha "
                f"{last_msg_age:.0f}s sem conclusao. Reiniciando streaming_pull "
                f"para forcar redelivery da mensagem...",
                flush=True,
            )
            # Reset estado para forcar nova puxada
            with HEALTHZ_LOCK:
                WORKER_STATE["current_state"] = "ready"
                WORKER_STATE["consecutive_errors"] += 1
            _restart_streaming_pull()


def main():
    """Loop principal: pull de Pub/Sub e processa."""
    print(f"[Worker {WORKER_ID}] Subscrevendo em {PUBSUB_SUBSCRIPTION}...", flush=True)

    # Inicia health check server em thread separada
    import threading
    health_thread = threading.Thread(target=health_check_server, daemon=True)
    health_thread.start()

    # Inicia watchdog em thread separada
    watchdog_thread = threading.Thread(target=watchdog_loop, daemon=True)
    watchdog_thread.start()

    # Pre-aquecimento: instancia transcriber e evaluator
    print(f"[Worker {WORKER_ID}] Pre-aquecendo modelos IA...", flush=True)
    try:
        get_transcriber()
        get_evaluator()
        print(f"[Worker {WORKER_ID}] Modelos IA prontos", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha pre-aquecimento IA: {e}", flush=True)

    global _subscriber_client, _streaming_pull_future
    _subscriber_client = pubsub_v1.SubscriberClient()
    subscriber = _subscriber_client
    subscription_path = subscriber.subscription_path(GCP_PROJECT, PUBSUB_SUBSCRIPTION)

    # Ensure subscription existe (criacao simples, sem DLQ por enquanto)
    try:
        subscriber.get_subscription(request={"subscription": subscription_path})
        print(f"[Worker {WORKER_ID}] Subscription {subscription_path} ja existe", flush=True)
    except Exception:
        print(f"[Worker {WORKER_ID}] Criando subscription {subscription_path}...", flush=True)
        try:
            topic_path = subscriber.topic_path(GCP_PROJECT, PUBSUB_TOPIC)
            subscriber.create_subscription(
                request={
                    "name": subscription_path,
                    "topic": topic_path,
                    "ack_deadline_seconds": 600,
                }
            )
            print(f"[Worker {WORKER_ID}] Subscription criada com sucesso", flush=True)
        except Exception as e:
            err_str = str(e)
            print(f"[Worker {WORKER_ID}] Subscription error (continuando): {err_str[:150]}", flush=True)
            # Sempre continua - subscription ja pode existir

    # Pull em streaming (bloqueante)
    flow_control = pubsub_v1.types.FlowControl(max_messages=2)  # 2 msgs por vez por instancia (Batch/Standalone)
    _streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=callback,
        flow_control=flow_control,
    )

    # NEW (07/07/2026): marca worker como "ready" apos subscribe OK.
    # Antes, WORKER_STATE["current_state"] permanecia "initializing" ate a
    # primeira mensagem, gerando logs WATCHDOG enganosos. Agora reflete
    # corretamente: "ready" = subscrito e aguardando, "processing" = msg
    # em maos, "stuck" = travado.
    with HEALTHZ_LOCK:
        WORKER_STATE["current_state"] = "ready"
    print(f"[Worker {WORKER_ID}] Aguardando mensagens... (Ctrl+C para parar)", flush=True)

    # FIX (06/07/2026 - v3): main thread agora LOOPA sobre o future global.
    # O restart (_restart_streaming_pull) cancela o future antigo e atribui
    # um novo a _streaming_pull_future. O loop abaixo detecta isso e re-bloqueia.
    # Sem isso, o .cancel() do restart matava o container inteiro (exit 0).
    while True:
        with _STREAMING_LOCK:
            current_future = _streaming_pull_future
        try:
            current_future.result(timeout=None)  # bloqueia ate cancelamento/excecao
            # Se chegou aqui sem exception, o future terminou OK (improvavel)
            print(f"[Worker {WORKER_ID}] streaming_pull future terminou limpo, criando novo...", flush=True)
        except KeyboardInterrupt:
            print(f"[Worker {WORKER_ID}] Parando worker (KeyboardInterrupt)...", flush=True)
            try:
                current_future.cancel()
            except Exception:
                pass
            break
        except Exception as e:
            # Restart cancelou nosso future OU exception no gRPC.
            # Se o watchdog fez cancel(), o global ja tem um NOVO future.
            # Se o cancel veio de outro lugar, vamos re-criar no proximo loop.
            print(f"[Worker {WORKER_ID}] streaming_pull future resolvido ({type(e).__name__}: {str(e)[:100]}). Loop...", flush=True)

        # Pequena pausa para nao entrar em hot loop se algo estiver muito errado
        time.sleep(1)


if __name__ == "__main__":
    main()