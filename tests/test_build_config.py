"""Testes de governança e guardrails para a configuração de CI/CD e Cloud Build.

Conforme a Esteira CI/CD v3 (ChatBotWhatsapp / ci_cd_workflow_v3):
1. A suíte completa de testes roda EXCLUSIVAMENTE no Portão do GitHub Actions (.github/workflows/pr-tests.yml),
   nunca no Cloud Build (evitando consumo duplicado/pago de minutos de build).
2. O Cloud Build deve utilizar máquina gratuita E2_STANDARD_2 (120 min/dia Free Tier).
3. O deploy deve respeitar --cpu-throttling e min-instances=0 (FinOps GCP).
4. O build deve conter a trava de ordem `deploy-guard` para prevenir concorrência fora de ordem.
"""
from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOUDBUILD_TEST = REPO_ROOT / "cloudbuild-test.yaml"
WORKFLOW_PR_TESTS = REPO_ROOT / ".github" / "workflows" / "pr-tests.yml"
PYTEST_SHARD_SCRIPT = REPO_ROOT / ".github" / "scripts" / "pytest-shard.sh"


@pytest.fixture(scope="module")
def cloudbuild_test_config() -> dict:
    assert CLOUDBUILD_TEST.exists(), f"{CLOUDBUILD_TEST} não existe."
    with CLOUDBUILD_TEST.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestCloudBuildConfig:
    def test_build_nao_roda_pytest_duplicado(self, cloudbuild_test_config):
        """A suíte pytest mora no Portão do GitHub Actions, não no Cloud Build."""
        for step in cloudbuild_test_config.get("steps", []):
            args = " ".join(str(a) for a in step.get("args") or [])
            assert "pytest" not in args, (
                f"Step {step.get('id', step.get('name'))} executa pytest no Cloud Build. "
                "Na v3, a suíte roda exclusivamente no Portão do GitHub Actions."
            )

    def test_machine_type_e2_standard_2(self, cloudbuild_test_config):
        """Uso obrigatório de E2_STANDARD_2 para usufruir dos 120 min/dia grátis."""
        options = cloudbuild_test_config.get("options", {})
        assert options.get("machineType") == "E2_STANDARD_2", (
            f"machineType esperado 'E2_STANDARD_2', obtido: '{options.get('machineType')}'"
        )

    def test_deploy_guard_present(self, cloudbuild_test_config):
        """Garante a trava de concorrência deploy-guard antes do deploy."""
        step_ids = [s.get("id") for s in cloudbuild_test_config.get("steps", []) if s.get("id")]
        assert "deploy-guard" in step_ids, "Step 'deploy-guard' deve existir para evitar deploys fora de ordem."

    def test_cpu_throttling_and_min_instances(self, cloudbuild_test_config):
        """Deploy no Cloud Run deve manter cpu-throttling ativo e min-instances=0."""
        deploy_step = None
        for step in cloudbuild_test_config.get("steps", []):
            if step.get("id") == "deploy":
                deploy_step = step
                break
        assert deploy_step is not None, "Step com id 'deploy' não encontrado no Cloud Build."
        args_text = " ".join(str(a) for a in deploy_step.get("args", []))
        assert "--cpu-throttling" in args_text, "Deploy deve conter '--cpu-throttling'."
        assert "--min-instances=0" in args_text or "min-instances=0" in args_text, "Deploy deve conter '--min-instances=0'."


class TestPortaoFilesExist:
    def test_portao_workflow_exists(self):
        """Workflow pr-tests.yml deve existir."""
        assert WORKFLOW_PR_TESTS.exists(), f"Workflow {WORKFLOW_PR_TESTS} deve existir."

    def test_pytest_shard_script_exists(self):
        """Script .github/scripts/pytest-shard.sh deve existir."""
        assert PYTEST_SHARD_SCRIPT.exists(), f"Script {PYTEST_SHARD_SCRIPT} deve existir."
