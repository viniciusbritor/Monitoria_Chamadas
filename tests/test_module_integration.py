"""Testes para validar o contrato de integração com o Portal Coherence.

Conforme docs/MODULE_INTEGRATION.md e a arquitetura oficial:
- module_id canônico é 'monitoria-chamadas'
- docs/MODULE_INTEGRATION.md existe e declara os metadados corretos
- core.portal_auth.MODULE_ID coincide com o module_id canônico
"""
from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
MODULE_INTEGRATION_MD = DOCS_DIR / "MODULE_INTEGRATION.md"


def test_module_integration_doc_exists():
    """Garante que docs/MODULE_INTEGRATION.md existe no repositório."""
    assert MODULE_INTEGRATION_MD.exists(), "docs/MODULE_INTEGRATION.md deve existir como fonte canônica de integração."


def test_module_integration_declares_canonical_module_id():
    """Valida se module_id: monitoria-chamadas está declarado explicitamente."""
    content = MODULE_INTEGRATION_MD.read_text(encoding="utf-8")
    assert "monitoria-chamadas" in content, "module_id 'monitoria-chamadas' deve constar em MODULE_INTEGRATION.md."
    assert "Headphones" in content, "Ícone 'Headphones' deve constar em MODULE_INTEGRATION.md."


def test_portal_auth_module_id_matches_canonical():
    """Valida se o MODULE_ID default em core/portal_auth.py é 'monitoria-chamadas'."""
    from core.portal_auth import MODULE_ID
    assert MODULE_ID == "monitoria-chamadas", f"MODULE_ID esperado 'monitoria-chamadas', obtido '{MODULE_ID}'"
