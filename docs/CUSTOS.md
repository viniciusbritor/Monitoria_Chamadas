# Custos e Projecao de Infraestrutura

> Data: 12/07/2026
> Projetos: Monitoria de Chamadas + WhatsApp Agente
> **Ambiente de teste: EFEMERO — criado sob demanda, destruido apos promover para prod.**

---

## 0. Fluxo de Trabalho (Zero Custo de Test)

```
branch test → ajustes → merge main → deploy prod → destroi ambiente test
```

1. **Criar branch `test`** a partir de `main` (ja existe)
2. **Ajustar/deployar** via `git push origin test` → Cloud Build deploya servicos de teste
3. **Testar** no ambiente `monitoria-test-env`
4. **Promover:** `git merge test → main` + `git push origin main` → Cloud Build deploya producao
5. **Destroi teste:** servicos de teste escalam a zero (`min=0`) e subscription Pub/Sub e seeked

**Custo do ambiente de teste: $0/mes** — servicos escalam a zero quando ociosos.
Apenas ha custo durante o desenvolvimento ativo (minutos/horas de uso).

---

## 1. Resumo de Custos (So Producao)

| Provedor | Servico | Custo Mensal (USD) | Custo Mensal (BRL) |
|---|---|---|---|
| **GCP** | Cloud Run (Monitoria + Portal prod) | ~$75 | ~R$ 415 |
| **GCP** | Compute Engine (WhatsApp VM) | ~$30 | ~R$ 165 |
| **GCP** | Firestore + GCS + Pub/Sub + Secrets | ~$8 | ~R$ 45 |
| **LLMs** | DeepSeek + MiniMax (sob demanda) | ~$6 | ~R$ 33 |
| **Total** | | **~$119** | **~R$ 658** |

---

## 2. Monitoria de Chamadas — Producao

### 2.1 Cloud Run (Producao)

| Service | CPU | RAM | min | max | Custo/mes | Por que |
|---|---|---|---|---|---|---|
| `monitoria` (API) | 4 vCPU | 8 GiB | 0 | 5 | ~$20 | Idle $0, ativo ~$0.06/h |
| `monitoria-worker` (worker) | 4 vCPU | 4 GiB | **1** | 4 | **~$50** | Sempre quente (PULL sub) |
| `coherence-portal` | - | - | 0 | - | ~$5 | Portal producao |
| **Subtotal** | | | | | **~$75** | |

### 2.2 Infra Compartilhada

| Recurso | Custo/mes | Detalhe |
|---|---|---|
| Firestore | ~$3 | Leituras/escritas de chamadas |
| Cloud Storage | ~$2 | Audios temporarios (deletados apos processar) |
| Pub/Sub | ~$1 | Topic `monitoria-whisper-jobs-prod` |
| Secret Manager | ~$1 | DEEPSEEK_API_KEY, NVIDIA_API_KEY, MINIMAX_API_KEY |
| Cloud Build | ~$2 | Trigger de producao (push main) |
| Artifact Registry | ~$1 | Imagens Docker |
| **Subtotal** | **~$10** | |

---

## 3. WhatsApp Agente — Producao

### 3.1 VM Atual (1 chatbot)

| Recurso | Especificacao | Custo/mes |
|---|---|---|
| VM e2-small | 2 vCPU, 2 GB RAM, 20 GB SSD | ~$17 (USD) / ~R$ 95 |
| Firestore | 4 collections | ~$3 |
| Cloud Storage | 3 buckets, backups 30d | ~$1 |
| Secret Manager | 7 secrets | ~$1 |
| IP Estatico | `34.39.162.165` | ~$3 |
| Cloud Build | Trigger test (eventual) | ~$1 |
| **Total** | | **~$26 / ~R$ 145** |

---

## 4. Projecao: 5 Chatbots Simultaneos

### 4.1 Cenarios

| Cenario | Infra/mes | LLM/mes | Total | Prós |
|---|---|---|---|---|
| **Atual** (1 chatbot, e2-small) | ~$26 | ~$3 | **~$29 / R$ 160** | Ja funciona |
| **A** (5 chatbots, VM upgrade) | ~$120 | ~$8 | **~$128 / R$ 710** | Simples, mesma VM |
| **B** (5 chatbots, Cloud Run)* | ~$80 | ~$8 | **~$88 / R$ 490** | +Barato, +Resiliente |
| **C** (5 chatbots, Cloud Run + GPU) | ~$200 | ~$4 | **~$204 / R$ 1130** | Whisper GPU local |

*\*Recomendado para 5 chatbots.*

### 4.2 Cenario B — Cloud Run (Recomendado)

| Componente | Config | Custo/mes |
|---|---|---|
| 5x Cloud Run (1 vCPU, 1 GiB, min=0) | Sob demanda | ~$30 |
| Cloud SQL Postgres (db-f1-micro) | 10 GB | ~$10 |
| Evolution API (Cloud Run) | 1 vCPU, 512 MiB, min=0 | ~$40 |
| Firestore + Secrets + Storage | Uso normal | ~$3 |
| **Total** | | **~$83 / R$ 460** |

### 4.3 Custo LLM (5 chatbots, ~200 msg/dia cada)

| Provider | Custo/mes |
|---|---|
| DeepSeek V4 Flash (primario) | ~$4 |
| MiniMax M3 (fallback) | ~$2 |
| NVIDIA NIM (ultimo recurso) | ~$1 |
| **Total LLM** | **~$7 / R$ 40** |

---

## 5. Otimizacoes

| Acao | Economia/mes | Risco |
|---|---|---|
| Desligar `monitoria-cx`, `monitoria-cx-v2` (legado) | ~$10 | Nenhum (nao usados) |
| Migrar worker prod PULL → PUSH | ~$40 | Medio (precisa migrar subscription) |
| Mudar API prod para 2 vCPU (em vez de 4) | ~$10 | Baixo (Whisper fica mais lento) |
| CUD 1y para Cloud Run | -20% total | Baixo (compromisso 1 ano) |

---

## 6. Resumo Final (So Producao)

| Categoria | USD/mes | BRL/mes |
|---|---|---|
| **Monitoria (prod)** | ~$85 | ~R$ 470 |
| **WhatsApp (1 chatbot)** | ~$29 | ~R$ 160 |
| **WhatsApp (5 chatbots futuro)** | ~$88 | ~R$ 490 |
| **Total Operacao Atual** | **~$114** | **~R$ 630** |
| **Total com 5 chatbots** | **~$173** | **~R$ 960** |

> *Precos baseados na tabela publica GCP jul/2026. Cambio: 1 USD ~ 5.5 BRL. Custo teste: $0/mes (efemero).*
