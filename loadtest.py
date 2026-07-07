"""
Monitoria Load Test Agent
=========================

Roda como Cloud Run Job (com GCS FUSE mount do mesmo DB e audio bucket).
Cada execucao:
  1. Limpa rows orfas do DB (>15min em estado inicial)
  2. Gera novo call_id
  3. Insere row no DB compartilhado
  4. Publica mensagem no Pub/Sub `monitoria-whisper-jobs`
  5. Polla o DB ate status terminal (Concluido / Erro)
  6. Loga timestamps de cada etapa para SLA analysis

Envia metricas estruturadas (JSON) para que a sessao pai possa extrair via gcloud logging.

SLA: cada chamada (audio 4min) deve completar em <= 5 min total.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

# Firestore (substituiu SQLite em 06/07/2026 — Plano A++)
from core.db import get_db

# ---- Configuration ----
PROJECT_ID = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs")
AUDIO_BUCKET = os.getenv("AUDIO_BUCKET", "coherence-monitoria-audios-tmp")
AUDIO_FILENAME = "loadtest_5_Cancelamento.mp3"
USER_ID = "loadtest-agent"  # synthetic user for load tests

GCS_URI = f"gs://{AUDIO_BUCKET}/{AUDIO_FILENAME}"
BRT = timezone(timedelta(hours=-3))

# Polling
POLL_INTERVAL_SEC = 5
TIMEOUT_TOTAL_SEC = 600  # 10 min max absoluto

# Stage detection (status LIKE patterns do codigo existente)
STAGE_PATTERNS = [
    ("start",      lambda s: s == "Concluído" or s.startswith("Erro") or s.startswith("Concl")),
    ("download",   lambda s: "Transcrevendo" in s),
    ("transcricao", lambda s: "Transcrevendo" in s),
    ("diarizacao", lambda s: "Separando" in s),
    ("avaliacao",  lambda s: "Analisando" in s),
    ("concluido",  lambda s: s == "Concluído" or s.startswith("Concl")),
    ("erro",       lambda s: s.startswith("Erro") or s.startswith("Erro:")),
]

def now_brt():
    return datetime.now(BRT).isoformat()

def log_structured(event_type, **kwargs):
    """Print a structured JSON log line for gcloud logging to parse."""
    payload = {"event": event_type, "ts_brt": now_brt(), **kwargs}
    print("LT_AGENT " + json.dumps(payload), flush=True)

def log(msg):
    print(f"[loadtest] {msg}", flush=True)

def cleanup_orphans():
    """Marca rows em estado inicial >15min como erro. Retorna count."""
    new_status = "Erro: load-test cleanup (>15min orfao)"
    cleaned = get_db().cleanup_orphans(older_than_seconds=15 * 60, new_status=new_status)
    return len(cleaned)

def insert_call_row(call_id):
    """Insere nova row para o teste (Firestore create)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    get_db().create(call_id, {
        "filename": AUDIO_FILENAME,
        "uploaded_at": now_iso,
        "status": "Na Fila de Processamento...",
        "user_id": USER_ID,
        "gcs_uri": GCS_URI,
        "audio_duration_sec": None,
        "progress_pct": 0.0,
    })

def get_status(call_id):
    doc = get_db().get(call_id)
    return doc.get("status") if doc else None

def detect_stage(status):
    """Identifica a fase atual baseado no status."""
    if status is None:
        return "unknown"
    if status.startswith("Erro"):
        return "erro"
    if status.startswith("Concluído") or status.startswith("Concl"):
        return "concluido"
    if "Transcrevendo" in status:
        return "transcricao"
    if "Separando" in status:
        return "diarizacao"
    if "Analisando" in status:
        return "avaliacao"
    if "Na Fila" in status:
        return "fila"
    return "unknown"

def publish_pubsub(call_id):
    """Publica mensagem para o worker processar."""
    from google.cloud import pubsub_v1
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)
    payload = {
        "call_id": call_id,
        "audio_gcs_uri": GCS_URI,
        "filename": AUDIO_FILENAME,
        "user_id": USER_ID,
    }
    data = json.dumps(payload).encode("utf-8")
    future = publisher.publish(topic_path, data)
    return future.result()

def main():
    log_structured("agent_start", config={
        "db": "firestore",
        "audio_gcs_uri": GCS_URI,
        "topic": f"projects/{PROJECT_ID}/topics/{PUBSUB_TOPIC}",
        "sla_sec": 300,
    })

    # 1. Cleanup
    cleanup_count = cleanup_orphans()
    log_structured("cleanup_done", orphans_cleaned=cleanup_count)

    # 2. Generate new call_id
    call_id = str(uuid.uuid4())
    log_structured("call_assigned", call_id=call_id)

    # 3. Insert row
    insert_call_row(call_id)
    log_structured("insert_done", call_id=call_id, gcs_uri=GCS_URI)

    # 4. Publish Pub/Sub
    try:
        msg_id = publish_pubsub(call_id)
        log_structured("publish_done", call_id=call_id, message_id=msg_id)
    except Exception as e:
        log_structured("publish_failed", call_id=call_id, error=str(e))
        sys.exit(3)

    # 5. Poll Firestore for status transitions
    start = time.time()
    stages_seen = set()
    stage_timestamps = {"start": start}
    last_status = None
    last_change = start

    while True:
        elapsed = time.time() - start
        if elapsed > TIMEOUT_TOTAL_SEC:
            log_structured("timeout", call_id=call_id, elapsed_sec=round(elapsed, 1))
            break

        status = get_status(call_id)
        if status is None:
            log_structured("row_gone", call_id=call_id)
            break

        if status != last_status:
            stage = detect_stage(status)
            now_t = time.time()
            stage_duration = round(now_t - last_change, 2)
            log_structured("stage_transition", call_id=call_id,
                          stage=stage, status=status,
                          elapsed_total_sec=round(elapsed, 1),
                          stage_duration_sec=stage_duration,
                          transition_at_brt=now_brt())
            stages_seen.add(stage)
            stage_timestamps[stage] = now_t
            last_status = status
            last_change = now_t

        if detect_stage(status) in ("concluido", "erro"):
            break

        time.sleep(POLL_INTERVAL_SEC)

    final_elapsed = round(time.time() - start, 1)
    final_status = last_status or "unknown"
    final_stage = detect_stage(final_status)
    success = final_stage == "concluido"

    log_structured("agent_end", call_id=call_id,
                  final_status=final_status,
                  total_elapsed_sec=final_elapsed,
                  stages_seen=sorted(list(stages_seen)),
                  success=success,
                  sla_violated=(final_elapsed > 300))

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()