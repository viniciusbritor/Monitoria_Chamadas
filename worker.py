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
    """Atualiza status da chamada no SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("UPDATE chamadas SET status = ? WHERE id = ?", (status_text, call_id))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[Worker {WORKER_ID}] Falha ao atualizar status: {e}", flush=True)


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

        process_call(call_id, gcs_uri, user_id, diretrizes)

        # Ack message (sucesso)
        message.ack()
        print(f"[Worker {WORKER_ID}] Message {message.message_id} ACKed", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO processando message {message.message_id}: {e}", flush=True)
        # Nack (vai ser reentregue)
        message.nack()


def health_check_server():
    """
    Cloud Run exige que o container escute em PORT (default 8080).
    Este servidor HTTP minimo responde 200 OK para health checks.
    Roda em thread separada para nao bloquear o consumer Pub/Sub.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/healthz":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "worker_id": WORKER_ID}).encode())
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


def main():
    """Loop principal: pull de Pub/Sub e processa."""
    print(f"[Worker {WORKER_ID}] Subscrevendo em {PUBSUB_SUBSCRIPTION}...", flush=True)

    # Inicia health check server em thread separada
    import threading
    health_thread = threading.Thread(target=health_check_server, daemon=True)
    health_thread.start()

    # Pre-aquecimento: instancia transcriber e evaluator
    print(f"[Worker {WORKER_ID}] Pre-aquecendo modelos IA...", flush=True)
    try:
        get_transcriber()
        get_evaluator()
        print(f"[Worker {WORKER_ID}] Modelos IA prontos", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] Falha pre-aquecimento IA: {e}", flush=True)

    subscriber = pubsub_v1.SubscriberClient()
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
    streaming_pull_future = subscriber.subscribe(
        subscription_path,
        callback=callback,
        flow_control=flow_control,
    )

    print(f"[Worker {WORKER_ID}] Aguardando mensagens... (Ctrl+C para parar)", flush=True)

    try:
        streaming_pull_future.result(timeout=None)  # bloqueia
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        print(f"[Worker {WORKER_ID}] Parando worker...", flush=True)
    except Exception as e:
        print(f"[Worker {WORKER_ID}] ERRO fatal: {e}", flush=True)
        streaming_pull_future.cancel()


if __name__ == "__main__":
    main()