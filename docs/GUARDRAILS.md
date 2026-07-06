# 🛡️ Guardrails e Regras Inegociáveis

> Este arquivo dita as regras DURAS que todos os agentes IA devemobedecer neste projeto especificamente.

## 🚫 Acesso EXCLUSIVO via Portal Coherence (REGRA #0 — mais alta prioridade)

**A URL `https://monitoria-test-env-c5nbfc5meq-uc.a.run.app/` NÃO É pública.**

1. **Único caminho válido de acesso**: usuário loga no **Portal Coherence** (`https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/`), clica no card do módulo **Monitoria de Chamadas**, e o Portal abre o módulo em nova aba via `window.open(${module.url}?token=${firebase_id_token}, '_blank')`.
2. **Acesso direto à URL do módulo (colar no navegador, bookmark, link direto)** é PROIBIDO. O resultado esperado é a tela "Acesso via Portal Coherence" com botão de redirect para `https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/dashboard`.
3. **Não reintroduzir formulário de login próprio** no módulo (Google, email/senha, magic-link, etc.). O módulo delega 100% da autenticação ao Portal.
4. **Não documentar, comunicar, nem compartilhar a URL do test-env** como ponto de entrada para usuários finais. A URL do módulo é detalhe de implementação interno do ecossistema Coherence.
5. **Não expor a URL do módulo em e-mails, README, comentários de código, nem variáveis `VITE_API_URL` em frontend público** sem o token via `?token=`. O bundle JS é servido pelo próprio Cloud Run e a URL está embutida — esse vazamento é aceitável apenas porque o backend rejeita chamadas sem Bearer token válido.
6. **Backend enforcement**: requests ao endpoint raiz `/` (SPA entry point) sem `Referer` apontando para o Portal Coherence são logadas como alerta de segurança (`[Security] direct-access attempt`). O fluxo legítimo sempre carrega `Referer: https://coherence-portal-test-c5nbfc5meq-uc.a.run.app/` (ou produção correspondente).

**Por que essa regra existe:**
- O Portal é o **source of truth** de identidade (Firebase SSO) e permissões (Firestore).
- O módulo não tem (nem deve ter) gestão própria de usuários, senhas, sessões, ou RBAC.
- Manter autenticação centralizada no Portal evita `user_permissions` duplicados, drift de dados, e complexidade operacional.
- Em conformidade com a **Regra #7 do Harness Global** (modelo Portal + Módulos).

## 🚫 Restrições Severas (O que NUNCA fazer)
1. **Nunca bloquear threads principais:** Nunca utilizar processamento bloqueante (Síncrono na rota) para transcrição e avaliação. Sempre usar `BackgroundTasks` ou Filas assíncronas no FastAPI para não causar Timeouts (HTTP 502/504) no GCP Cloud Run ou travar o navegador.
2. **Identidade Visual Coherence.AI:** Nunca usar cores aleatórias na UI; sempre respeitar a identidade visual detalhada em docs/UI_GUIDELINES.md (Estilo Clean Light Glassmorphism em todas as telas, incluindo Login e Dashboard).
3. **Dependências em Nuvem:** Nunca fazer um Deploy no GCP Cloud sem verificar se o arquivo `requirements.txt` contém `fastapi`, `uvicorn` e `python-multipart`.
4. **Implementação em Produção:** NUNCA implemente código novo diretamente no ambiente de produção (`Monitoria_Chamadas`). A primeira implementação é SEMPRE no ambiente de testes (`Monitoria_Chamadas_Teste`). Com base neste ambiente, o usuário decidirá se o código será virado para produção.
5. **Não reintroduzir tela de Login no módulo** (ver Regra #0). O módulo NÃO tem (nem deve ter) autenticação própria. Toda identidade vem do Portal via `?token=` ou `Authorization: Bearer`.

## ✅ Regras de Ouro (O que SEMPRE fazer)
1. **Feedback na UI Obrigatório:** Qualquer operação assíncrona ou demorada no backend DEVE fornecer feedback imediato e visual para a UI através de atualização de status (Ex: `Transcrevendo...`, `Analisando...`) com as respectivas barras de carregamento (progress bars).
2. **Ambiente GCP e Whisper:** Em ambiente Cloud Run, ferramentas Multi-Threading em C++ (como o CTranslate2 do faster-whisper) podem engasgar silenciosamente. É mandatório configurar `OMP_NUM_THREADS=2` e o `compute_type="default"` no Cloud Run. Sempre adicionar `PYTHONUNBUFFERED=1` para forçar a visibilidade dos logs.
3. **Injeção de Segredos no Deploy:** Ao trocar a engine de IA (ex: Gemini para MiniMax), NUNCA esqueça de também injetar a respectiva chave de API (ex: `MINIMAX_API_KEY`) no container da nuvem, pois o cofre local (`monitoria_ia.db`) gerado após o deploy não reflete as variáveis da máquina local original.
4. **Tratamento de Arquivos:** Todo arquivo gerado ou feito upload no backend deve ser sanitizado e garantido que a pasta de destino (como `uploads/`) exista antes de qualquer gravação.

## 🔒 Regras de Segurança / Privacidade
1. Nenhuma chave de API, credencial ou token deve ser escrito no código em hardcode (plaintext).
2. Todo segredo precisa passar obrigatoriamente pelo `secrets_manager` (SQLite central).

## 🛡️ Regras de Resiliência (Fase 1 — 05/07/2026)

Estas regras foram criadas após incidente crítico em que chamadas órfãs no Pub/Sub travaram o worker em loop infinito porque (a) test-env usava SQLite local volátil, perdendo INSERTs em deploys; (b) worker não checava idempotência antes de processar; (c) subscription não tinha DLQ.

### REGRA #6 — Volume mount obrigatório em todos os serviços que compartilham DB
1. **Qualquer serviço que lê/escreve no SQLite compartilhado DEVE ter `--add-volume name=db-vol,type=cloud-storage,bucket=consultoria-bess-mme136-db-bucket`** no deploy.
2. Sem o mount, o serviço cai no fallback `monitoria_ia.db` LOCAL, que é VOLÁTIL — todas as escritas se perdem quando o container reinicia.
3. Antes de cada deploy de serviço novo que toque no DB, validar com `gcloud run services describe <service> --format="value(spec.template.spec.volumes)"` que o volume está presente.
4. **Por que:** Sem o mount, test-env inseria no SQLite local e publicava no Pub/Sub; deploy matava o container, INSERT sumia, worker processava mensagem órfã. **Esta foi a causa raiz dos loops infinitos**.

### REGRA #7 — Idempotency do Worker
1. **Worker DEVE consultar `SELECT status FROM chamadas WHERE id = ?` ANTES de processar qualquer mensagem Pub/Sub.**
2. Comportamento esperado:
   - Linha **ausente** → ack + log `[Worker] ORPHAN: ...` (poison-ack, NÃO nack)
   - Status `Concluído` ou `Erro:...` → ack + log `[Worker] JÁ PROCESSADO: ...` (idempotente)
   - Status intermediário (`Transcrevendo/Separando/Analisando/Na Fila`) → continuar (retomada)
3. **NUNCA** nack uma mensagem sem antes validar que a falha é transient. Nack causa redelivery infinito em poison messages.
4. **Por que:** Pub/Sub garante at-least-once delivery. Sem idempotency, reprocessamento causa trabalho duplicado e loops em dados inválidos.

### REGRA #8 — DLQ obrigatória em subscriptions Pub/Sub
1. **Toda subscription DEVE ter DLQ topic associado + `max-delivery-attempts = 3`.**
2. Comando obrigatório na criação:
   ```
   gcloud pubsub subscriptions create <sub> --topic=<topic> \
     --dead-letter-topic=<dlq-topic> --max-delivery-attempts=3
   ```
3. Mensagens que falham 3x vão automaticamente para a DLQ. Admin inspeciona DLQ periodicamente.
4. **Por que:** Sem DLQ, mensagens poison (inválidas, órfãs) ficam em loop infinito, bloqueando toda a subscription.

### REGRA #9 — Schema migrations devem ser explícitas
1. **Migrations DEVEM ser tracked em uma tabela `schema_version(version, applied_at, checksum)`.**
2. **NUNCA** silenciar `sqlite3.OperationalError` em `ALTER TABLE` — log o erro explicitamente.
3. Falha de migração = startup **recusa subir** (fail-fast). Não continuar com schema parcial.
4. Cada migration incrementa a versão e registra checksum para evitar drift entre instâncias.
5. **Por que:** Migrations silenciosas mascaram problemas de compatibilidade. Dois serviços com schemas diferentes = bugs sutis e órfãos (campos NULL inesperados).

### REGRA #10 — fsync após DB write
1. **Após `conn.commit()`, chamar `os.fsync()` no arquivo SQLite para garantir flush ao disco (GCS FUSE).**
2. Configurar `PRAGMA journal_mode=WAL` em `init_db()` para concorrência segura.
3. Configurar `PRAGMA synchronous=NORMAL` (ou FULL para paths críticos de upload).
4. **Por que:** GCS FUSE tem write-back cache. Sem fsync, deploy/scale pode matar container ANTES do write ser flushed, perdendo o INSERT.

## Barreiras Limitantes
- **Processamento em CPU (Whisper):** O Cloud Run operando com recursos de CPU (sem GPU dedicada) é a principal barreira arquitetural de performance. A transcrição via faster-whisper em arquivos de áudio leva em média cerca de 1 a 2 minutos, o que afeta a percepção do usuário (ansiedade gerando sensação de erro) já que o frontend não possui websockets para atualizar o status em tempo real. A barreira requer a gestão de expectativa do tempo de processamento.

## 🎙️ Configuração do Whisper (Performance vs Qualidade)

### Regra de Ouro
**Nunca alterar `compute_type` para `int8` ou reduzir tamanho do modelo sem aprovação do owner.** A qualidade da transcrição é crítica para o score de QA e análise de sentimentos. Mudanças nessas variáveis degradam detecção de nuances em PT-BR.

### Configuração aprovada (2026-07-03)
- **Modelo**: `base` (75M params, melhor custo/benefício)
- **compute_type**: `default` (float32) — **NÃO** alterar
- **num_workers**: `2` (paralelismo CPU, sem perda de qualidade)
- **OMP_NUM_THREADS**: `2` (evita contenção em CPUs do Cloud Run)
- **vad_filter**: `True` (pula silêncios, não afeta qualidade)
- **Pré-processamento**: `ffmpeg` → mono 16kHz PCM antes do Whisper (não afeta qualidade)
- **Modelo pré-carregado** no `@app.on_event("startup")` — salva 33s no primeiro upload

### Variáveis de ambiente relacionadas
- `OMP_NUM_THREADS=2`: Obrigatório no Cloud Run (evita hang do CTranslate2)
- `PYTHONUNBUFFERED=1`: Obrigatório para logs em tempo real
- `WHISPER_MODEL=base`: Padrão (definido em `secrets/` ou env)
