"""
Cost Model — Fonte unica de verdade para todos os materiais (PPTX + Excel).
Importado por build_pptx_mckinsey.py e exec_summary.py.
Valores identicos garantidos em ambos.
"""
# ═══════ CONSTANTS ═══════
BRL = 5.50
SLACK = 1.10
MM_PLAN = 20  # MiniMax Plus fixed plan

# ═══════ HELPERS ═══════
def R(v):
    """Apply 10% safety margin"""
    return round(v * SLACK, 2)

# ═══════ COST DATA ═══════

# --- GCP Infrastructure (monthly, USD with 10% margin) ---
INFRA = [
    ("Cloud Run Worker (4vCPU/4GB, min=1, 730h/mes)", R(77.38)),
    ("API + Portal Cloud Run (min=0, idle)", R(7.00)),
    ("Firestore (2 projetos: chamadas + WhatsApp)", R(15.00)),
    ("Cloud Storage (audios temporarios + backups)", R(6.00)),
    ("Pub/Sub + Secret Manager (10 secrets)", R(3.00)),
    ("Cloud Build + Artifact Registry (CI/CD)", R(4.00)),
    ("VM e2-small + IP WhatsApp (Evolution API)", R(20.00)),
]

# --- AI: Development ---
AI_DEV = [
    ("DeepSeek V4 Flash — Desenvolvimento (testes, prompts, engenharia)", R(15.00)),
    ("MiniMax Plus — Plano fixo mensal ($20/mes, fallback + creditos)", MM_PLAN),
]

# --- AI: Production modules ---
AI_PROD = [
    ("DeepSeek V4 Flash — Monitoria de Chamadas (~20 chamadas/dia)", R(2.00)),
    ("DeepSeek V4 Flash — Chatbots WhatsApp (5 bots, 200 msg/dia)", R(8.00)),
    ("DeepSeek V4 Flash — Extras (URA dev, overflow, melhorias)", R(15.00)),
]

# --- Totals ---
GCP_TOTAL = sum(v for _, v in INFRA)
AI_DEV_TOTAL = sum(v for _, v in AI_DEV)
AI_PROD_TOTAL = sum(v for _, v in AI_PROD)
TOTAL_HOJE = GCP_TOTAL + AI_DEV_TOTAL + AI_PROD_TOTAL

# ═══════ PROJECTIONS ═══════

def ds_token_cost(calls_per_month):
    """DeepSeek token cost for N calls/month (2500 in + 1200 out tokens)"""
    return (calls_per_month * 2500 / 1_000_000 * 0.14) + \
           (calls_per_month * 1200 / 1_000_000 * 0.28)

def build_scenario(calls_per_day):
    """Build full cost projection for a given call volume."""
    cpm = calls_per_day * 30
    ds_mono = ds_token_cost(cpm)
    ds_chat = 8.80  # fixed chatbot LLM cost
    mm_token_fallback = ds_mono * 0.05 * 0.75  # 5% fallback at 75% price ratio
    wa_infra = R(91.00)  # WhatsApp 5 bots infra (Cloud Run + SQL + Evolution)

    s = {
        "calls_day": calls_per_day,
        "calls_month": cpm,
        "worker": R(7.29 * calls_per_day / 500),
        "ds_mono": R(ds_mono),
        "mm_plan": MM_PLAN,
        "mm_token": R(mm_token_fallback),
        "ds_chat": R(ds_chat),
        "ds_dev": R(15.00),
        "ds_extra": R(15.00),
        "infra": R(23.10),
        "wa_infra": wa_infra,
    }

    # Grouped costs
    s["gcp"] = s["worker"] + s["infra"] + s["wa_infra"]
    s["ai_dev"] = s["mm_plan"] + s["ds_dev"]
    s["ai_prod"] = s["ds_mono"] + s["mm_token"] + s["ds_chat"] + s["ds_extra"]

    # Totals
    s["total_usd"] = s["gcp"] + s["ai_dev"] + s["ai_prod"]
    s["total_brl"] = s["total_usd"] * BRL
    s["cost_per_call_brl"] = s["total_brl"] / cpm

    return s

# Pre-compute all scenarios
SCENARIOS = {
    500: build_scenario(500),
    1000: build_scenario(1000),
    5000: build_scenario(5000),
}

# ═══════ BENCHMARKS ═══════
BENCHMARKS_BR = [
    ("Teleperformance Brasil",
     "BPO global, 80 mil funcionarios no Brasil",
     "QA humano — analistas escutam amostras (2-5% das chamadas)",
     0.50, 1.00),
    ("Atento Brasil",
     "Maior BPO da America Latina, 90 mil func. BR",
     "Monitoria manual — equipe dedicada de qualidade",
     0.40, 0.80),
]

# ═══════ ROADMAP ═══════
ROADMAP = [
    ("JUL-AGO 2026", "Estabilizar", "Otimizar worker\n(PUSH subscription)", f"Economia de\nR$ 468/mes", "#002B4D"),
    ("SET 2026", "Vender", "Fechar 1o cliente\nBPO (500 chamadas/dia)", "Validacao\nde mercado", "#0073BE"),
    ("OUT-DEZ 2026", "Escalar", "1.000+ chamadas/dia\nSegundo cliente", "Custo cai para\nR$ 0,04/chamada", "#005B96"),
    ("JAN-MAR 2027", "Expandir", "Lancar URA + Voz\n(portfolio completo)", "Novos modulos\nde receita", "#006100"),
    ("ABR 2027+", "SaaS", "Plataforma multi-cliente\n5.000+ chamadas/dia", "Margem 85%+\nReceita recorrente", "#D35400"),
]

# ═══════ PREMISSES TABLE ═══════
PREMISSAS = [
    ("Cambio USD/BRL", "R$ 5,50", "Cotacao Julho 2026"),
    ("Margem de seguranca", "10% sobre todos os valores", "Politica conservadora"),
    ("LLM Primario", "DeepSeek V4 Flash", "Pay-per-token: $0,14/1M input + $0,28/1M output"),
    ("LLM Fallback", "MiniMax M3 Plus", f"Plano fixo ${MM_PLAN}/mes (creditos + fallback 5%)"),
    ("Infraestrutura Cloud", "Google Cloud Run (us-central1)", "Gen2, 4vCPU/4GB worker, min=1"),
    ("Audio medio por chamada", "5 minutos", "Formato WAV, mono, 16kHz"),
    ("Modelo Transcricao", "Whisper base (74MB, int8)", "faster-whisper, ~0.1x tempo real"),
    ("Projeto GCP Principal", "coherence-ominichannel-fs", "Cloud Run + Firestore + Pub/Sub + GCS + Compute Engine"),
]

# ═══════ CAPACITY ═══════
CAPACITY = [
    ("500-1.000", "Chamadas por dia\nsem gargalo", "Capacidade atual comprovada\nWorker 4vCPU/4GB, concurrency=2"),
    ("16.000", "Pico maximo diario\ncom auto-scaling", "Cloud Run escala ate 4 instancias\nProcessamento paralelo automatico"),
    ("< 2 min", "Tempo de resposta\npor chamada", "Upload -> Transcricao -> Analise\nResultado completo em tempo real"),
]

DIFFERENTIALS = [
    "Cobertura de 100% das chamadas vs 2-5% do modelo tradicional de QA humano",
    "Analise em 3 fases: Apresentacao, Resolucao e Fechamento - com probabilidade de sentimentos",
    "Relatorios automaticos com nota QA, NPS e checklist de conformidade (POP)",
    "Processamento 100% automatizado - zero intervencao humana do upload ao relatorio final",
]
