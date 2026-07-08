# HARNESS do Modulo Monitoria de Chamadas

> Ultima atualizacao: 07/07/2026 (refactor total + objetivo principal)

## Objetivo Principal

O modulo de Monitoria de Chamadas tem 5 objetivos principais, executados em sequencia:

| # | Objetivo | Componente | Status |
|---|---|---|---|
| 1 | **Upload de chamada** (audio file) | Frontend + `api.py:POST /api/upload` | Ativo |
| 2 | **Transcricao audio -> texto** | `worker.py:process_call` (Whisper) | Ativo |
| 3 | **Separar audio atendente e cliente** (diarizacao) | `core/evaluator.py:diarize` (LLM) | Ativo |
| 4 | **Avaliar nota QA do atendente + nota NPS do cliente** | `core/evaluator.py:evaluate` (LLM) | Ativo |
| 5 | **Categorizar motivos principais da chamada** | `core/evaluator.py:evaluate` (LLM) | Ativo |

## Stack Tecnologico

| Camada | Tecnologia |
|---|---|
| Frontend | React 19, Vite, TailwindCSS, Lucide Icons, Axios |
| Backend (API) | Python 3.11, FastAPI, Uvicorn |
| Worker (processamento) | Python 3.11, `faster-whisper` (CPU, int8), `MiniMax M3` (LLM) |
| Database | **Firestore** (`coherence-ominichannel-fs`) - source of truth |
| Queue assincrono | GCP Pub/Sub (`monitoria-whisper-jobs` topic) |
| Storage audio | GCP Cloud Storage (`coherence-monitoria-audios-tmp` bucket) |
| Auth | Firebase Auth (token via Portal Coherence) |
| SSO | Portal Coherence (`/api/auth/me` endpoint) |

## Endpoints principais

### Publicos (requer Bearer token)
- `GET /api/auth/me` - Verifica sessao + role
- `GET /api/calls` - Lista chamadas do user
- `GET /api/calls/{id}` - Detalhe de uma chamada (com bypass super-admin)
- `GET /api/calls/{id}/audio` - URL do audio (signed)
- `GET /api/settings` / `POST /api/settings` - QA settings do user
- `POST /api/upload` - Upload de 1 audio (cria chamada no Firestore + publica no Pub/Sub)
- `POST /api/upload-batch` - **NEW (08/07/2026)**: Upload em batch, max 50 arquivos, max 20MB cada

### Service-to-service (requer OIDC)
- `POST /api/internal/calls/{id}/status` - Callback OIDC do worker
- `POST /api/internal/recover-stale` - Recover jobs orfaos
- `POST /api/internal/cleanup-orphans` - Cleanup admin

### Admin (requer super-admin)
- `GET /api/queue/*` - Gerenciar fila Pub/Sub
- `GET /api/admin/stuck-calls` - Listar chamadas stuck

## Fluxo E2E (sequencia completa)

1. **Upload** (frontend) - User seleciona audio, frontend POST `/api/upload`
2. **Persistencia** (api.py) - Salva audio no GCS, cria doc no Firestore (`status="Na Fila..."`), publica no Pub/Sub
3. **Polling** (frontend) - User ve lista de chamadas com status atualizado
4. **Consumo** (worker.py) - Worker recebe msg, faz idempotency check, processa
5. **Transcricao** (worker.py + core/transcriber.py) - Whisper transcreve audio
6. **Diarizacao** (worker.py + core/evaluator.py) - LLM separa Operador vs Cliente
7. **Avaliacao** (worker.py + core/evaluator.py) - LLM gera QA, NPS, motivos, 3 fases
8. **Callback** (worker.py) - Worker chama `/api/internal/calls/{id}/status` com OIDC
9. **Atualizacao** (api.py) - test-env valida OIDC, normaliza status, atualiza Firestore
10. **Visualizacao** (frontend) - User ve "Concluido" no dashboard, clica "Inspecionar"
11. **Inspecao** (frontend) - CallInspector mostra Relatorio, Transcricao, Sentimentos, Audio

## Variaveis de ambiente

### test-env (Cloud Run monitoria-test-env)
| Variavel | Default | Origem |
|---|---|---|
| `MINIMAX_API_KEY` | (secreto) | `gcloud run services update` (NUNCA commitada) |
| `FIRESTORE_PROJECT_ID` | `coherence-ominichannel-fs` | cloudbuild-test.yaml |
| `PORTAL_API_URL` | `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app` | cloudbuild-test.yaml |
| `TEST_ENV_AUDIENCE` | URL com project number | cloudbuild-test.yaml |
| `PERM_CACHE_TTL_SEC` | `300` | cloudbuild-test.yaml |
| `OMP_NUM_THREADS` | `2` | cloudbuild-test.yaml |
| `PYTHONUNBUFFERED` | `1` | cloudbuild-test.yaml |

### worker (Cloud Run monitoria-whisper-worker)
| Variavel | Default |
|---|---|
| `GCP_PROJECT` | `coherence-ominichannel-fs` |
| `PUBSUB_TOPIC` | `monitoria-whisper-jobs` |
| `PUBSUB_SUBSCRIPTION` | `monitoria-whisper-jobs-worker` |
| `AUDIO_BUCKET` | `coherence-monitoria-audios-tmp` |
| `WORKER_CALLBACK_URL` | URL do test-env (opcional desde 08/07/2026) |
| `LEGACY_CALLBACK` | **`false`** (NEW 08/07/2026 - Plano Ultra-Economico). Se `true`, worker usa callback OIDC legado em vez de gravar direto no Firestore. |
| `OMP_NUM_THREADS` | `2` |
| `WHISPER_DOWNLOAD_ROOT` | `/app/whisper_models` |

### worker Cloud Run (recursos desde 08/07/2026 - Plano Ultra-Economico)
| Recurso | Valor |
|---|---|
| CPU | 4 vCPU |
| Memory | 4 GiB |
| max-instances | 2 |
| min-instances | 0 (scale-to-zero) |
| concurrency | 1 |
| `--no-cpu-throttling` | ativo |
| Custo estimado | ~$96/mês (300h ativas) |

## URL canonica

- **Producao**: `https://monitoria.coherenceai.com.br`
- **Test (este projeto)**: `https://monitoria-test-env-894828119087.us-central1.run.app`
- **Portal Coherence (referencia)**: `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app`

## Acesso ao Modulo - SEMPRE via Portal Coherence

> IMPORTANTE: A URL do Cloud Run NAO e' endpoint publico. Unico caminho
> de acesso legitimo e' via Portal Coherence.

**Fluxo de acesso:**
1. User acessa Portal Coherence
2. Faz login (Firebase SSO)
3. Clica no card "Monitoria de Chamadas"
4. Portal abre: `window.open(module.url + '?token=' + firebase_id_token, '_blank')`
5. Modulo valida token via `/api/auth/me` no Portal e renderiza dashboard

**Para testes locais:**
- Copie `frontend/.env.example` para `frontend/.env.local`
- Ajuste `VITE_API_URL=http://127.0.0.1:8001`
- **NUNCA compartilhe a URL publica do Cloud Run** como ponto de entrada

## Workflow de Deploy

| Build | Trigger | Resultado |
|---|---|---|
| `cloudbuild-test.yaml` | push em `test` | Build + push imagem + deploy `monitoria-test-env` |
| `cloudbuild-worker.yaml` | manual | Build + push imagem + deploy `monitoria-whisper-worker` |

**IMPORTANTE:** deployar test-env e worker simultaneamente para evitar inconsistencias.

## Build do Frontend

- **REGRA CRITICA:** `VITE_API_URL` DEVE ser injetado via Cloud Build substitutions ANTES do `npm run build`. NUNCA deixar `VITE_API_URL` cair no fallback hard-coded.
- **NUNCA** criar `frontend/.env.local` (seu conteudo e' embutido no bundle).
- Para desenvolvimento local: copiar `.env.example` para `.env.local`.
- **Cache-bust:** o `cloudbuild-test.yaml` cria `frontend/.cache-bust` antes do build.

## Ver tambem

- [ARQUITETURA.md](ARQUITETURA.md) - Detalhes tecnicos do sistema
- [GUARDRAILS.md](GUARDRAILS.md) - Regras inegociaveis
- [conexao_modulo.md](conexao_modulo.md) - Spec do contrato com Portal
- [DIARIO_BORDO.md](DIARIO_BORDO.md) - Historico de mudancas
