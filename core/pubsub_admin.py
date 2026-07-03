"""Helpers para gerenciar a subscription Pub/Sub do Monitoria.

Usado pelo modulo admin Queue Manager para:
- Listar mensagens pendentes sem consumi-las (peek)
- Obter estatisticas da subscription (profundidade, idade oldest)
- Acknowledge (descartar) mensagens orfas
- Republicar (retry) mensagens no topico

ATENCAO: o "peek" usa modify_ack_deadline(ack_ids, 0) para devolver a mensagem
imediatamente a fila, sem afetar o worker real. Isso evita janela onde o
worker real perde a mensagem.

Reutilizavel por qualquer modulo do ecossistema Coherence.
"""
import os
import json
import time
import base64
from typing import Optional
from google.cloud import pubsub_v1

GCP_PROJECT = os.getenv("GCP_PROJECT", "coherence-ominichannel-fs")
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "monitoria-whisper-jobs")
PUBSUB_SUBSCRIPTION = os.getenv("PUBSUB_SUBSCRIPTION", "monitoria-whisper-jobs-worker")

PROJECT_PATH = f"projects/{GCP_PROJECT}"
SUBSCRIPTION_PATH = f"{PROJECT_PATH}/subscriptions/{PUBSUB_SUBSCRIPTION}"
TOPIC_PATH = f"{PROJECT_PATH}/topics/{PUBSUB_TOPIC}"

DEFAULT_PEEK_BATCH = 50
DEFAULT_PEEK_DEADLINE_SEC = 10  # janela em que worker real NAO ve a msg


def _decode_payload(data: bytes) -> str:
    """Decodifica payload Pub/Sub (base64) para string. Trunca para preview."""
    try:
        decoded = base64.b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return "<binario>"
    if len(decoded) > 256:
        return decoded[:256] + "..."
    return decoded


def get_stats() -> dict:
    """Retorna metricas da subscription.

    Campos:
      - message_count: total de mensagens NAO acknowledged (NACK + unacked)
      - oldest_unacked_seconds: idade da mensagem mais antiga (None se vazio)
      - ack_deadline_seconds: deadline configurado (padrao 600)
    """
    subscriber = pubsub_v1.SubscriberClient()
    try:
        sub = subscriber.get_subscription(request={"subscription": SUBSCRIPTION_PATH})
        stats = {
            "message_count": getattr(sub, "message_count", 0) or 0,
            "oldest_unacked_seconds": None,
            "ack_deadline_seconds": getattr(sub, "ack_deadline_seconds", 600) or 600,
        }
        # id da mensagem mais antiga (gera idade por timestamp comparativo)
        oldest_id = getattr(sub, "oldest_message_id", None)
        if oldest_id and stats["message_count"] > 0:
            # Sem timestamp direto: estimamos via publish_time de um peek
            peek = list_pending(limit=1)
            if peek["messages"]:
                publish_time_str = peek["messages"][0].get("publish_time")
                if publish_time_str:
                    try:
                        from datetime import datetime
                        pub_dt = datetime.fromisoformat(publish_time_str.replace("Z", "+00:00"))
                        age = (datetime.now(pub_dt.tzinfo) - pub_dt).total_seconds()
                        stats["oldest_unacked_seconds"] = int(age)
                    except Exception:
                        pass
        return stats
    finally:
        subscriber.close()


def list_pending(limit: int = DEFAULT_PEEK_BATCH) -> dict:
    """Lista mensagens pendentes (peek sem consumir).

    Estrategia: usa pull(return_immediately=True) + modify_ack_deadline(ack_id, 0)
    para devolver a mensagem IMEDIATAMENTE ao worker real. Sem janela de perda.

    Retorna:
      {
        "messages": [
          {
            "message_id": str,
            "ack_id": str,
            "publish_time": ISO8601 str,
            "attributes": dict,
            "payload_preview": str (256 chars JSON),
          },
          ...
        ],
        "peeked_count": int,
      }
    """
    subscriber = pubsub_v1.SubscriberClient()
    result = {"messages": [], "peeked_count": 0}
    ack_ids_to_release = []
    try:
        # Pull com janela minima (return_immediately=True evita bloquear ate deadline)
        response = subscriber.pull(
            request={
                "subscription": SUBSCRIPTION_PATH,
                "max_messages": min(limit, DEFAULT_PEEK_BATCH),
                "return_immediately": True,
            },
            timeout=5.0,
        )
        received = response.received_messages or []
        result["peeked_count"] = len(received)
        for rm in received:
            msg = rm.message
            ack_id = rm.ack_id
            publish_time = None
            if msg.publish_time and hasattr(msg.publish_time, "isoformat"):
                publish_time = msg.publish_time.isoformat()
            payload_preview = _decode_payload(msg.data) if msg.data else ""
            msg_dict = {
                "message_id": msg.message_id,
                "ack_id": ack_id,
                "publish_time": publish_time,
                "attributes": dict(msg.attributes or {}),
                "payload_preview": payload_preview,
            }
            result["messages"].append(msg_dict)
            ack_ids_to_release.append(ack_id)
    except Exception as e:
        # Em caso de erro (subscription vazia, permission denied), retornar vazio
        print(f"[pubsub_admin] list_pending error: {e}", flush=True)
    finally:
        # LIBERAR mensagens IMEDIATAMENTE para o worker real
        if ack_ids_to_release:
            try:
                subscriber.modify_ack_deadline(
                    request={
                        "subscription": SUBSCRIPTION_PATH,
                        "ack_ids": ack_ids_to_release,
                        "ack_deadline_seconds": 0,
                    },
                    timeout=5.0,
                )
            except Exception as e:
                print(f"[pubsub_admin] WARN: nao liberou ack_ids: {e}", flush=True)
        subscriber.close()
    return result


def acknowledge(ack_ids: list[str]) -> int:
    """Descarta mensagens (acknowledge). Retorna qtd confirmada."""
    if not ack_ids:
        return 0
    subscriber = pubsub_v1.SubscriberClient()
    try:
        subscriber.acknowledge(
            request={
                "subscription": SUBSCRIPTION_PATH,
                "ack_ids": list(ack_ids),
            },
            timeout=10.0,
        )
        return len(ack_ids)
    finally:
        subscriber.close()


def retry_message(message_id: str, payload_b64: str = "", attributes: dict = None) -> str:
    """Republica uma mensagem no topico. Retorna o novo message_id."""
    publisher = pubsub_v1.PublisherClient()
    try:
        data = base64.b64decode(payload_b64) if payload_b64 else b""
        # novo publish_time = agora (atributo automatico do Pub/Sub)
        attrs = dict(attributes or {})
        attrs["retried_from"] = message_id
        attrs["retry_ts"] = str(int(time.time()))
        future = publisher.publish(
            TOPIC_PATH,
            data=data,
            **attrs,
        )
        new_id = future.result(timeout=10.0)
        return new_id
    finally:
        publisher.close()


def purge_all(max_per_call: int = 1000) -> int:
    """Ack em massa: descarta TODAS mensagens pendentes. Retorna qtd descartada.

    ATENCAO: use apenas apos confirmacao explicita do usuario.
    Implementacao: loop de peek+ack ate esvaziar ou atingir max_per_call.
    """
    total_acked = 0
    while total_acked < max_per_call:
        result = list_pending(limit=100)
        if not result["messages"]:
            break
        ack_ids = [m["ack_id"] for m in result["messages"]]
        acked = acknowledge(ack_ids)
        total_acked += acked
        if len(result["messages"]) < 100:
            break
    return total_acked
