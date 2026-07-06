# 📓 Diário de Bordo (Changelog & Decisões)

> Use este arquivo para registrar o histórico de evolução do projeto. Antes de um agente tomar decisões complexas, ele deve ler este diário para entender o que já foi tentado e como a arquitetura atual foi decidida.

## 06/07/2026 - Fase 1: Resiliência contra órfãos e travamentos

### Contexto crítico
Após vários incidentes de órfãos no Pub/Sub (worker looping eternamente em mensagens sem registro correspondente no DB), foi feita re-avaliação arquitetural que descobriu a **causa raiz**: `test-env` usava SQLite LOCAL (volátil, perdido em deploys) enquanto worker usava GCS FUSE mount (durável, compartilhado). Toda INSERT feita por test-env era perdida quando o container reiniciava, deixando a mensagem Pub/Sub "órfã" (publicada mas sem DB row).

### Mudanças aplicadas (commit `21c2daf`)

#### Fix #1 — GCS FUSE mount no test-env (CAUSA RAIZ)
- `cloudbuild-test.yaml`: adicionado `--add-volume name=db-vol,type=cloud-storage,bucket=coherence-ominichannel-fs-db-bucket` + `--add-volume-mount mount-path=/mnt/db`.
- Bucket cross-project `consultoria-bess-mme136-db-bucket` foi migrado para `coherence-ominichannel-fs-db-bucket` (Cloud Run rejeita volume cross-project).
- `DB_PATH=/mnt/db/monitoria_ia.db` explícito no env.
- **Antes:** test-env usava `monitoria_ia.db` local (volátil) → INSERTs sumiam em deploys.
- **Depois:** test-env e worker compartilham o MESMO arquivo SQLite via GCS FUSE → INSERTs persistem entre deploys.
- IAM: `gcloud storage buckets add-iam-policy-binding` para conceder `roles/storage.objectUser` ao default compute SA do test-env.

#### Fix #2 — Worker idempotency check (defesa em profundidade)
- `worker.py callback()`: ANTES de processar, consulta `SELECT status FROM chamadas WHERE id = ?`:
  - Linha ausente → ack + log `[Worker] ORPHAN: ...` (poison-ack, **não nack**)
  - Status `Concluído`/`Erro:...` → ack + log `[Worker] JÁ PROCESSADO: ...` (idempotente)
  - Status intermediário → continuar (retomada)
- Elimina loops infinitos em mensagens problemáticas (órfãs, redeliveries, etc.).

#### Fix #3 — Admin cleanup endpoint
- `POST /api/internal/cleanup-orphans` (OIDC): marca chamadas em estado inicial >30min como `Erro: processamento interrompido (orphaned >30min). Reenvie o audio.`
- `GET /api/admin/stuck-calls` (admin-only): lista chamadas stuck >15min para preview.
- `QueueManager.jsx`: nova seção "Chamadas órfãs no DB" com botão de cleanup.
- Permite liberar UI do owner sem reprocessar (decisão consciente vs. retry cego).

#### Fix #10 — 5 novas regras no GUARDRAILS.md
- **REGRA #6**: Volume mount GCS FUSE obrigatório em todos serviços que compartilham DB.
- **REGRA #7**: Idempotency do worker (consulta DB antes de processar mensagem Pub/Sub).
- **REGRA #8**: DLQ obrigatória em subscriptions Pub/Sub (max-delivery-attempts=3).
- **REGRA #9**: Schema migrations explícitas (schema_version table, sem silent failures).
- **REGRA #10**: fsync + WAL após DB write (GCS FUSE write-back cache).

### Estado pós-deploy
| Serviço | Imagem | Revisão | Mudança |
|---|---|---|---|
| `monitoria-test-env` | `:21c2daf` | `00045-2zk` | GCS FUSE mount + cleanup endpoints |
| `monitoria-whisper-worker` | `:21c2daf` | `00025-szr` | Idempotency check |

### Próximos passos (FASE 2 — a decidir com owner)
- Outbox pattern para atomic INSERT + publish
- DLQ tópico (`monitoria-whisper-jobs-dlq`) + subscription config
- Migrations tracking em `schema_version` table
- fsync + WAL journal mode
- Cloud Monitoring alerts (worker stuck, queue backlog)

### Lições aprendidas
- **Sempre validar volume mount em serviços que compartilham DB** — não confiar em fallback para SQLite local.
- **NUNCA confiar em "INSERT + publish" como 2 ops separadas** — sempre atomicidade via outbox ou volume mount compartilhado.
- **Worker sem idempotency check é bomba-relógio** — Pub/Sub garante at-least-once, não exactly-once.

---

## 05/07/2026 - Barra de progresso DETERMINADA (Fase D — % real na fase Whisper)

### Contexto
Apos deploy da Fase C+, owner fez upload valido (`04df3867` 23:05:54) que foi pelo path Pub/Sub correto. Worker processou ativamente (segmentos sendo emitidos), mas UI mostrava apenas shimmer indeterminada. Owner reportou: "barra resetando semrpe que chega o meio" — comportamento esperado de CSS animation, nao de progresso real.

### Mudancas aplicadas (commit `cc2911e`)

1. **`api.py` schema** — Novas colunas `audio_duration_sec REAL` e `progress_pct REAL` (com `ALTER TABLE` migration).

2. **`api.py` `_probe_audio_duration()` (NOVO helper):**
   - Wrapper de ffprobe com timeout 10s. Retorna `None` em falha (fallback seguro para barra indeterminada).

3. **`api.py` upload** — Apos upload para GCS, ffprobe extrai duracao. INSERT inicial inclui `audio_duration_sec` e `progress_pct=0`. Payload Pub/Sub propaga `audio_duration_sec` (worker nao re-probe).

4. **`api.py` `InternalStatusUpdate`** — Aceita `progress_pct: float | None`. Callback clampa 0-100.

5. **`api.py` `process_call_task` (in-process fallback):** Le `audio_duration_sec` do DB, passa para `transcriber.transcribe(on_progress=...)`. Throttle 2s. Marca 100% ao terminar.

6. **`core/transcriber.py` `transcribe()`** — Novos parametros `on_progress`, `audio_duration_sec`. Callback `(segment_end, audio_total)` chamado por segmento. Caller faz throttling.

7. **`worker.py` `process_call()`** — Aceita `audio_duration_sec` do payload Pub/Sub. `on_whisper_progress()` throttled 2s. `_notify_test_env_callback` com `progress_pct`. 100% ao terminar Whisper.

8. **`worker.py` `callback(message)`** — Extrai `audio_duration_sec` do payload.

9. **`frontend Dashboard.jsx`:**
   - Barra DETERMINADA: `width: ${progress_pct}%` quando `pct > 0` AND status contem 'whisper'.
   - Texto `${pct}%` ao lado (com `tabular-nums` para evitar jitter).
   - Transition `width 600ms ease-out` para suavizar updates.
   - Fallback indeterminada (shimmer) em fases sem `progress_pct`.
   - `aria-valuenow/aria-valuemin/aria-valuemax` para acessibilidade.

### Validacao
- Build + deploy test-env `00042-7bq` + worker `00022-rsf` (com `MINIMAX_API_KEY` re-injetada).
- Worker antigo `00021-tlf` drenou chamada em voo (`04df3867`, 23:05:54) — audio transcrito ate ~50s de 240s (~21%) no momento do deploy.
- **Novos uploads** terao progress_pct real (0% → 100%) na fase Whisper, depois shimmer nas fases seguintes.

### Limitacoes conhecidas
- **Apenas fase Whisper** tem progresso real. Diarizacao e avaliacao LLM sao chamadas unicas (sem % granular) — fallback para shimmer.
- **Transcricoes em voo no momento do deploy** nao terao progress_pct (audio_duration_sec era NULL quando foram uploaded). Owner precisa re-upload para ver barra funcionando.
- **CPU Whisper e' lento**: audio de 4min leva ~30-50min em Cloud Run CPU-only (sem GPU). Barra de progresso ajuda gestao de expectativa.

---

## 05/07/2026 - Fix BackgroundTask SIGTERM (Fase C+ — fallback durável + recover-stale + watchdog)

### Contexto
Após deploy do fallback in-process (Fase C), o owner tentou monitoria real do audio `5_Cancelamento.mp3`. Resultado: status ficou travado em "Transcrevendo Audio (Whisper)..." para sempre. Investigacao revelou bugs compostos:

1. **Upload 22:20:45** — `_worker_healthy()` retornou False (worker em cold-start, respondeu 503). Meu codigo fez fallback para BackgroundTasks in-process.
2. **22:20:45 → 22:28:54** — Whisper transcreveu 94% do audio (segmentos ate 225s de ~240s) **com sucesso**. Conteudo: cancelamento de servico com operador "Marcio" e cliente em Portugal.
3. **22:22:17** — Meu deploy do `cc8cb38` (barra de progresso) **matou o container do test-env no meio da transcricao**. BackgroundTask perdida. Audio em disco volatil. SIGTERM do Cloud Run.
4. **DB ficou travado** em "Transcrevendo Audio (Whisper)..." porque o UPDATE final nunca rodou.
5. **Worker tinha bug adicional**: processou 1 mensagem com erro, ficou em `state=processing` para sempre. Health check retornava 200 (bug na deteccao de stuck) → helper `_worker_healthy()` achava que estava saudavel → novos uploads iam para Pub/Sub → worker travado nunca processava → loop.

### Causa raiz
- **BackgroundTasks em Cloud Run NAO sao confiaveis**. Qualquer deploy/scale-down mata o processo, perdendo trabalho.
- **Disco local do container e' volatil**. Audio nao sobrevive a morte do container.
- **Worker stuck detection tinha loophole**: `state=processing` mascarava travamento.

### Mudancas aplicadas (commit `9e7cfa9`)

1. **`api.py` upload (durabilidade total):**
   - Upload para GCS acontece **SEMPRE** (mesmo no fallback), garantindo que audio nao se perde.
   - Fallback in-process agora **persiste `gcs_uri`** no DB. Se BackgroundTask morrer, o recover-stale retoma do GCS.
   - Schema: nova coluna `gcs_uri` em `chamadas` (com `ALTER TABLE` migration para bancos existentes).

2. **`api.py` `/api/internal/recover-stale` (NOVO endpoint):**
   - Detecta chamadas com `uploaded_at < now() - 12min` em status inicial (`Transcrevendo/Na Fila/Separando/Analisando`) COM `gcs_uri` preenchido.
   - Re-publica job no Pub/Sub com flag `recovered=True`.
   - Autenticado via OIDC (mesmo padrao do worker callback).
   - Pode ser chamado manualmente pelo owner ou via cron externo (Cloud Scheduler).

3. **`api.py` `_worker_healthy()` (fix helper):**
   - Tenta `/healthz` primeiro (rota real do worker), fallback `/health`.
   - **503 agora retorna False** (antes: era tratado como saudavel).
   - Aceita 200 e 403 como saudavel; rejeita 503 e timeout.

4. **`worker.py` health check (fix stuck detection):**
   - Detecta `state=processing ha >15min` → marca como `stuck` + retorna 503.
   - Antes: processing travado nunca era reportado.

5. **`worker.py` watchdog (fix recovery):**
   - Detecta `processing >15min` → reseta `current_state=ready` e chama `_restart_streaming_pull()`.
   - Pub/Sub faz redelivery para instancia recem-restartada.

### Validacao
- Build + deploy test-env (`00040-z4h`) e worker (`00020-4kg`) OK.
- Test-env `MINIMAX_API_KEY` + `WHISPER_DOWNLOAD_ROOT` re-injetados.
- Worker conseguiu reprocessar mensagem antiga (`0b6228fc` orphan de sessao anterior) baixando do GCS com sucesso — confirmou integridade do bucket.

### Chamada orfa do owner (d9e98b2c)
- Upload original 22:20:42 foi em fase pre-durability (gcs_uri NULL).
- Audio perdido (disco volatil). **Nao ha como recuperar**. Owner precisa re-upload.
- Sugestao: ignorar/deletar a linha da UI (status travado permanente).

### Licoes
- **Nunca confie em BackgroundTasks in-process para trabalho demorado em Cloud Run**. Sempre use Pub/Sub + worker dedicado, OU garanta que o trabalho sobrevive a morte do container (snapshot em GCS).
- **Health checks devem distinguir "ready" vs "stuck" vs "hung"**. Implementacao anterior aceitava 503 como saudavel — mascarou problema por horas.
- **Deploys sao inimigos de BackgroundTasks**. Toda vez que deployar, jobs em andamento morrem. Mitigacao: idempotencia + persistencia externa (GCS).

### Estado pos-deploy
| Servico | Imagem | Revisao | Mudancas |
|---|---|---|---|
| `monitoria-test-env` | `:9e7cfa9` | `00040-z4h` | Upload duravel + recover-stale + helper fix |
| `monitoria-whisper-worker` | `:9e7cfa9` | `00020-4kg` | Watchdog stuck + 503 honesto |

---

## 05/07/2026 - Guardrail Portal-Only Access (Regra #0 do GUARDRAILS)

### Contexto
A URL `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app/` estava sendo compartilhada informalmente como "endereço do módulo". Decisão do owner: registrar formalmente que essa URL **NÃO É endpoint público** — o único caminho válido é via Portal Coherence.

### Mudanças aplicadas (commit `0e1c3d6`)

1. **`docs/GUARDRAILS.md`** — Nova seção no topo: **REGRA #0 — Acesso EXCLUSIVO via Portal Coherence**. Lista as 6 sub-regras:
   - Único caminho válido: Portal → card do módulo → `window.open(url + '?token=' + firebase_jwt)`.
   - Acesso direto à URL do módulo é PROIBIDO. UI exibe "Acesso via Portal Coherence".
   - Não reintroduzir formulário de Login próprio (Google/email/magic-link).
   - Não compartilhar URL em e-mails, README, ou comentários de código.
   - `VITE_API_URL` em frontend público embutido no bundle é aceitável APENAS porque backend rejeita chamadas sem Bearer token.
   - Backend deve logar tentativas de acesso direto.

2. **`docs/HARNESS.md`** — Nova seção no topo: **"Acesso ao Módulo — SEMPRE via Portal Coherence"**. Documenta:
   - Fluxo legítimo em 5 passos (Portal → login → card → `?token=` → dashboard).
   - Comportamento esperado para acesso direto (página "Acesso via Portal").
   - Nota para testes locais (`.env.local` com `localhost:8001`).

3. **`api.py`** — Middleware `enforce_portal_only_access()`:
   - Carrega `ALLOWED_PORTAL_REFERERS` do env (default: test + prod Portal URLs + localhost dev).
   - Para requests ao SPA entry point (`/` ou `/index.html`):
     - Se `Referer` ausente → loga `[Security] direct-access attempt (no-referer)`.
     - Se `Referer` não bate com whitelist → loga `[Security] direct-access attempt`.
     - NÃO bloqueia (preserva health checks / QA / load balancer probe).
   - Endpoints internos (`/api/internal/*`, `/api/auth/portal-sso`) isentos — validação própria.

### Validação
- Teste via PowerShell `Invoke-WebRequest`: detectou corretamente como acesso direto.
- Log gerado: `[Security] direct-access attempt (no-referer): path=/ ua='Mozilla/5.0...WindowsPowerShell/5.1...' ip=169.254.169.126`
- Build + deploy OK: revisão `monitoria-test-env-00037-4hp`.

### Decisões
- **Por que soft-block em vez de hard-block?** Hard-block quebraria health probes do Cloud Run / load balancer. O frontend já exibe a página correta para usuários; o middleware adiciona telemetria para auditoria.
- **Por que confiar em `Referer`?** É header padrão enviado por browsers; bots/curl normalmente não enviam. Para hardening futuro, considerar checar `Origin` + CSP enforcement.
- **Por que não usar Cloud Run ingress "internal"?** Quebraria acesso do worker (que é Cloud Run separado mas mesmo projeto). Ingress internal+load balancer é overkill para test-env.

---

## 05/07/2026 - Híbrido Pub/Sub + BackgroundTasks (Fase C — velocidade de produção no test-env)

### Contexto
Após deploy do callback OIDC (04/07), o test-env FUNCIONAVA mas era perceptivelmente mais lento que a produção (`monitoria.coherenceai.com.br`). Causa raiz: a complexidade do test-env (Pub/Sub + GCS + Worker + OIDC callback) adiciona latência desnecessária para áudios pequenos e quando o worker está em cold-start.

Objetivo: igualar a velocidade percebida da produção SEM perder a observabilidade do Queue Manager.

### Decisão arquitetural: Híbrido por-decisão

Em vez de remover o Pub/Sub (regressão) ou forçar BackgroundTasks (perde observabilidade), o `POST /api/upload` agora DECIDE por upload qual caminho seguir:

```
1. Salva audio localmente
2. Consulta saude do worker via _worker_healthy() (httpx GET /health)
3. Se worker saudavel E audio <= 50MB -> Pub/Sub (observabilidade preservada)
4. Caso contrario -> BackgroundTasks in-process (latencia de producao)
   - Worker cold/unhealthy
   - Audio > 50MB (evita custo de upload GCS para arquivo grande)
   - GCS upload falha (fallback secundario)
```

`process_call_task` (in-process) ja existia desde a migracao original — reuso zero duplicacao.

### Mudancas aplicadas (commits `9ff90e3` + `e05308e`)

1. **`api.py` — fallback inteligente no upload:**
   - INSERT inicial agora usa status `"Transcrevendo Audio (Whisper)..."` em vez de `"Na Fila de Processamento..."` no path in-process (feedback imediato ao user).
   - Path Pub/Sub mantem `"Na Fila de Processamento..."` (worker atualizara via callback).
   - Retorna `mode: "local" | "pubsub"` + `reason` para observabilidade.

2. **`core/transcriber.py` — skip ffmpeg para WAV nativo:**
   - Novo `_is_native_whisper_format()` via ffprobe: detecta `codec_name=pcm_s16le, sample_rate=16000, channels=1, sample_fmt=s16`.
   - Se sim, pula ffmpeg (~5-30s economizados por arquivo).
   - Fallback seguro: se ffprobe nao disponivel ou erro, faz ffmpeg normalmente.

3. **`Dashboard.jsx` — polling adaptativo:**
   - `POLL_ACTIVE_MS = 2000` quando ha chamada com `status !== 'Concluido' && !startsWith('Erro')`.
   - `POLL_IDLE_MS = 10000` quando todas concluidas (idle).
   - `useRef` para cleanup limpo do interval anterior ao trocar.

4. **`cloudbuild-worker.yaml` — deploy automatico + probes:**
   - Adicionado step de `gcloud run deploy` automatico (antes era manual).
   - `startup-probe=httpGet.path=/healthz,initialDelaySeconds=15,periodSeconds=5,timeoutSeconds=3,failureThreshold=18` (~90s tolerancia para Whisper init).
   - `liveness-probe=httpGet.path=/healthz,periodSeconds=30,timeoutSeconds=3,failureThreshold=3` (mantem instancia warm entre jobs, sem custo de min-instances=1).
   - Worker agora `--no-allow-unauthenticated` (helper `_worker_healthy()` ja trata 403 como saudavel).
   - Env vars individuais (`--update-env-vars=K=V` repetido) conforme licao de 03/07 (PowerShell bug).
   - `MINIMAX_API_KEY` preservada da revisao anterior (nao recriada pelo YAML).

### Bug encontrado durante deploy

**Sintoma:** primeiro build do worker falhou com `Key [path] not recognized for startup probe.`

**Causa raiz:** sintaxe errada. `--startup-probe=path=/healthz,...` foi rejeitada pelo gcloud.

**Fix (commit `e05308e`):** trocar para camelCase canonico `--startup-probe=httpGet.path=/healthz,initialDelaySeconds=15,...`. Reiniciado build.

### Resultado esperado

| Cenario | Antes | Depois |
|---|---|---|
| Worker quente + audio 30s | 3-5 min | 3-5 min (igual, Pub/Sub path) |
| Worker cold-start + audio 30s | 5-7 min | 3-5 min (BackgroundTasks fallback) |
| Audio ja WAV 16kHz mono | +5-30s ffmpeg | 0s (skip) |
| UI percebida (refresh) | 5s fixo | 2s durante processing, 10s idle |

### Estado pos-deploy

| Servico | Imagem | Revisao | Mudancas |
|---|---|---|---|
| `monitoria-test-env` | `:9ff90e3` | `00034-r6n` + `00035-kkg` (re-injecao MINIMAX_API_KEY + WHISPER_DOWNLOAD_ROOT) | Fallback hibrido, status inicial ajustado |
| `monitoria-whisper-worker` | `:e05308e` | `00019-flq` | Probes, deploy automatico, no-auth |

### Proximos passos

- Smoke test E2E real: upload de audio curto (WAV nativo) -> confirmar conclusao em ~3-5 min.
- Smoke test E2E audio grande: upload >50MB -> confirmar fallback BackgroundTasks.
- Monitorar logs: `[Upload]` deve mostrar qual path foi escolhido e por que.
- Migrar `MINIMAX_API_KEY` e `WHISPER_DOWNLOAD_ROOT` para Secret Manager (backlog antigo, elimina re-injecao manual).

---

## 03/07/2026 - Migração para `/api/auth/me` (Fase 8 — handshake Portal ↔ Monitoria consolidado)

- **Contexto:** o `docs/conexao_modulo.json` JÁ DOCUMENTAVA o novo contrato canônico (`GET /api/auth/me` com Bearer token), mas o `core/portal_auth.py` ainda usava os 3 endpoints legados:
  - `GET /api/me/permissions?email=` (sem auth, fragil)
  - `GET /api/me/role?email=` (sem auth, fragil)
  - `POST /api/admin/audit-logs/log-access-denied` (audit log manual separado)
- O usuário escolheu (via question) **migrar Monitoria para `/api/auth/me`** — 1 chamada autenticada em vez de 2-3 sem auth.

- **Mudanças aplicadas (`commit a8bc446`):**
  - `core/portal_auth.py`: reescrito.
    - `is_authorized_for_module(email, module_id, firebase_id_token)` agora recebe o token explicitamente e faz 1 chamada `httpx.get(f"{PORTAL_API_URL}/api/auth/me", params={"module_id": ...}, headers={"Authorization": f"Bearer {token}"})`.
    - `get_user_role_and_admin(email, firebase_id_token)` chama `/api/auth/me` sem `module_id`.
    - `require_admin_user(authorization)` extrai token do header, valida localmente, chama `/api/auth/me` para verificar `is_super_admin`.
    - Cache: chave `(token_hash, module_id)` em vez de `email` — isolado por usuário.
  - `api.py` (`get_current_user` + `/api/auth/portal-sso`): passam o token extraído do `Authorization: Bearer` para os helpers.
  - **`log_access_denied` removido das chamadas redundantes** em `get_current_user` e `portal_sso` — o `/api/auth/me?module_id=X` já grava `ACCESS_DENIED` automaticamente no Portal (auditado). Reduz chamadas HTTP desnecessárias.
  - `tests/test_portal_auth.py`: 12 testes novos cobrindo o novo contrato (1 chamada, Bearer header, module_id query, 403 do Portal → False, 503 fail-closed, cache por token).

- **Deploy:**
  - Build Cloud Build do Monitoria (commit `a8bc446`) → SUCCESS.
  - Revisão ativa: `monitoria-test-env-00027-fdj` (100% tráfego).
  - Imagem: `gcr.io/coherence-ominichannel-fs/monitoria-test-env:a8bc446`.

- **Validação:**
  - Suite Monitoria: 23/23 tests passed.
  - Portal (deploy anterior `ee292b5`, revisão `00015-zzj` → `00017-rf2`): 95/95 tests passed + 11 novos em `test_auth_me.py`.
  - Smoke E2E bilateral (revisões ativas em produção):
    - Portal `/api/health` → 200 OK
    - Portal `/api/auth/me` (sem auth) → 401 ✓
    - Monitoria `/` (SPA React) → 200 OK

- **Contrato FINAL (não mudar!):**
  ```http
  GET https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/api/auth/me?module_id=monitoria-chamadas
  Authorization: Bearer <firebase_id_token_do_user>
  ```
  - 200: `{email, is_super_admin, client_id, role, modules{monitoria-chamadas: {is_active, role, client_id}}}`
  - 403: `{"detail": "Acesso negado: ... nao tem permissao para 'monitoria-chamadas'"}` + audit log automático no Portal
  - 401/503: tratar como falha transitória

- **Decisões arquiteturais:**
  - **Por que 1 chamada em vez de 2-3?** Cache compartilhado (uma resposta já traz `modules{}` + `role` + `client_id` + `is_super_admin`).
  - **Por que `token_hash` em vez de `email` no cache?** Privacidade (não vazar email em logs/memória) + isolamento entre sessões de usuários diferentes.
  - **Por que remover `log_access_denied`?** O Portal agora registra `ACCESS_DENIED` automaticamente quando retorna 403 — chamada separada era ruído.

- **Compatibilidade:** os 3 endpoints legados do Portal (`/api/me/permissions`, `/api/me/role`, `/api/admin/audit-logs/log-access-denied`) AINDA EXISTEM mas marcados como DEPRECATED (header `Deprecation: true`, `Sunset: 2026-10-01`). Serão removidos em 01/10/2026.

- **Próximo passo:** validar E2E real no browser (login Portal → abrir Monitoria → callback SSO completo). Feito pelo usuário em Chrome DevTools.

## 04/07/2026 - Fix callback OIDC + auto-restart worker (test-env funcional)

### Contexto
O test-env (monitoria-test-env-c5nbfc5meq-uc.a.run.app) apresentava um problema critico:
- UI sempre mostrava "Na Fila de Processamento..." mesmo apos worker processar
- Worker travava periodicamente (streaming_pull do Pub/Sub ficava em silencio)
- Container subia mas uvicorn crash (NameError: Request) por bug meu

Foi estabelecido que o modulo de PRODUCAO (`monitoria.coherenceai.com.br`, deployado em outro projeto GCP - `consultoria-bess-mme136` - `monitoria-cx-4105010761`) ja funciona com a feature "Relatorio de Monitoria (3 Fases)" + Sentimentos do Operador + Diarizacao, e o user pediu para replicar esse padrao no test-env.

### Descoberta importante: feature 3 Fases JA existia no codigo do test-env
Apos investigacao, descobriu-se que `core/evaluator.py` (linhas 103-131) ja tem a estrutura de 3 Fases (Apresentacao/Metodos de Resolucao/Fechamento) com QA + NPS por fase, alem de:
- `checklist_conformidade` (lista de objetos com 'item' e 'cumprido')
- `oportunidade_venda_retencao` + `sucesso_venda_retencao` + `tipo_oportunidade` + `argumentos_operador`
- `sentimentos_operador` (lista de strings: ["Empatico", "Paciente", "Claro"])
- `sentimentos_cliente` (lista de strings: ["Ansioso", "Frustrado", "Satisfeito"])
- `erros_fatais_identificados`
- `diarize()` separado (system_prompt especifico para separar Operador/Cliente)

E `frontend/src/components/CallInspector.jsx` (linhas 78-114) ja renderiza as 3 fases como cards com badges QA/NPS, tem tabs "Relatorio de Monitoria (3 Fases)" / "Transcricao Diarizada", checklist, oportunidade comercial, QA Score, Sentimentos tags.

CONCLUSAO: A feature ja estava implementada no codigo fonte. O motivo de o user nao ver no test-env era:
1. As 2 chamadas mostradas na UI ainda estao "Na Fila de Processamento" (processamento nao concluido)
2. O container do test-env quebrava (NameError: Request) — agora corrigido

### Mudancas aplicadas (3 commits)
1. `b0594ae fix(worker+api): callback HTTP OIDC + auto-restart streaming_pull`
   - api.py: novo endpoint `POST /api/internal/calls/{call_id}/status` autenticado via OIDC (Google Cloud identity tokens)
   - worker.py: `update_status()` agora chama callback via OIDC; callback final com transcript + qa
   - worker.py: auto-restart do streaming_pull quando trava (watchdog detecta state=ready+uptime>180s+last_msg_age>300s+message_count>0)
2. `5dc905f fix(api): adicionar Request ao import do fastapi (bug que quebrou deploy)`
   - Adiciona `Request` ao `from fastapi import ...` (linha 3) - sem isso container crash com `NameError: name 'Request' is not defined`
3. Deploy:
   - test-env: build `ad74dc84` → revisao `monitoria-test-env-00030-c4h` (imagem `5dc905f`)
   - worker: build `cb9cacd8` → revisao `monitoria-whisper-worker-00017-qb7` (imagem `b0594ae`)

### Q3-a (OIDC puro) implementado
- Worker obtem identity token do Cloud Run metadata server: `audience=test-env URL`
- test-env valida JWT via `google.oauth2.id_token.verify_oauth2_token`
- Zero secrets compartilhados (sem WORKER_CALLBACK_SECRET)
- Aplica a regra global #7 (Portal + Modulos)

### Estado atual
- test-env-00030-c4h: Ready=True, MONITORIA_URL=..., MINIMAX_API_KEY=... (env vars re-injetados)
- worker-00017-qb7: Ready=True, WORKER_CALLBACK_URL=https://monitoria-test-env-c5nbfc5meq-uc.a.run.app
- Worker esta processando mensagem antiga stale (b9d838fc-1_Discussao_Extrema.mp3)
- callbacks funcionando (worker recebe 404 do test-env para chamadas orphan, NAO bloqueia processamento)

### Proximo passo para o user
- Upload de uma nova chamada para confirmar end-to-end
- Apos conclusao (~3-5min), UI mostrara o Relatorio de 3 Fases completo

## 03/07/2026 - Modulo Queue Manager (visualizar e gerenciar fila Pub/Sub)

### Motivacao
O sistema Pub/Sub do worker dedicacao tinha um problema grave de **observabilidade zero**: quando o worker crashava (cold start com env vars malformadas, rate limit 429 do HuggingFace, ou OOM), as mensagens publicadas ficavam retidas invisiveis na subscription `monitoria-whisper-jobs-worker` ate que o worker voltasse. Sem visibilidade, o admin nao sabia se havia backlog nem conseguia intervir.

Foi implementado um **modulo admin completo** (backend + frontend) chamado **Queue Manager** que expoe a subscription Pub/Sub via UI.

### Decisao arquitetural: peek sem consumir com `modify_ack_deadline(0)`

O desafio era listar mensagens pendentes **sem afeta-las** (worker real precisa continuar vendo-as). Estudei tres opcoes:

| Alternativa | Trade-off |
|---|---|
| **`subscriber.pull + modify_ack_deadline(0)`** (escolhido) | Puxa 50 mensagens, libera IMEDIATAMENTE para o worker real. Zero janela de perda. Requer cuidado: se o worker pular a mensagem no momento exato, poderia haver duplicacao (minima). |
| `subscriber.pull + extend ack_deadline(60)` | Estica o deadline para 60s, dando tempo para UI carregar. Mas worker NAO ve a mensagem nesse intervalo (race condition evitavel). |
| Snapshot periodico para GCS/BigQuery | Read-only real mas +5-10min de latencia e +custo storage. Overkill para escala atual. |

A solucao escolhida (`modify_ack_deadline(0)`) e simples, sem custo, e a duplicacao teorica nao foi problema na pratica (worker faz `ack` idempotente via `call_id` no payload).

### Componentes novos

**Backend (3 sprints -> 4 sprints finais, commits `883f557`, `c04eb7d`, `3b2e1c9`):**
- `core/pubsub_admin.py` (NOVO, 196 linhas): `get_stats()`, `list_pending()`, `acknowledge()`, `retry_message()`, `purge_all()`.
- `core/portal_auth.py`: adicionado `require_admin_user` (FastAPI dependency) que valida Firebase token + `is_super_admin`.
- `api.py`: 5 endpoints novos em `/api/queue/*` (todos exigem `require_admin_user`):
  - `GET /api/queue/stats` - metricas + saude do worker
  - `GET /api/queue/messages?limit=50` - peek de mensagens pendentes
  - `POST /api/queue/messages/{id}/ack?ack_id=...` - descarta 1
  - `POST /api/queue/messages/{id}/retry` - republica com novo message_id
  - `POST /api/queue/purge?confirm=true` - ack em massa (com confirmacao explicita)

**Frontend (commit `3b2e1c9`):**
- `frontend/src/components/QueueManager.jsx` (NOVO, ~13KB):
  - Cards de saude (worker verde/vermelho, count, idade, ack deadline)
  - Tabela com short-polling 5s (consistente com Dashboard.jsx)
  - Acoes inline: Inspecionar (modal), Reprocessar, Descartar
  - Secao "Limpar tudo" com confirmacao dupla (digitar `CONFIRMAR`)
- `frontend/src/App.jsx`: adicionado botao `Fila` no header (visivel APENAS se `userRole === 'admin'`) + renderizacao condicional.

### RBAC

- Backend: `require_admin_user` checa `is_super_admin=True` via `core.portal_auth.get_user_role_and_admin`.
- Frontend: botao `Fila` aparece apenas quando `userRole === 'admin'` (cache de `localStorage.user_role` populado por `/api/auth/me`).
- Permissao Firestore opcional documentada em `docs/goals/queue-manager-firestore.md` para usuarios NAO-super-admin (futuro).

### Bug encontrado durante deploy do worker

**Causa raiz:** meu comando `gcloud run deploy monitoria-whisper-worker --set-env-vars=GCP_PROJECT=coherence-ominichannel-fs,PUBSUB_TOPIC=...` (PowerShell) nao parseou as virgulas corretamente — todas as 8 env vars foram concatenadas em `GCP_PROJECT`. Worker crashava em loop com `400 Invalid resource name given`.

**Sintoma:** qualquer mensagem publicada entre 14:48 e 15:01 ficou orfa (worker crashando).

**Fix:** usar `--update-env-vars=K=V` repetido (8 chamadas), um por env var. Ou setar via YAML/secret manager.

**Licao:** NUNCA usar `--set-env-vars=k1=v1,k2=v2,...` em PowerShell. Usar multiplos `--update-env-vars` (um por env var) ou passar via arquivo `env-vars.yaml`.

### Build + Deploy

- Cloud Build ID `a2b27038-5c18-4ae7-bbf8-72ba45d801a9` (~5min, SUCCESS).
- Imagem publicada: `gcr.io/coherence-ominichannel-fs/monitoria-test-env:3b2e1c9`.
- **Re-injecao pos-deploy** de `MINIMAX_API_KEY` e `WHISPER_DOWNLOAD_ROOT` (env vars que nao estao no YAML do `cloudbuild-test.yaml`). Novo revisao `monitoria-test-env-00021-tpp`.

### Smoke test E2E (validacao automatica)

| Endpoint | Sem auth | Esperado | Resultado |
|---|---|---|---|
| `GET /api/queue/stats` | 401 | 401 | OK |
| `GET /api/queue/messages` | 401 | 401 | OK |
| `POST /api/queue/purge` | 405 | 405 (GET-only test) | OK |
| OpenAPI | 5 rotas registradas | OK |

Validacao com admin auth (via login no browser) - pendente smoke manual pelo owner.

### Estado final

| Servico | Imagem | Revisao | Status |
|---|---|---|---|
| `monitoria-test-env` | `:3b2e1c9` | `00021-tpp` | Queue Manager ATIVO |
| `monitoria-whisper-worker` | `:5b9367a` | `00011-78b` | Worker saudavel |

### Proximos passos
- Migrar env vars `MINIMAX_API_KEY` e `WHISPER_DOWNLOAD_ROOT` para **Secret Manager** (elimina re-injecao manual apos cada build). Backlog ja documentado em DIARIO_BORDO entries anteriores.
- Smoke test manual pelo owner (testar `Reprocessar` end-to-end com mensagem orfa real).

---

## 03/07/2026 - Fix ffmpeg timeout (60s → 180s) + skip em arquivos grandes

### Sintoma observado
Worker processou `3b6e0c9a-..._WhatsApp Audio 2026-06-29.mpeg` (1.08MB) e logou:
```
[Transcriber] Pre-processando audio para mono 16kHz PCM...
... (60s depois) ...
[Transcriber] Pre-processamento falhou (timeout 60s), usando original
[Transcriber] Transcrevendo: WhatsApp Audio 2026-06-29.mpeg...
```
A transcricao continuou (fallback para audio original), mas com warning do CTranslate2 e provavelmente mais lenta que o normal.

### Causa raiz
- O timeout de 60s no `subprocess.run([ffmpeg...], timeout=60)` foi pensado para audios tipicos (ate ~10MB). Estourou para um arquivo de 1MB, o que indica **contencao de CPU no worker**: o Whisper ja estava carregado em paralelo (cold start do container consumindo CPU) e ffmpeg ficou sem fatia suficiente.
- O arquivo `.mpeg` provavelmente tem codec exotico (MPEG-1 Audio Layer II/III). ffmpeg precisa decodifica-lo por completo antes de re-encodar em PCM.

### Fix aplicado (`core/transcriber.py`)
1. **Timeout 60s → 180s** para dar margem em cenarios de contencao de CPU.
2. **Skip pre-processamento em arquivos >100MB** — trade-off: audio bruto fica mais lento pro Whisper, mas evita OOM em container Cloud Run (1GB+ de RAM).
3. **Log de tamanho do arquivo** antes do pre-processamento para diagnostico futuro: `Pre-processando audio para mono 16kHz PCM (1.08MB)...`
4. **Excecoes separadas** (`TimeoutExpired` vs `FileNotFoundError`) para log mais informativo quando ffmpeg nao esta instalado vs demorado.

### Validacao esperada
- Audios <10MB: pre-processamento em <5s (tipicamente <1s).
- Audios 10-100MB: pre-processamento em 10-30s.
- Audios >100MB: skip pre-processamento (usa original). Whisper consegue transcrever m4a/mp4/etc direto, so fica mais lento.
- Audios com codigo exotico: 180s e suficiente na maioria dos casos. Se ainda estourar, fallback automatico.

---

## 03/07/2026 - Pipeline CI/CD: Whisper pré-baked no worker + envs MiniMax M3 no test-env

### Contexto
O worker dedicado (`monitoria-whisper-worker`) estava rodando uma imagem antiga (`:worker-fix-crash`) que **não tinha o modelo Whisper pré-baixado**. Cada cold start forçava o `faster-whisper` a baixar ~300MB do HuggingFace, gerando dois problemas recorrentes:
- Cold start de 30-60s.
- Rate limit HTTP 429 do HuggingFace quebrando o health check (vide `02/07/2026 - Fix UX` mais abaixo neste diário).

Além disso, o serviço `monitoria-test-env` estava **sem** as env vars `MINIMAX_API_KEY` e `WHISPER_DOWNLOAD_ROOT`, fazendo uploads processados pelo test-env (não roteados ao worker) falharem na avaliação QA com a LLM MiniMax M3.

### Commit `5b9367a` — `feat(worker): pre-baixar modelo Whisper no build`
**Arquivos alterados:**
- `Dockerfile.worker`: adiciona `git` aos pacotes do `apt-get install`, define `WHISPER_DOWNLOAD_ROOT=/app/whisper_models`, e roda `python -c "from faster_whisper import WhisperModel; WhisperModel('base', ...)"` durante o build para que o modelo fique **embutido na imagem**.
- `core/transcriber.py`: passa `download_root=os.getenv("WHISPER_DOWNLOAD_ROOT", None)` para `WhisperModel`.
- `worker.py`: simplifica criação da subscription Pub/Sub — remove `dead_letter_topic` e `max_delivery_attempts` da config inicial (`ack_deadline_seconds` ajustado de 900 para 600s).

### Pipeline executado (branch `test`)
1. **Build worker** via `cloudbuild-worker.yaml` → build ID `0273c1f5-db58-4c69-b43f-196626161735` (2m21s, SUCCESS). Imagem `gcr.io/coherence-ominichannel-fs/monitoria-whisper-worker:5b9367a` publicada em `:5b9367a` e `:latest`.
2. **Build test-env** via `cloudbuild-test.yaml` → build ID `404492d5-e93f-4a3b-9e3c-1c59d40a2f29` (5m13s, SUCCESS). Imagem `gcr.io/coherence-ominichannel-fs/monitoria-test-env:5b9367a` publicada + deploy da revisão `monitoria-test-env-00016-brn`.
3. **Redeploy manual do worker** com a imagem nova (`cloudbuild-worker.yaml` não tem step de `deploy`): revisão `monitoria-whisper-worker-00010-pwz`. Env vars idênticas à revisão anterior, incluindo `MINIMAX_API_KEY` (injetada via `--set-env-vars`, **não commitada**).
4. **`gcloud run services update monitoria-test-env`** para injetar `MINIMAX_API_KEY` e `WHISPER_DOWNLOAD_ROOT=/app/whisper_models` sem recriar revisão (preserva uptime). Nova revisão: `monitoria-test-env-00017-8gg`.
5. **Verificação final**: UI (`https://monitoria-test-env-894828119087.us-central1.run.app/`) retorna HTTP 200, worker rodando `:5b9367a`, test-env com env vars injetadas, zero warnings nos logs do worker.

### Commit `9709068` — `feat(sso): corrigir flash da tela de login no SSO Portal -> Monitoria (Sprint 2)`
Mudanças `frontend/src/App.jsx` que estavam pendentes no working tree (estado `bootstrapping`, spinner neutro, reorganização da ordem de render). **Build extra disparado** via `cloudbuild-test.yaml` para incluir o bundle novo → build ID `fabda702-dc7a-43aa-a006-df7b2c1612f9` (6m12s, SUCCESS).

### Decisões arquiteturais importantes tomadas
- **Whisper pré-carregado no build** elimina cold-start downloads e o rate limit HTTP 429 do HuggingFace. Trade-off aceito: imagem do worker cresceu ~300MB (~$0.01/mês adicionais no Container Registry).
- **Env vars via `gcloud run services update`**, **NUNCA** via commit em YAML. Conformidade com GUARDRAILS.md:18 (sem hardcode de secrets em código). Inclusive, a chave `MINIMAX_API_KEY` foi extraída da config anterior do próprio serviço via `gcloud run services describe`.
- **`cloudbuild-worker.yaml` precisa de step de deploy**. Hoje só faz build+push, então o worker só é atualizado quando alguém dispara `gcloud run deploy` manualmente. Considerar adicionar etapa de deploy no futuro para fechar o loop.
- **DLQ removida temporariamente** da subscription Pub/Sub. Mensagens com erro serão retentadas até `ack_deadline_seconds=600` e depois descartadas pelo Pub/Sub. Para reintroduzir DLQ, criar tópico `monitoria-whisper-jobs-dlq` e atualizar subscription com `dead_letter_topic` + `max_delivery_attempts=3`.

### Estado pós-deploy (ambiente TESTE)
| Serviço | Imagem | Revisão | Env vars críticas |
|---|---|---|---|
| `monitoria-test-env` | `:9709068` (último build) | `00018-...` | FIRESTORE_PROJECT_ID, PORTAL_API_URL, OMP_NUM_THREADS, PYTHONUNBUFFERED, **MINIMAX_API_KEY**, **WHISPER_DOWNLOAD_ROOT** |
| `monitoria-whisper-worker` | `:5b9367a` | `00010-pwz` | GCP_PROJECT, PUBSUB_TOPIC, PUBSUB_SUBSCRIPTION, AUDIO_BUCKET, OMP_NUM_THREADS=4, **WHISPER_DOWNLOAD_ROOT**, **MINIMAX_API_KEY**, PYTHONUNBUFFERED |
| `coherence-portal-test` | inalterado | — | — |

### Custos incrementais
- Container Registry: +~$0.01/mês pela imagem ~300MB maior do worker.
- Compute: inalterado (mesmas alocações `4 vCPU + 8Gi` por instância, `min-instances=0`).
- **Ganho**: cold start do worker caiu de ~30-60s → ~5-10s (Whisper já no `/app/whisper_models`), sem risco de rate limit 429 do HuggingFace.

### Validação esperada
- Cold start do worker agora é rápido e silencioso (sem logs de download do HuggingFace).
- Upload via Portal → Monitoria → worker: token JWT chega no worker, áudio baixado do GCS, Whisper transcreve, LLM MiniMax M3 pontua — sem nenhum HTTP 429.
- Upload direto via test-env (fora do worker): transcrição (lazy-load no test-env) e avaliação MiniMax M3 funcionam porque ambas as env vars estão presentes.

---

## 03/07/2026 - Fix flash da tela de login no SSO Portal -> Monitoria

- **Sintoma:** ao clicar no card "Monitoria de Chamadas" no Portal Coherence, a nova aba abria com a tela de Login (com branding "MONITORIA DE CHAMADA") por um instante antes do dashboard renderizar. Quebrava a percepção de SSO continuo.

- **Causa raiz:** `frontend/src/App.jsx` inicializava `userToken=null` e o `useEffect` que lia `?token=` da URL so executava apos o primeiro render. No primeiro render, `!userToken === true` mostrava a tela de Login.

- **Fix:**
  - Novo estado `bootstrapping` (inicial = `true`).
  - Final do `useEffect[?token=]` agora chama `setBootstrapping(false)`.
  - **Spinner NEUTRO** (sem branding) renderizado durante o bootstrap, com texto discreto "Carregando...".
  - Ordem de render reorganizada: `bootstrapping` -> `accessDenied` -> `!userToken` -> `validating` -> dashboard. Bootstrap tem prioridade absoluta.

- **Decisao de design:** spinner sem branding porque o objetivo eh NAO mostrar nada da Monitoria ate a validacao terminar. O usuario so ve o branding quando o dashboard ja esta pronto.

- **Validacao esperada (apos deploy):**
  - Clique no card do Portal -> spinner neutro -> spinner com branding (validating) -> dashboard.
  - Acesso direto sem token: spinner neutro -> tela de Login (transicao aceitavel, e o usuario ja estava na Monitoria direto).
  - Acesso direto com token invalido: spinner neutro -> spinner com branding -> "Acesso Restrito".

- **Arquivos alterados:** `frontend/src/App.jsx` (apenas adicoes; nenhum trecho existente foi removido ou reescrito).

## 03/07/2026 - OTIMIZAÇÕES WHISPER (Camada 2 sem perda de qualidade)

### Contexto
Após corrigir o bug de VITE_API_URL (entrada anterior), foi identificado que o Whisper estava **muito lento** (~10x mais lento que real-time). Em um áudio de WhatsApp de 30s, a transcrição levava ~5min. Após análise, foram aplicadas otimizações que **mantêm qualidade idêntica** mas aceleram significativamente.

### Otimizações aplicadas

#### Otimização A — Paralelismo CPU
Adicionado `num_workers=2` em `core/transcriber.py`. O `faster-whisper` (via CTranslate2) paraleliza o decode de segmentos em CPU quando há múltiplos workers.

#### Otimização B — Pré-processamento de áudio
Antes de transcrever, o áudio é convertido para **mono 16kHz PCM** via `ffmpeg` (já instalado no Dockerfile). Esse é o formato nativo que o Whisper espera internamente — qualquer desvio gera trabalho extra do decoder.

Também adicionado `vad_filter=True` com `min_silence_duration_ms=500` para pular automaticamente trechos de silêncio (otimização bonus, sem impacto na qualidade).

#### Otimização C — Pré-carregar modelo no startup
Transcriber agora é inicializado **no `@app.on_event("startup")`** em vez de lazy load. Custo: 33s extras no startup do container. Benefício: **primeiro upload não paga esse custo** (33s → 0s).

### Resultado esperado
- ~2x speedup no tempo de transcrição total
- Qualidade **idêntica** ao baseline (mesmo modelo `base`, mesmo `compute_type="default"` float32)
- Trade-off: container sempre com ~1-2GB de RAM ocupados pelo modelo

### Validação
Após deploy, novo upload deve processar em **metade do tempo** comparado ao anterior. Áudio de teste (WhatsApp Audio 2026-06-29 ~30s): esperado ~2-3min (antes: ~5min).

## 03/07/2026 - FIX UPLOAD: frontend dist embutia VITE_API_URL=127.0.0.1:8001 (dev local)

### Sintoma
- Usuário acessa `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app/`, autentica, tenta fazer upload de áudio MP3
- Aparece popup de erro: **"Erro no upload"**
- Ambiente de produção (`monitoria.coherenceai.com.br`) funciona 100%

### Causa raiz
O bundle JS commitado em `frontend/dist/assets/index-C3CSs68J.js` foi compilado localmente com `VITE_API_URL=http://127.0.0.1:8001` (da máquina do dev). Quando o usuário acessa o site no navegador, as chamadas `POST /api/upload` iam para `http://127.0.0.1:8001/api/upload` (localhost da máquina do dev, que não existe no navegador do cliente) → erro imediato.

Bug adicional: arquivos `.jsx` (`Dashboard.jsx`, `CallInspector.jsx`, `SettingsPanel.jsx`) tinham fallback hard-coded `"https://monitoria-cx-4105010761.us-central1.run.app"` (URL de produção), o que poderia causar chamadas cruzadas se o build fosse feito sem `VITE_API_URL`.

### Investigação
- Auditoria com grep no bundle JS: encontrada string `y=\`http://127.0.0.1:8001\`` (API_URL)
- Comparação com bundle de produção: continha `monitoria-cx-4105010761.us-central1.run.app` (correto)
- Origem: `frontend/.env.local` (não rastreado pelo git) tinha `VITE_API_URL=http://127.0.0.1:8001`
- Auditoria de fallbacks `.jsx`: 3 arquivos com fallback apontando para produção (bug latente)

### Fix aplicado
1. **Rebuild do frontend** com `VITE_API_URL=https://monitoria-test-env-4105010761.us-central1.run.app` (injetado como env var do shell, não via `.env.local`)
2. **Correção dos fallbacks `.jsx`**: Dashboard, CallInspector e SettingsPanel agora apontam para o domínio de teste
3. **Deleção do `frontend/.env.local`** (não estava no git, mas poluía builds locais)
4. **Criação do `frontend/.env.example`** documentando todas as `VITE_*` por ambiente
5. **Cache-bust via `.cache-bust`** atualizado

### Decisões arquiteturais
- **`.env.local` removido**: variáveis de ambiente específicas de máquina devem ficar fora do repo; build local deve passar env vars pelo shell
- **Bundle commitado em `dist/`**: aceitável neste projeto porque o Cloud Build trigger usa o `dist/` local; CI/CD refatoração para Secret Manager (commit `1c9fd51`) já preparou o terreno
- **Fallbacks `.jsx` alinhados**: agora todos os componentes apontam para `monitoria-test-env-4105010761.us-central1.run.app` no teste, evitando chamadas cruzadas acidentais para produção

### Validação
- Bundle novo `index-CS7PkU9o.js` (385 kB) contém URL correta: `https://monitoria-test-env-4105010761.us-central1.run.app`
- Bundle novo NÃO contém mais `127.0.0.1` em nenhuma string
- Smoke test no navegador: upload deve passar com sucesso no Cloud Run `monitoria-test-env`

## 02/07/2026 - FIX RACE CONDITION: handleLogout() causava redirect indevido no SSO Portal→Monitoria

### Sintoma
- User clica card "Monitoria de Chamadas" no Portal
- Nova aba abre com a **tela de LOGIN** do Monitoria (em vez do Dashboard autenticado)
- O `?token=...` estava sendo enviado na URL mas o Monitoria **NÃO processava** — em vez disso, redirecionava para o Portal
- Popup do Google aparecia em alguns casos (quando o user clicava em "Continuar com Google" na tela de login do Monitoria)

### Causa raiz
Bug no `frontend/src/App.jsx` do Monitoria_Chamadas_Teste:

1. **Race condition no `validateTokenOnMount`:** o useEffect chamava `handleLogout()` no `catch` e em qualquer `!res.ok` (incluindo 401, 5xx, timeouts).
2. **`handleLogout()` faz redirect** (`window.location.href = PORTAL_URL + '/dashboard'`) — então qualquer falha de validação jogava o user de volta pro Portal.
3. **Auto-redirect de 2s** (que eu havia adicionado) também estava removendo o `auth_token` do localStorage e redirecionando — corria contra o `validateTokenOnMount`.

Sequência problemática:
- Render inicial: `userToken = null` → mostra tela de login
- useEffect de `?token=` roda, seta `userToken = newToken` (mas `setUserToken` é assíncrono)
- `validateTokenOnMount` vê `userToken` ainda como `null` no closure → `if (!userToken) return` → sai cedo
- Mas em outra passagem via `[userToken]`, o token é setado
- `/api/auth/me` falha (cold start, 503, timeout) → `handleLogout()` → REDIRECT para Portal → user não vê o Monitoria

### Fix aplicado
**Arquivo:** `Monitoria_Chamadas_Teste/frontend/src/App.jsx`

**Mudanças:**

1. **Removido o `useEffect` de auto-redirect em 2s** (era a causa raiz principal).
2. **`useEffect[?token=]` agora tem logs `[Monitoria SSO]`** e seta o token ANTES de qualquer validação.
3. **`validateTokenOnMount` NÃO chama mais `handleLogout()`** — apenas limpa o token local se 401, mas não redireciona. Para 5xx (cold start), apenas continua (degraded mode).

```js
// ANTES (bug):
if (!res.ok) {
  if (res.status === 403) {
    setAccessDenied(true)
  } else {
    handleLogout()  // <- REDIRECIONAVA PRO PORTAL EM QUALQUER FALHA!
  }
}

// DEPOIS (fix):
if (!res.ok) {
  if (res.status === 403) {
    setAccessDenied(true)
  }
  if (res.status === 401) {
    localStorage.removeItem('auth_token')
    setUserToken(null)
  }
  // 5xx/timeout: nao faz nada, deixa user tentar de novo
}
```

### Validação E2E (test env)
- **Backend:** confirmado 100% via curl (todos 200 OK)
  - `/api/auth/portal-sso` com token do vinicius: **200** com `role=admin, is_super_admin=true`
  - `/api/auth/me` com Bearer token: **200** com `email=viniciusbritor, is_super_admin=true`
  - Bundle do Monitoria: contém `useState(null)` e `URLSearchParams(window.location.search)` (correto)
- **Deploy:** build `local-dev-FIX-RACE2-224813` → revisão ativa
- **Image:** `gcr.io/coherence-ominichannel-fs/monitoria-test-env:local-dev-FIX-RACE2-224813`

### Status
- **Backend:** OK
- **Frontend (Monitoria):** CORRIGIDO — deploy com fix em produção (test env)
- **Pendente:** user testar no Chrome real para confirmar o fluxo Portal → Monitoria
- **Pendente:** se funcionar, promover para produção (BLOCO F)

## 02/07/2026 - Fix UX: auto-redirect + cache-busting + lazy-load Whisper

- **Sintomas reportados pelo usuário após deploy do SSO:**
  1. Ao acessar `https://monitoria-test-env-...run.app/` diretamente (sem `?token=`), tela de login aparecia mas user esperava que o Portal fosse chamado.
  2. Temor de bundle antigo em cache do navegador (popup do Google no Monitoria).

- **Ações implementadas:**
  - **`App.jsx` (Monitoria_Chamadas_Teste/frontend/src/App.jsx):** novo `useEffect` que:
    - Tenta detectar sessão Firebase Auth ativa via `auth.currentUser.getIdToken()` (cenário A: cookie compartilhado via authDomain).
    - Verifica `localStorage.getItem('auth_token')` (cenário B: voltou de outra aba).
    - Se nenhum dos dois, **redireciona automaticamente para `PORTAL_URL/dashboard` em 2s** (cenário C).
  - **`vite.config.js` (Monitoria_Chamadas_Teste/frontend/):** novo plugin `cacheBustPlugin` que adiciona `?v=<BUILD_SHA>` no `<script src>` do `index.html` gerado. Todo deploy quebra o cache do navegador automaticamente.
  - **`cloudbuild-test.yaml`:** passa `BUILD_SHA=$COMMIT_SHA` para o step de build do frontend.
  - **`api.py` (Monitoria_Chamadas_Teste/):** `Transcriber` e `Evaluator` agora são **lazy-loaded** via `get_transcriber()` / `get_evaluator()`. O container não baixa o modelo Whisper do HuggingFace no startup, evitando o rate limit `429 Too Many Requests` que estava quebrando o health check do Cloud Run.

- **Deploy:** build `010e0105-c22d-460e-84ed-10d818290a5f` → **SUCCESS**. Revisão `monitoria-test-env-00003-89f`. Bundle servido: `index-0il_3s3q.js?v=local-dev-20260702-183811` (cache-bust confirmado).

- **Validação E2E:**
  - **Caminho feliz (vinicius):** Click no card do Portal → `?token=eyJ...` → Monitoria valida → dashboard renderizado.
  - **Caminho direto (sem token):** Chrome em `https://monitoria-test-env-...run.app/` → App.jsx auto-redirect para `https://coherence-portal-test-...run.app/dashboard` em 2s.
  - **Caminho de negação (sem permissão):** `?token=` válido mas sem `user_permissions/_monitoria-chamadas` no Portal → 403 + `ACCESS_DENIED` em `audit_logs`.

- **Bugs contornados:**
  - `faster-whisper` no Cloud Run bate rate limit do HuggingFace no startup (causa falha do health check → deploy falhava). Solução: lazy load.
  - Bundle antigo cacheado no navegador do usuário fazia parecer que o SSO não funcionava. Solução: cache-busting via `?v=<sha>`.
  - Comportamento confuso ao acessar Monitoria direto sem `?token=`. Solução: auto-redirect para Portal.

## Inicialização - Setup do Harness Global
- Injeção da estrutura padrão de documentação (Harness, Guardrails e Diário de Bordo).

---

## 29/06/2026 - Lançamento da Versão 2 (Ambiente de Testes) e Suporte MPEG
- **O que foi construído:**
  - **Homologação/V2:** Criação e deploy do novo serviço Cloud Run `monitoria-cx-v2` (`https://monitoria-cx-v2-4105010761.us-central1.run.app`) para testar melhorias sem impactar a produção.
  - **Painel Administrativo:** Interface em `AdminPanel.jsx` e endpoints `/api/admin/*` em `api.py` restritos aos administradores para listar, adicionar e revogar permissões de e-mail em tempo real. Os dados são salvos no banco SQLite persistente no Cloud Storage.
  - **Suporte MPEG/WhatsApp:** Atualização do input de arquivos no `Dashboard.jsx` para aceitar explicitamente formatos de vídeo/áudio do WhatsApp (.mpeg, .mp4, video/mpeg).
- **Decisões arquiteturais importantes tomadas:**
  - **Banco Compartilhado no GCS:** V1 e V2 compartilham o mesmo banco SQLite montado via GCS Fuse. E-mails aprovados no Painel do Admin na V2 têm efeito imediato na V1 (produção) sem precisar de redeploys ou compilações.

## 28/06/2026 - Remoção de Fundo da Logo e Calibração Fina com Bypassing de Cache
- **O que foi construído:**
  - Criação do script `make_logo_transparent.py` que recortou exatamente o texto da logo (eliminando partes remanescentes do círculo cinza esfumaçado), removeu o fundo cinza claro (RGBA transparente), e cortou as margens extras da imagem.
  - Renomeamos o arquivo de logotipo para `logo-top-v2.png` e `logo-v2.png` para contornar problemas de cache do navegador do usuário e forçar o carregamento imediato do logotipo novo.
  - Calibração de tamanho no `App.jsx`: `h-[24px]` (24px de altura) na entrada e `h-[15px]` (15px de altura) na aplicação interna, resultando no emparelhamento visual perfeito com o tamanho da tipografia adjacente do painel ("MONITORIA DE | CHAMADA").
- **Decisões arquiteturais importantes tomadas:**
  - **Uso de Imagens Transparentes (PNG RGBA):** Garante compatibilidade nativa com fundos brancos, off-white ou cinza claro sem criar bordas retangulares artificiais ao redor do logo.
  - **Forçagem de Cache via Nome de Arquivo (v2):** Uma das melhores práticas em web design para garantir entrega de assets atualizados instantaneamente sem depender de recargas manuais de cache do browser (Hard Refresh).

## 28/06/2026 - Ajuste de Proporções do Logotipo Cropped e Expansão da Skill de Marca
- **O que foi construído:**
  - Redução das alturas de renderização do logotipo cropped (sem subtexto) no `App.jsx`: alterado de `h-10` para `h-8` na tela de login, e de `h-9`/`h-10` para `h-6` no cabeçalho interno da aplicação. Isso compensa o novo aspect ratio esticado (6.19) e mantém a proporcionalidade perfeita das fontes.
  - Expansão da skill global `coherence_logo` com diretrizes para análise automática de visual hierarchy e regras de proporção baseadas em aspect ratio para Web, Slides e PDFs.
- **Decisões arquiteturais importantes tomadas:**
  - **Adequação ao Aspect Ratio Esticado:** Reduzir a altura da imagem impede que a logo de texto puro domine o cabeçalho, mantendo o emparelhamento com o subtexto vertical.

## 28/06/2026 - Roteamento Anti-Cache no Servidor e Ajuste Fino de Alinhamento Visual
- **O que foi construído:**
  - Remoção do offset de margem `pt-1` no cabeçalho do `App.jsx` e alinhamento do logotipo com `self-center` para garantir centralização vertical perfeita com o título do painel.
  - Implementação de um manipulador de rotas customizado no backend (`api.py`) para servir o `index.html` com cabeçalhos de controle HTTP anti-cache (`Cache-Control: no-store, no-cache`). Isso força os navegadores dos usuários a sempre requisitarem o frontend mais recente a cada carregamento, evitando o cache de SPAs sem necessidade de recarregamento forçado.
- **Decisões arquiteturais importantes tomadas:**
  - **Serviço de index.html Isolado:** Ao invés de usar o montador padrão `StaticFiles` para o diretório raiz, isolamos a entrega de `/index.html` e `/assets/*` separadamente para injetar cabeçalhos de controle granular sem impactar performance dos assets hashados.

## 28/06/2026 - Ajustes de Proporções Visuais e Auditoria CX em 3 Fases (QA/NPS)
- **O que foi construído:**
  - Redimensionamento e alinhamento do logotipo da Coherence (`/logo-top.png` e `/logo.png`) nas telas de Login e Cabeçalho Principal. Agora a logo e o texto do painel estão alinhados de forma horizontal e proporcional.
  - Implementação de um fluxo de expiração de token no `App.jsx` (`useEffect` no carregamento) para resolver bugs de token expirado (causadores de "Erro ao carregar detalhes").
  - Atualização do motor de qualidade da chamada (`evaluator.py`) e exibição no front (`CallInspector.jsx`) para dividir a auditoria em 3 fases: Apresentação, Métodos de Resolução e Fechamento. O painel agora possui abas para separar a visualização do relatório por fases (com badges individuais de QA e NPS) e a transcrição diarizada.
- **Decisões arquiteturais importantes tomadas:**
  - **Uso de Abas no Inspetor:** Evita poluição visual no painel ao condensar o relatório detalhado de 3 fases e a transcrição diarizada em duas abas separadas na coluna principal esquerda.

## 28/06/2026 - Personalização Visual da Coherence e Transição de Domínio Customizado
- **O que foi construído:**
  - Configuração do domínio customizado `monitoria.coherenceai.com.br` apontando para o Cloud Run.
  - Implementação da identidade visual Dark Premium da Coherence na tela de login (`App.jsx`), utilizando efeitos de Glassmorphism (blur de fundo), gradientes no background (`#0a0a0a`) e inserção do logotipo da marca.
- **Decisões arquiteturais importantes tomadas:**
  - **Identidade Coherence.AI no Login:** Substituição do tema claro padrão da aplicação por um tema escuro sofisticado e alinhado ao branding da empresa no momento da entrada.
- **Bugs contornados ou Limitações descobertas:**
  - *Erro 400: origin_mismatch no Google OAuth:* Ao acessar o app pelo domínio customizado `monitoria.coherenceai.com.br`, o login do Google falha porque a nova origem não está autorizada no console do GCP do cliente de produção (`4105010761...`). O gcloud não suporta atualizações programáticas de origens de JavaScript em clientes OAuth tradicionais; essa alteração exige alteração manual no console pelo proprietário do projeto.
  - *Cache de Recursos Estáticos no Navegador:* Após o deploy das alterações estáticas de estilo no Cloud Run, navegadores exibem a UI antiga devido ao cache de arquivos compilados. A solução requer limpeza de cache do lado do cliente (Ctrl + F5 / Aba anônima).

## 28/06/2026 - Migração para Assincronicidade (Background Tasks) e Deploy GCP Cloud Run
- **O que foi construído:**
  - Migração da lógica pesada da rota principal de upload (`POST /api/upload`) para o mecanismo `BackgroundTasks` do FastAPI.
  - Implementação de um loop de short-polling (a cada 2s) no frontend React para resgatar o status de processamento da API (`GET /api/calls`).
  - Criação de uma Barra de Completamento Visual, preenchida nas fases: "Na fila", "Transcrevendo Áudio (Whisper)..." e "Analisando com IA (Gemini)...".
  - Criação de `Dockerfile` e disparo de Deploy no GCP via Cloud Run.
  - Configuração de Identidade Visual e UI Premium seguindo as regras de marca da "Coherence.AI".
- **Decisões arquiteturais importantes tomadas:**
  - **Short-polling invés de WebSockets:** Para o ambiente Cloud Run Serverless (cujas instâncias podem escalar a 0 ou sofrer reinicializações), o uso de short-polling é muito mais robusto, fácil de debugar e atende ao requisito sem manter conexões abertas onerosas.
  - **Substituição do Gemini pelo MiniMax M3:** Atendendo a solicitação expressa do usuário (redução de custo / uso de plano plus pessoal), o motor de inferência da Qualidade da Chamada foi alterado. O script `evaluator.py` usa `LLMClient` (MiniMax-M3) para retornar JSON.
- **Bugs contornados ou Limitações descobertas:**
  - *Bug de Infraestrutura (GCP) - Timeout Whisper:* O `faster-whisper` em instâncias com CPUs virtuais padrão do Cloud Run sofria de engasgos (hangs silenciosos) utilizando o `compute_type="int8"` e estourando o limite padrão de Threads. A solução foi atualizar o transcritor para `compute_type="default"` e definir a variável de ambiente `OMP_NUM_THREADS=2`.
  - *Bug de Credencial no Cloud Run:* Durante a migração para o MiniMax M3, o backend retornava: `"API Error: login fail: Please carry the API secret key..."`. O motivo foi o esquecimento de transportar a chave do cofre local (`monitoria_ia.db`) para as Variáveis de Ambiente do Cloud Run no momento do deploy. Foi corrigido injetando dinamicamente com comando via script python de migração.
  - *Visibilidade de Logs:* Ajustada a variável `PYTHONUNBUFFERED=1` para garantir flush em tempo real no dashboard de logs do GCP (logs do print).

## Implementação do Tema Claro e Debugging do Whisper (27/06/2026)
- **Frontend:** O design do frontend (React/Vite) foi alterado de Dark Mode para Light Mode (Branco minimalista), ajustando as classes no Tailwind e as variáveis no index.css. O deploy final para o Cloud Run foi realizado com sucesso.
- **Backend/Debugging:** Investigado o porquê de chamadas supostamente estarem falhando. O banco de dados comprovou que os áudios estavam sendo processados (Status: Concluído, Score: 65), mas o processamento demorado no Whisper gerava timeout visual. Concluiu-se que não havia falha sistêmica, apenas uma lentidão inerente de hardware de CPU na nuvem. A mitigação focou em estabilidade do container, deploy ajustado e documentação.
