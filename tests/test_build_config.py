"""Governanca da esteira CI/CD (/ci-cd-workflow-gcp v4, 16/10/2026).

1. O portao de PR e' o Cloud Build (`cloudbuild-pr-tests.yaml`), que roda a MESMA suite
   do push local (`.github/scripts/pytest-shard.sh TODOS`). Os yamls de deploy nao rodam pytest.
2. Todo deploy usa E2_STANDARD_2 (so' o yaml de teste da API), `--cpu-throttling`,
   `--min-instances=0` e injeta COMMIT_SHA; depois confere a revisao (`validar-health`).
3. O yaml de teste da API mantem a trava `deploy-guard` contra deploys fora de ordem.
"""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PR_TESTS = REPO_ROOT / "cloudbuild-pr-tests.yaml"
PYTEST_SHARD_SCRIPT = REPO_ROOT / ".github" / "scripts" / "pytest-shard.sh"
DEPLOYS = [
    "cloudbuild-test.yaml",
    "cloudbuild-prod.yaml",
    "cloudbuild-worker.yaml",
    "cloudbuild-worker-prod.yaml",
]


def _carregar(nome: str) -> dict:
    caminho = REPO_ROOT / nome
    assert caminho.exists(), f"{caminho} nao existe."
    with caminho.open(encoding="utf-8-sig") as f:
        return yaml.safe_load(f)


def _texto_args(passo: dict) -> str:
    return " ".join(str(a) for a in passo.get("args") or [])


@pytest.fixture(scope="module")
def cloudbuild_test_config() -> dict:
    return _carregar("cloudbuild-test.yaml")


class TestPortaoDePR:
    def test_pr_tests_roda_a_suite_unica(self):
        cfg = _carregar("cloudbuild-pr-tests.yaml")
        ids = [s.get("id") for s in cfg["steps"]]
        assert ids == ["validar-branch", "pytest"]
        assert "pytest-shard.sh TODOS" in _texto_args(cfg["steps"][1])

    def test_pr_tests_nao_faz_deploy_nem_recebe_secret(self):
        cfg = _carregar("cloudbuild-pr-tests.yaml")
        texto = PR_TESTS.read_text(encoding="utf-8")
        assert "run deploy" not in texto and "availableSecrets" not in cfg
        assert cfg["options"]["machineType"] == "E2_STANDARD_2"

    def test_pytest_shard_script_aceita_todos(self):
        assert "TODOS" in PYTEST_SHARD_SCRIPT.read_text(encoding="utf-8-sig")

    def test_workflow_do_actions_foi_desligado(self):
        assert not (REPO_ROOT / ".github" / "workflows" / "pr-tests.yml").exists()


class TestDeploys:
    @pytest.mark.parametrize("nome", DEPLOYS)
    def test_deploy_nao_roda_pytest(self, nome):
        for passo in _carregar(nome)["steps"]:
            assert "pytest" not in _texto_args(passo), f"{nome}: o portao e' o cloudbuild-pr-tests.yaml."

    @pytest.mark.parametrize("nome", DEPLOYS)
    def test_cloud_run_throttling_min_zero_e_commit_sha(self, nome):
        texto = (REPO_ROOT / nome).read_text(encoding="utf-8-sig")
        assert "--no-cpu-throttling" not in texto
        assert "--cpu-throttling" in texto, f"{nome}: falta --cpu-throttling"
        assert "min-instances=0" in texto, f"{nome}: falta --min-instances=0"
        assert "COMMIT_SHA=$COMMIT_SHA" in texto, f"{nome}: o deploy deve injetar COMMIT_SHA"

    @pytest.mark.parametrize("nome", DEPLOYS)
    def test_valida_a_revisao_no_ar_depois_do_deploy(self, nome):
        passos = _carregar(nome)["steps"]
        assert any(p.get("id") == "validar-health" for p in passos), f"{nome}: falta o passo validar-health"

    def test_machine_type_e2_standard_2(self, cloudbuild_test_config):
        assert cloudbuild_test_config.get("options", {}).get("machineType") == "E2_STANDARD_2"

    def test_deploy_guard_present(self, cloudbuild_test_config):
        ids = [s.get("id") for s in cloudbuild_test_config["steps"]]
        assert "deploy-guard" in ids
        assert ids.index("deploy-guard") < ids.index("deploy") < ids.index("validar-health")
