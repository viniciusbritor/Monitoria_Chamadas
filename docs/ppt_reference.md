# Projecao de Custos - Ecossistema OmniChannel

## Estrutura do Ecossistema
O OmniChannel possui 4 modulos com diferentes estagios de maturidade:

1. **MONITORIA DE CHAMADAS** (ativo) - Transcricao e avaliacao QA via IA
2. **WHATSAPP AGENTE** (ativo) - 5 chatbots simultaneos com LLM
3. **URA** (projecao) - Unidade de Resposta Audivel / IVR inteligente
4. **VOZ** (projecao) - Sintese de voz / TTS para atendimento

## Modelo de Precificacao
Todos os modulos usam infraestrutura GCP (Cloud Run, Firestore) com:
- Computacao sob demanda (min=0, escala a zero quando ocioso)
- LLM via DeepSeek V4 Flash ($0.14/1M tokens input, $0.28/1M tokens output) com fallback MiniMax M3
- Folga de seguranca de 25% aplicada a todos os valores
- Rateio de custos de desenvolvimento: $6,000 investidos, diluidos em 12 meses ($500/mes)

## Cenarios de Volume
Tres cenarios projetados: 500, 1,000 e 5,000 chamadas/dia.

## MONITORIA DE CHAMADAS - Custos Mensais (PUSH, min=0)

### 500 chamadas/dia (15,000/mes)
- Worker Cloud Run (4vCPU/4GB): $10/mes (variavel)
- DeepSeek LLM: $13/mes (2,500 tokens in + 1,200 tokens out)
- API + Firestore + Storage + PubSub: $16/mes
- Rateio Desenvolvimento: $500/mes
- Subtotal Monitoria: ~$539/mes | $0.036/chamada

### 1,000 chamadas/dia (30,000/mes)
- Worker Cloud Run: $21/mes
- DeepSeek LLM: $27/mes
- Infra: $20/mes
- Rateio: $500/mes
- Subtotal: ~$568/mes | $0.019/chamada

### 5,000 chamadas/dia (150,000/mes)
- Worker Cloud Run: $103/mes
- DeepSeek LLM: $134/mes
- Infra: $51/mes
- Rateio: $500/mes
- Subtotal: ~$788/mes | $0.005/chamada

## WHATSAPP AGENTE (5 Chatbots)
- 5x Cloud Run agentes (1vCPU/1GiB): $38/mes
- Cloud SQL Postgres: $13/mes
- Evolution API Cloud Run: $50/mes
- Firestore extra: $4/mes
- DeepSeek LLM (200 msg/dia x 5): $10/mes
- Total Chatbots: ~$113/mes (fixo, nao escala com calls)

## URA - Unidade de Resposta Audivel (Projecao)
Modulo de IVR inteligente com:
- Speech-to-Text via Google STT ou Whisper ($0.002/call)
- Navegacao IVR/DTMF via LLM ($0.0005/call)
- Roteamento de chamadas ($0.001/call)
- Infra Cloud Run: $25/mes base

### Custos por Cenario
- 500 calls/dia: $78/mes | $0.0052/chamada
- 1,000 calls/dia: $130/mes | $0.0043/chamada
- 5,000 calls/dia: $550/mes | $0.0037/chamada

## VOZ - Sintese de Voz (Projecao)
Modulo de TTS com:
- Sintese de voz MiniMax TTS ou ElevenLabs ($0.005/call para 500 caracteres)
- Voice cloning/styling ($0.002/call)
- Infra Cloud Run: $19/mes base

### Custos por Cenario
- 500 calls/dia: $129/mes | $0.0086/chamada
- 1,000 calls/dia: $239/mes | $0.0080/chamada
- 5,000 calls/dia: $1,109/mes | $0.0074/chamada

## TOTAIS CONSOLIDADOS (com folga 25% + rateio dev)

### 500 chamadas/dia
- Monitoria: $539/mes
- Chatbots: $113/mes
- URA (projecao): $78/mes
- VOZ (projecao): $129/mes
- TOTAL: $859/mes (USD) | R$ 4,725/mes (BRL)

### 1,000 chamadas/dia
- Monitoria: $568/mes
- Chatbots: $113/mes
- URA (projecao): $130/mes
- VOZ (projecao): $239/mes
- TOTAL: $1,050/mes (USD) | R$ 5,775/mes (BRL)

### 5,000 chamadas/dia
- Monitoria: $788/mes
- Chatbots: $113/mes
- URA (projecao): $550/mes
- VOZ (projecao): $1,109/mes
- TOTAL: $2,560/mes (USD) | R$ 14,080/mes (BRL)

## Bayesian Monte Carlo (P50, com folga 25%)
Simulacao com 10,000 iteracoes, priors:
- Whisper timing: LogNormal(0.55, 0.2)
- Tokens LLM: Uniform(2000-3000 input, 800-1800 output)
- Concorrencia: [1,2,2,2,3]

Intervalo de credibilidade 80% (P10-P90) para Monitoria:
- 500 calls/dia: $43 - $54/mes (variavel) + $500 rateio
- 1,000 calls/dia: $63 - $80/mes + $500 rateio
- 5,000 calls/dia: $247 - $320/mes + $500 rateio

## Comparativo de Mercado (custo por chamada)
- CallMiner (enterprise): $0.05 - $0.15/chamada
- Observe.AI: $0.10 - $0.20/chamada
- Gong.io: $0.08 - $0.12/chamada
- Chorus.ai: $0.06 - $0.10/chamada
- Cogito: $0.04 - $0.08/chamada
- NOSSA SOLUCAO (PUSH): $0.004 - $0.036/chamada (6-15x mais barato)

## Otimizacoes Futuras
- PUSH subscription (elimina min=1): -40% no custo worker
- DeepSeek V4 Flash (primario): $0.14/1M input, o mais barato do mercado
- Compromisso de uso 1 ano (CUD): -20% em Cloud Run
- Potencial de revenda como SaaS: precificar a $0.05/chamada (margem ~90% sobre custo)
