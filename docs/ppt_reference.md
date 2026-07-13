# Custos OmniChannel — Infra + IA (Dev + Produção)

## CAMBIO: USD 1 = R$ 5,50 | MARGEM: 10%
## CUSTO TOTAL HOJE: R$ 1.153/mês

---

## CUSTOS REAIS HOJE (Julho 2026)

### INFRAESTRUTURA GCP — R$ 801/mês
| Serviço | BRL/mês |
|---|---|
| Cloud Run Worker (4vCPU/4GB, min=1, 730h/mês) | R$ 468 |
| API + Portal Cloud Run (min=0) | R$ 42 |
| Firestore (2 projetos) + Cloud Storage + PubSub + Secrets | R$ 145 |
| Cloud Build + Artifact Registry | R$ 24 |
| VM e2-small + IP WhatsApp | R$ 121 |

### IA — USO REAL PARA DESENVOLVIMENTO — R$ 201/mês
Este é o custo da inteligência artificial usada para criar e testar o produto.

| Uso | BRL/mês |
|---|---|
| DeepSeek V4 Flash — testes de prompts, engenharia, ajustes de qualidade | R$ 91 |
| MiniMax Plus — plano mensal fixo ($20/mês, créditos + fallback) | R$ 110 |

### IA — USO REAL NOS MÓDULOS EM PRODUÇÃO — R$ 151/mês
Este é o custo da IA rodando nos módulos ativos (Monitoria + Chatbots).

| Módulo | BRL/mês |
|---|---|
| DeepSeek — Monitoria de Chamadas (~20 chamadas/dia, diarização + QA) | R$ 12 |
| DeepSeek — Chatbots WhatsApp (5 bots simultâneos, 200 mensagens/dia) | R$ 48 |
| DeepSeek — Extras (testes URA, overflow, melhorias contínuas) | R$ 91 |

**RESUMO: GCP R$ 801 + IA Dev R$ 201 + IA Prod R$ 151 = R$ 1.153/mês**

---

## PROJEÇÃO PRINCIPAL: 500 CHAMADAS POR DIA (15.000/mês)

ESTE É O CENÁRIO-ALVO. Primeiro cliente BPO com 500 chamadas diárias.

| Categoria | BRL/mês |
|---|---|
| GCP (Worker escala + Infra + WhatsApp 5 bots) | R$ 734 |
| IA Desenvolvimento (estabilizado) | R$ 201 |
| IA Produção — DeepSeek Monitoria (15.000 chamadas × 3.700 tokens) | R$ 115 |
| IA Produção — DeepSeek Chatbots (fixo) | R$ 48 |
| IA Produção — MiniMax fallback (5%) | R$ 5 |
| IA Produção — Extras (URA dev, overflow) | R$ 100 |
| **TOTAL** | **R$ 1.210** |
| **CUSTO POR CHAMADA** | **R$ 0,08** |

Comparação com 1.000 e 5.000 chamadas/dia:
- 1.000 chamadas/dia: R$ 1.318/mês, R$ 0,04/chamada
- 5.000 chamadas/dia: R$ 2.188/mês, R$ 0,01/chamada

---

## COMPARATIVO: OPERADORAS BRASILEIRAS

### Nosso custo de QA automatizado vs QA humano tradicional

| Empresa | Modelo de QA | Custo por Chamada |
|---|---|---|
| **Teleperformance Brasil** | QA humano — analistas escutam amostras (2-5% das chamadas) | R$ 0,50 a R$ 1,00 |
| **Atento Brasil** | Monitoria manual — equipe dedicada de qualidade | R$ 0,40 a R$ 0,80 |
| **NOSSA SOLUÇÃO (500 chamadas/dia)** | 100% automatizado — DeepSeek V4 Flash analisa CADA chamada | **R$ 0,08** |

Vantagem da nossa solução:
- Custo 5-12x menor que QA humano
- Cobertura de 100% das chamadas (vs 2-5% do modelo tradicional)
- Análise em tempo real, sem atraso humano
- Relatórios automáticos por chamada

---

## CAPACIDADE DE NEGÓCIO

Nossa plataforma hoje suporta:
- **500 a 1.000 chamadas por dia** sem gargalo
- Pico de até **16.000 chamadas/dia** com auto-scaling
- **5 chatbots WhatsApp** simultâneos
- Processamento **100% automatizado** — zero intervenção humana
- Entrega de relatório completo em **menos de 2 minutos** por chamada

---

## ROADMAP — Próximos Passos

| Fase | Quando | Ação | Resultado |
|---|---|---|---|
| **Estabilizar** | Jul-Ago 2026 | Otimizar worker (PUSH subscription) | Economia de R$ 468/mês |
| **Vender** | Set 2026 | Fechar primeiro cliente BPO (500 chamadas/dia) | Validação de mercado |
| **Escalar** | Out-Dez 2026 | 1.000+ chamadas/dia, segundo cliente | Custo cai para R$ 0,04/chamada |
| **Expandir** | Jan-Mar 2027 | Lançar URA + Voz (TTS) | Portfólio completo |
| **SaaS** | Abr 2027+ | Plataforma multi-cliente, 5.000+ chamadas/dia | Margem 85%+ |

---

## PIX QR CODE (Último Slide)

Incluir QR Code PIX com CPF 047.799.777-54 e a frase:
"Segue meu PIX para apoiar o desenvolvimento do OmniChannel: CPF 047.799.777-54 — Vinícius Brito"
