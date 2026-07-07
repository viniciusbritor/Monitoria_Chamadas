# 🚀 Harness do Projeto

> **Última atualização:** 07/07/2026 (Plano A++ + OIDC fix + revisão docs)

## Visão Geral

Sistema de "Monitoria de Chamadas" baseado em IA:
- **Transcrição** de áudios de atendimento ao cliente via **faster-whisper** (CPU, int8, OMP_NUM_THREADS=2)
- **Avaliação** contra critérios de qualidade via **MiniMax M3** (substituiu Gemini 1.5 Pro em 28/06/2026)
- **Dashboard** React/Vite com UX Clean Light Glassmorphism

## 🔐 Acesso ao Módulo — SEMPRE via Portal Coherence

> **IMPORTANTE:** A URL do Cloud Run `https://monitoria-test-env-894828119087.us-central1.run.app/` **NÃO é endpoint público para usuários finais**. É detalhe de implementação interno do ecossistema Coherence.
>
> Alias deprecated (funciona mas não canônico): `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app/`

**Único fluxo válido:**
1. Usuário acessa `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/`
2. Faz login (Firebase SSO via Google ou email/senha)
3. No Dashboard do Portal, clica no card **"Monitoria de Chamadas"**
4. O Portal abre o módulo em nova aba: `window.open(${module.url}?token=${firebase_id_token}, '_blank')`
5. O módulo valida o token via `GET /api/auth/me` no Portal e renderiza o dashboard autenticado

**Acesso direto (colar a URL no navegador):**
- Exibe a página "Acesso via Portal Coherence" com botão de redirect.
- Backend loga como `[Security] direct-access attempt from <IP>` para auditoria.

**Para testes/desenvolvimento local:**
- Use `frontend/.env.example` → `frontend/.env.local` apontando para `VITE_API_URL=http://127.0.0.1:8001`.
- **Não compartilhe** a URL pública do Cloud Run como ponto de entrada para demos ou testes com usuários reais.

## 🧪 Ambiente de Teste vs Produção

- **REGRA ESTABELECIDA:** A primeira implementação de qualquer nova funcionalidade ou alteração **SEMPRE** deve ser feita no ambiente de Teste/Homologação (`Monitoria_Chamadas_Teste`). Nenhuma alteração deve ser feita diretamente no ambiente de produção.
- Após a implementação no ambiente de teste, o usuário avaliará e decidirá se as alterações devem ser "viradas" para Produção.

## 📂 Estrutura de Diretórios

```
.
├── api.py                      # Roteador principal FastAPI (test-env)
├── worker.py                   # Worker dedicado (Pub/Sub consumer, transcrição, avaliação)
├── loadtest.py                 # Cloud Run Job para testes de carga
├── main.py                     # Entry point local (sem Cloud Run)
├── core/
│   ├── transcriber.py          # Wrapper faster-whisper (com progress callback)
│   ├── evaluator.py            # Wrapper MiniMax M3 (diarize + evaluate)
│   ├── llm_provider.py         # Cliente LLM centralizado
│   ├── db.py                   # Wrappers Firestore (ChamadasDB + UserSettingsDB)
│   ├── portal_auth.py          # SSO canônico via Portal (/api/auth/me)
│   ├── portal_audit.py         # Audit logs de acesso negado
│   └── pubsub_admin.py         # Helper admin para gerenciar subscription
├── frontend/
│   ├── src/components/         # Dashboard, CallInspector, SettingsPanel, QueueManager
│   ├── .env.example            # Template para devs
│   └── .cache-bust             # Timestamp para forçar rebuild
├── docs/                       # Documentação técnica (ARQUITETURA, HARNESS, GUARDRAILS, DIARIO_BORDO, conexao_modulo.{md,json})
├── secrets/
│   └── secrets_manager.py      # Cofre local de credenciais (não commitar)
├── scripts/                    # Utilitários (migração, load test, inspect)
├── tests/                      # Testes automatizados (pytest)
├── Dockerfile                  # Imagem test-env
├── Dockerfile.base             # Imagem base com Whisper pré-baked
├── Dockerfile.worker           # Imagem worker dedicado
├── Dockerfile.loadtest         # Imagem Cloud Run Job do loadtest
├── cloudbuild-test.yaml        # Build + deploy test-env
├── cloudbuild-worker.yaml      # Build + deploy worker
├── cloudbuild-loadtest.yaml    # Build do loadtest
└── cloudbuild-loadtest-deploy.yaml  # Dispara execução do loadtest
```

## 🔑 Autenticação e Segredos

- O projeto consome segredos via env vars injetadas no deploy (`gcloud run services update --update-env-vars`).
- Variável crítica: `MINIMAX_API_KEY` (LLM MiniMax M3 para extração de QA), extraída de `secrets_manager.py` (banco cofre local) durante o deploy. **Nunca commitada em código ou YAML.** Ver `docs/DIARIO_BORDO.md` 28/06/2026 (bug `login fail: Please carry the API secret key` no deploy).
- Firestore access: SA default do Cloud Run (`894828119087-compute@developer.gserviceaccount.com`) tem role `roles/datastore.user` no projeto `coherence-ominichannel-fs`.

## 🤝 SSO com Portal Coherence (Fase 8 — 03/07/2026)

O Monitoria **consome o endpoint canônico de SSO** do Portal para validar sessão + permissões:

```http
GET {PORTAL_API_URL}/api/auth/me[?module_id=<id>]
Authorization: Bearer <firebase_id_token>
```

- **200** → payload `{email, is_super_admin, client_id, role, modules{}}`. User tem permissão.
- **403** → Portal gravou `ACCESS_DENIED` automaticamente. User sem permissão.
- **401/503** → falha transitória.

**Helpers em `core/portal_auth.py`:**
- `is_authorized_for_module(email, module_id, firebase_id_token) → bool`
- `get_user_role_and_admin(email, firebase_id_token) → dict`
- `require_admin_user(authorization: str = Header(None)) → dict` (FastAPI dependency)

**Cache:** TTL 300s in-memory, chave `(token_hash, module_id)`. Isolamento por usuário (token).

> **ATENÇÃO:** desde a Fase 8, NÃO chamar `log_access_denied()` manualmente após `is_authorized_for_module()` retornar False. O Portal grava `ACCESS_DENIED` automaticamente no 403 — chamada extra é ruído.

**Procedimento de rotação de URL do Portal:** ver `docs/HARNESS.md` do Portal (seção "Rotação de URL de Módulo"). Resumo: atualizar `PORTAL_API_URL` no `cloudbuild-test.yaml` do Monitoria → commit + push → redeploy. Cache TTL 300s garante que a próxima chamada HTTP pega a URL nova.

## 🔄 OIDC Audience — Worker → Test-env (07/07/2026)

O worker dedicado (`monitoria-whisper-worker`) usa **Google Cloud Identity Tokens (OIDC)** para chamar o callback `POST /api/internal/calls/{id}/status` no test-env de forma service-to-service (sem precisar de Firebase token).

**Fluxo OIDC:**
1. Worker obtém identity token do Cloud Run metadata server:
   ```
   GET http://metadata/computeMetadata/v1/instance/service-accounts/default/identity?audience={TEST_ENV_URL}
   Header: Metadata-Flavor: Google
   ```
2. Worker envia POST com `Authorization: Bearer <token>`
3. test-env valida via `google.oauth2.id_token.verify_oauth2_token(token, audience=TEST_ENV_AUDIENCE)`

**Configuração crítica (3 lugares devem estar alinhados):**

| Local | Variável | Valor esperado |
|---|---|---|
| `cloudbuild-worker.yaml:55` | `--update-env-vars=WORKER_CALLBACK_URL=...` | URL canônico do test-env |
| `api.py:568` (default) | `TEST_ENV_AUDIENCE = os.getenv("TEST_ENV_AUDIENCE", "...")` | MESMO URL |
| `cloudbuild-test.yaml:60` | `--set-env-vars=TEST_ENV_AUDIENCE=...` | MESMO URL (injetado para garantia) |

**Bug OIDC audience mismatch (07/07/2026):** o commit `07d94de` atualizou `WORKER_CALLBACK_URL` para URL com project number (`894828119087`), mas esqueci de alinhar `TEST_ENV_AUDIENCE` em `api.py:568`. Resultado: worker gerava token com `audience=894828119087`, mas test-env validava contra `c5nbfc5meq` (default antigo) → **401 em todos os callbacks OIDC** → chamada presa em "Na Fila de Processamento..." por horas.

**Fix:** commit `25db426 fix(oidc): alinhar TEST_ENV_AUDIENCE com WORKER_CALLBACK_URL canonico`.

## 💾 Firestore como Fonte de Verdade (Plano A++ — 06/07/2026)

**Migração completa de SQLite/GCS FUSE para Firestore** (commit `22261d7` ... `0b57c7b`).

**Por que Firestore:**
- Zero race conditions (vs 4 bugs históricos do SQLite GCS FUSE: `BufferedWriteHandler.OutOfOrderError`, stale file handle, generation/metageneration mismatch, FUSE cache invalidation)
- Sem volume mount (sem cold-start I/O)
- Concorrência via last-write-wins com timestamps
- Queries indexadas (composite indexes)

**Wrappers em `core/db.py`:**
- `ChamadasDB` (collection `chamadas`): `create`, `update_or_create`, `get`, `update`, `delete`, `list_all`, `list_by_status`, `list_stale`, `cleanup_orphans`
- `UserSettingsDB` (collection `user_settings`): `get`, `upsert` (com whitelist de fields)
- `WRITABLE_FIELDS` e `USER_SETTINGS_WRITABLE` (frozen sets) protegem contra key injection

**Índices compostos provisionados em 06/07/2026:**

| Collection | Fields | Order | Usado por |
|---|---|---|---|
| `chamadas` | `user_id, uploaded_at` | ASC, DESC | `GET /api/calls` |
| `chamadas` | `status, uploaded_at` | ASC, DESC | `list_by_status` (admin UI) |
| `chamadas` | `status, uploaded_at` | ASC, ASC | `list_stale` (recover/cleanup/stuck) |

Schema: ver `docs/ARQUITETURA.md`.

## 🛡️ Worker Dedicado + Pub/Sub

**Arquitetura assíncrona com worker desacoplado** (substituiu BackgroundTasks in-process para garantir durabilidade).

**Fluxo Pub/Sub (primário):**
1. test-env salva áudio no GCS
2. test-env publica mensagem no tópico `monitoria-whisper-jobs`
3. Worker (subscription `monitoria-whisper-jobs-worker`) consome
4. Worker baixa do GCS, transcreve, diariza, avalia
5. Worker chama callback OIDC `POST /api/internal/calls/{id}/status` (sucessivo)
6. test-env valida OIDC e atualiza Firestore

**Idempotency (worker):** ANTES de processar, `get_call(call_id).get('status')`:
- Linha ausente → `ORPHAN` (ack + descarta)
- Status `Concluído` ou `Erro:...` → `JÁ PROCESSADO` (ack idempotente)
- Status intermediário → continuar (retomada)

**Idempotency (status):** `STATUS_NORMALIZATION` dict em `api.py:610` normaliza variantes (`Concluido` → `Concluído`) no callback. Defesa em profundidade contra typos.

**Cleanup de órfãos:** `/api/internal/cleanup-orphans` (OIDC) marca chamadas em status inicial >30min como erro. Chamadas em estado inicial há >12min são re-enfileiradas pelo `/api/internal/recover-stale`.

## 🏗️ Build do Frontend (Vite) — Variáveis de Ambiente

- **REGRA CRÍTICA:** A variável `VITE_API_URL` **DEVE** ser injetada via Cloud Build substitutions (`cloudbuild-test.yaml` ou `cloudbuild.yaml`) ANTES do `npm run build`. Nunca deixar `VITE_API_URL` cair no fallback hard-coded.
- **NÃO criar `frontend/.env.local`** — esse arquivo é ignorado pelo git mas seu conteúdo é embutido no bundle JS compilado, podendo causar bugs sutis de URL (vide DIARIO_BORDO 03/07/2026).
- Para desenvolvimento local, copie `frontend/.env.example` → `frontend/.env.local` e ajuste a `VITE_API_URL` para `http://127.0.0.1:8001`.
- **Cache-bust:** o `cloudbuild-test.yaml` cria o arquivo `frontend/.cache-bust` antes do build para forçar o navegador a recarregar o `index.html` (que tem `Cache-Control: no-store` no backend).
- **Rebuild obrigatório** após mudanças em `frontend/src/**` — sem rebuild, o browser continua servindo bundle antigo (ver DIARIO_BORDO 07/07/2026 "Rebuild frontend").

## 🚀 Workflow de Deploy

**Cloud Build** (3 builds independentes):

| Build | Trigger | Resultado |
|---|---|---|
| `cloudbuild-test.yaml` | push em `test` | Build + push imagem + deploy `monitoria-test-env` (Cloud Run) |
| `cloudbuild-worker.yaml` | manual ou `cloudbuild-trigger` | Build + push imagem + deploy `monitoria-whisper-worker` (Cloud Run) |
| `cloudbuild-loadtest*.yaml` | manual | Build + push imagem `monitoria-loadtest` + executar Cloud Run Job |

**Disparar build localmente:**
```bash
$commit_sha = git rev-parse --short HEAD
gcloud builds submit --config=cloudbuild-test.yaml "--substitutions=COMMIT_SHA=$commit_sha" --project=coherence-ominichannel-fs
```

**IMPORTANTE:** deployar test-env e worker **simultaneamente** quando há mudanças em ambos. Deploy sequencial gera janela de inconsistência (worker com código novo falando com test-env com código antigo, ou vice-versa).

**Rotação de URL canônica do módulo** (procedimento):
1. Atualizar URL em `docs/conexao_modulo.{md,json}` (este repo) E em `Coherence_Portal/docs/conexao_modulo.{md,json}` (Portal)
2. Atualizar Firestore `modules/monitoria-chamadas.url` (via Portal admin API ou console)
3. Atualizar `cloudbuild-test.yaml` (`_VITE_API_URL`) e `cloudbuild-worker.yaml` (`WORKER_CALLBACK_URL`)
4. Atualizar fallbacks em `frontend/src/components/{Dashboard,CallInspector,SettingsPanel,QueueManager}.jsx`
5. Atualizar `frontend/.env.example` (template)
6. Atualizar `api.py:TEST_ENV_AUDIENCE` (default) E `cloudbuild-test.yaml` (`--set-env-vars=TEST_ENV_AUDIENCE=...`)
7. Atualizar `docs/HARNESS.md` e `docs/GUARDRAILS.md` (REGRA #0)
8. Commit + push
9. Deploy test-env + worker
10. Smoke test E2E

**ATENÇÃO:** o passo 6 é fácil de esquecer (foi o que causou o bug OIDC audience mismatch em 07/07/2026).

## Histórico de Erros e Resoluções

- **Erro de "Erro no upload" no ambiente de teste (03/07/2026):** O bundle JS em `frontend/dist/` foi compilado com `VITE_API_URL=http://127.0.0.1:8001` (dev local), fazendo o navegador do usuário tentar POST para localhost. Bug adicional: 3 arquivos `.jsx` tinham fallback apontando para a URL de produção. Corrigido rebuildando o frontend com a URL correta e alinhando os fallbacks.

- **Erro de Falhou na Interface:** Ao enviar áudios, a interface do usuário exibia o status Falhou após um longo tempo aguardando. Isso ocorreu porque o processo do Whisper no Cloud Run consome tempo substancial de CPU e a interface assumia um timeout ou um erro prematuro, apesar de o servidor continuar processando e salvar os resultados corretamente no **Firestore** (collection `chamadas`). Foi mitigado ajustando a alocação de threads no Whisper e documentando a necessidade de paciência do usuário devido ao uso de CPU. (Pré-06/07/2026 a persistência era em SQLite GCS FUSE; migrada para Firestore no Plano A++.)

- **Loop infinito "Concluido" sem acento (07/07/2026):** worker gravava `"Concluido"` no Firestore, mas `Dashboard.jsx` comparava com `"Concluído"` (com acento). Resultado: UI nunca reconhecia conclusão (ícone girando, barra visível, polling 2s infinito) e worker reprocessava a cada redelivery. Fix em 3 commits (`25b1ef2`, `ad61496`, `532bae3`): typo corrigido + `STATUS_NORMALIZATION` dict (defesa em profundidade) + 2 endpoints admin para migração retroativa. Ver DIARIO_BORDO.md.

- **403 de ownership (07/07/2026):** `GET /api/calls/{id}` rejeitava user que não era owner do documento no Firestore. Fix em commit `de962e9`: bypass para `is_super_admin=True` com audit log + CallInspector com mensagens de erro específicas (403/404/401).

- **OIDC audience mismatch (07/07/2026):** após commit `07d94de` trocar `WORKER_CALLBACK_URL` para URL com project number, o `TEST_ENV_AUDIENCE` em `api.py:568` ficou desatualizado (continuava com URL hash). Worker gerava token com audience errado, test-env rejeitava com 401. Chamada `230e22e4-...` ficou presa em "Na Fila de Processamento..." por horas. Fix em commit `25db426`: alinhar `TEST_ENV_AUDIENCE` default em `api.py:568` + injetar env var no `cloudbuild-test.yaml`.

- **Bundle JS desatualizado (07/07/2026):** o bundle deployed era pré-CallInspector (200KB) porque o cloudbuild não foi disparado após implementação da feature. Resultado: clicar "Inspecionar" levava a tela vazia. Fix em commit `4256d22 build(frontend): atualizar .cache-bust`. Lição: rebuildar frontend a cada mudança em `frontend/src/**`.

## Visual Identity

All UI changes must strictly follow [UI_GUIDELINES.md](UI_GUIDELINES.md) ensuring the Coherence visual identity guidelines (Clean Light Glassmorphism).
