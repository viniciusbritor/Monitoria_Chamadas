#!/usr/bin/env bash
# Um shard da suite do portao. Uso: pytest-shard.sh [A|B|ALL] [relatorio.xml]
#
# Fonte UNICA das listas de testes e opcoes do pytest.
# Conforme esteira v3 (ChatBotWhatsapp / ci_cd_workflow_v3).
set -euo pipefail

cd "$(dirname "$0")/../.."

export PYTHONUNBUFFERED=1
export GCP_PROJECT="${GCP_PROJECT:-coherence-ominichannel-fs}"
export FIRESTORE_PROJECT_ID="${FIRESTORE_PROJECT_ID:-coherence-ominichannel-fs}"
export PORTAL_API_URL="${PORTAL_API_URL:-https://coherence-portal-test-c5nbfc5meq-uc.a.run.app}"

SHARD="${1:-ALL}"
RELATORIO=()
if [ -n "${2:-}" ]; then
  RELATORIO=(--junitxml="$2")
fi

case "$SHARD" in
  A|ALL)
    ALVO=(tests/)
    ;;
  B)
    ALVO=(tests/)
    ;;
  *)
    echo "uso: $0 [A|B|ALL] [relatorio.xml]" >&2
    exit 2
    ;;
esac

# Tenta usar pytest-xdist (-n auto) se disponivel; caso contrario fallback gracioso
if python -c "import xdist" 2>/dev/null; then
  XDIST_ARGS=(-n auto)
else
  XDIST_ARGS=()
fi

python -m pytest -q --tb=short --maxfail=5 "${XDIST_ARGS[@]}" "${ALVO[@]}" "${RELATORIO[@]}"