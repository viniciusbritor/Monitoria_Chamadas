# 🏗️ Arquitetura do Projeto

> Última atualização: 07/07/2026 (Plano A++ — migração SQLite → Firestore).

- **Stack Tecnológico:**
  - **Backend:** Python 3.11, FastAPI, Uvicorn
  - **Frontend:** React, Vite, TailwindCSS (Identidade Visual Coherence.AI), Lucide Icons
  - **IA (Transcrição):** `faster-whisper` base + CTranslate2 (int8, OMP_NUM_THREADS=2)
  - **IA (Avaliação):** **MiniMax M3** (substituiu Gemini 1.5 Pro em 28/06/2026)
  - **Worker dedicado:** `monitoria-whisper-worker` (Cloud Run service, Pub/Sub consumer)

- **Integrações (APIs/Bancos):**
  - **Firestore** (`coherence-ominichannel-fs`, db `(default)`) — **única fonte de verdade de DB** (Plano A++, 06/07/2026). Substituiu SQLite/GCS FUSE.
    - Collections ativas: `chamadas` (chamadas processadas), `user_settings` (QA settings por usuário)
    - Wrappers: `core/db.py::ChamadasDB`, `core/db.py::UserSettingsDB`
  - **GCP Pub/Sub** — fila de jobs assíncrona (`monitoria-whisper-jobs` topic, `monitoria-whisper-jobs-worker` subscription)
  - **GCP Cloud Storage** — bucket de áudios (`coherence-monitoria-audios-tmp`), bucket DB legado `coherence-ominichannel-fs-db-bucket` (cleanup pendente)
  - **Firebase Auth** — identidade de usuários (token validado em `api.py::get_current_user` via `firebase_admin`)
  - **Portal Coherence** — SSO canônico via `/api/auth/me?module_id=monitoria-chamadas` (Bearer token)
  - **MiniMax M3 API** — extração de QA, sentimentos, 3 fases de avaliação
  - **Google Cloud Identity Tokens (OIDC)** — autenticação worker → test-env callback (`/api/internal/calls/{id}/status`)

- **Variáveis de Ambiente (GCP Cloud Run):**
  - `MINIMAX_API_KEY`: Chave para inferência MiniMax M3 (injetada via `gcloud run services update` pós-deploy, NUNCA commitada).
  - `FIRESTORE_PROJECT_ID=coherence-ominichannel-fs`: Projeto GCP do Firestore.
  - `PORTAL_API_URL=https://coherence-portal-test-c5nbfc5meq-uc.a.run.app`: URL do Portal para validação SSO.
  - `PERM_CACHE_TTL_SEC=300`: TTL do cache de permissões em `core/portal_auth.py`.
  - `PUBSUB_TOPIC=monitoria-whisper-jobs`: Tópico Pub/Sub (test-env publica, worker consume).
  - `PUBSUB_SUBSCRIPTION=monitoria-whisper-jobs-worker`: Subscription do worker.
  - `AUDIO_BUCKET=coherence-monitoria-audios-tmp`: Bucket GCS de áudios brutos.
  - `WORKER_CALLBACK_URL`: URL do test-env para callback OIDC do worker.
  - `OMP_NUM_THREADS=2`: Evita hang do CTranslate2 em Cloud Run.
  - `PYTHONUNBUFFERED=1`: Logs em tempo real.
  - `WHISPER_DOWNLOAD_ROOT=/app/whisper_models`: Modelo Whisper pré-baked no build (evita rate limit 429 HuggingFace em runtime).

- **Fluxo de Dados Principal (modo Pub/Sub — primário):**
  1. Frontend (React) faz upload de áudio para `POST /api/upload` no test-env.
  2. test-env (FastAPI) salva áudio no GCS (durabilidade), cria documento em `chamadas` (Firestore) via `get_db().create()`, publica mensagem no Pub/Sub.
  3. test-env retorna imediatamente. Frontend monitora `GET /api/calls` via short-polling (2s durante processamento, 10s idle).
  4. Worker dedicado (`monitoria-whisper-worker`) consome a mensagem Pub/Sub.
  5. Worker: idempotency check via `get_call(call_id).get('status')` (Firestore), baixa áudio do GCS, transcreve via `faster-whisper`, diariza via `Evaluator.diarize()`, avalia via `Evaluator.evaluate()` (MiniMax M3).
  6. Worker notifica test-env via **callback OIDC** (`POST /api/internal/calls/{call_id}/status` com identity token do Cloud Run metadata server).
  7. test-env valida o token OIDC e atualiza Firestore via `get_db().update()`.
  8. Frontend recebe `Concluído` no próximo poll. UI atualiza com 3 Fases (Apresentação/Métodos/Fechamento), Sentimentos, QA Score, Checklist, Relatório Diarizado.

- **Fluxo de Dados (modo in-process — fallback):**
  - Usado quando worker está unhealthy OU áudio > 50MB. test-env processa localmente em `BackgroundTask` mas **durable**: áudio no GCS + Firestore INSERT. Se container morrer, `/api/internal/recover-stale` republica job no Pub/Sub.

- **Componentes deployados:**
  | Serviço | Cloud Run | Responsabilidade |
  |---|---|---|
  | `monitoria-test-env` | público (via Portal) | API FastAPI, upload, settings, admin endpoints |
  | `monitoria-whisper-worker` | `--no-allow-unauthenticated` (OIDC) | Consumer Pub/Sub, transcrição, diarização, avaliação LLM |
  | `coherence-portal-test` | (projeto separado) | SSO, RBAC, audit logs |

- **Persistência — Firestore collections:**
  ```
  collection: chamadas
    documentId: <call_id uuid>
    fields: filename, uploaded_at, status, nota, transcricao, transcricao_diarizada,
            sentimentos_cliente, sentimentos_operador, erros_fatais, raw_evaluation,
            user_id, diretrizes_qualidade, nota_sentimento_cliente, nota_qualidade_operador,
            gcs_uri, audio_duration_sec, progress_pct, created_at, updated_at
  collection: user_settings
    documentId: <user_id> (Firebase sub)
    fields: checklist_items, estrategia_vendas, estrategia_retencao, updated_at
  ```

- **Locking policy:** last-write-wins (sem transactions). Worker é o único writer de `status`; test-env é o único writer de `nota`/`raw_evaluation`. Conflitos são raros e benignos (UI polling de 2s absorve sobreposições).

- **Índices Firestore (provisionados em 06/07/2026):**
  1. `chamadas`: `user_id ASC, uploaded_at DESC` → `GET /api/calls`
  2. `chamadas`: `status ASC, uploaded_at DESC` → `list_by_status` (admin UI)
  3. `chamadas`: `status ASC, uploaded_at ASC` → `list_stale` (recover/cleanup/stuck)

- **Decisão arquitetural crítica (Plano A++):** SQLite + GCS FUSE mount compartilhado foram removidos por causa de 4 bugs históricos de race conditions / clobber / cache invalidation. Firestore é gerenciado (zero I/O, zero race conditions, queries indexadas). Ver `docs/DIARIO_BORDO.md` 06/07/2026 23:30 BRT e `docs/GUARDRAILS.md` REGRA #11.