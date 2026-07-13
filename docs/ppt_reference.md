# Custos OmniChannel — Infra + IA (Dev + Produção)

## CAMBIO: USD 1 = R$ 5,50 | MARGEM SEGURANCA: 10%

## CUSTO HOJE — 3 Pilares

### 1. INFRAESTRUTURA GCP (R$ 801/mês)
| Servico | BRL/mes |
|---|---|
| Worker Cloud Run (4vCPU/4GB, min=1, 730h/mes) | R$ 468 |
| API + Portal Cloud Run (min=0) | R$ 42 |
| Firestore + Storage + PubSub + Secrets | R$ 145 |
| Cloud Build + Artifact Registry | R$ 24 |
| VM e2-small + IP (WhatsApp) | R$ 121 |

### 2. IA — DESENVOLVIMENTO (R$ 201/mês)
| Uso | BRL/mes |
|---|---|
| DeepSeek tokens — testes, prompts, engenharia | R$ 91 |
| MiniMax Plus — plano fixo (fallback + créditos) | R$ 110 |

### 3. IA — PRODUCAO NOS MODULOS (R$ 151/mês)
| Modulo | BRL/mes |
|---|---|
| DeepSeek — Monitoria de Chamadas (~20 calls/dia) | R$ 12 |
| DeepSeek — Chatbots WhatsApp (5 bots, 200 msg/dia) | R$ 48 |
| DeepSeek — Extras (URA dev, overflow, testes prod) | R$ 91 |

**TOTAL HOJE: R$ 1.153/mês** (GCP R$ 801 + IA Dev R$ 201 + IA Prod R$ 151)

## ESCALA — Custo por Volume de Chamadas

A IA de desenvolvimento estabiliza (~R$ 201/mês). A IA de produção escala com volume de chamadas. GCP otimiza com uso.

### 500 chamadas/dia (15.000/mês)
| Categoria | BRL/mes |
|---|---|
| GCP (Worker+Infra+WhatsApp) | R$ 734 |
| IA Desenvolvimento (estabilizado) | R$ 201 |
| IA Produção (DeepSeek escala + MiniMax fallback) | R$ 209 |
| **TOTAL** | **R$ 1.144** |
| **Custo por Chamada** | **R$ 0,08** |

### 1.000 chamadas/dia (30.000/mês)
| Categoria | BRL/mes |
|---|---|
| GCP | R$ 779 |
| IA Desenvolvimento | R$ 201 |
| IA Produção | R$ 273 |
| **TOTAL** | **R$ 1.252** |
| **Custo por Chamada** | **R$ 0,04** |

### 5.000 chamadas/dia (150.000/mês)
| Categoria | BRL/mes |
|---|---|
| GCP | R$ 1.131 |
| IA Desenvolvimento | R$ 201 |
| IA Produção | R$ 790 |
| **TOTAL** | **R$ 2.122** |
| **Custo por Chamada** | **R$ 0,01** |

## COMPARATIVO — Operadoras Nacionais (Brasil)

### Custo de QA/Monitoria por Chamada

| Empresa | Perfil | Modelo QA | Custo por Chamada |
|---|---|---|---|
| **Teleperformance** | BPO global, 80 mil func. no Brasil | QA humano — analistas escutam amostras de chamadas | **R$ 0,50–1,00** |
| **Atento** | Maior BPO da América Latina, 90 mil func. BR | Monitoria manual de chamadas, equipe dedicada | **R$ 0,40–0,80** |
| **Liq (Bertelsmann)** | BPO digital, 40 mil func. BR | Plataforma própria + terceiros para QA | **R$ 0,35–0,70** |
| **Algar Tech** | BPO médio, 20 mil func. BR | Soluções híbridas, parte manual parte automatizada | **R$ 0,30–0,60** |
| **NOSSA SOLUÇÃO** | OmniChannel, IA automatizada | 100% automatizado — DeepSeek V4 Flash analisa cada chamada | **R$ 0,08** |

**Nossa solução é 5-13x mais barata que o QA humano das operadoras nacionais.**
Além da economia, entregamos 100% de cobertura (vs 2-5% de amostragem do modelo humano).

Para uma operação de 500 chamadas/dia, a economia vs Teleperformance é de aproximadamente R$ 10.000/mês.

## CAPACIDADE ATUAL E CRESCIMENTO

Nossa infraestrutura atual suporta:
- 500 a 1.000 chamadas/dia sem gargalo
- Pico de até 16.000 chamadas/dia com auto-scaling
- 5 chatbots WhatsApp simultâneos
- Processamento 100% automatizado — sem intervenção humana

Diferencial competitivo:
- Cobertura de 100% das chamadas (concorrentes auditam 2-5%)
- Análise em 3 fases (apresentação, resolução, fechamento)
- Sentimentos com probabilidade por fase
- Relatórios em tempo real

## ROADMAP DE NEGÓCIO

| Fase | Quando | O que | Impacto |
|---|---|---|---|
| **Fase 1 — Estabilização** | Jul-Ago 2026 | Migrar worker para PUSH subscription | Reduz custo GCP em R$ 468/mês |
| **Fase 2 — Aquisição** | Set-Out 2026 | Primeiro cliente BPO (operação de 500 chamadas/dia) | Receita recorrente, validação de mercado |
| **Fase 3 — Expansão** | Nov-Dez 2026 | Segundo cliente, escala para 1.000 chamadas/dia | Custo por chamada cai para R$ 0,04 |
| **Fase 4 — Módulos** | Jan-Mar 2027 | Lançamento URA inteligente + Voz (TTS) | Portfólio completo para BPOs |
| **Fase 5 — Escala** | Abr 2027+ | SaaS multi-cliente, 5.000+ chamadas/dia | Custo marginal próximo de zero |

Modelo de receita: cobrar por chamada analisada (R$ 0,50/chamada) — margem de ~85% sobre custo operacional de R$ 0,08.

## OTIMIZACOES IMEDIATAS

| Acao | Economia | Prazo |
|---|---|---|
| PUSH subscription (eliminar min=1 worker) | -R$ 468/mês | 1-2 semanas |
| Compromisso de Uso Cloud Run 1 ano | -20% no GCP | Imediato |
| Otimizar cache de tokens DeepSeek | -30% no custo LLM | 1 mês |
