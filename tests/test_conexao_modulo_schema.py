"""
Valida que docs/conexao_modulo.json segue o schema esperado (fonte canonica).

Este teste vive no Modulo (Monitoria_Chamadas_Teste) porque a fonte canonica
do spec esta em Monitoria_Chamadas_Teste/docs/conexao_modulo.json (Q4=b).
Portal clona este arquivo no build-time via cloudbuild-test.yaml step 0.

Este teste roda no CI do Modulo e falha se:
- Arquivo nao existe
- JSON invalido
- Campos obrigatorios ausentes
- module_id nao bate com o esperado
- URLs nao sao canonicas (c5nbfc5meq-uc)
- schema_version nao segue semver

Se voce adicionar campos, atualize REQUIRED_FIELDS abaixo.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "docs", "conexao_modulo.json")

REQUIRED_TOP_LEVEL = {
    "module_id",
    "display_name",
    "description",
    "icon",
    "schema_version",
    "last_updated",
    "owner",
    "repository",
    "variants",
    "entry_point",
    "required_portal_apis",
    "firestore_schema",
    "ui_in_portal",
    "permissions",
    "env_vars",
    "module_capabilities",
    "rotation_procedure",
    "contract_breakers",
}

REQUIRED_VARIANTS = {"test", "prod"}
URL_PATTERN = re.compile(r"^https://monitoria-(test-)?env-[a-z0-9-]+\.a\.run\.app/?$")
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _load():
    assert os.path.exists(CONFIG_PATH), (
        f"Arquivo ausente: {CONFIG_PATH}. "
        f"A fonte canonica vive no Modulo (Monitoria_Chamadas_Teste/docs/conexao_modulo.json)."
    )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_conexao_modulo_json_exists_and_parses():
    """Arquivo existe e e' JSON valido."""
    data = _load()
    assert isinstance(data, dict), "conexao_modulo.json deve ser um objeto"


def test_conexao_modulo_required_top_level_fields():
    """Todos os campos top-level obrigatorios estao presentes."""
    data = _load()
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    assert not missing, f"Campos obrigatorios ausentes: {sorted(missing)}"


def test_conexao_modulo_module_id_is_canonical():
    """module_id deve ser exatamente 'monitoria-chamadas'."""
    data = _load()
    assert data["module_id"] == "monitoria-chamadas", (
        f"module_id divergente: '{data['module_id']}'. "
        f"Constante imutavel: 'monitoria-chamadas'."
    )


def test_conexao_modulo_schema_version_is_semver():
    """schema_version segue semver MAJOR.MINOR.PATCH."""
    data = _load()
    assert SEMVER_PATTERN.match(data["schema_version"]), (
        f"schema_version invalido: '{data['schema_version']}'. Esperado semver (ex: 1.2.3)."
    )


def test_conexao_modulo_has_test_and_prod_variants():
    """variants deve ter pelo menos 'test' e 'prod'."""
    data = _load()
    assert REQUIRED_VARIANTS.issubset(set(data["variants"].keys())), (
        f"variants deve conter {sorted(REQUIRED_VARIANTS)}. "
        f"Encontrado: {sorted(data['variants'].keys())}"
    )


def test_conexao_modulo_test_url_is_canonical():
    """URL da variante test segue o pattern canonico."""
    data = _load()
    test_url = data["variants"]["test"]["url"]
    assert test_url and URL_PATTERN.match(test_url), (
        f"URL test invalida: '{test_url}'. "
        f"Pattern esperado: https://monitoria-test-env-...a.run.app"
    )


def test_conexao_modulo_required_apis_declared():
    """As APIs criticas que o modulo chama no Portal devem estar declaradas."""
    data = _load()
    declared = {(a["method"], a["path"]) for a in data["required_portal_apis"]}
    # OBRIGATORIO: GET /api/auth/me (canonico Fase 8)
    assert ("GET", "/api/auth/me") in declared, (
        "API canonica /api/auth/me ausente de required_portal_apis. "
        "Modulo Monitoria quebra sem ela."
    )


def test_conexao_modulo_firestore_doc_id_is_module_id():
    """firestore_schema.doc_id deve ser igual a module_id."""
    data = _load()
    assert data["firestore_schema"]["doc_id"] == data["module_id"], (
        f"firestore_schema.doc_id deve ser igual a module_id. "
        f"Encontrado: {data['firestore_schema']['doc_id']}"
    )


def test_conexao_modulo_url_pattern_matches_test():
    """URL pattern em firestore_schema deve validar a URL test."""
    data = _load()
    pattern = data["firestore_schema"]["fields"]["url"]["pattern"]
    assert pattern, "firestore_schema.fields.url.pattern nao pode ser vazio"
    compiled = re.compile(pattern)
    test_url = data["variants"]["test"]["url"]
    assert test_url and compiled.match(test_url), (
        f"URL test '{test_url}' nao bate com pattern '{pattern}'"
    )


def test_conexao_modulo_icon_in_lucide_react():
    """icon deve ser um componente valido do lucide-react (validacao basica)."""
    data = _load()
    icon = data["icon"]
    assert icon and icon[0].isupper(), (
        f"icone lucide-react deve ser PascalCase. Encontrado: '{icon}'"
    )


def test_conexao_modulo_removed_from_portal():
    """Lembrete arquitetural: Portal NAO deve ter este arquivo (Q4=b).

    Este teste documenta a decisao. Ele nao bloqueia CI do Modulo,
    mas serve de documentacao viva. A verificacao real acontece no
    Portal (ausencia de docs/conexao_modulo.{md,json} no repo).
    """
    # Apenas garante que o modulo TEM o arquivo
    assert os.path.exists(CONFIG_PATH), (
        "Este arquivo DEVE existir no Modulo (fonte canonica). "
        "Portal nao deve ter (foi movido em 03/07/2026 - Q4=b)."
    )