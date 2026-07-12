# Guardrails e Regras Inegociáveis

> Ultima atualizacao: 12/07/2026 (Secret Manager + dominio producao + LLM keys)
> Este arquivo dita as regras DURAS que todos os agentes IA devem obedecer neste projeto.

## Regra #0 (mais alta prioridade) - Acesso EXCLUSIVO via Portal Coherence

**A URL `https://monitoria-test-env-894828119087.us-central1.run.app/` NAO e' publica.**

1. **Unico caminho valido**: usuario loga no **Portal Coherence** (producao: `https://portal-omnichannel.coherenceai.com.br/` ou test: `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/`), clica no card "Monitoria de Chamadas", e o Portal abre o modulo via `window.open(module.url + '?token=' + firebase_id_token, '_blank')`.
2. **Acesso direto** (colar URL no navegador, bookmark, link direto) e' PROIBIDO. Mostra a tela "Acesso via Portal Coherence" com botao de redirect.
3. **Nao reintroduzir** formulario de login proprio (Google, email/senha, magic-link).
4. **Nao compartilhar** a URL do modulo como ponto de entrada.
5. **Nao expor** a URL em e-mails, README, comentarios de codigo, nem `VITE_API_URL` em frontend publico sem o token via `?token=`.
6. **Backend enforcement**: requests ao `/` sem `Referer` do Portal sao logadas como `[Security] direct-access attempt`.

**Por que:** Portal e' source of truth de identidade (Firebase SSO) e permissoes. Modulo delega 100% da autenticacao ao Portal.

## Regra #1 - Objetivo Principal (Negocio)

O modulo existe para executar 5 objetivos em sequencia:

| # | Objetivo | Onde |
|---|---|---|
| 1 | Upload de chamada (audio file) | frontend + api.py |
| 2 | Transcricao audio -> texto | worker.py + core/transcriber.py |
| 3 | Separar audio atendente e cliente (diarizacao) | worker.py + core/evaluator.py |
| 4 | Avaliar nota QA do atendente + nota NPS do cliente | worker.py + core/evaluator.py |
| 5 | Categorizar motivos principais da chamada | worker.py + core/evaluator.py |

Qualquer codigo novo deve contribuir para um desses 5 objetivos. Codigo fora desse escopo deve ser justificado explicitamente.

## Regra #2 - Firestore como Source of Truth (DB unico)

1. **Firestore** e' a unica fonte de verdade para dados de chamada, settings de user, e audit logs.
2. **NUNCA** usar SQLite, GCS FUSE mount, ou arquivos locais como persistencia.
3. **NUNCA** criar `--add-volume` no `cloudbuild-*.yaml` para SQLite/GCS FUSE (foi removido no Plano A++).
4. **Todos os writes** devem passar pelo wrapper `core/db.py` (que aplica `WRITABLE_FIELDS` whitelist como defesa contra key injection).
5. **Migracao de dados** (Plano A++, 06/07/2026): SQLite/GCS FUSE -> Firestore. Qualquer referencia a SQLite legado deve ser removida em novos PRs.

**Por que:** 4 bugs historicos do SQLite GCS FUSE (OutOfOrderError, stale handle, file clobbered, FUSE cache invalidation) causaram loops infinitos. Firestore e' gerenciado e nao tem esses problemas.

## Regra #3 - OIDC Audience Alinhado

3 lugares DEVEM estar alinhados com a MESMA URL:

| Local | Variavel |
|---|---|
| `cloudbuild-worker.yaml:55` | `WORKER_CALLBACK_URL` |
| `api.py:568` (default) | `TEST_ENV_AUDIENCE` |
| `cloudbuild-test.yaml:60` (env var) | `TEST_ENV_AUDIENCE` |

Se qualquer um dos 3 tiver URL diferente, o worker gera tokens com audience errado, test-env rejeita com 401, e a chamada fica presa em "Na Fila de Processamento...".

**Procedimento de rotacao de URL:** ver `docs/HARNESS.md` secao "Rotacao de URL canonica do modulo" (atualizar 5+ lugares, nao esquecer `api.py:TEST_ENV_AUDIENCE`).

## Regra #4 - Status Normalization

O worker pode gravar `Concluido` (sem acento) por typo. O callback OIDC no `api.py` normaliza para `Concluido` (com acento) via `STATUS_NORMALIZATION` dict (api.py:610). **NUNCA** remover essa normalizacao.

Variaveis aceitas: `Concluido`, `concluido`, `concluido`, `CONCLUIDO`, `CONCLUIDO`. Todas normalizadas para `Concluido`.

**Por que:** UI do Dashboard.jsx compara `call.status === 'Concluido'`. Sem normalizacao, UI nunca reconhece conclusao, polling 2s infinito, worker reprocessa a cada redelivery.

## Regra #5 - Worker Idempotency Check

1. Worker DEVE consultar `get_call(call_id)` (Firestore) ANTES de processar qualquer mensagem Pub/Sub.
2. Comportamento:
   - Linha ausente -> ack + log `[Worker] ORPHAN: ...` (poison-ack, NAO nack)
   - Status `Concluido` ou `Erro:...` -> ack + log idempotente
   - Status intermediario -> continuar (retomada)
 3. **NUNCA** nack uma mensagem sem antes validar que a falha e' transient. Nack causa redelivery infinito em poison messages.
 4. **Timeout em process_call**: 30 minutos (`PROCESSING_TIMEOUT_SEC=1800`). Se exceder, marca como erro e faz nack para redelivery em outra instancia.

## Regra #6 - Sem Animacoes no Frontend (evita tela em branco)

O `<div key={...}>` em `App.jsx` causa remount a cada `navigateTo`. Animoes CSS (`animation: fadeInUp 500ms` com `opacity: 0 -> 1`) deixam o conteudo invisivel por 500ms, fazendo parecer "tela em branco".

**PROIBIDO** adicionar animacoes Tailwind (`animate-*`, `transition-content`, `transition-page`) no frontend. O conteudo deve aparecer IMEDIATAMENTE.

Classes Tailwind permitidas: `transition-all`, `transition-colors`, `transition-opacity` (apenas em hover/click states, nao em page transitions).

## Regra #7 - Encoding UTF-8 (sem mojibake)

1. **NUNCA** salvar arquivos `.jsx`/`.js`/`.json`/`.md` com encoding latin1 ou windows-1252.
2. **SEMPRE** usar UTF-8 (com BOM opcional).
3. **NUNCA** fazer double-encoding (latin1 -> UTF-8) de strings acentuadas.
4. O `.gitattributes` ja tem `text eol=lf` para todos os arquivos de texto, evitando que git converta LF <-> CRLF no cloudbuild.

**Por que:** PowerShell exibe mal bytes UTF-8 (mostra `Ã­` em vez de `í`). Use Python para verificar encoding de bundles deployed (`grep -c C3 83 C2 AD` no bundle JS).

## Regra #8 - Restricoes Severas (o que NUNCA fazer)

1. **Nunca** bloquear threads principais com processamento sincrono. Sempre usar Pub/Sub + worker, ou BackgroundTasks.
2. **Nunca** hardcodear cores na UI. Sempre usar `tailwindcss` e `docs/UI_GUIDELINES.md`.
3. **Nunca** fazer deploy no GCP Cloud sem verificar se `requirements.txt` tem `fastapi`, `uvicorn`, `python-multipart`.
4. **Nunca** implementar direto em producao. Primeiro em `Monitoria_Chamadas` (este projeto), depois promover.
5. **Nunca** reintroduzir tela de Login no modulo (ver Regra #0).
6. **Nunca** criar `frontend/.env.local` (conteudo e' embutido no bundle).
7. **Nunca** reintroduzir SQLite como persistencia (ver Regra #2).

## Regra #9 - Regras de Ouro (o que SEMPRE fazer)

1. **Feedback na UI obrigatorio**: qualquer operacao async DEVE fornecer feedback visual (status, progress bars).
2. **Em Cloud Run**: `OMP_NUM_THREADS=2` (test-env) e `PYTHONUNBUFFERED=1` sao mandatorios. Worker usa `OMP_NUM_THREADS=6` para acelerar Whisper.
3. **Injecao de segredos no deploy**: ao trocar engine de IA, NAO esquecer de injetar a chave de API via `gcloud run services update`.
4. **Sanitizacao de arquivos**: todo upload DEVE ter pasta de destino criada antes.

## Regra #10 - Seguranca / Privacidade

1. Nenhuma chave de API, credencial ou token em hardcode.
2. Todo segredo passa pelo `secrets_manager` (cofre local SQLite), NAO commitado.
3. Auditoria: requests ao `/` sem `Referer` do Portal sao logadas como `[Security] direct-access attempt`.

## Regra #11 - Limites de Upload (worker 4 GiB)

**Aplicavel desde 08/07/2026 (Plano Ultra-Economico)**.

1. **Audio individual**: max **20MB** por arquivo (validacao client-side em Dashboard.jsx + server-side em api.py).
2. **Batch upload**: max **50 arquivos** por request via `POST /api/upload-batch`.
3. Justificativa: worker reduzido de 8 GiB para 4 GiB (custo). 20MB cobre audio de ~10min em WAV 16kHz mono (cenario tipico de monitoria). Audio maior deve ser dividido em chunks ou convertido para MP3.
4. **Risco de OOM**: arquivo > 20MB pode crashar o worker por falta de memoria. Validacao dupla (frontend + backend) e obrigatoria.

## Regra #12 — Cold Start (worker min-instances)

**Aplicavel desde 08/07/2026. Atualizado 12/07/2026 (test min-instances=0, prod min-instances=1).**

1. **Producao**: `min-instances=1` no worker `monitoria-worker` garante sem cold start (1 container sempre ativo). Custo ~$50/mes.
2. **Test**: `min-instances=0` no worker `monitoria-whisper-worker` — sob demanda, escala a zero quando ocioso (custo $0 idle). Ativado via `git push origin test` ou `scripts/dev.ps1 up`.
3. Cold start de ~15s ocorre APENAS em caso de crash/reinicio forcado do container.
4. **Ver Regra #16** para detalhes arquiteturais sobre PULL vs PUSH.
5. Solucao definitiva: migracao para PUSH subscription (elimina necessidade de min-instances).

## Regra #13 - Integracao com Portal Coherence (08/07/2026)

**Aplicavel a partir de 08/07/2026 (Padrao de Integracao).**

1. **Cloud Build step final** (em `cloudbuild-test.yaml`) DEVE chamar API admin do Portal apos deploy bem-sucedido:
   ```
   POST https://coherence-portal-test-.../api/admin/modules/monitoria-chamadas
   ```
   Body: `{name, url, revision, description, icon}`. Auth: Bearer Firebase ID Token (super-admin).
2. **Pre-requisito**: Cloud Build SA `894828119087-compute@developer.gserviceaccount.com` deve estar em `SUPER_ADMIN_EMAILS` do Portal.
3. **Step eh best-effort**: se falhar (rede, auth), Cloud Build NAO falha o deploy. Portal fica desatualizado ate proximo deploy ou admin manual.
4. **Atualizar `docs/MODULE_INTEGRATION.md`** sempre que contrato ou URL mudar (pre-commit).
5. **PROIBIDO clonar repo cross-repo em build** (ex: Portal clonando este repo). Git e' apenas versionamento.
6. **Use a skill `coherence_module_integration`** sempre que criar/alterar integracao com Portal.

Padrao canonico em `OmniChannel/docs/MODULE_INTEGRATION.md`.

## Ver tambem

- [HARNESS.md](HARNESS.md) - Objetivo principal + stack
- [ARQUITETURA.md](ARQUITETURA.md) - Detalhes tecnicos
- [MODULE_INTEGRATION.md](MODULE_INTEGRATION.md) - Como este modulo se integra ao Portal
- [PRIVACIDADE.md](PRIVACIDADE.md) - Politica de Privacidade LGPD

## 🔒 Regra #14 — LGPD Compliance (Harness Global) (08/07/2026)

**Aplicavel a partir de 08/07/2026.**

1. **PII Masker obrigatorio**: `core/masker.py` DEVE ser aplicado em qualquer transcricao antes de enviar para LLM (DeepSeek, NVIDIA, MiniMax). Patterns: CPF, RG, telefone, email, cartao (LGPD Art. 12).

2. **PROIBIDO** salvar transcricao com PII em texto plano no Firestore. Aplicar `mask_pii()` antes de persistir (ja feito em `worker.py`).

3. **PROIBIDO** `print(transcript_completo)` em logs. Logs devem conter apenas metadados (call_id, user_id, status) - nunca transcricao.

4. **Audio deletado do GCS imediatamente apos 'Concluido'** (worker cleanup). NAO espera 90 dias de lifecycle - ja processou e salvou resultado no Firestore.

5. **Retention obrigatoria** (LGPD Art. 16):
   - Ver `OmniChannel/docs/LGPD_RETENTION.md` para detalhes tecnicos
   - GCS: 90 dias (lifecycle policy)
   - Firestore: 365 dias (TTL field)

6. **Skill `lgpd_compliance` obrigatoria** ao trabalhar com dados pessoais. Ver `~/.config/opencode/skills/lgpd_compliance/`.

7. **CI check `check_lgpd_compliance.py`** DEVE rodar em todo `cloudbuild-*.yaml` (Fase 2 pendente).

## Regra #15 — Timezone Obrigatorio BRT (America/Sao_Paulo)

**Aplicavel a partir de 10/07/2026.**

1. **Todas as maquinas Cloud Run** (worker, test-env, Portal) operam em UTC internamente (padrao GCP), mas **logs, timestamps no Firestore e UI** devem refletir horario de Brasilia (GMT-3, America/Sao_Paulo).
2. **Cloud Scheduler**: jobs de mantenção (warmup, cleanup) devem usar timezone `America/Sao_Paulo`.
3. **Proibido** usar UTC ou qualquer outro fuso para metadados de upload (`uploaded_at`, `updated_at`). Frontend exibe em BRT.
4. **DIARIO_BORDO.md**: todas as entradas devem ser registradas com timestamp BRT + UTC (ex: `10/07/2026 00:16 BRT`).

## Regra #16 — Resiliência contra Inatividade (Anti-Scale-to-Zero Break)

**Aplicavel a partir de 10/07/2026. Atualizado 12/07/2026 (test = excecao).**

1. **O pipeline NAO PODE quebrar por inatividade do worker.** O usuario deve poder
   enviar chamadas a qualquer momento, mesmo apos horas ou dias sem uso.

2. **Producao: PROIBIDO** `min-instances=0`. Worker `monitoria-worker` usa `min-instances=1`.

3. **Test: ACEITO** `min-instances=0` (worker `monitoria-whisper-worker`). Justificativa:
   - Ambiente de teste fica idle quando nao usado (custo $0).
   - Ao pushar (`git push origin test`), Cloud Build deploya e worker fica ativo.
   - Script `scripts/dev.ps1 up` reativa manualmente.

4. **Streaming PULL subscription e' INCOMPATIVEL com min-instances=0.** Em PULL,
   o worker inicia a conexao gRPC. Se o container morrer (scale-to-zero), nenhum
   evento dispara um novo container. Mensagens acumulam eternamente.

5. **Alternativa correta:** PUSH subscription. O Pub/Sub envia HTTP POST para o
   worker, e o Cloud Run inicia o container automaticamente.

## Regra #19 — Operacao Exclusiva em Test (Proibido Deploy em Prod sem Ordem)

**Aplicavel a partir de 10/07/2026.**

1. **Trabalhamos EXCLUSIVAMENTE na branch `test`.** Todo commit, ajuste e deploy deve ser feito em test.
2. **PROIBIDO fazer `git push` na branch `main`** ou qualquer operacao que acione os triggers de producao sem autorizacao explicita do usuario.
3. **PROIBIDO executar `git merge test` para `main`** sem que o usuario diga expressamente "publique em prod" ou "promova para producao".
4. **PROIBIDO usar `git push --force`** em qualquer branch compartilhada.
5. A unica excecao: quando o usuario solicitar explicitamente a publicacao em producao, usar a skill `test_to_prod_promoter`.
6. O fluxo padrao de trabalho e: `git checkout test` → ajustes → `git push origin test` → deploy automatico em test. Usar a skill `test_workflow_manager`.

## Regra #21 — LLM Keys via GCP Secret Manager (obrigatorio em Cloud Run)

**Aplicavel a partir de 12/07/2026.**

1. **Todas as chaves de API LLM** (DEEPSEEK_API_KEY, NVIDIA_API_KEY, MINIMAX_API_KEY) DEVEM estar no **GCP Secret Manager** do projeto `coherence-ominichannel-fs`.
2. O `requirements.txt` DEVE conter `google-cloud-secret-manager` — sem ela, o `secrets_manager.py` nao consegue ler as chaves e todos os providers falham.
3. A SA do Cloud Run (`894828119087-compute@developer.gserviceaccount.com`) DEVE ter `roles/secretmanager.secretAccessor` no projeto.
4. **NUNCA** injetar chaves LLM como env vars no `cloudbuild-*.yaml` (vazamento via logs do Cloud Build).
5. **NUNCA** depender de SQLite local em Cloud Run (armazenamento efemero — chaves desaparecem apos restart).
6. Ao adicionar novo provider LLM, criar a secret no GCP SM antes do merge.

**Historico:** Bug critico em 12/07/2026: DEEPSEEK_API_KEY foi corrompida ao subir para GCP SM (caracteres non-latin1). Fix: reupload com `gcloud secrets versions add`.

## Regra #22 — Signed URL requer signBlob no SA da API

**Aplicavel a partir de 11/07/2026.**

1. A SA que executa a API (`894828119087-compute@developer.gserviceaccount.com`) DEVE ter `roles/iam.serviceAccountTokenCreator` como auto-binding (`iam.serviceAccounts.signBlob`).
2. Sem essa permissao, `blob.generate_signed_url()` retorna 500 e o frontend exibe "Audio nao disponivel".
3. `roles/editor` no projeto NAO inclui `signBlob`. A permissao deve ser adicionada explicitamente:
   ```bash
   gcloud iam service-accounts add-iam-policy-binding \
     894828119087-compute@... \
     --member=serviceAccount:894828119087-compute@... \
     --role=roles/iam.serviceAccountTokenCreator
   ```
4. **Verificar apos cada reset de projeto** se a permissao ainda esta presente.

## Regra #23 — Fluxo de Desenvolvimento: TUDO em Test, NUNCA em Prod

**Aplicavel a partir de 12/07/2026. Regra absoluta.**

1. **Todo desenvolvimento, commit e deploy DEVE ser na branch `test`.**
2. **PRODUÇÃO recebe APENAS merge da `test`** (`test → main`), e somente **após aprovação explícita do usuário**.
3. **PROIBIDO** commitar diretamente em `main`.
4. **PROIBIDO** fazer `git push origin main` exceto via `git merge test` autorizado.
5. **Testes de verificação** (upload, inspeção, LLM) devem ser feitos no ambiente `monitoria-test-env`.
6. **O ambiente de produção** (`monitoria.coherenceai.com.br`) só recebe deploy quando o usuário disser "publique em prod" ou equivalente.
7. **Exceção:** correções críticas (crash, security, dados corrompidos) podem pular a fila com autorização explícita do usuário.

- [DIARIO_BORDO.md](DIARIO_BORDO.md) - Historico de mudancas
