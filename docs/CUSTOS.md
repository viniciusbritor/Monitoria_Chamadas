# Custos e Projecao de Infraestrutura

> Data: 12/07/2026
> Projetos: Monitoria de Chamadas + WhatsApp Agente

---

## 1. Resumo Atual (Custos Agregados)

| Provedor | Servico | Custo Mensal (USD) | Custo Mensal (BRL) |
|---|---|---|---|
| **GCP** | Cloud Run (Monitoria + Portal) | ~$85 | ~R$ 470 |
| **GCP** | Compute Engine (WhatsApp VM) | ~$30 | ~R$ 165 |
| **GCP** | Firestore + GCS + Pub/Sub + Secrets | ~$10 | ~R$ 55 |
| **MiniMax** | LLM API (sob demanda) | ~$5 | ~R$ 28 |
| **DeepSeek** | LLM API (sob demanda) | ~$1 | ~R$ 6 |
| **Total** | | **~$131** | **~R$ 724** |

---

## 2. Monitoria de Chamadas — Detalhamento

### 2.1 Cloud Run Services

| Service | CPU | RAM | min | max | Estimativa/mes |
|---|---|---|---|---|---|
| `monitoria` (prod API) | 4 vCPU | 8 GiB | 0 | 5 | ~$20 (idle $0, ~$0.06/hora ativo) |
| `monitoria-worker` (prod worker) | 4 vCPU | 4 GiB | **1** | 4 | **~$50** (sempre ativo) |
| `monitoria-test-env` (test API) | 4 vCPU | 8 GiB | 0 | 5 | ~$2 (sob demanda) |
| `monitoria-whisper-worker` (test worker) | 4 vCPU | 4 GiB | 0 | 4 | ~$1 (sob demanda) |
| `coherence-portal` (Portal prod) | - | - | 0 | - | ~$5 |
| `coherence-portal-test` (Portal test) | - | - | 0 | 20 | ~$5 |
| **Subtotal Cloud Run** | | | | | **~$83** |

### 2.2 Outros Servicos GCP (Monitoria)

| Recurso | Projeto | Custo/mes |
|---|---|---|
| Firestore (leituras/escritas) | `coherence-ominichannel-fs` | ~$3 |
| Cloud Storage (audios temporarios) | `coherence-monitoria-audios-tmp` | ~$2 |
| Pub/Sub (2 topicos + subscriptions) | `monitoria-whisper-jobs` | ~$1 |
| Secret Manager (3 secrets) | `DEEPSEEK_API_KEY, NVIDIA_API_KEY, MINIMAX_API_KEY` | ~$1 |
| Cloud Build (4 triggers, ~10 builds/dia) | `coherence-ominichannel-fs` | ~$5 |
| Container Registry / Artifact Registry | Imagens Docker | ~$2 |
| **Subtotal Monitoria** | | **~$14** |

---

## 3. WhatsApp Agente — Detalhamento

### 3.1 Infraestrutura Atual (1 chatbot)

| Recurso | Projeto GCP | Especificacao | Custo/mes |
|---|---|---|---|
| **VM e2-small** | `jennifer-bot` | 2 vCPU, 2 GB RAM, 20 GB SSD | **~$17 (USD) / ~R$ 95** |
| Firestore Nativo | `jennifer-bot` | 4 collections, baixo throughput | ~$3 |
| Cloud Storage (backups + painel) | `evolution-backups-jennifer-bot` | 3 buckets, ~1 GB | ~$1 |
| Secret Manager | `jennifer-bot` | 7 secrets | ~$1 |
| Cloud Build (trigger test) | `jennifer-bot` | Eventual (push test) | ~$1 |
| IP Estatico | `jennifer-bot` | `whatsapp-server-ip` (34.39.162.165) | ~$3 |
| **Total atual** | | | **~$26 (USD) / ~R$ 144** |

### 3.2 Stack por Chatbot

Cada instancia de chatbot roda como container Docker na VM:

| Container | Imagem | Porta | Funcao |
|---|---|---|---|
| `evolution_api` | `evoapicloud/evolution-api:latest` | 8080 | Gerenciamento de conexao WhatsApp |
| `agente` | `evolution-agente` (custom) | 8000 | LLM + logica de resposta |
| (futuro) `whatsapp-web` | `n8n` ou custom | - | Automacao midia/grupos |

---

## 4. Projecao para 5 Chatbots Simultaneos

### 4.1 Infraestrutura Necessaria

Para suportar 5 instancias do Evolution API + 5 agentes LLM simultaneos:

| Componente | Configuracao | Estimativa/mes |
|---|---|---|
| **VM** | `e2-standard-4` (4 vCPU, 16 GB RAM, 50 GB SSD) | ~$90 (USD) / ~R$ 500 |
| **OU** `e2-highmem-4` (4 vCPU, 32 GB RAM, 50 GB SSD)* | | ~$120 (USD) / ~R$ 665 |
| Evolution API (5x containers) | 5 x ~300 MB RAM cada | incluso na VM |
| Postgres | Instancia dedicada ou Cloud SQL (db-f1-micro) | ~$10 (USD) / ~R$ 55 |
| IPs Estaticos | 1 IP para load balancer ou 5 IPs | ~$3-15 (USD) |
| Firestore | Mesmo projeto, throughput 5x maior | ~$5 |
| **Total 5 chatbots (VM)** | | **~$110-150 (USD) / ~R$ 600-830** |

*\*Recomendado: e2-highmem-4 se usar MiniMax ou LLMs pesados localmente.*

### 4.2 Alternativa: Migrar para Cloud Run (sem VM)

Se cada chatbot for um servico Cloud Run separado:

| Componente | Configuracao | Estimativa/mes |
|---|---|---|
| Cloud Run (5 servicos) | 1 vCPU, 1 GiB, min=0, max=2 | ~$30 (USD) |
| Cloud SQL (Postgres) | db-f1-micro, 10 GB | ~$10 (USD) |
| Evolution API | Cloud Run ou Cloud Run + Redis | ~$40-60 (USD) |
| **Total 5 chatbots (Cloud Run)** | | **~$80-100 (USD) / ~R$ 440-550** |

### 4.3 LLM Cost Breakdown

| Provider | Preco Input (1M tokens) | Preco Output (1M tokens) | Custo/chat (est.) |
|---|---|---|---|
| DeepSeek V4 Flash | $0.14 | $0.28 | $0.0005 |
| DeepSeek V4 Pro | $0.435 | $0.87 | $0.002 |
| MiniMax M3 | ~$0.20 | ~$0.40 | ~$0.001 |
| NVIDIA NIM (fallback) | $0.15 | $0.30 | $0.0006 |

**Estimativa para 5 chatbots** processando ~200 mensagens/dia cada:
- 1000 mensagens/dia total
- ~500 tokens input + ~300 tokens output por mensagem
- LLM chamadas: ~0.4M tokens/dia
- Custo LLM: **~$4-8/mes** (DeepSeek Flash)

---

## 5. Cenarios Comparativos

| Cenario | Infra/mes | LLM/mes | Total/mes | Observacao |
|---|---|---|---|---|
| **Atual** (1 chatbot, e2-small) | ~$26 | ~$3 | **~$29 / ~R$ 160** | Monitoria incluso e separado |
| **Cenario A** (5 chatbots, VM upgrade) | ~$120 | ~$8 | **~$128 / ~R$ 710** | e2-highmem-4 + Postgres |
| **Cenario B** (5 chatbots, Cloud Run) | ~$80 | ~$8 | **~$88 / ~R$ 490** | Mais resiliente, menos custo |
| **Cenario C** (5 chatbots, Cloud Run + GPU) | ~$200 | ~$4 | **~$204 / ~R$ 1130** | Whisper GPU + LLM local |

---

## 6. Otimizacoes Recomendadas

| Acao | Economia | Esforco |
|---|---|---|
| Desligar `monitoria-cx` e `monitoria-cx-v2` (legado) | ~$10/mes | Baixo |
| Migrar worker prod para PUSH subscription (eliminar min=1) | ~$40/mes | Medio |
| Usar DeepSeek V4 Flash (em vez de MiniMax) | ~$3-5/mes | Nenhum (ja e primario) |
| Comprar CUD (Committed Use Discount) 1y para Cloud Run | -20% | Baixo |
| VMs Preemptive/Spot para dev/teste | -60% | Baixo |

---

## 7. Resumo Final

| Categoria | USD/mes | BRL/mes |
|---|---|---|
| **Monitoria Producao** (API + Worker + infra) | ~$80 | ~R$ 440 |
| **Monitoria Teste** (idle) | ~$3 | ~R$ 17 |
| **WhatsApp Atual** (1 chatbot, VM) | ~$29 | ~R$ 160 |
| **WhatsApp Futuro** (5 chatbots, recomendado) | ~$128 | ~R$ 710 |
| **Total Operacao** | **~$240** | **~R$ 1330** |

> *Precos baseados na tabela publica GCP jul/2026. Câmbio: 1 USD ~ 5.5 BRL. Custo MiniMax: ~$0.001/chat. DeepSeek: ~$0.0005/chat.*
