# 🚀 Harness do Projeto

> **Objetivo Principal:** Sistema de "Monitoria de Chamadas" baseado em IA. Transcreve áudios de atendimento ao cliente usando Whisper (local ou Cloud Run) e os avalia contra critérios de qualidade utilizando Gemini (Google), fornecendo notas (QA Score) e feedback através de um Dashboard web interativo.

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

## 🏗️ Build do Frontend (Vite) — Variáveis de Ambiente
- **REGRA CRÍTICA:** A variável `VITE_API_URL` **DEVE** ser injetada via Cloud Build substitutions (`cloudbuild-test.yaml` ou `cloudbuild.yaml`) ANTES do `npm run build`. Nunca deixar `VITE_API_URL` cair no fallback hard-coded.
- **NÃO criar `frontend/.env.local`** — esse arquivo é ignorado pelo git mas seu conteúdo é embutido no bundle JS compilado, podendo causar bugs sutis de URL (vide DIARIO_BORDO 03/07/2026).
- Para desenvolvimento local, copie `frontend/.env.example` → `frontend/.env.local` e ajuste a `VITE_API_URL` para `http://127.0.0.1:8001`.
- **Cache-bust:** o `cloudbuild-test.yaml` cria o arquivo `frontend/.cache-bust` antes do build para forçar o navegador a recarregar o `index.html` (que tem `Cache-Control: no-store` no backend).

## Histórico de Erros e Resoluções
- **Erro de "Erro no upload" no ambiente de teste (03/07/2026):** O bundle JS em `frontend/dist/` foi compilado com `VITE_API_URL=http://127.0.0.1:8001` (dev local), fazendo o navegador do usuário tentar POST para localhost. Bug adicional: 3 arquivos `.jsx` tinham fallback apontando para a URL de produção. Corrigido rebuildando o frontend com a URL correta e alinhando os fallbacks.
- **Erro de Falhou na Interface:** Ao enviar áudios, a interface do usuário exibia o status Falhou após um longo tempo aguardando. Isso ocorreu porque o processo do Whisper no Cloud Run consome tempo substancial de CPU e a interface assumia um timeout ou um erro prematuro, apesar de o servidor continuar processando e salvar os resultados corretamente no SQLite (monitoria_ia.db). Foi mitigado ajustando a alocação de threads no Whisper e documentando a necessidade de paciência do usuário devido ao uso de CPU.

## Visual Identity
All UI changes must strictly follow [UI_GUIDELINES.md](UI_GUIDELINES.md) ensuring the Coherence visual identity guidelines (Clean Light Glassmorphism).