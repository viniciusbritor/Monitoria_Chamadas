import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

def generate_excel_report(calls: list[dict]) -> bytes:
    """
    Gera uma planilha Excel analítica profissional contendo:
    1. Resumo Executivo (KPIs & Estatísticas)
    2. Detalhamento Analítico por Chamada
    3. Transcrições Diarizadas
    """
    wb = Workbook()
    
    # ----------------------------------------------------
    # Estilos Visuais Padronizados (Coherence Theme)
    # ----------------------------------------------------
    title_font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    regular_font = Font(name="Segoe UI", size=10, color="334155")
    
    header_fill = PatternFill(start_color="1A6B52", end_color="1A6B52", fill_type="solid") # Verde Jade Coherence
    title_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid") # Dark slate
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    thin_border_side = Side(border_style="thin", color="E2E8F0")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="top", wrap_text=True)
    
    # ----------------------------------------------------
    # TAB 1: Resumo Executivo
    # ----------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "Resumo Executivo"
    
    ws_summary.merge_cells("A1:E1")
    cell_title = ws_summary["A1"]
    cell_title.value = "COHERENCE AI - RELATÓRIO ANALÍTICO DE MONITORIA DE CHAMADAS"
    cell_title.font = title_font
    cell_title.fill = title_fill
    cell_title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_summary.row_dimensions[1].height = 40
    
    total_chamadas = len(calls)
    concluidas = [c for c in calls if c.get("status") in ["Concluído", "Concluido", "finalizado"]]
    total_concluidas = len(concluidas)
    
    notas_qa = [float(c.get("nota") or 0) for c in concluidas if c.get("nota") is not None]
    qa_medio = round(sum(notas_qa) / len(notas_qa), 1) if notas_qa else 0.0
    
    # NPS / Sentimento do Cliente
    nps_list = []
    for c in concluidas:
        val = c.get("nota_sentimento_cliente") or c.get("nps")
        if val is not None:
            try:
                nps_list.append(float(val))
            except (ValueError, TypeError):
                pass
    nps_medio = round(sum(nps_list) / len(nps_list), 1) if nps_list else 0.0
    
    erros_criticos = sum(1 for c in concluidas if c.get("erro_critico"))
    
    kpis = [
        ("Métrica Executiva", "Valor"),
        ("Total de Chamadas Recebidas", total_chamadas),
        ("Chamadas Auditadas com Sucesso", total_concluidas),
        ("QA Score Médio (/100)", f"{qa_medio} / 100"),
        ("NPS Médio de Sentimento (/10)", f"{nps_medio} / 10"),
        ("Alertas de Erros Críticos", erros_criticos),
    ]
    
    ws_summary.append([]) # Linha em branco
    for row_idx, (label, val) in enumerate(kpis, start=3):
        ws_summary.cell(row=row_idx, column=1, value=label)
        ws_summary.cell(row=row_idx, column=2, value=str(val))
        
        c1 = ws_summary.cell(row=row_idx, column=1)
        c2 = ws_summary.cell(row=row_idx, column=2)
        
        if row_idx == 3:
            c1.font = header_font
            c1.fill = header_fill
            c2.font = header_font
            c2.fill = header_fill
        else:
            c1.font = bold_font
            c2.font = regular_font
            c1.border = thin_border
            c2.border = thin_border
            
    # Auto-fit tab 1
    ws_summary.column_dimensions['A'].width = 35
    ws_summary.column_dimensions['B'].width = 25

    # ----------------------------------------------------
    # TAB 2: Detalhamento Analítico
    # ----------------------------------------------------
    ws_detail = wb.create_sheet(title="Detalhamento Analítico")
    
    headers_detail = [
        "ID Chamada", "Data / Horário", "Arquivo", "Atendente", "Setor",
        "Nota QA Geral", "Nota Operador", "NPS Cliente", "Motivo do Contato",
        "Classificação", "Humor Cliente", "Humor Atendente", "Erro Crítico",
        "Fase 1: QA", "Fase 1: NPS", "Fase 1: Análise",
        "Fase 2: QA", "Fase 2: NPS", "Fase 2: Análise",
        "Fase 3: QA", "Fase 3: NPS", "Fase 3: Análise",
        "Pontos Positivos", "Pontos de Melhoria", "Recomendação de Treinamento"
    ]
    
    ws_detail.append(headers_detail)
    ws_detail.row_dimensions[1].height = 28
    
    for col_num, header in enumerate(headers_detail, 1):
        cell = ws_detail.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border

    for row_idx, c in enumerate(calls, start=2):
        created_at = c.get("created_at") or c.get("data") or ""
        filename = c.get("filename") or c.get("arquivo") or ""
        atendente = c.get("atendente") or c.get("nome_atendente") or "Não Identificado"
        setor = c.get("setor") or c.get("equipe") or "Geral"
        
        nota_qa = c.get("nota") or c.get("nota_geral") or 0
        nota_op = c.get("nota_qualidade_operador") or "-"
        nps_cli = c.get("nota_sentimento_cliente") or c.get("nps") or "-"
        
        motivo = c.get("motivo_contato") or "-"
        classif = c.get("classificacao_motivo") or "-"
        humor_cli = c.get("humor_cliente") or "-"
        humor_op = c.get("humor_expert") or "-"
        erro_crit = "SIM" if c.get("erro_critico") else "Não"
        
        fases = c.get("fases") or {}
        fase1 = fases.get("apresentacao") or fases.get("inicio") or {}
        fase2 = fases.get("resolucao") or {}
        fase3 = fases.get("fechamento") or {}
        
        p_pos = "\n".join(c.get("pontos_positivos") or [])
        p_neg = "\n".join(c.get("pontos_melhoria") or [])
        rec_trein = c.get("recomendacao_treinamento") or "-"
        
        row_data = [
            c.get("id", ""),
            str(created_at),
            str(filename),
            str(atendente),
            str(setor),
            nota_qa,
            nota_op,
            nps_cli,
            str(motivo),
            str(classif),
            str(humor_cli),
            str(humor_op),
            erro_crit,
            fase1.get("nota_qa", "-"), fase1.get("nota_nps", "-"), str(fase1.get("analise", "-")),
            fase2.get("nota_qa", "-"), fase2.get("nota_nps", "-"), str(fase2.get("analise", "-")),
            fase3.get("nota_qa", "-"), fase3.get("nota_nps", "-"), str(fase3.get("analise", "-")),
            p_pos,
            p_neg,
            rec_trein
        ]
        
        ws_detail.append(row_data)
        current_row = ws_detail.row_dimensions[row_idx]
        current_row.height = 35
        
        row_fill = zebra_fill if row_idx % 2 == 0 else white_fill
        
        for col_idx in range(1, len(row_data) + 1):
            cell = ws_detail.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.fill = row_fill
            cell.border = thin_border
            cell.alignment = align_left if col_idx not in [1, 2, 6, 7, 8, 13, 14, 15, 17, 18, 20, 21] else align_center

    # Auto-fit colunas tab 2
    for col in ws_detail.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws_detail.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 45)

    # ----------------------------------------------------
    # TAB 3: Transcrições Diarizadas
    # ----------------------------------------------------
    ws_trans = wb.create_sheet(title="Transcrições Diarizadas")
    ws_trans.append(["ID Chamada", "Arquivo", "Atendente", "Transcrição Diarizada Completa"])
    ws_trans.row_dimensions[1].height = 25
    
    for col_num in range(1, 5):
        cell = ws_trans.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border
        
    for row_idx, c in enumerate(calls, start=2):
        diarized = c.get("diarized_transcript") or c.get("transcricao") or "-"
        row_data = [
            c.get("id", ""),
            c.get("filename", ""),
            c.get("atendente", "Não Identificado"),
            diarized
        ]
        ws_trans.append(row_data)
        ws_trans.row_dimensions[row_idx].height = 60
        row_fill = zebra_fill if row_idx % 2 == 0 else white_fill
        
        for col_idx in range(1, 5):
            cell = ws_trans.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.fill = row_fill
            cell.border = thin_border
            cell.alignment = align_left
            
    ws_trans.column_dimensions['A'].width = 20
    ws_trans.column_dimensions['B'].width = 30
    ws_trans.column_dimensions['C'].width = 20
    ws_trans.column_dimensions['D'].width = 80
    
    # Renderiza para buffer em memória
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
