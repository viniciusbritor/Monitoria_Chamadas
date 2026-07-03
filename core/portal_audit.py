"""Helper para registrar acesso negado no Firestore do Portal.

Reutilizavel por qualquer modulo do ecossistema Coherence.
O Portal valida o Firebase token do user no body, garantindo que o audit log
fica atrelado ao user real (e nao a um service-account generico).
"""
import os
import httpx

PORTAL_API_URL = os.getenv("PORTAL_API_URL", "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app")
HTTP_TIMEOUT_SEC = 3.0


def log_access_denied(module_id: str, firebase_id_token: str, reason: str = ""):
    """Chama POST /api/admin/audit-logs/log-access-denied no Portal.

    NAO levanta excecao: falhas de audit sao logadas mas NAO bloqueiam o fluxo principal.
    """
    if not firebase_id_token:
        return False
    try:
        r = httpx.post(
            f"{PORTAL_API_URL}/api/admin/audit-logs/log-access-denied",
            json={
                "module_id": module_id,
                "firebase_id_token": firebase_id_token,
                "reason": reason,
            },
            timeout=HTTP_TIMEOUT_SEC,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[portal_audit] Falha ao registrar acesso negado: {e}", flush=True)
        return False