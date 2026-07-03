"""Testes para os helpers de Portal Auth + Audit do Monitoria."""
import pytest
import time
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.portal_auth import (
    _PERM_CACHE,
    _call_portal_api,
    is_authorized_for_module,
    get_user_role_and_admin,
    clear_cache,
)
from core.portal_audit import log_access_denied


@pytest.fixture(autouse=True)
def reset_cache():
    clear_cache()
    yield
    clear_cache()


def _mock_permissions_response(modules):
    """Helper: cria mock response com lista de permissoes."""
    return [{"module_id": m, "is_active": True, "is_approved": True} for m in modules]


def test_is_authorized_user_has_module():
    """User com permissao ativa no modulo retorna True."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: _mock_permissions_response(["monitoria-chamadas"])),
            MagicMock(status_code=200, json=lambda: {"is_super_admin": False, "client_id": "coherence-ai"}),
        ]
        assert is_authorized_for_module("user@example.com", "monitoria-chamadas") is True


def test_is_authorized_user_lacks_module():
    """User SEM permissao no modulo retorna False."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: _mock_permissions_response(["outro-modulo"])),
            MagicMock(status_code=200, json=lambda: {"is_super_admin": False}),
        ]
        assert is_authorized_for_module("user@example.com", "monitoria-chamadas") is False


def test_is_authorized_inactive_permission_excluded():
    """Permissao com is_active=False nao conta."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: [{"module_id": "monitoria-chamadas", "is_active": False, "is_approved": True}]),
            MagicMock(status_code=200, json=lambda: {"is_super_admin": False}),
        ]
        assert is_authorized_for_module("user@example.com", "monitoria-chamadas") is False


def test_cache_hits_within_ttl():
    """Segunda chamada dentro do TTL usa cache (nao chama httpx de novo)."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: _mock_permissions_response(["monitoria-chamadas"])),
            MagicMock(status_code=200, json=lambda: {"is_super_admin": False, "client_id": "coherence-ai"}),
        ]
        # 1a chamada: popula cache
        is_authorized_for_module("user@example.com", "monitoria-chamadas")
        # 2a chamada dentro do TTL: deve usar cache (sem chamar httpx)
        is_authorized_for_module("user@example.com", "monitoria-chamadas")
        # httpx.get foi chamado 2x (1 batch de permissions + 1 de role), nao 4x
        assert mock_get.call_count == 2


def test_cache_expires_and_refetches():
    """Apos TTL expirar, busca no Portal de novo."""
    # TTL baixo para teste
    os.environ["PERM_CACHE_TTL_SEC"] = "1"
    import importlib
    import core.portal_auth
    importlib.reload(core.portal_auth)
    try:
        with patch("core.portal_auth.httpx.get") as mock_get:
            mock_get.side_effect = [
                MagicMock(status_code=200, json=lambda: _mock_permissions_response(["monitoria-chamadas"])),
                MagicMock(status_code=200, json=lambda: {"is_super_admin": False}),
                MagicMock(status_code=200, json=lambda: _mock_permissions_response(["monitoria-chamadas"])),
                MagicMock(status_code=200, json=lambda: {"is_super_admin": False}),
            ]
            core.portal_auth.is_authorized_for_module("u@e.com", "monitoria-chamadas")
            time.sleep(1.1)  # Espera TTL expirar
            core.portal_auth.is_authorized_for_module("u@e.com", "monitoria-chamadas")
            # 2 batches = 4 chamadas httpx
            assert mock_get.call_count == 4
    finally:
        os.environ.pop("PERM_CACHE_TTL_SEC", None)
        importlib.reload(core.portal_auth)


def test_is_authorized_portal_down_raises_503():
    """Portal down (httpx.HTTPError) → 503, NAO cache stale (fail-closed)."""
    import httpx
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("Portal down")
        with pytest.raises(Exception) as exc:
            is_authorized_for_module("u@e.com", "monitoria-chamadas")
        assert "503" in str(exc.value) or "indisponivel" in str(exc.value).lower()


def test_get_user_role_and_admin_super():
    """Super admin vem do Portal."""
    with patch("core.portal_auth.httpx.get") as mock_get:
        mock_get.side_effect = [
            MagicMock(status_code=200, json=lambda: []),
            MagicMock(status_code=200, json=lambda: {"is_super_admin": True, "client_id": "coherence-ai"}),
        ]
        info = get_user_role_and_admin("admin@e.com")
        assert info["is_super_admin"] is True
        assert info["client_id"] == "coherence-ai"


def test_log_access_denied_calls_portal():
    """log_access_denied faz POST no Portal com payload correto."""
    with patch("core.portal_audit.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        result = log_access_denied("monitoria-chamadas", "fake-token", "Sem permissao")
        assert result is True
        mock_post.assert_called_once()
        args = mock_post.call_args
        assert args[0][0].endswith("/api/admin/audit-logs/log-access-denied")
        body = args[1]["json"]
        assert body["module_id"] == "monitoria-chamadas"
        assert body["firebase_id_token"] == "fake-token"
        assert body["reason"] == "Sem permissao"


def test_log_access_denied_handles_500_gracefully():
    """Falha de audit NAO bloqueia o fluxo principal (retorna False)."""
    with patch("core.portal_audit.httpx.post") as mock_post:
        mock_post.side_effect = Exception("network error")
        result = log_access_denied("monitoria-chamadas", "fake", "reason")
        assert result is False  # Nao levanta excecao