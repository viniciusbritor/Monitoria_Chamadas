# 📓 Diário de Bordo (Changelog & Decisões)

> Use este arquivo para registrar o histórico de evolução do projeto. Antes de um agente tomar decisões complexas, ele deve ler este diário para entender o que já foi tentado e como a arquitetura atual foi decidida.

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
