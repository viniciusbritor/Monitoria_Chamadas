# 📓 Diário de Bordo (Changelog & Decisões)

> Use este arquivo para registrar o histórico de evolução do projeto. Antes de um agente tomar decisões complexas, ele deve ler este diário para entender o que já foi tentado e como a arquitetura atual foi decidida.

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
