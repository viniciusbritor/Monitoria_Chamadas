# Custos OmniChannel — Custo Operacional Real

## CAMBIO: USD 1 = R$ 5,50 | MARGEM: 10%

## CUSTO HOJE (recorrente, 24/7)

| Servico | USD/mes | BRL/mes | Categoria |
|---|---|---|---|
| Worker Cloud Run (4vCPU/4GB, min=1) | 85 | R$ 468 | GCP |
| API + Portal Cloud Run | 10 | R$ 54 | GCP |
| Firestore + Storage + PubSub + Secrets | 26 | R$ 145 | GCP |
| Cloud Build + Artifact Registry | 4 | R$ 24 | GCP |
| VM e2-small + IP (WhatsApp) | 22 | R$ 121 | GCP |
| DeepSeek V4 Flash (Monitoria QA) | 2 | R$ 12 | LLM |
| DeepSeek V4 Flash (Chatbots) | 9 | R$ 48 | LLM |
| MiniMax + NVIDIA (fallback) | 1 | R$ 4 | LLM |
| **TOTAL HOJE** | **160** | **R$ 878** | |

*Audio medio 5 min, Whisper base 0.1x real-time.*

## ESCALA — Custo por Volume de Chamadas (Monitoria + 5 Chatbots)

### 500 chamadas/dia (15.000/mes)
| Componente | BRL/mes |
|---|---|
| Worker variavel (PUSH, min=0) | R$ 44 |
| DeepSeek V4 Flash (15K calls) | R$ 62 |
| MiniMax+NVIDIA fallback | R$ 5 |
| Infra (API+Storage+PubSub) | R$ 127 |
| LLM Chatbots | R$ 48 |
| WhatsApp 5 bots (Cloud Run+SQL+Evolution) | R$ 556 |
| **TOTAL 500/dia** | **R$ 850** |
| Custo por Chamada | **R$ 0,06** |

### 1.000 chamadas/dia (30.000/mes)
| Componente | BRL/mes |
|---|---|
| Worker variavel | R$ 88 |
| DeepSeek (30K calls) | R$ 124 |
| Fallback + Infra + LLM Chat | R$ 185 |
| WhatsApp 5 bots | R$ 556 |
| **TOTAL 1.000/dia** | **R$ 972** |
| Custo por Chamada | **R$ 0,03** |

### 5.000 chamadas/dia (150.000/mes)
| Componente | BRL/mes |
|---|---|
| Worker variavel | R$ 441 |
| DeepSeek (150K calls) | R$ 622 |
| Fallback + Infra + LLM Chat | R$ 465 |
| WhatsApp 5 bots | R$ 556 |
| **TOTAL 5.000/dia** | **R$ 2.101** |
| Custo por Chamada | **R$ 0,01** |

## COMPARATIVO MERCADO (500 chamadas/dia)

| Solucao | BRL/chamada | vs Nos (R$ 0,06) |
|---|---|---|
| CallMiner | R$ 0,55-0,83 | 9-14x mais caro |
| Observe.AI | R$ 0,83-1,10 | 14-18x mais caro |
| Gong.io | R$ 0,44-0,66 | 7-11x mais caro |
| Chorus.ai | R$ 0,33-0,55 | 6-9x mais caro |
| **NOSSA (500/dia)** | **R$ 0,06** | — |
| **NOSSA (5.000/dia)** | **R$ 0,01** | — |

Economia vs CallMiner: R$ 9.500/mes. R$ 114.000/ano.

## BAYESIAN (Monte Carlo 10K, sem rateio)

| Cenario | Mediana (P50) | P10-P90 |
|---|---|---|
| 500/dia (só Monitoria) | R$ 226 | R$ 197-260 |
| 1.000/dia | R$ 320 | R$ 278-368 |
| 5.000/dia | R$ 1.263 | R$ 1.098-1.452 |

*Adicionar WhatsApp R$ 556 para custo total. Priors: Whisper LogNormal, tokens Uniform, concorrencia [1,2,2,2,3].*

## OTIMIZACOES FUTURAS

| Acao | Economia | Prazo |
|---|---|---|
| PUSH subscription (eliminar min=1) | -R$ 468/mes | 1-2 semanas |
| CUD 1 ano Cloud Run | -20% GCP | Imediato |
| DeepSeek V4 Flash token cache | -50% LLM | 1 mes |
| SaaS revenda R$ 0,50/chamada | Margem 88% | 3-6 meses |
