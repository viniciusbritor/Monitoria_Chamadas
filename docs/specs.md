# Especificações do Sistema: Monitoria de Chamadas com IA

## 1. Características Gerais

- **Referência de Negócio:** Baseado no escopo do documento `MONITORIA COM IA.doc`, visando automatizar o processo de Quality Assurance (QA) para operações de CX. O objetivo é gerar valor através de auditoria em massa, automação de coaching e dashboards de qualidade e aderência a POPs.
- **Arquitetura de Sistemas (Padrão Corporativo):** O projeto adota estritamente as diretrizes da arquitetura global corporativa (skill `@eng_sistema`):
  - **Borda e Interface:** Frontend Web SPA/Responsivo com estratégia de Edge Caching.
  - **Segurança e Gateways:** Autenticação via **OAuth2**, proteção WAF, API Gateway central e controle de acesso rigoroso baseado em perfis (Role-Based Access Control).
  - **Processamento Assíncrono (Event-Driven):** Uso de mensageria (ex: GCP Pub/Sub ou RabbitMQ) para orquestrar o pipeline das chamadas, desacoplando o backend do processamento massivo da IA.
  - **Persistência Poliglota:** 
    - Relacional (PostgreSQL) para configurações de negócio, usuários e cadastros.
    - Armazenamento de Objetos (GCP Cloud Storage) para os áudios brutos de gravação.
    - Banco Vetorial (RAG): Utilização da própria instância relacional (PostgreSQL no Cloud SQL) com a extensão nativa `pgvector` para buscas semânticas em POPs. Isso zera os custos com bancos vetoriais externos.
  - **Compliance e LGPD:** Criptografia em repouso e trânsito, mascaramento de dados sensíveis (PII, como CPF) antes de enviar *prompts* externos e isolamento de segredos (Secret Manager).
- **Hospedagem e Infraestrutura:** Google Cloud Platform (GCP) com arquitetura inicial *Low Cost* dimensionada para o MVP, com capacidade provisionada para processar e armazenar 100 chamadas com baixo overhead.
- **Inteligência Artificial:** A IA generativa padrão será o modelo **Minimax M3**. (Nota: A chave de acesso da API estará hospedada no Artifact Registry / Secret Manager da GCP).
- **Processamento de Mídia:** Suporte multi-formato, com capacidade nativa de ingerir, normalizar e ler arquivos de áudio em diferentes extensões.
- **Gestão de Acesso:** Interface administrativa para provisionar perfis de uso padrão: `Administrador`, `Especialista` e `Analista`.
- **Governança de Custos:** Como premissa de desenvolvimento ágil do projeto, antes de iniciar o código de cada novo componente, será apresentada uma estimativa/análise de custo de cloud e API para tomada de decisão consciente.

## 2. Funcionalidades

- **Transcrição e Diarização:** Capacidade de transcrever integralmente o áudio da chamada de forma segmentada, separando de maneira clara as falas do operador e do cliente.
- **Parametrização de Contexto de Negócio:** Interface de setup (Setup de POPs) para o administrador informar ao sistema o tipo da operação e suas diretrizes de qualidade. *Exemplo:* "Clínica de Beleza - Vendas", "Telecomunicações - SAC". Este campo injeta o prompt e contexto analítico para que o modelo avalie a chamada corretamente sob o ponto de vista daquele serviço.
- **Análise de Sentimentos:** Para cada chamada processada, a IA deverá identificar e listar os **3 principais sentimentos** demonstrados pelo cliente e os **3 principais sentimentos** do operador durante a interação.
- **Acesso Contínuo à Gravação:** Interface com a transcrição completa lado a lado com um player do arquivo de áudio sincronizado. A gravação e seu resultado textual devem ficar perpetuamente disponíveis na plataforma.
- **Mecanismo Avançado de Busca:** Os usuários poderão localizar chamadas pregressas através dos filtros:
  - Nome do cliente
  - Documento de identificação (CPF)
  - Data do contato
  - Hora do contato
- **Avaliação Contínua do Operador (Dia a dia):**
  - O sistema aplicará um modelo de pontuação (QA Score) no fim de cada atendimento analisado.
  - O sistema consumirá ativamente o banco de dados de pesquisas de satisfação do cliente (ex: CSAT/NPS pós-chamada). 
  - A métrica de qualidade levará em conta os sentimentos extraídos da chamada cruzados com a nota dada pelo cliente.
  - **Fallback:** Caso não exista uma nota/pesquisa registrada do cliente, a avaliação do operador será calculada inferindo o resultado da interação estritamente através dos sentimentos medidos na chamada e dos itens técnicos do POP validados pela IA.

## 3. Aparência e Interface

- **Identidade Visual:** Interface puramente **minimalista**, priorizando a visualização limpa de dados, utilizando a logomarca da **Choerencia.AI**.
- **Dashboard de Execução em Tempo Real:** Para garantir transparência aos analistas, o sistema deve exibir uma tela de processamento *live* mostrando cada etapa do fluxo da análise da chamada em tempo real (ex: Envio de Arquivo -> Diarização de Canais -> Transcrição Textual -> Contextualização do Prompts -> Inferência de IA M3 -> Geração de Avaliação e Notas).

## 4. Suporte

- **Central de Ajuda:** Uma sessão fixa no sistema contendo o **Manual de Uso** abrangente e um compilado em formato **FAQ** (Perguntas Frequentes) para auxiliar a curva de aprendizagem dos operadores, especialistas e administradores.
