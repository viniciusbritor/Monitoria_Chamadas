"""Helpers para validar sessoes de usuarios via Portal Coherence.

O Portal e' a SOURCE OF TRUTH de sessoes + permissoes. A partir de 03/07/2026
(Fase 8), o Monitoria consome o endpoint canonico de SSO:

    GET {PORTAL_API_URL}/api/auth/me[?module_id=<id>]
    Authorization: Bearer <firebase_id_token>

Este endpoint:
  - 200: payload da sessao ({email, is_super_admin, client_id, role, modules{}})
  - 403: user sem permissao ativa em ?module_id=X (audit log ACCESS_DENIED automatico)
  - 401: token ausente/invalido

Substitui o contrato anterior (2 chamadas separadas para /api/me/permissions +
/api/me/role, sem auth) por 1 chamada autenticada.

Reutilizavel por qualquer modulo novo do ecossistema Coherence.
"""
import os
import time
import httpx
from fastapi import HTTPException, Header

PORTAL_API_URL = os.getenv("PORTAL_API_URL", "https://coherence-portal-test-c5nbfc5meq-uc.a.run.app")
PERM_CACHE_TTL_SEC = int(os.getenv("PERM_CACHE_TTL_SEC", "300"))
HTTP_TIMEOUT_SEC = 3.0
MODULE_ID = os.getenv("MODULE_ID", "monitoria-chamadas")  # usado como default em chamadas

# Cache: {(token_hash, module_id_or_None): {"data": dict, "ts": epoch}}
# key inclui token_hash (nao token cru) para nao vazar secrets em logs/memoria.
_SESSION_CACHE = {}


def _token_hash(token: str) -> str:
    """Hash simples do token para usar como chave de cache (sem vazar o secret)."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _fetch_from_portal(firebase_id_token: str, module_id: str = None) -> dict:
    """Busca sessao canonica do Portal via /api/auth/me. Cache por (token, module_id)."""
    key = (_token_hash(firebase_id_token), module_id)
    now = time.time()
    if key in _SESSION_CACHE:
        cached = _SESSION_CACHE[key]
        if now - cached["ts"] < PERM_CACHE_TTL_SEC:
            return cached["data"]
        # Cache expirado: tenta refresh; se Portal down, usa cache stale
        # (degraded mode - melhor que derrubar todas as requisicoes)
        try:
            return _call_portal_api(firebase_id_token, module_id)
        except Exception:
            return cached["data"]

    return _call_portal_api(firebase_id_token, module_id)


def _call_portal_api(firebase_id_token: str, module_id: str = None) -> dict:
    """Faz 1 chamada ao Portal /api/auth/me e retorna o payload completo.

    200 OK: retorna o payload.
    403 Forbidden: user sem permissao no module_id (Portal ja gravou audit log).
    401/503: levanta HTTPException via raise_for_status.
    """
    params = {}
    if module_id:
        params["module_id"] = module_id
    r = httpx.get(
        f"{PORTAL_API_URL}/api/auth/me",
        params=params,
        headers={"Authorization": f"Bearer {firebase_id_token}"},
        timeout=HTTP_TIMEOUT_SEC,
    )
    if r.status_code == 403:
        # Portal ja gravou ACCESS_DENIED. Propaga 403 para o caller decidir.
        raise HTTPException(
            status_code=403,
            detail=r.json().get("detail", "Acesso negado pelo Portal"),
        )
    r.raise_for_status()
    data = r.json()
    key = (_token_hash(firebase_id_token), module_id)
    _SESSION_CACHE[key] = {"data": data, "ts": time.time()}
    return data


def is_authorized_for_module(email: str, module_id: str, firebase_id_token: str) -> bool:
    """Retorna True se o user tem permissao ativa no modulo.

    Implementacao: chama /api/auth/me?module_id=X com Bearer token. Se Portal
    retornar 200, tem permissao. Se retornar 403, NAO tem (Portal ja gravou
    ACCESS_DENIED). Outros erros viram 503 (Portal indisponivel).
    """
    try:
        _fetch_from_portal(firebase_id_token, module_id=module_id)
        return True
    except HTTPException as e:
        if e.status_code == 403:
            return False
        raise
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Portal indisponivel para validar permissao: {e}"
        )


def get_user_role_and_admin(email: str, firebase_id_token: str) -> dict:
    """Retorna is_super_admin, client_id, role do user (do payload /api/auth/me)."""
    try:
        data = _fetch_from_portal(firebase_id_token, module_id=None)
    except Exception:
        # Fail-closed no caminho de role (sem permissao = user comum)
        return {"is_super_admin": False, "client_id": None, "global_role": None}
    return {
        "is_super_admin": data.get("is_super_admin", False),
        "client_id": data.get("client_id"),
        "global_role": data.get("role"),
    }


def clear_cache():
    """Limpa cache (util para testes)."""
    _SESSION_CACHE.clear()


# ============================================================================
# Dependencias FastAPI (para usar com Depends(...))
# ============================================================================

def require_admin_user(authorization: str = Header(None)) -> dict:
    """Validacao lightweight para endpoints /api/* admin-only.

    NAO revalida permissao de modulo (modulo inteiro e admin-only).
    Apenas:
      1. Extrai Bearer token do header Authorization
      2. Valida Firebase token (fb_auth.verify_id_token) localmente
      3. Consulta Portal: GET /api/auth/me (sem module_id) - valida is_super_admin

    Retorna dict com keys: email, is_super_admin, role.

    Levanta HTTPException 401/403/503 conforme o caso.

    Uso:
      @app.get("/api/admin/foo")
      def foo(user = Depends(require_admin_user)):
          ...
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        token = authorization.split("Bearer ", 1)[1]
    except (IndexError, AttributeError):
        raise HTTPException(status_code=401, detail="Authorization Header mal formado")
    try:
        # Import lazy para evitar erro se firebase-admin nao inicializou
        import firebase_admin
        from firebase_admin import auth as fb_auth
        if not firebase_admin._apps:
            raise RuntimeError("firebase-admin nao inicializado")
        decoded = fb_auth.verify_id_token(token)
        email = decoded.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Token sem email")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Firebase token: {e}")

    role_info = get_user_role_and_admin(email, token)
    if not role_info.get("is_super_admin"):
        raise HTTPException(
            status_code=403,
            detail=f"Acesso restrito a administradores: {email}"
        )

    decoded["is_super_admin"] = True
    decoded["role"] = "admin"
    decoded["client_id"] = role_info.get("client_id")
    return decoded