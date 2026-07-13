"""
Planilha de Custos — Projecao 500 chamadas/dia + Bayesian
Gera Excel e faz upload para Google Drive do projeto.
"""
import json, os, sys, random, math
from datetime import datetime, timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.utils import get_column_letter

# ─── GOOGLE DRIVE AUTH ───
TOKEN_PATH = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
OUTFILE = fr"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_500_Calls_Day.xlsx"
FOLDER_ID = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"

# ============================================================
# COST MODEL (Market References)
# ============================================================
CALLS_DAY = 500
CALLS_MONTH = CALLS_DAY * 30
AUDIO_MINUTES = 5  # avg audio length

# Cloud Run pricing (us-central1, Gen2, on-demand)
VCPU_HOUR = 0.024
GB_HOUR_MEM = 0.0025
WORKER_CPU = 4
WORKER_MEM = 4
API_CPU = 4
API_MEM = 8

WORKER_COST_HOUR = (WORKER_CPU * VCPU_HOUR) + (WORKER_MEM * GB_HOUR_MEM)
API_COST_HOUR = (API_CPU * VCPU_HOUR) + (API_MEM * GB_HOUR_MEM)

# Whisper timing (base model, ~0.1x real-time)
WHISPER_MULT = 0.1
LLM_SEC_PER_CALL = 3  # avg LLM response time
PROCESSING_MIN_PER_CALL = (AUDIO_MINUTES * WHISPER_MULT) + (LLM_SEC_PER_CALL / 60)

# Concurrency
CONCURRENCY = 2

# DeepSeek V4 Flash tokens
TOKENS_IN = 2500
TOKENS_OUT = 1200
DS_INPUT_COST_1M = 0.14
DS_OUTPUT_COST_1M = 0.28

# MiniMax fallback (5% of calls)
FALLBACK_PCT = 0.05
MM_COST_PER_CALL = 0.001  # estimated

# Firebase/Storage/PubSub fixed
FIRESTORE_COST = 3
STORAGE_COST = 5
PUBSUB_COST = 2
SECRETS_COST = 1
CLOUD_BUILD_COST = 3
REGISTRY_COST = 1

# Market benchmarks (per-call)
BENCHMARKS = {
    "CallMiner (enterprise)": (0.05, 0.15),
    "Observe.AI": (0.10, 0.20),
    "Gong.io (sales)": (0.08, 0.12),
    "Chorus.ai": (0.06, 0.10),
    "Cogito": (0.04, 0.08),
    "NOSSA SOLUCAO (PUSH)": (0.002, 0.003),
    "NOSSA SOLUCAO (PULL)": (0.005, 0.010),
}

# ============================================================
# BAYESIAN MODEL (Monte Carlo)
# ============================================================
def monte_carlo_simulation(calls_month, n_simulations=10000):
    """Run Monte Carlo with priors on cost per call."""
    # Prior distributions (Bayesian priors)
    # Whisper: avg 0.5-0.7 min per call with log-normal
    whisper_prior = lambda: max(0.3, random.lognormvariate(math.log(0.55), 0.2))
    # LLM token variation: 2000-3000 input, 800-1800 output
    llm_tokens_prior = lambda: (random.randint(2000, 3000), random.randint(800, 1800))
    # Concurrency variation
    conc_prior = lambda: random.choice([1, 2, 2, 2, 3])  # mostly 2

    costs_total = []
    costs_worker = []
    costs_llm = []
    costs_per_call = []

    for _ in range(n_simulations):
        w_min = whisper_prior()
        ti, to = llm_tokens_prior()
        conc = conc_prior()

        proc_min = (AUDIO_MINUTES * w_min) + (LLM_SEC_PER_CALL / 60)
        hours_day = (calls_month / 30) / (60 / proc_min * conc)
        worker_var_cost = hours_day * 30 * WORKER_COST_HOUR

        # LLM cost
        llm_cost = (ti * calls_month / 1_000_000 * DS_INPUT_COST_1M) + \
                   (to * calls_month / 1_000_000 * DS_OUTPUT_COST_1M)

        # Fixed + variable
        total = worker_var_cost + llm_cost + FIRESTORE_COST + STORAGE_COST + \
                PUBSUB_COST + SECRETS_COST + CLOUD_BUILD_COST + REGISTRY_COST

        costs_total.append(total)
        costs_worker.append(worker_var_cost)
        costs_llm.append(llm_cost)
        costs_per_call.append(total / calls_month)

    sorted_total = sorted(costs_total)
    sorted_per_call = sorted(costs_per_call)

    def ci(data, p):
        idx = int(p * len(data))
        return data[idx]

    return {
        "median_total": sorted_total[len(sorted_total)//2],
        "ci_10": ci(sorted_total, 0.10),
        "ci_25": ci(sorted_total, 0.25),
        "ci_75": ci(sorted_total, 0.75),
        "ci_90": ci(sorted_total, 0.90),
        "mean_total": sum(costs_total) / n_simulations,
        "median_per_call": sorted_per_call[len(sorted_per_call)//2],
        "ci_10_per_call": ci(sorted_per_call, 0.10),
        "ci_90_per_call": ci(sorted_per_call, 0.90),
        "mean_worker": sum(costs_worker) / n_simulations,
        "mean_llm": sum(costs_llm) / n_simulations,
        "simulations": n_simulations,
    }

# ============================================================
# RUN SIMULATIONS
# ============================================================
print("Running Bayesian Monte Carlo (10K simulations)...")
results_push = monte_carlo_simulation(CALLS_MONTH)

# PULL (min=1): add fixed worker cost
results_pull = dict(results_push)
fixed_worker = WORKER_COST_HOUR * 730  # always-on
results_pull["median_total"] += fixed_worker
results_pull["ci_10"] += fixed_worker
results_pull["ci_25"] += fixed_worker
results_pull["ci_75"] += fixed_worker
results_pull["ci_90"] += fixed_worker
results_pull["mean_total"] += fixed_worker
results_pull["median_per_call"] = results_pull["median_total"] / CALLS_MONTH
results_pull["ci_10_per_call"] = results_pull["ci_10"] / CALLS_MONTH
results_pull["ci_90_per_call"] = results_pull["ci_90"] / CALLS_MONTH
results_pull["mean_worker"] += fixed_worker

print(f"PUSH median: ${results_push['median_total']:.2f}/mo | per-call: ${results_push['median_per_call']:.6f}")
print(f"PULL median: ${results_pull['median_total']:.2f}/mo | per-call: ${results_pull['median_per_call']:.6f}")

# ============================================================
# CREATE EXCEL
# ============================================================
print("Creating Excel...")
wb = openpyxl.Workbook()

# Styles
hdr_font = Font(name='Calibri', bold=True, size=11, color='FFFFFF')
hdr_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
sub_fill = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
green_fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
yellow_fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
num_fmt = '#,##0.000'
pct_fmt = '0.0%'
usd_fmt = '$#,##0.00'
thin_border = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin'))
center = Alignment(horizontal='center', vertical='center', wrap_text=True)

def style_header(ws, row, cols):
    for c in range(1, cols+1):
        cell = ws.cell(row=row, column=c)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = center
        cell.border = thin_border

def style_row(ws, row, cols, fill=None):
    for c in range(1, cols+1):
        cell = ws.cell(row=row, column=c)
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        if fill:
            cell.fill = fill

# ─── SHEET 1: RESUMO ───
ws1 = wb.active
ws1.title = "Resumo"
ws1.sheet_properties.tabColor = "1F4E79"

ws1.merge_cells('A1:F1')
ws1.cell(row=1, column=1, value="Projecao de Custos — 500 Chamadas/Dia (15.000/mes)").font = Font(bold=True, size=14)
ws1.merge_cells('A2:F2')
ws1.cell(row=2, column=1, value=f"Gerado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')} | Referencia: GCP Pricing jul/2026, DeepSeek V4 Flash, MiniMax M3").font = Font(color='666666', size=9)

headers1 = ["Item", "Custo/mes (PUSH, min=0)", "Custo/mes (PULL, min=1)", "% do Total (PUSH)", "% do Total (PULL)", "Nota"]
for i, h in enumerate(headers1, 1):
    ws1.cell(row=4, column=i, value=h)
style_header(ws1, 4, 6)

# Cost items
items = [
    ("Worker Cloud Run (compute)", results_push["mean_worker"], results_pull["mean_worker"], "4vCPU/4GB, 500 calls/dia"),
    ("DeepSeek V4 Flash (LLM)", results_push["mean_llm"], results_push["mean_llm"], "2500 in + 1200 out tokens/call"),
    ("MiniMax M3 (fallback 5%)", FALLBACK_PCT * CALLS_MONTH * MM_COST_PER_CALL, FALLBACK_PCT * CALLS_MONTH * MM_COST_PER_CALL, "fallback quando DeepSeek falha"),
    ("API Cloud Run", API_COST_HOUR * 10, API_COST_HOUR * 10, "4vCPU/8GB, min=0, uso leve"),
    ("Firestore", FIRESTORE_COST, FIRESTORE_COST, "leituras/escritas"),
    ("Cloud Storage (audios temp)", STORAGE_COST, STORAGE_COST, "auto-delete apos processar"),
    ("Pub/Sub + Secret Manager", PUBSUB_COST + SECRETS_COST, PUBSUB_COST + SECRETS_COST, "mensageria + secrets"),
    ("Cloud Build + Registry", CLOUD_BUILD_COST + REGISTRY_COST, CLOUD_BUILD_COST + REGISTRY_COST, "deploys + imagens"),
]

push_total = results_push["mean_total"]
pull_total = results_pull["mean_total"]

for r, (name, push, pull, note) in enumerate(items, 5):
    ws1.cell(row=r, column=1, value=name).alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws1.cell(row=r, column=2, value=round(push, 2)).number_format = usd_fmt
    ws1.cell(row=r, column=3, value=round(pull, 2)).number_format = usd_fmt
    ws1.cell(row=r, column=4, value=push / push_total).number_format = pct_fmt
    ws1.cell(row=r, column=5, value=pull / pull_total).number_format = pct_fmt
    ws1.cell(row=r, column=6, value=note).alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    style_row(ws1, r, 6)

# Total row
tr = 5 + len(items)
ws1.cell(row=tr, column=1, value="TOTAL").font = Font(bold=True, size=12)
ws1.cell(row=tr, column=2, value=round(push_total, 2)).number_format = usd_fmt
ws1.cell(row=tr, column=2).font = Font(bold=True, color='006100')
ws1.cell(row=tr, column=3, value=round(pull_total, 2)).number_format = usd_fmt
ws1.cell(row=tr, column=3).font = Font(bold=True, color='9C0006')
style_row(ws1, tr, 6, PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid'))

# Per-call row
tr += 1
ws1.cell(row=tr, column=1, value="Custo por Chamada").font = Font(bold=True)
ws1.cell(row=tr, column=2, value=push_total / CALLS_MONTH).number_format = '$#,##0.0000'
ws1.cell(row=tr, column=2).font = Font(bold=True, color='006100')
ws1.cell(row=tr, column=3, value=pull_total / CALLS_MONTH).number_format = '$#,##0.0000'
ws1.cell(row=tr, column=3).font = Font(bold=True, color='9C0006')
style_row(ws1, tr, 6, PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid'))

# Per-day row
tr += 1
ws1.cell(row=tr, column=1, value="Custo por Dia (500 chamadas)")
ws1.cell(row=tr, column=2, value=push_total / 30).number_format = usd_fmt
ws1.cell(row=tr, column=3, value=pull_total / 30).number_format = usd_fmt
style_row(ws1, tr, 6)

# Column widths
ws1.column_dimensions['A'].width = 32
for c in 'BCDEF': ws1.column_dimensions[c].width = 16

# ─── SHEET 2: BAYESIAN ───
ws2 = wb.create_sheet("Bayesian")
ws2.sheet_properties.tabColor = "4472C4"

ws2.merge_cells('A1:E1')
ws2.cell(row=1, column=1, value="Modelo Bayesiano — Monte Carlo (10.000 simulacoes)").font = Font(bold=True, size=14)
ws2.merge_cells('A2:E2')
ws2.cell(row=2, column=1, value="Priors: Whisper ~ LogNormal(0.55, 0.2) | Tokens ~ Uniform(2000-3000 in, 800-1800 out) | Concurrency ~[1,2,2,2,3]").font = Font(color='666666', size=9)

# PUSH scenario
ws2.cell(row=4, column=1, value="Cenario PUSH (min=0)").font = Font(bold=True, size=11, color='006100')
bayes_headers = ["Estimativa", "Valor Total/mes", "Custo por Chamada", "Intervalo", ""]
styles = [
    ("Mediana (P50)", results_push["median_total"], results_push["median_per_call"], "50% probabilidade abaixo"),
    ("Media", results_push["mean_total"], results_push["mean_total"]/CALLS_MONTH, "media aritmetica"),
    ("P10 (otimista)", results_push["ci_10"], results_push["ci_10_per_call"], "10% probabilidade abaixo"),
    ("P25", results_push["ci_25"], results_push["ci_25"]/CALLS_MONTH, ""),
    ("P75", results_push["ci_75"], results_push["ci_75"]/CALLS_MONTH, ""),
    ("P90 (pessimista)", results_push["ci_90"], results_push["ci_90_per_call"], "90% probabilidade abaixo"),
]

for i, h in enumerate(bayes_headers, 1):
    ws2.cell(row=5, column=i, value=h)
style_header(ws2, 5, 5)

for r, (label, total, per_call, interval) in enumerate(styles, 6):
    ws2.cell(row=r, column=1, value=label)
    ws2.cell(row=r, column=2, value=round(total, 2)).number_format = usd_fmt
    ws2.cell(row=r, column=3, value=round(per_call, 6)).number_format = '$#,##0.000000'
    ws2.cell(row=r, column=4, value="")
    ws2.cell(row=r, column=5, value=interval).alignment = Alignment(horizontal='left')
    style_row(ws2, r, 5)

# PULL scenario
r_start = 6 + len(styles) + 1
ws2.cell(row=r_start, column=1, value="Cenario PULL (min=1)").font = Font(bold=True, size=11, color='9C0006')
pull_styles = [
    ("Mediana (P50)", results_pull["median_total"], results_pull["median_per_call"], "50% probabilidade abaixo"),
    ("Media", results_pull["mean_total"], results_pull["mean_total"]/CALLS_MONTH, "media aritmetica"),
    ("P10 (otimista)", results_pull["ci_10"], results_pull["ci_10_per_call"], "10% probabilidade abaixo"),
    ("P25", results_pull["ci_25"], results_pull["ci_25"]/CALLS_MONTH, ""),
    ("P75", results_pull["ci_75"], results_pull["ci_75"]/CALLS_MONTH, ""),
    ("P90 (pessimista)", results_pull["ci_90"], results_pull["ci_90_per_call"], "90% probabilidade abaixo"),
]

for i, h in enumerate(bayes_headers, 1):
    ws2.cell(row=r_start+1, column=i, value=h)
style_header(ws2, r_start+1, 5)

for r, (label, total, per_call, interval) in enumerate(pull_styles, r_start+2):
    ws2.cell(row=r, column=1, value=label)
    ws2.cell(row=r, column=2, value=round(total, 2)).number_format = usd_fmt
    ws2.cell(row=r, column=3, value=round(per_call, 6)).number_format = '$#,##0.000000'
    ws2.cell(row=r, column=4, value="")
    ws2.cell(row=r, column=5, value=interval).alignment = Alignment(horizontal='left')
    style_row(ws2, r, 5)

# Credible interval row
r_end = r_start + 2 + len(pull_styles) + 1
ws2.merge_cells(f'A{r_end}:E{r_end}')
ws2.cell(row=r_end, column=1, value="Intervalo de Credibilidade 80% (P10—P90): PUSH [$" + \
    f"{results_push['ci_10']:.2f} — ${results_push['ci_90']:.2f}] | PULL [${results_pull['ci_10']:.2f} — ${results_pull['ci_90']:.2f}]").font = Font(italic=True, color='666666')

ws2.column_dimensions['A'].width = 20
ws2.column_dimensions['B'].width = 18
ws2.column_dimensions['C'].width = 18
ws2.column_dimensions['D'].width = 15
ws2.column_dimensions['E'].width = 30

# ─── SHEET 3: MARKET BENCHMARKS ───
ws3 = wb.create_sheet("Benchmarks")
ws3.sheet_properties.tabColor = "548235"

ws3.merge_cells('A1:D1')
ws3.cell(row=1, column=1, value="Referencias de Mercado — Custo por Chamada (QA/Monitoria)").font = Font(bold=True, size=14)

bench_headers = ["Solucao", "Custo Min/Chamada", "Custo Max/Chamada", "Tipo"]
for i, h in enumerate(bench_headers, 1):
    ws3.cell(row=3, column=i, value=h)
style_header(ws3, 3, 4)

r = 4
for name, (lo, hi) in BENCHMARKS.items():
    is_ours = "NOSSA" in name
    ws3.cell(row=r, column=1, value=name).font = Font(bold=is_ours, color='006100' if is_ours else '000000')
    ws3.cell(row=r, column=2, value=lo).number_format = '$#,##0.000'
    ws3.cell(row=r, column=3, value=hi).number_format = '$#,##0.000'
    ws3.cell(row=r, column=4, value="Propria" if is_ours else "Mercado")
    style_row(ws3, r, 4, green_fill if is_ours else None)
    r += 1

# Bar chart
chart = BarChart()
chart.type = "col"
chart.title = "Custo por Chamada (USD) — Mercado vs Nossa Solucao"
chart.y_axis.title = "USD"
chart.x_axis.title = "Solucao"
data = Reference(ws3, min_col=2, min_row=3, max_row=r-1, max_col=3)
cats = Reference(ws3, min_col=1, min_row=4, max_row=r-1)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.style = 10
chart.width = 25
chart.height = 14
ws3.add_chart(chart, f"A{r+1}")

ws3.column_dimensions['A'].width = 28
ws3.column_dimensions['B'].width = 20
ws3.column_dimensions['C'].width = 20
ws3.column_dimensions['D'].width = 12

# ─── SHEET 4: PREMISSAS ───
ws4 = wb.create_sheet("Premissas")
ws4.sheet_properties.tabColor = "BF8F00"

ws4.merge_cells('A1:C1')
ws4.cell(row=1, column=1, value="Premissas do Calculo").font = Font(bold=True, size=14)

prem_headers = ["Parametro", "Valor", "Fonte"]
for i, h in enumerate(prem_headers, 1):
    ws4.cell(row=3, column=i, value=h)
style_header(ws4, 3, 3)

premissas = [
    ("Chamadas/dia", "500", "Usuario"),
    ("Chamadas/mes", "15.000", "Calculado"),
    ("Audio medio (minutos)", "5", "Estimado"),
    ("Modelo Whisper", "base (74MB, int8)", "faster-whisper"),
    ("Tempo Whisper (real-time)", "~0.1x", "Benchmark local"),
    ("Concorrencia worker", "2", "cloudbuild-worker.yaml"),
    ("Worker vCPU", "4", "cloudbuild-worker.yaml"),
    ("Worker RAM (GiB)", "4", "cloudbuild-worker.yaml"),
    ("Cloud Run vCPU/hr (us-central1)", "$0.024", "GCP Pricing jul/2026"),
    ("Cloud Run GiB-hr", "$0.0025", "GCP Pricing jul/2026"),
    ("DeepSeek V4 Flash input ($/1M)", "$0.14", "api-docs.deepseek.com"),
    ("DeepSeek V4 Flash output ($/1M)", "$0.28", "api-docs.deepseek.com"),
    ("Tokens input/call", "~2.500", "Estimado (prompt + contexto)"),
    ("Tokens output/call", "~1.200", "Estimado (JSON resposta)"),
    ("Fallback MiniMax %", "5%", "Estimado (taxa de falha DeepSeek)"),
    ("Simulacoes Monte Carlo", "10.000", "Configuracao"),
]

for r, (param, val, source) in enumerate(premissas, 4):
    ws4.cell(row=r, column=1, value=param).alignment = Alignment(horizontal='left')
    ws4.cell(row=r, column=2, value=val)
    ws4.cell(row=r, column=3, value=source).alignment = Alignment(horizontal='left')
    style_row(ws4, r, 3)

ws4.column_dimensions['A'].width = 35
ws4.column_dimensions['B'].width = 20
ws4.column_dimensions['C'].width = 28

# ─── SAVE ───
wb.save(OUTFILE)
print(f"Excel saved: {OUTFILE}")

# ─── UPLOAD TO GOOGLE DRIVE ───
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

with open(TOKEN_PATH) as f:
    creds_data = json.load(f)

creds = Credentials.from_authorized_user_info(creds_data, scopes=["https://www.googleapis.com/auth/drive"])
service = build("drive", "v3", credentials=creds)

file_metadata = {
    "name": "Custos_500_Calls_Day.xlsx",
    "parents": [FOLDER_ID],
}
media = MediaFileUpload(OUTFILE, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
uploaded = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()

print(f"Uploaded to Drive: {uploaded['webViewLink']}")
print(f"File ID: {uploaded['id']}")
print(f"Local: {OUTFILE}")
