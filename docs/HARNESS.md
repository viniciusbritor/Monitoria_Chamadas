# 🚀 Harness do Projeto

> **Objetivo Principal:** Sistema de "Monitoria de Chamadas" baseado em IA. Transcreve áudios de atendimento ao cliente usando Whisper (local ou Cloud Run) e os avalia contra critérios de qualidade utilizando Gemini (Google), fornecendo notas (QA Score) e feedback através de um Dashboard web interativo.

## 🏗️ Arquitetura
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

## 🧪 Ambiente de Teste vs Produção
- **REGRA ESTABELECIDA:** A primeira implementação de qualquer nova funcionalidade ou alteração **SEMPRE** deve ser feita no ambiente de Teste/Homologação (`Monitoria_Chamadas_Teste`). Nenhuma alteração deve ser feita diretamente no ambiente de produção.
- Após a implementação no ambiente de teste, o usuário avaliará e decidirá se as alterações devem ser "viradas" para Produção.

## 📂 Estrutura de Diretórios
- `/core`: Lógicas isoladas de IA (`transcriber.py`, `evaluator.py`).
- `/frontend`: Aplicação React/Vite isolada (dist build é servido estaticamente no backend FastAPI).
- `api.py`: Roteador principal FastAPI e BackgroundTasks.
- `Dockerfile`: Arquivo responsável pela construção da infraestrutura no GCP (Cloud Run).
- `/docs`: Documentação técnica essencial.

## 🔑 Autenticação e Segredos
- O projeto consome segredos utilizando o arquivo global `secrets_manager.py` (banco cofre). A variável `GEMINI_API_KEY` é extraída de maneira segura para inferência, evitando credenciais hardcoded.

## Histórico de Erros e Resoluções
- **Erro de Falhou na Interface:** Ao enviar áudios, a interface do usuário exibia o status Falhou após um longo tempo aguardando. Isso ocorreu porque o processo do Whisper no Cloud Run consome tempo substancial de CPU e a interface assumia um timeout ou um erro prematuro, apesar de o servidor continuar processando e salvar os resultados corretamente no SQLite (monitoria_ia.db). Foi mitigado ajustando a alocação de threads no Whisper e documentando a necessidade de paciência do usuário devido ao uso de CPU.


## Visual Identity
All UI changes must strictly follow [UI_GUIDELINES.md](UI_GUIDELINES.md) ensuring the Coherence visual identity guidelines (Clean Light Glassmorphism).
