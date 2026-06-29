# 🛡️ Guardrails e Regras Inegociáveis

> Este arquivo dita as regras DURAS que todos os agentes IA devem obedecer neste projeto especificamente.

## 🚫 Restrições Severas (O que NUNCA fazer)
1. **Nunca bloquear threads principais:** Nunca utilizar processamento bloqueante (Síncrono na rota) para transcrição e avaliação. Sempre usar `BackgroundTasks` ou Filas assíncronas no FastAPI para não causar Timeouts (HTTP 502/504) no GCP Cloud Run ou travar o navegador.
2. **Identidade Visual Coherence.AI:** Nunca usar cores aleatórias na UI; sempre respeitar a identidade visual detalhada em docs/UI_GUIDELINES.md (Estilo Clean Light Glassmorphism em todas as telas, incluindo Login e Dashboard).
3. **Dependências em Nuvem:** Nunca fazer um Deploy no GCP Cloud sem verificar se o arquivo `requirements.txt` contém `fastapi`, `uvicorn` e `python-multipart`.

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
