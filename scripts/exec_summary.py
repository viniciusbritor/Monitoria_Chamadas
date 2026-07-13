"""
Planilha Custos OmniChannel — LLM Planos Reais (MiniMax Plus + DeepSeek)
Infra GCP + MiniMax Plano + DeepSeek Pay-per-token + Escala
"""
import json, os
from datetime import datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_OmniChannel_Executivo.xlsx"
FID = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"
TKN = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")
BRL = 5.50

# ─── LLM PLAN COSTS ───
MM_PLUS = 20      # MiniMax Plus — $20/mes fixo (créditos inclusos)
MM_MAX = 50       # MiniMax MAX — $50/mes (possível upgrade futuro)
DS_NO_PLAN = True # DeepSeek não tem plano — pay-per-token puro
DS_CURRENT = 40   # Custo real atual DeepSeek ~$40/mês

# ─── Styles ───
DB, GR, OR, LG, BL = "1F4E79", "C6EFCE", "FCE4D6", "F5F5F5", "4472C4"
hf = Font(name='Calibri',bold=True,size=11,color='FFFFFF')
hd = PatternFill(start_color=DB,end_color=DB,fill_type='solid')
gf = PatternFill(start_color=GR,end_color=GR,fill_type='solid')
of = PatternFill(start_color=OR,end_color=OR,fill_type='solid')
lf = PatternFill(start_color=LG,end_color=LG,fill_type='solid')
bf = PatternFill(start_color=BL,end_color=BL,fill_type='solid')
th = Border(left=Side('thin'),right=Side('thin'),top=Side('thin'),bottom=Side('thin'))
C = Alignment(horizontal='center',vertical='center',wrap_text=True)
L = Alignment(horizontal='left',vertical='center',wrap_text=True)

def W(ws,r,c,v,fmt=None,bold=False,color=None,fill=None,align=None,sz=None):
    cl=ws.cell(row=r,column=c,value=v)
    cl.border=th; cl.alignment=align or C
    if fmt: cl.number_format=fmt
    if bold: cl.font=Font(bold=True,size=sz or 11,color=color or '333333')
    if fill: cl.fill=fill
    if sz and not bold: cl.font=Font(size=sz)
    return cl

def H(ws,r,data):
    for c,v in enumerate(data,1):
        cl=ws.cell(row=r,column=c,value=v)
        cl.font=hf; cl.fill=hd; cl.alignment=C; cl.border=th

SL = 1.10
def R(v): return round(v*SL,2)

# ══════ DATA ══════

# --- GCP INFRA (recorrente) ---
INFRA = [
    ("Cloud Run — Worker (4vCPU/4GB, min=1)", R(77.38)),
    ("Cloud Run — API + Portal (min=0)", R(7.00)),
    ("Firestore (2 projetos)", R(15.00)),
    ("Cloud Storage (audios + backups)", R(6.00)),
    ("Pub/Sub + Secret Manager", R(3.00)),
    ("Cloud Build + Artifact Registry", R(4.00)),
    ("Compute Engine VM e2-small (WhatsApp)", R(17.00)),
    ("IP Estatico", R(3.00)),
]
INFRA_T = sum(v for _,v in INFRA)

# --- LLM: PLANOS + TOKENS ---
# MiniMax — plano fixo mensal (cobre fallback e créditos)
# DeepSeek — pay-per-token (primário para todos workloads)

# HOJE (uso atual, ~20 chamadas/dia Monitoria + Chatbots)
LLM_HOJE = [
    ("MiniMax Plus — Plano fixo mensal", MM_PLUS, "Cobertura fallback + créditos inclusos"),
    ("DeepSeek V4 Flash — Tokens (uso atual)", R(DS_CURRENT), "Pay-per-token ~$0.14/1M in + $0.28/1M out"),
]
LLM_HOJE_T = sum(v for _,v,_ in LLM_HOJE)

# PROJEÇÕES
# DeepSeek token costs at scale (primary for ALL: Monitoria + Chat + URA)
def ds_cost(calls_month):
    """DeepSeek cost for N calls/month with 2500 in + 1200 out tokens"""
    tokens_in = calls_month * 2500
    tokens_out = calls_month * 1200
    return (tokens_in / 1_000_000 * 0.14) + (tokens_out / 1_000_000 * 0.28)

S = {}
for c in [500, 1000, 5000]:
    cm = c * 30
    ds = ds_cost(cm)  # DeepSeek token cost
    ds_chat = 8.80    # Chatbot LLM cost (200 msg/dia x 5 bots x 1000 tokens)
    mm_token = ds * 0.05 * 0.75  # MiniMax fallback 5% of calls, 75% of DeepSeek price ratio
    wa = R(91.00)     # WhatsApp infra
    
    S[c] = {
        "worker": R(7.29 * c / 500),
        "ds_tokens": R(ds),
        "mm_plano": MM_PLUS,
        "mm_tokens": R(mm_token),
        "ds_chat": R(ds_chat),
        "infra": R(23.10),
        "wa_infra": wa,
    }
    s = S[c]
    s["total"] = s["worker"] + s["ds_tokens"] + s["mm_plano"] + s["mm_tokens"] + s["ds_chat"] + s["infra"] + s["wa_infra"]
    s["pc"] = s["total"] * BRL / cm

# COMPARATIVO
OURS = S[500]["pc"]
BENCH = [("CallMiner",0.55,0.83),("Observe.AI",0.83,1.10),("Gong.io",0.44,0.66),("Chorus.ai",0.33,0.55)]

# ══════ BUILD ══════
wb = Workbook()

# ── SHEET 1: RESUMO ──
ws = wb.active; ws.title="Resumo"; ws.sheet_properties.tabColor=DB
ws.merge_cells('A1:F1')
ws.cell(row=1,column=1,value="CUSTOS OMNI CHANNEL · GCP + LLM (Planos + Tokens)").font=Font(bold=True,size=16,color=DB)
ws.merge_cells('A2:F2')
ws.cell(row=2,column=1,value=f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} | R${BRL:.2f}/USD | Margem 10% | MiniMax Plus ${MM_PLUS}/mês | DeepSeek pay-per-token").font=Font(color='666666',size=9)

# LLM Plan Info
ws.cell(row=4,column=1,value="MODELO DE CUSTO LLM").font=Font(bold=True,size=13,color=DB)
ws.merge_cells('A4:F4')
H(ws,5,["Provedor","Plano","Custo Fixo/mês","Tokens (primário)","Tokens (fallback)","Avaliação"])

llm_rows = [
    ("DeepSeek V4 Flash", "Pay-per-token", "$0/mês", "PRIMÁRIO — Monitoria + Chat + URA", "—", "Certo. Mais barato por token. Sem plano fixo."),
    ("MiniMax M3", "Plus ($20/mês)", "$20/mês (R$ 110)", "—", "Fallback 5% chamadas", "Correto. Plano cobre fallback. Monitorar se precisa MAX."),
    ("MiniMax M3 (MAX)", "MAX ($50/mês)", "$50/mês (R$ 275)", "—", "Fallback + mais créditos", "Avaliar migração se uso exceder Plus."),
]
for ri,(prov,plan,fixed,prim,fall,av) in enumerate(llm_rows,6):
    W(ws,ri,1,prov,align=L,bold=True,color='006100' if "DeepSeek" in prov else DB)
    W(ws,ri,2,plan,align=L,sz=10)
    W(ws,ri,3,fixed,align=L,sz=10)
    W(ws,ri,4,prim,align=L,sz=9)
    W(ws,ri,5,fall,align=L,sz=9)
    W(ws,ri,6,av,align=L,sz=9,color='006100' if "Certo" in av else '666666')
    for c2 in range(1,7):
        if "DeepSeek" in prov: ws.cell(row=ri,column=c2).fill=gf
    ws.row_dimensions[ri].height=26

# HOJE
r=len(llm_rows)+7
ws.cell(row=r,column=1,value="HOJE — Infra GCP + LLM").font=Font(bold=True,size=13,color=DB)
ws.merge_cells(f'A{r}:F{r}'); r+=1
H(ws,r,["Serviço","USD/mês","BRL/mês","%","Categoria"]); r+=1

for nm,usd in INFRA:
    W(ws,r,1,nm,align=L,sz=9); W(ws,r,2,usd,'$#,##0'); W(ws,r,3,usd*BRL,'R$ #,##0')
    W(ws,r,4,usd/(INFRA_T+LLM_HOJE_T),'0%',sz=9); W(ws,r,5,"GCP",sz=9)
    ws.row_dimensions[r].height=20; r+=1

for nm,usd,note in LLM_HOJE:
    W(ws,r,1,nm,align=L,sz=9); W(ws,r,2,usd,'$#,##0'); W(ws,r,3,usd*BRL,'R$ #,##0')
    W(ws,r,4,usd/(INFRA_T+LLM_HOJE_T),'0%',sz=9); W(ws,r,5,"LLM",sz=9)
    ws.row_dimensions[r].height=20; r+=1

TOT = INFRA_T + LLM_HOJE_T
W(ws,r,1,"TOTAL HOJE",bold=True,sz=13,fill=gf)
W(ws,r,2,TOT,'$#,##0',bold=True,fill=gf)
W(ws,r,3,TOT*BRL,'R$ #,##0',bold=True,sz=14,fill=gf)
W(ws,r,4,"100%",bold=True,fill=gf); W(ws,r,5,"",fill=gf)

# SCALE
r+=2
ws.merge_cells(f'A{r}:F{r}')
ws.cell(row=r,column=1,value="ESCALA — Custo por Volume de Chamadas (DeepSeek primário + MiniMax Plus fallback)").font=Font(bold=True,size=13,color=DB)
r+=1
H(ws,r,["Cenário","Chamadas/mês","Custo GCP+LLM/mês","Custo/Chamada","vs Mercado",""])

scenarios = [(10,TOT,None),(500,S[500]["total"],OURS),(1000,S[1000]["total"],S[1000]["pc"]),(5000,S[5000]["total"],S[5000]["pc"])]
labels = ["Atual","500/dia","1.000/dia","5.000/dia"]

for ci,(c,usd,pc) in enumerate(scenarios,r+1):
    f=gf if c>1000 else (lf if c==10 else None)
    W(ws,ci,1,labels[(10,500,1000,5000).index(c)],align=L,bold=True,sz=11)
    W(ws,ci,2,c*30,'#,##0',bold=True)
    W(ws,ci,3,usd*BRL,'R$ #,##0',bold=True,sz=13 if c>10 else 12,fill=f)
    W(ws,ci,4,pc,'R$ #,##0.00' if pc else 'R$ #,##0.00',bold=True,color=DB,sz=14)
    W(ws,ci,5,f"R$ {pc:.0f}/call vs R$ 0.55-1.10 mercado" if pc else "Uso baixo, custo fixo domina",align=L,sz=9)
    for c2 in range(1,7):
        if f: ws.cell(row=ci,column=c2).fill=f
    ws.row_dimensions[ci].height=28

for c2 in 'ABCDEF': ws.column_dimensions[c2].width=34 if c2=='A' else 22

# ── SHEET 2: DETALHE ──
ws2=wb.create_sheet("Detalhe"); ws2.sheet_properties.tabColor=BL
ws2.merge_cells('A1:G1')
ws2.cell(row=1,column=1,value="DETALHE: GCP + LLM (Planos + Tokens)").font=Font(bold=True,size=14,color=DB)

r=3
for title,data in [("INFRAESTRUTURA GCP",INFRA),("LLM — PLANOS + TOKENS",LLM_HOJE)]:
    ws2.merge_cells(f'A{r}:F{r}')
    ws2.cell(row=r,column=1,value=title).font=Font(bold=True,size=11,color=DB); r+=1
    H(ws2,r,["Serviço","Base (USD)","+10% (USD)","+10% (BRL)","Tipo","Nota"])
    for items in [data]:
        for nm,usd,*rest in items:
            nt = rest[0] if rest else ""
            W(ws2,r,1,nm,align=L,sz=10)
            W(ws2,r,2,round(usd/SL,2),'$#,##0.00',sz=10)
            W(ws2,r,3,usd,'$#,##0.00',sz=10)
            W(ws2,r,4,usd*BRL,'R$ #,##0',sz=10)
            W(ws2,r,5,"Plano" if "Plano" in nm else "Token" if "Token" in nm else "GCP",sz=9)
            W(ws2,r,6,nt,align=L,sz=9)
            ws2.row_dimensions[r].height=20; r+=1
    sub=sum(v for _,v,*_ in data)
    W(ws2,r,1,"Subtotal",bold=True,fill=lf)
    W(ws2,r,2,round(sub/SL,0),'$#,##0',bold=True,fill=lf)
    W(ws2,r,3,sub,'$#,##0',bold=True,fill=lf)
    W(ws2,r,4,sub*BRL,'R$ #,##0',bold=True,fill=lf); W(ws2,r,5,"",fill=lf); W(ws2,r,6,"",fill=lf)
    r+=2

W(ws2,r,1,"TOTAL MENSAL",bold=True,sz=13,fill=gf)
W(ws2,r,2,round(TOT/SL,0),'$#,##0',bold=True,fill=gf)
W(ws2,r,3,TOT,'$#,##0',bold=True,fill=gf)
W(ws2,r,4,TOT*BRL,'R$ #,##0',bold=True,sz=14,fill=gf); W(ws2,r,5,"",fill=gf); W(ws2,r,6,"",fill=gf)

for c2 in 'ABCDEF': ws2.column_dimensions[c2].width=38 if c2=='A' else 20

# ── SHEET 3: PROJEÇÕES ──
ws3=wb.create_sheet("Projeções"); ws3.sheet_properties.tabColor="548235"
ws3.merge_cells('A1:G1')
ws3.cell(row=1,column=1,value="PROJEÇÕES DE CRESCIMENTO — DeepSeek primário + MiniMax Plus fallback").font=Font(bold=True,size=14,color=DB)
ws3.merge_cells('A2:G2')
ws3.cell(row=2,column=1,value=f"MiniMax Plus: ${MM_PLUS}/mês fixo | DeepSeek: pay-per-token ($0.14/1M in, $0.28/1M out) | Audio: 5min, Whisper base 0.1x").font=Font(color='666666',size=9)

H(ws3,4,["Componente","500/dia","1.000/dia","5.000/dia","Nota"])
proj = [
    ("Worker Cloud Run (PUSH, min=0)","worker","Processamento Whisper"),
    ("DeepSeek Tokens — Monitoria","ds_tokens","Primário: diarização + QA, 2500 in + 1200 out"),
    ("DeepSeek Tokens — Chatbots","ds_chat","200 msg/dia x 5 bots"),
    ("MiniMax Plus — Plano fixo","mm_plano","Fallback + créditos inclusos"),
    ("MiniMax Tokens — Fallback (5%)","mm_tokens","5% das chamadas quando DeepSeek falha"),
    ("Infra (API+Storage+PubSub)","infra","Escala com volume"),
    ("WhatsApp 5 bots (Cloud Run+SQL)","wa_infra","Fixo, não escala com chamadas"),
]
for ri,(nm,k,note) in enumerate(proj,5):
    W(ws3,ri,1,nm,align=L,sz=10,bold=True)
    for ci,c in enumerate([500,1000,5000],2): W(ws3,ri,ci,S[c][k]*BRL,'R$ #,##0')
    W(ws3,ri,5,note,align=L,sz=9); ws3.row_dimensions[ri].height=22

ri=5+len(proj)
W(ws3,ri,1,"TOTAL",bold=True,sz=13,fill=gf)
for ci,c in enumerate([500,1000,5000],2): W(ws3,ri,ci,S[c]["total"]*BRL,'R$ #,##0',bold=True,sz=13,fill=gf)
W(ws3,ri,5,"",fill=gf); ri+=1

ri+=1
W(ws3,ri,1,"Custo por Chamada",bold=True,color=DB,sz=12)
for ci,c in enumerate([500,1000,5000],2): W(ws3,ri,ci,S[c]["pc"],'R$ #,##0.00',bold=True,color=DB,sz=14)

for c2 in 'ABCDE': ws3.column_dimensions[c2].width=36 if c2=='A' else 22

# ── SHEET 4: MERCADO ──
ws4=wb.create_sheet("vs Mercado"); ws4.sheet_properties.tabColor="BF8F00"
ws4.merge_cells('A1:F1')
ws4.cell(row=1,column=1,value="COMPARATIVO DE MERCADO — Nossa solução vs Concorrentes (500 chamadas/dia)").font=Font(bold=True,size=14,color=DB)
ws4.merge_cells('A2:F2')
ws4.cell(row=2,column=1,value=f"Nós: R$ {OURS:.2f}/chamada | Concorrentes: R$ 0,33-1,10 | Economia: R$ {(0.69-OURS)*15000:,.0f}/mês").font=Font(color='666666',size=9)

H(ws4,4,["Solução","Mín (BRL)","Máx (BRL)","vs Nós","Economia/mês","Tipo"])
for r,(nm,lo,hi) in enumerate(BENCH,5):
    mid=(lo+hi)/2; sav=(mid-OURS)*15000
    W(ws4,r,1,nm,align=L,bold=True)
    W(ws4,r,2,lo,'R$ #,##0.00'); W(ws4,r,3,hi,'R$ #,##0.00')
    W(ws4,r,4,f"{mid/OURS:.0f}x",bold=True,color=DB)
    W(ws4,r,5,sav,'R$ #,##0',bold=True,color='006100')
    W(ws4,r,6,"Mercado",sz=9); ws4.row_dimensions[r].height=24

for nm,pc,n in [("NOSSA (500/dia)",OURS,"Própria"),("NOSSA (5.000/dia)",S[5000]["pc"],"Própria")]:
    r+=1; W(ws4,r,1,nm,align=L,bold=True,color='006100')
    W(ws4,r,2,pc,'R$ #,##0.00'); W(ws4,r,3,pc,'R$ #,##0.00')
    W(ws4,r,4,"—"); W(ws4,r,5,"—"); W(ws4,r,6,n,sz=9)
    for c2 in range(1,7): ws4.cell(row=r,column=c2).fill=gf

for c2 in 'ABCDEF': ws4.column_dimensions[c2].width=28 if c2=='A' else 22

# ══════ SAVE ══════
wb.save(OUT); print(f"Local: {OUT}")

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

with open(TKN) as f: cr=Credentials.from_authorized_user_info(json.load(f),scopes=["https://www.googleapis.com/auth/drive"])
svc=build("drive","v3",credentials=cr)
old=svc.files().list(q=f"name='Custos_OmniChannel_Executivo.xlsx' and '{FID}' in parents",fields="files(id)").execute()
for f in old.get("files",[]): svc.files().delete(fileId=f["id"]).execute()
up=svc.files().create(body={"name":"Custos_OmniChannel_Executivo.xlsx","parents":[FID]},
    media_body=MediaFileUpload(OUT,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    fields="id,webViewLink").execute()
print(f"Drive: {up['webViewLink']}")

print(f"\nHOJE: R${TOT*BRL:,.0f}/mês (GCP {INFRA_T*BRL:,.0f} + LLM {LLM_HOJE_T*BRL:,.0f})")
for c in [500,1000,5000]:
    s=S[c]; print(f"{c}/dia: R${s['total']*BRL:,.0f}/mês | R${s['pc']:,.2f}/chamada")
print(f"LLM: MiniMax Plus ${MM_PLUS}/mês fixo + DeepSeek pay-per-token")
