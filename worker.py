"""
Worker dedicado para transcricao de chamadas via Pub/Sub.
Substitui o BackgroundTasks do FastAPI por um consumer desacoplado.

Vantagens:
- Backend principal fica leve (responde <100ms)
- Worker escala independentemente (0-10 instancias)
- Falhas nao afetam API
- Suporta multiplos uploads simultaneos

Deploy: Cloud Run service monitoria-whisper-worker
- 8 CPU, 16Gi RAM
- min-instances=0 (scale to zero)
- max-instances=10
- timeout=900s
- concurrency=1
"""
import os
import json
import time
import sqlite3
import tempfile
import shutil
import urllib.request
from datetime import datetime
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1, storage as gcs_storage

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
DB_PATH = "/mnt/db/monitoria_ia.db" if os.path.exists("/mnt/db") else "monitoria_ia.db"
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


def update_status(call_id: str, status_text: str):
    """Atualiza status da chamada no SQLite E notifica test-env via callback."""
    # 1. Escreve no SQLite local (worker tem volume mount, GCS compartilhado)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("UPDATE chamadas SET status = ? WHERE id = ?", (status_text, call_id))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[Worker {WORKER_ID}] Falha ao atualizar status: {e}", flush=True)

    # 2. Notifica test-env via callback OIDC (para UI dashboard)
    _notify_test_env_callback(call_id, {"status": status_text})


def _notify_test_env_callback(call_id: str, payload: dict):
    """Envia update de status para test-env via HTTP + OIDC identity token.

    Necessario porque test-env NAO tem volume mount GCS, entao nao le o
    SQLite compartilhado do worker. Sem este callback, a UI do test-env
    sempre mostra 'Na Fila de Processamento...'.
    """
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
    except Exception as e:
        # Falha no callback NAO bloqueia processamento (ja escrevemos no SQLite)
        print(f"[Worker {WORKER_ID}] callback falhou (continuando): {e}", flush=True)


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


def process_call(call_id: str, gcs_uri: str, user_id: str, diretrizes: str):
    """
    Processa uma chamada: baixa do GCS, transcreve, diariza, avalia.
    Atualiza SQLite com progresso e resultado final.
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

    # 2. Busca user_settings (igual ao backend principal)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
        settings_row = cursor.fetchone()
        conn.close()
        user_settings = dict(settings_row) if settings_row else {}
    except Exception:
        user_settings = {}

    # 3. Transcricao
    update_status(call_id, "Transcrevendo Audio (Whisper)...")
    try:
        raw_transcript, segments = get_transcriber().transcribe(local_audio_path)
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

    # 4. Diarizacao
    update_status(call_id, "Separando falas (Diarizacao MiniMax)...")
    try:
        diarized_transcript = get_evaluator().diarize(raw_transcript)
        print(f"[Worker {WORKER_ID}] Diarizacao OK", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha diarizacao (continuando): {e}", flush=True)
        diarized_transcript = raw_transcript

    # 5. Avaliacao LLM
    update_status(call_id, "Analisando Qualidade e Sentimento (MiniMax M3)...")
    try:
        evaluation = get_evaluator().evaluate(
            diarized_transcript,
            user_settings=user_settings,
            pop_context="",
            quality_form=diretrizes,
        )
        print(f"[Worker {WORKER_ID}] Avaliacao OK: nota={evaluation.get('nota_geral')}", flush=True)
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

    # 7. UPDATE final no SQLite
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE chamadas
            SET status = ?, nota = ?, transcricao = ?, sentimentos_cliente = ?, sentimentos_operador = ?,
                erros_fatais = ?, raw_evaluation = ?, transcricao_diarizada = ?,
                nota_sentimento_cliente = ?, nota_qualidade_operador = ?
            WHERE id = ?
        ''', (
            "Concluido",
            nota,
            json.dumps(segments),
            json.dumps(evaluation.get("sentimentos_cliente", [])),
            json.dumps(evaluation.get("sentimentos_operador", [])),
            json.dumps(evaluation.get("erros_fatais_identificados", [])),
            json.dumps(evaluation),
            diarized_transcript,
            nota_sentimento_cliente,
            nota_qualidade_operador,
            call_id,
        ))
        conn.commit()
        conn.close()
        elapsed = time.time() - start_time
        print(f"[Worker {WORKER_ID}] {call_id} CONCLUIDO em {elapsed:.1f}s (nota={nota})", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha ao salvar resultado: {e}", flush=True)

    # 7b. Callback final com resultado completo (transcript + qa)
    _notify_test_env_callback(call_id, {
        "status": "Concluido",
        "transcript": "\n".join(seg.get("text", "") for seg in segments),
        "qa_score": nota,
        "qa_details": {
            "nota_qualidade_operador": nota_qualidade_operador,
            "nota_sentimento_cliente": nota_sentimento_cliente,
            "raw_evaluation": evaluation,
        },
    })

    # 8. Cleanup
    shutil.rmtree(tmp_dir, ignore_errors=True)
    try:
        blob.delete()
        print(f"[Worker {WORKER_ID}] Audio deletado do GCS: {gcs_uri}", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha ao deletar audio do GCS: {e}", flush=True)


def callback(message):
    """Callback para mensagens do Pub/Sub."""
    try:
        data = json.loads(message.data.decode("utf-8"))
        call_id = data["call_id"]
        gcs_uri = data["gcs_uri"]
        user_id = data["user_id"]
        diretrizes = data.get("diretrizes", "")

        with HEALTHZ_LOCK:
            WORKER_STATE["last_msg_received_at"] = time.time()
            WORKER_STATE["last_msg_id"] = message.message_id
            WORKER_STATE["last_msg_call_id"] = call_id
            WORKER_STATE["current_state"] = "processing"

        process_call(call_id, gcs_uri, user_id, diretrizes)

        # Ack message (sucesso)
        message.ack()
        print(f"[Worker {WORKER_ID}] Message {message.message_id} ACKed", flush=True)

        with HEALTHZ_LOCK:
            WORKER_STATE["messages_processed"] += 1
            WORKER_STATE["consecutive_errors"] = 0
            WORKER_STATE["current_state"] = "ready"
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO processando message {message.message_id}: {e}", flush=True)
        # Nack (vai ser reentregue)
        message.nack()
with HEALTHZ_LOCK:
    WORKER_STATE["consecutive_errors"] += 1


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
    global _streaming_pull_future
    with _STREAMING_LOCK:
        if _streaming_pull_future is not None:
            try:
                _streaming_pull_future.cancel()
            except Exception:
                pass
        if _subscriber_client is None:
            return  # nao inicializado ainda, nao pode recriar
        try:
            subscription_path = _subscriber_client.subscription_path(GCP_PROJECT, PUBSUB_SUBSCRIPTION)
            flow_control = pubsub_v1.types.FlowControl(max_messages=1)
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

    Endpoint /healthz:
      - 200 OK se worker esta saudavel (ready ou processing)
      - 503 SERVICE_UNAVAILABLE se worker travado (stuck por mais de 5min)
      - JSON com: state, uptime_sec, last_msg_age_sec, msgs_processed, consecutive_errors
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    STUCK_THRESHOLD_SEC = 300  # 5min sem mensagem = travado

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/healthz"):
                with HEALTHZ_LOCK:
                    now = time.time()
                    uptime = now - WORKER_STATE["started_at"]
                    last_msg_at = WORKER_STATE["last_msg_received_at"]
                    last_msg_age = (now - last_msg_at) if last_msg_at else None

                    # Detecta travamento: ready + sem mensagem ha muito tempo
                    if last_msg_age is not None and last_msg_age > STUCK_THRESHOLD_SEC and WORKER_STATE["current_state"] != "processing":
                        WORKER_STATE["current_state"] = "stuck"
                        status_code = 503
                    elif WORKER_STATE["current_state"] == "processing":
                        status_code = 200  # trabalhando = saudavel
                    else:
                        status_code = 200  # ready (pode estar idle aguardando)

                    payload = {
                        "status": "ok" if status_code == 200 else "stuck",
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
        #  - Subscription tem mensagens pendentes (message_count > 0)
        #  - Ha mais de 5min sem receber mensagem
        if (
            state == "ready"
            and uptime > 180
            and last_msg_age is not None
            and last_msg_age > 300
        ):
            try:
                if _subscriber_client is not None:
                    sub_info = _subscriber_client.get_subscription(
                        request={"subscription": _subscriber_client.subscription_path(GCP_PROJECT, PUBSUB_SUBSCRIPTION)}
                    )
                    pending = sub_info.message_count or 0
                    if pending > 0:
                        print(
                            f"[WATCHDOG] STUCK detectado: state=ready, "
                            f"last_msg_age={last_msg_age:.0f}s, pending={pending} msgs. "
                            f"Reiniciando streaming_pull...",
                            flush=True,
                        )
                        _restart_streaming_pull()
            except Exception as e:
                print(f"[WATCHDOG] Falha ao checar subscription: {e}", flush=True)


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
    flow_control = pubsub_v1.types.FlowControl(max_messages=1)  # 1 msg por vez por instancia
    _streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=callback,
        flow_control=flow_control,
    )

    with HEALTHZ_LOCK:
        WORKER_STATE["current_state"] = "ready"

    print(f"[Worker {WORKER_ID}] Aguardando mensagens... (Ctrl+C para parar)", flush=True)

    try:
        _streaming_pull_future.result(timeout=None)  # bloqueia
    except KeyboardInterrupt:
        _streaming_pull_future.cancel()
        print(f"[Worker {WORKER_ID}] Parando worker...", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO fatal: {e}", flush=True)
        _streaming_pull_future.cancel()


if __name__ == "__main__":
    main()