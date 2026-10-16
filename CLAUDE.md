# CLAUDE.md — Monitoria_Chamadas

## O que é
Módulo de monitoria de qualidade de call center: recebe áudios de chamadas, transcreve com Whisper, diariza (Operador vs Cliente) e avalia com LLM (nota de QA, NPS, 3 fases da ligação, motivos e sentimentos). É um **módulo filho do Coherence_Portal** — autenticação por SSO Firebase + RBAC herdados do portal.

- Repo: `github.com/viniciusbritor/Monitoria_Chamadas`
- Projeto GCP: `coherence-ominichannel-fs` (us-central1)
- Produção: `https://monitoria.coherenceai.com.br`

## Leia antes de mexer
1. `docs/ARQUITETURA.md` — serviços Cloud Run (vivos e órfãos), tópicos Pub/Sub, gatilhos, diagrama E2E
2. `docs/HARNESS.md` (como rodar, testar e a esteira v4), `docs/GUARDRAILS.md`, `docs/DIARIO_BORDO.md`
3. `Melhorias/` — backlog/propostas (se existir na sua cópia)

## Esteira (obrigatória): `/ci-cd-workflow-gcp`
`worktree de origin/test -> implementar -> bash .github/scripts/pytest-shard.sh TODOS -> commit convencional -> push -> PR contra test -> portão Cloud Build (pr-tests-monitoria-test) -> gh pr merge -> deploy por gatilho -> validar /health`.
Nunca editar `test`/`main`, nunca `git push` na `test`, nunca merge pela web, nunca `gcloud builds submit`. Promoção `test` → `main` é só do dono. IAM e credenciais são do dono.

## Arquitetura / Estrutura
Serviços Cloud Run (detalhe e situação em `docs/ARQUITETURA.md`):

| Serviço | Papel | Situação (16/10/2026) |
|---|---|---|
| `monitoria-test-env` | API FastAPI (test) | vivo |
| `monitoria` | API FastAPI (prod, domínio customizado) | vivo |
| `monitoria-whisper-worker` | Worker test, privado via OIDC | com gatilho, 0 requisições em 30 dias, sem subscription Pub/Sub |
| `monitoria-worker` | Worker prod, privado via OIDC | idem |
| `monitoria-cx`, `monitoria-cx-v2` | legado | órfãos (sem gatilho, 0 requisições); baixa é decisão do dono |

Fluxo: Portal → frontend React (token Firebase na URL) → `POST /api/upload` → GCS + Firestore `chamadas/{call_id}` + publish Pub/Sub → worker (ou Whisper in-process como reserva) → LLM diarize/evaluate → `POST /api/internal/calls/{id}/status` (OIDC) → Firestore → frontend faz polling.

- `api.py` (API), `worker.py`, `core/`, `frontend/`, `scripts/`, `tests/`
- Dockerfiles: `Dockerfile`, `Dockerfile.base`, `Dockerfile.worker`, `Dockerfile.loadtest`
- Cloud Build: `cloudbuild-pr-tests.yaml` (portão), `cloudbuild-test.yaml`, `cloudbuild-prod.yaml`, `cloudbuild-worker.yaml`, `cloudbuild-worker-prod.yaml`, `cloudbuild-loadtest*.yaml`
- Observabilidade: `GET /health` (`commit_sha`), `core/log_json.py` (log JSON com `severity`)

## Como rodar
- Local: `run_local.ps1` (PowerShell) e `requirements.txt`; no Windows, `pip install tzdata`.
- Testes: `bash .github/scripts/pytest-shard.sh TODOS` (a mesma suíte do portão; hermética).
- Secrets: `setup_secrets.ps1` popula o GCP Secret Manager; `secrets_manager.py` lê em runtime.

## Guardrails / cuidados
- **Registro no Portal**: o módulo de teste registra-se como `monitoria-chamadas-test`; só a promoção `test` → `main` restaura o ID canônico `monitoria-chamadas`. Firestore é compartilhado entre test e prod.
- Cloud Run: sempre `--cpu-throttling` e `--min-instances=0` (testado em `tests/test_build_config.py`).
- `ignoredFiles` nos gatilhos de deploy: mudança só em `cloudbuild*.yaml`, `docs/**`, `*.md` ou `scripts/**` não faz deploy. O portão de PR roda em todo PR.
- Workers são privados: chamadas internas exigem token OIDC com `audience` correta.
- Idempotência do worker depende do check de `status` no Firestore antes de processar — não remover.
- `uploads/`, `media/`, `chamadas_simuladas/`, `chamadas_testes/` guardam **áudio real de chamadas** (LGPD). Não subir para repositório público, não anexar em chat. Não logar PII.
- Erro real = `log.error(..., exc_info=True)` (JSON com `severity`); `print` não aparece no monitor de erros.

## Erro em produção: investigação imediata (decisão do dono, 16/10/2026)

Erro em produção não espera pedido. Vale para qualquer sessão, a qualquer momento:

1. **Viu um ERROR** (log com `severity>=ERROR` de `monitoria`, `monitoria-test-env` ou dos workers; issue "Erro novo em produção" no GitHub)? Comece a investigação na hora, mesmo no meio de outra tarefa: diga em uma linha que vai investigar e siga.
2. **Causa raiz, com evidência**: log com horário (BRT), arquivo:linha, dado real (mascarado, sem PII de chamadas). "Flake" e "intermitente" não são causa.
3. **Corrija pela esteira** (worktree de `origin/test`, teste de regressão, suíte, PR, portão, merge) quando está no código. Se depende de decisão ou acesso do dono, diga exatamente o que falta.
4. **Feche o registro**: a issue do erro recebe o PR (`investigando`), o commit depois de conferir nos logs que parou (`corrigido`) ou o motivo quando não é defeito (`explicado`).

Onde ler: Cloud Logging, `resource.type="cloud_run_revision" resource.labels.service_name="<servico>" severity>=ERROR` (pelo MCP `google-cloud-logging`; fallback Python SDK, nunca `gcloud logging read` no PowerShell). O monitor central que abre as issues é do dono e ainda está sendo montado; até lá, o sinal é o log.

## Projetos relacionados
`../Coherence_Portal` (SSO/RBAC pai), `../OmniChannel` (plataforma), `../ChatBotWhatsapp`, `../Call Center` (só especificação), `../Finops`.

## Status
**Ativo em produção** (`monitoria`). Esteira v4 desde 16/10/2026.
