# 🏗️ Arquitetura do Projeto

- **Stack Tecnológico:**
  - **Backend:** Python, FastAPI, Uvicorn (Assíncrono com BackgroundTasks)
  - **Frontend:** React, Vite, TailwindCSS (Identidade Visual Coherence.AI), Lucide Icons
  - **IA (Transcrição):** faster-whisper (PyTorch, CTranslate2)
  - **IA (Avaliação):** Google Generative AI (Gemini 1.5 Pro)
- **Integrações (APIs/Bancos):** 
  - Banco Local SQLite (`monitoria.db`)
  - MiniMax M3 API (para extração de QA e feedback, substituindo Gemini)
- **Variáveis de Ambiente Necessárias (GCP Cloud Run):**
  - `MINIMAX_API_KEY`: Chave para inferência do LLM.
  - `PYTHONUNBUFFERED=1`: Para garantir logs em tempo real (print flush).
  - `OMP_NUM_THREADS=2`: Para evitar crash/concorrência excessiva do faster-whisper (CTranslate2) nas CPUs do Cloud Run.
- **Fluxo de Dados Principal:**
  1. Frontend (React) faz upload de um arquivo de áudio para `POST /api/upload`.
  2. Backend (FastAPI) cria um registro no SQLite e enfileira um BackgroundTask de processamento para não travar a UI.
  3. A UI monitora `GET /api/calls` via short-polling (a cada 1 ou 2 segundos).
  4. O Background Task executa `Transcriber` (Whisper), atualiza o status.
  5. O Background Task executa `Evaluator` (Gemini), atualizando o status e nota final.
  6. Frontend recebe "Concluído" e a interface atualiza com o Score de QA (Verde, Amarelo, Vermelho) e esconde a barra de progresso em troca do detalhe.