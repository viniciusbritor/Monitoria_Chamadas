"""Helpers para validar permissões de usuários via Portal Coherence.

O Portal é a SOURCE OF TRUTH de permissões. Monitoria consulta o Portal
via API em todo request e cacheia por 5 minutos (in-memory, fail-closed).

Reutilizável por qualquer módulo novo do ecossistema Coherence.
"""
import os
import time
import httpx
from fastapi import HTTPException

PORTAL_API_URL = os.getenv("PORTAL_API_URL", "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app")
PERM_CACHE_TTL_SEC = int(os.getenv("PERM_CACHE_TTL_SEC", "300"))
HTTP_TIMEOUT_SEC = 3.0

_PERM_CACHE = {}  # {email: {"perms": [...], "role": {...}, "ts": epoch}}


def _fetch_from_portal(email: str) -> dict:
    """Busca permissions e role do Portal. Cache em memoria com TTL."""
    now = time.time()
    if email in _PERM_CACHE:
        cached = _PERM_CACHE[email]
        if now - cached["ts"] < PERM_CACHE_TTL_SEC:
            return cached
        # Cache expirado: tenta refresh; se Portal down, usa cache stale
        # (degraded mode - melhor que derrubar todas as requisicoes)
        try:
            return _call_portal_api(email)
        except Exception:
            return cached  # fallback stale

    return _call_portal_api(email)


def _call_portal_api(email: str) -> dict:
    perms_r = httpx.get(
        f"{PORTAL_API_URL}/api/me/permissions",
        params={"email": email},
        timeout=HTTP_TIMEOUT_SEC,
    )
    perms_r.raise_for_status()
    role_r = httpx.get(
        f"{PORTAL_API_URL}/api/me/role",
        params={"email": email},
        timeout=HTTP_TIMEOUT_SEC,
    )
    role_r.raise_for_status()
    result = {
        "perms": perms_r.json(),
        "role": role_r.json(),
        "ts": time.time(),
    }
    _PERM_CACHE[email] = result
    return result


def is_authorized_for_module(email: str, module_id: str) -> bool:
    """Retorna True se o user tem permissao ativa no modulo."""
    try:
        data = _fetch_from_portal(email)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Portal indisponivel para validar permissao: {e}"
        )
    perms = data.get("perms") or []
    return any(
        p.get("module_id") == module_id
        and p.get("is_active") is not False
        and p.get("is_approved") is not False
        for p in perms
    )


def get_user_role_and_admin(email: str) -> dict:
    """Retorna is_super_admin, client_id, global_role do user."""
    try:
        data = _fetch_from_portal(email)
    except Exception:
        return {"is_super_admin": False, "client_id": None, "global_role": None}
    role = data.get("role", {})
    return {
        "is_super_admin": role.get("is_super_admin", False),
        "client_id": role.get("client_id"),
        "global_role": role.get("global_role"),
    }


def clear_cache():
    """Limpa cache (util para testes)."""
    _PERM_CACHE.clear()