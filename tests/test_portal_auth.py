"""Testes para os helpers de Portal Auth do Monitoria.

Fase 8 (03/07/2026): monitoria agora consome o endpoint canonico /api/auth/me
do Portal (1 chamada autenticada via Bearer token), substituindo o contrato
anterior de 2 chamadas via /api/me/permissions + /api/me/role (sem auth).

Estes testes mockam httpx.get para validar o NOVO contrato:
  - 1 chamada por is_authorized_for_module() (em vez de 2)
  - Header Authorization: Bearer <token> presente
  - Query param module_id=<id> presente quando chamada e de autorizacao
  - 403 do Portal => retorna False (sem re-raise)
  - 503 do Portal => HTTPException
"""
import pytest
import time
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portal_auth import (
    _SESSION_CACHE,
    _call_portal_api,
    is_authorized_for_module,
    get_user_role_and_admin,
    clear_cache,
)


TOKEN = "fake-firebase-id-token-abc123"


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


def _mock_session_response(modules=None, is_super_admin=False, role="user", client_id="coherence-ai"):
    """Mock do payload 200 do /api/auth/me."""
    return {
        "email": "user@example.com",
        "is_super_admin": is_super_admin,
        "client_id": client_id,
        "role": role,
        "modules": {
            m: {"is_active": True, "role": role, "client_id": client_id} for m in (modules or [])
        },
    }


# -----------------------------------------------------------------------------
# is_authorized_for_module
# -----------------------------------------------------------------------------

def test_is_authorized_single_call_with_bearer():
    """UMA chamada httpx.get com Authorization: Bearer e ?module_id=<id>."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: _mock_session_response(modules=["monitoria-chamadas"]),
        )
        result = is_authorized_for_module("user@example.com", "monitoria-chamadas", TOKEN)
        assert result is True
        assert mock_get.call_count == 1
        # Verifica URL + headers + query params
        args = mock_get.call_args
        assert args[0][0].endswith("/api/auth/me")
        assert args[1]["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert args[1]["params"] == {"module_id": "monitoria-chamadas"}


def test_is_authorized_lacks_module_returns_false():
    """403 do Portal (sem permissao ativa no module_id) => False."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=403,
            json=lambda: {"detail": "Acesso negado: user@example.com nao tem permissao para 'monitoria-chamadas'"},
        )
        result = is_authorized_for_module("user@example.com", "monitoria-chamadas", TOKEN)
        assert result is False
        assert mock_get.call_count == 1


def test_is_authorized_portal_403_returns_false():
    """403 do Portal => False (Portal ja gravou ACCESS_DENIED)."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=403,
            json=lambda: {"detail": "Acesso negado: user@example.com nao tem permissao para 'monitoria-chamadas'"},
        )
        result = is_authorized_for_module("user@example.com", "monitoria-chamadas", TOKEN)
        assert result is False
        assert mock_get.call_count == 1


def test_is_authorized_portal_503_raises():
    """Erro de conexao com Portal => HTTPException 503 (fail-closed)."""
    import httpx
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("Portal down")
        with pytest.raises(Exception) as exc:
            is_authorized_for_module("u@e.com", "monitoria-chamadas", TOKEN)
        assert "503" in str(exc.value) or "indisponivel" in str(exc.value).lower()


# -----------------------------------------------------------------------------
# Cache
# -----------------------------------------------------------------------------

def test_cache_hits_within_ttl():
    """Segunda chamada dentro do TTL NAO chama httpx de novo."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: _mock_session_response(modules=["monitoria-chamadas"]),
        )
        is_authorized_for_module("user@example.com", "monitoria-chamadas", TOKEN)
        is_authorized_for_module("user@example.com", "monitoria-chamadas", TOKEN)
        # Cache hit: so 1 chamada httpx (nao 2).
        assert mock_get.call_count == 1


def test_cache_expires_and_refetches():
    """Apos TTL expirar, busca no Portal de novo."""
    os.environ["PERM_CACHE_TTL_SEC"] = "1"
    import importlib
    import core.portal_auth
    importlib.reload(core.portal_auth)
    try:
        with patch("core.portal_auth.httpx.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: _mock_session_response(modules=["monitoria-chamadas"]),
            )
            core.portal_auth.is_authorized_for_module("u@e.com", "monitoria-chamadas", TOKEN)
            time.sleep(1.1)
            core.portal_auth.is_authorized_for_module("u@e.com", "monitoria-chamadas", TOKEN)
            assert mock_get.call_count == 2
    finally:
        os.environ.pop("PERM_CACHE_TTL_SEC", None)
        importlib.reload(core.portal_auth)


def test_cache_isolated_per_token():
    """Tokens diferentes tem entradas de cache separadas."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: _mock_session_response(modules=["monitoria-chamadas"])),
            MagicMock(status_code=200, json=lambda: _mock_session_response(modules=[])),
        ]
        is_authorized_for_module("u@e.com", "monitoria-chamadas", "token-A")
        is_authorized_for_module("u@e.com", "monitoria-chamadas", "token-B")
        # 2 chamadas (1 por token, sem cache hit entre eles).
        assert mock_get.call_count == 2


# -----------------------------------------------------------------------------
# get_user_role_and_admin
# -----------------------------------------------------------------------------

def test_get_user_role_and_admin_super():
    """Super admin vem do payload /api/auth/me."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: _mock_session_response(is_super_admin=True, role="super-admin", client_id="coherence-ai"),
        )
        info = get_user_role_and_admin("admin@e.com", TOKEN)
        assert info["is_super_admin"] is True
        assert info["client_id"] == "coherence-ai"
        assert info["global_role"] == "super-admin"
        # Verifica que chamou /api/auth/me (sem module_id)
        args = mock_get.call_args
        assert args[0][0].endswith("/api/auth/me")
        assert args[1]["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert "module_id" not in args[1]["params"]


def test_get_user_role_and_admin_returns_safe_defaults_on_error():
    """Erro no Portal => defaults seguros (is_super_admin=False, role=None)."""
    import httpx
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("Portal down")
        info = get_user_role_and_admin("u@e.com", TOKEN)
        assert info["is_super_admin"] is False
        assert info["client_id"] is None
        assert info["global_role"] is None


# -----------------------------------------------------------------------------
# _call_portal_api (helper interno)
# -----------------------------------------------------------------------------

def test_call_portal_api_passes_bearer_header():
    """_call_portal_api inclui header Authorization: Bearer no request."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: _mock_session_response(modules=[]),
        )
        _call_portal_api(TOKEN)
        args = mock_get.call_args
        assert args[1]["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_call_portal_api_passes_module_id_when_provided():
    """_call_portal_api(module_id=X) inclui ?module_id=X no request."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: _mock_session_response(modules=["monitoria-chamadas"]),
        )
        _call_portal_api(TOKEN, module_id="monitoria-chamadas")
        args = mock_get.call_args
        assert args[1]["params"] == {"module_id": "monitoria-chamadas"}


def test_call_portal_api_403_raises_http_exception():
    """_call_portal_api propaga 403 como HTTPException(403)."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=403,
            json=lambda: {"detail": "Acesso negado"},
        )
        with pytest.raises(Exception) as exc:
            _call_portal_api(TOKEN, module_id="monitoria-chamadas")
        assert "403" in str(exc.value)