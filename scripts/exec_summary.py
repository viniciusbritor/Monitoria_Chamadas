"""
Planilha Custos OmniChannel — importa do core/cost_model.py
Valores identicos ao PPTX garantidos.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.cost_model import *

from datetime import datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\docs\Custos_OmniChannel_Executivo.xlsx"
FID = "1aNCHHOiQQzquuxzaeQQa8qr3ciZcsfMt"
TKN = os.path.expanduser(r"~\.gemini\config\skills\google_calendar_manager\resources\token_drive.json")

# Styles
DB, GR, OR, LG = "1F4E79", "C6EFCE", "FCE4D6", "F5F5F5"
hf = Font(name='Calibri',bold=True,size=11,color='FFFFFF')
hd = PatternFill(start_color=DB,end_color=DB,fill_type='solid')
gf = PatternFill(start_color=GR,end_color=GR,fill_type='solid')
of = PatternFill(start_color=OR,end_color=OR,fill_type='solid')
lf = PatternFill(start_color=LG,end_color=LG,fill_type='solid')
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

wb = Workbook()

# ══════ SHEET 1: RESUMO ══════
ws = wb.active; ws.title="Resumo"; ws.sheet_properties.tabColor=DB
ws.merge_cells('A1:F1')
ws.cell(row=1,column=1,value="CUSTOS OMNI CHANNEL · Infra + IA (Dev + Producao)").font=Font(bold=True,size=16,color=DB)
ws.merge_cells('A2:F2')
ws.cell(row=2,column=1,value=f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} | R${BRL:.2f}/USD | 10% margem | DeepSeek pay-per-token | MiniMax Plus ${MM_PLAN}/mes").font=Font(color='666666',size=9)

# HOJE
ws.cell(row=4,column=1,value="HOJE — Custo Operacional (recorrente 24/7)").font=Font(bold=True,size=13,color=DB)
ws.merge_cells('A4:F4')
H(ws,5,["Categoria","Servico","USD/mes","BRL/mes","%","Tipo"])

r=6
for nm,usd in INFRA:
    W(ws,r,1,"GCP",align=L,sz=9,color=DB); W(ws,r,2,nm,align=L,sz=9)
    W(ws,r,3,usd,'$#,##0'); W(ws,r,4,usd*BRL,'R$ #,##0'); W(ws,r,5,usd/TOTAL_HOJE,'0%',sz=9)
    W(ws,r,6,"Infra",sz=9); ws.row_dimensions[r].height=20; r+=1

for nm,usd in AI_DEV+AI_PROD:
    cat = "IA Dev" if any(k in nm.lower() for k in ["desenvolvimento","plano"]) else "IA Prod"
    W(ws,r,1,cat,align=L,sz=9,color=DB if "Dev" in cat else "4472C4")
    W(ws,r,2,nm,align=L,sz=9); W(ws,r,3,usd,'$#,##0'); W(ws,r,4,usd*BRL,'R$ #,##0')
    W(ws,r,5,usd/TOTAL_HOJE,'0%',sz=9); W(ws,r,6,"LLM",sz=9)
    ws.row_dimensions[r].height=20; r+=1

for lbl,val,clr in [("GCP Infra",GCP_TOTAL,DB),("IA Desenvolvimento",AI_DEV_TOTAL,DB),("IA Producao",AI_PROD_TOTAL,DB)]:
    W(ws,r,1,lbl,bold=True,color=clr); W(ws,r,3,val,'$#,##0',bold=True)
    W(ws,r,4,val*BRL,'R$ #,##0',bold=True); W(ws,r,5,val/TOTAL_HOJE,'0%',bold=True)
    ws.row_dimensions[r].height=22; r+=1

W(ws,r,1,"TOTAL HOJE",bold=True,sz=14,fill=gf)
W(ws,r,3,TOTAL_HOJE,'$#,##0',bold=True,fill=gf)
W(ws,r,4,TOTAL_HOJE*BRL,'R$ #,##0',bold=True,sz=15,fill=gf); W(ws,r,5,"100%",bold=True,fill=gf)

# SCALE
r+=2
ws.merge_cells(f'A{r}:F{r}')
ws.cell(row=r,column=1,value="PROJECOES DE CRESCIMENTO — Custo por volume de chamadas").font=Font(bold=True,size=13,color=DB)
r+=1
H(ws,r,["Cenario","Chamadas/mes","Total/mes (BRL)","Custo/Chamada","GCP","IA Dev","IA Prod"])

for ci,c in enumerate([500,1000,5000],r+1):
    s=SCENARIOS[c]; cm=c*30
    f=gf if c>=5000 else (lf if c==500 else None)
    W(ws,ci,1,f"{c}/dia ({cm:,}/mes)",align=L,bold=True,sz=11)
    W(ws,ci,2,cm,'#,##0',bold=True)
    W(ws,ci,3,s["total_brl"],'R$ #,##0',bold=True,sz=13,fill=f)
    W(ws,ci,4,s["cost_per_call_brl"],'R$ #,##0.00',bold=True,color=DB,sz=14)
    W(ws,ci,5,s["gcp"]*BRL,'R$ #,##0',sz=10)
    W(ws,ci,6,s["ai_dev"]*BRL,'R$ #,##0',sz=10)
    W(ws,ci,7,s["ai_prod"]*BRL,'R$ #,##0',sz=10)
    for c2 in range(1,8):
        if f: ws.cell(row=ci,column=c2).fill=f
    ws.row_dimensions[ci].height=28

for c2 in 'ABCDEFG': ws.column_dimensions[c2].width=34 if c2=='A' else 20
ws.column_dimensions['B'].width=40

# ══════ SHEET 2: PROJECOES DETALHE ══════
ws2=wb.create_sheet("Projecoes Detalhe"); ws2.sheet_properties.tabColor="548235"
ws2.merge_cells('A1:G1')
ws2.cell(row=1,column=1,value="PROJECOES DETALHADAS — Todos os componentes por cenario").font=Font(bold=True,size=14,color=DB)
ws2.merge_cells('A2:G2')
ws2.cell(row=2,column=1,value="Valores em BRL com 10% de margem. WhatsApp 5 bots incluso nos 3 cenarios.").font=Font(color='666666',size=9)

H(ws2,4,["Componente","500/dia","1.000/dia","5.000/dia","Tipo"])

proj = [
    ("GCP — Worker (PUSH, min=0)","worker","Infra"),
    ("GCP — API+Storage+PubSub","infra","Infra"),
    ("GCP — WhatsApp 5 bots","wa_infra","Infra"),
    ("IA Dev — DeepSeek (testes)","ds_dev","IA Dev"),
    ("IA Dev — MiniMax Plus plano","mm_plan","IA Dev"),
    ("IA Prod — DeepSeek Monitoria","ds_mono","IA Prod"),
    ("IA Prod — DeepSeek Chatbots","ds_chat","IA Prod"),
    ("IA Prod — DeepSeek Extras","ds_extra","IA Prod"),
    ("IA Prod — MiniMax fallback","mm_token","IA Prod"),
]
for ri,(nm,k,cat) in enumerate(proj,5):
    W(ws2,ri,1,nm,align=L,sz=9,bold=True)
    for ci,c in enumerate([500,1000,5000],2): W(ws2,ri,ci,SCENARIOS[c][k]*BRL,'R$ #,##0')
    W(ws2,ri,5,cat,sz=9); ws2.row_dimensions[ri].height=20

ri=5+len(proj)
for lbl,key in [("TOTAL GCP","gcp"),("TOTAL IA Desenvolvimento","ai_dev"),("TOTAL IA Producao","ai_prod")]:
    W(ws2,ri,1,lbl,bold=True,fill=lf)
    for ci,c in enumerate([500,1000,5000],2): W(ws2,ri,ci,SCENARIOS[c][key]*BRL,'R$ #,##0',bold=True,fill=lf)
    W(ws2,ri,5,"",fill=lf); ri+=1

W(ws2,ri,1,"CUSTO TOTAL",bold=True,sz=13,fill=gf)
for ci,c in enumerate([500,1000,5000],2): W(ws2,ri,ci,SCENARIOS[c]["total_brl"],'R$ #,##0',bold=True,sz=13,fill=gf)
W(ws2,ri,5,"",fill=gf); ri+=2

W(ws2,ri,1,"Custo por Chamada",bold=True,color=DB,sz=12)
for ci,c in enumerate([500,1000,5000],2): W(ws2,ri,ci,SCENARIOS[c]["cost_per_call_brl"],'R$ #,##0.00',bold=True,color=DB,sz=14)

for c2 in 'ABCDE': ws2.column_dimensions[c2].width=38 if c2=='A' else 20

# ══════ SHEET 3: MERCADO BR ─═════
ws3=wb.create_sheet("vs Mercado BR"); ws3.sheet_properties.tabColor="BF8F00"
ws3.merge_cells('A1:F1')
ws3.cell(row=1,column=1,value="COMPARATIVO — Operadoras Nacionais (Brasil)").font=Font(bold=True,size=14,color=DB)
ws3.merge_cells('A2:F2')
OURS = SCENARIOS[500]["cost_per_call_brl"]
ws3.cell(row=2,column=1,value=f"Nossa solucao: R$ {OURS:.2f}/chamada (500/dia). Trade: QA humano — amostragem 2-5% vs 100% automatizado.").font=Font(color='666666',size=9)

H(ws3,4,["Empresa","Perfil","Modelo QA","Custo/chamada","vs Nos","Nossa Vantagem"])

for r,(emp,perfil,modelo,lo,hi) in enumerate(BENCHMARKS_BR,5):
    mid=(lo+hi)/2
    W(ws3,r,1,emp,align=L,bold=True,sz=11)
    W(ws3,r,2,perfil,align=L,sz=9)
    W(ws3,r,3,modelo,align=L,sz=9)
    W(ws3,r,4,f"R$ {lo:.2f}–{hi:.2f}")
    W(ws3,r,5,f"{mid/OURS:.0f}x mais caro",bold=True,color=DB)
    W(ws3,r,6,f"Automatizavel — R$ {OURS:.2f}",align=L,sz=9,color='006100')
    ws3.row_dimensions[r].height=28

r+=1
for nm,pc in [("NOSSA (500/dia)",OURS),("NOSSA (5.000/dia)",SCENARIOS[5000]["cost_per_call_brl"])]:
    W(ws3,r,1,nm,align=L,bold=True,color='006100',sz=11)
    W(ws3,r,2,"OmniChannel",align=L,sz=9); W(ws3,r,3,"IA — 100% automatizado",align=L,sz=9)
    W(ws3,r,4,f"R$ {pc:.2f}",bold=True,color='006100',sz=12)
    W(ws3,r,5,"Referencia",bold=True)
    W(ws3,r,6,"",sz=9)
    for c2 in range(1,7): ws3.cell(row=r,column=c2).fill=gf
    ws3.row_dimensions[r].height=24; r+=1

for c2 in 'ABCDEF': ws3.column_dimensions[c2].width=28 if c2 in ['A','F'] else 22

# ══════ SHEET 4: DETALHE COMPLETO ══════
ws4=wb.create_sheet("Infra + IA"); ws4.sheet_properties.tabColor="4472C4"
ws4.merge_cells('A1:F1')
ws4.cell(row=1,column=1,value="DETALHE COMPLETO — Todos os servicos GCP + LLM").font=Font(bold=True,size=14,color=DB)

r=3
for title,data in [("INFRAESTRUTURA GCP",INFRA),("IA — DESENVOLVIMENTO",AI_DEV),("IA — PRODUCAO (Modulos)",AI_PROD)]:
    ws4.merge_cells(f'A{r}:F{r}')
    ws4.cell(row=r,column=1,value=title).font=Font(bold=True,size=11,color=DB); r+=1
    H(ws4,r,["Servico/API","Base (USD)","+10% Margem (USD)","+10% (BRL)","Categoria"])
    for nm,usd in data:
        is_plan = "plano" in nm.lower()
        W(ws4,r,1,nm,align=L,sz=10)
        W(ws4,r,2,round(usd/SLACK if not is_plan else usd,2),'$#,##0.00',sz=10)
        W(ws4,r,3,usd,'$#,##0.00',sz=10)
        W(ws4,r,4,usd*BRL,'R$ #,##0',sz=10)
        W(ws4,r,5,"Plano" if is_plan else "IA Token" if "DeepSeek" in nm or "MiniMax" in nm else "GCP",sz=9)
        ws4.row_dimensions[r].height=20; r+=1
    sub=sum(v for _,v in data)
    W(ws4,r,1,"Subtotal",bold=True,fill=lf); W(ws4,r,2,"",fill=lf)
    W(ws4,r,3,sub,'$#,##0',bold=True,fill=lf); W(ws4,r,4,sub*BRL,'R$ #,##0',bold=True,fill=lf)
    W(ws4,r,5,"",fill=lf); r+=2

W(ws4,r,1,"TOTAL MENSAL",bold=True,sz=13,fill=gf)
W(ws4,r,3,TOTAL_HOJE,'$#,##0',bold=True,fill=gf)
W(ws4,r,4,TOTAL_HOJE*BRL,'R$ #,##0',bold=True,sz=14,fill=gf); W(ws4,r,5,"",fill=gf)

for c2 in 'ABCDEF': ws4.column_dimensions[c2].width=38 if c2 in ['A','F'] else 20

# ══════ SAVE ══════
wb.save(OUT); print(f"Excel saved: {OUT}")

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
print(f"Excel Drive: {up['webViewLink']}")

print(f"\nHOJE: R$ {TOTAL_HOJE*BRL:,.0f}/mes")
for c in [500,1000,5000]:
    s=SCENARIOS[c]; print(f"{c}/dia: R$ {s['total_brl']:,.0f}/mes | R$ {s['cost_per_call_brl']:.2f}/chamada")
print(f"vs Teleperformance: economia ~R$ {int((0.75-SCENARIOS[500]['cost_per_call_brl'])*15000):,}/mes")
