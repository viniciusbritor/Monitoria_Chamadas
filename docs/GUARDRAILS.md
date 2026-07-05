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
