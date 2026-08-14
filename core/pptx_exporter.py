import io
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

def generate_pptx_report(calls: list[dict]) -> bytes:
    """
    Gera uma Apresentação Executiva em PowerPoint (.pptx) de 5 slides
    estritamente limitada às 50 chamadas fornecidas.
    """
    # Limita rigorosamente a 50 chamadas como ordenado nas diretrizes
    limited_calls = calls[:50]
    
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_slide_layout = prs.slide_layouts[6]
    
    # Cores Oficiais da Identidade Visual Coherence
    DARK_SLATE = RGBColor(15, 23, 42)    # #0F172A
    JADE_GREEN = RGBColor(26, 107, 82)   # #1A6B52
    LIGHT_BG = RGBColor(248, 250, 252)   # #F8FAFC
    CARD_BG = RGBColor(255, 255, 255)    # #FFFFFF
    TEXT_MAIN = RGBColor(51, 65, 85)     # #334155
    TEXT_MUTED = RGBColor(100, 116, 139) # #64748B
    BORDER_COLOR = RGBColor(226, 232, 240)
    
    def set_background(slide, color):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = color

    def add_header(slide, title_text, subtitle_text=""):
        # Header banner
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.1))
        shape.fill.solid()
        shape.fill.fore_color.rgb = DARK_SLATE
        shape.line.fill.background()
        
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.15), Inches(11.5), Inches(0.8))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.size = Pt(22)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)
        
        if subtitle_text:
            p2 = tf.add_paragraph()
            p2.text = subtitle_text
            p2.font.size = Pt(12)
            p2.font.color.rgb = RGBColor(148, 163, 184)

    # ----------------------------------------------------
    # SLIDE 1: Capa Executiva
    # ----------------------------------------------------
    slide1 = prs.slides.add_slide(blank_slide_layout)
    set_background(slide1, DARK_SLATE)
    
    # Accent Line
    line = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(2.2), Inches(1.5), Inches(0.08))
    line.fill.solid()
    line.fill.fore_color.rgb = JADE_GREEN
    line.line.fill.background()
    
    title_box = slide1.shapes.add_textbox(Inches(1.2), Inches(2.5), Inches(11), Inches(2.5))
    tf1 = title_box.text_frame
    tf1.word_wrap = True
    
    p_title = tf1.paragraphs[0]
    p_title.text = "Relatório Executivo de Monitoria de Chamadas"
    p_title.font.size = Pt(36)
    p_title.font.bold = True
    p_title.font.color.rgb = RGBColor(255, 255, 255)
    
    p_sub = tf1.add_paragraph()
    p_sub.text = f"Coherence AI • Auditoria de Atendimentos ({len(limited_calls)} chamadas analisadas)"
    p_sub.font.size = Pt(18)
    p_sub.font.color.rgb = RGBColor(148, 163, 184)

    # ----------------------------------------------------
    # SLIDE 2: Visão Geral de Performance (KPIs)
    # ----------------------------------------------------
    slide2 = prs.slides.add_slide(blank_slide_layout)
    set_background(slide2, LIGHT_BG)
    add_header(slide2, "Visão Geral de Performance Operacional", "Métricas consolidadas do lote de chamadas")
    
    concluidas = [c for c in limited_calls if c.get("status") in ["Concluído", "Concluido", "finalizado"]]
    notas_qa = [float(c.get("nota") or 0) for c in concluidas if c.get("nota") is not None]
    qa_medio = round(sum(notas_qa) / len(notas_qa), 1) if notas_qa else 0.0
    
    nps_list = [float(c.get("nota_sentimento_cliente") or c.get("nps") or 0) for c in concluidas if c.get("nota_sentimento_cliente") or c.get("nps")]
    nps_medio = round(sum(nps_list) / len(nps_list), 1) if nps_list else 0.0
    
    erros_criticos = sum(1 for c in concluidas if c.get("erro_critico"))
    
    cards_data = [
        ("Total Auditado", str(len(limited_calls)), "Chamadas analisadas"),
        ("QA Score Médio", f"{qa_medio}/100", "Nota técnica de qualidade"),
        ("NPS Sentimento", f"{nps_medio}/10", "Índice de satisfação do cliente"),
        ("Erros Críticos", str(erros_criticos), "Alertas de inconformidade"),
    ]
    
    for idx, (label, val, sub) in enumerate(cards_data):
        left_pos = Inches(0.8 + idx * 3.0)
        top_pos = Inches(2.2)
        card = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_pos, top_pos, Inches(2.7), Inches(3.5))
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.color.rgb = BORDER_COLOR
        
        tb = slide2.shapes.add_textbox(left_pos + Inches(0.15), top_pos + Inches(0.3), Inches(2.4), Inches(2.9))
        tf = tb.text_frame
        tf.word_wrap = True
        
        p1 = tf.paragraphs[0]
        p1.text = label
        p1.font.size = Pt(14)
        p1.font.bold = True
        p1.font.color.rgb = TEXT_MUTED
        
        p2 = tf.add_paragraph()
        p2.text = val
        p2.font.size = Pt(36)
        p2.font.bold = True
        p2.font.color.rgb = JADE_GREEN if "QA" in label or "Total" in label else DARK_SLATE
        
        p3 = tf.add_paragraph()
        p3.text = sub
        p3.font.size = Pt(11)
        p3.font.color.rgb = TEXT_MUTED

    # ----------------------------------------------------
    # SLIDE 3: Sentimento & Humor dos Clientes
    # ----------------------------------------------------
    slide3 = prs.slides.add_slide(blank_slide_layout)
    set_background(slide3, LIGHT_BG)
    add_header(slide3, "Análise de Sentimento & Humor dos Clientes", "Distribuição de humor e polaridade percebida na amostra")
    
    humores = {}
    for c in concluidas:
        h = c.get("humor_cliente") or "Não Informado"
        humores[h] = humores.get(h, 0) + 1
        
    left_c = Inches(0.8)
    top_c = Inches(1.8)
    
    box_humor = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_c, top_c, Inches(11.733), Inches(4.8))
    box_humor.fill.solid()
    box_humor.fill.fore_color.rgb = CARD_BG
    box_humor.line.color.rgb = BORDER_COLOR
    
    tb_h = slide3.shapes.add_textbox(left_c + Inches(0.3), top_c + Inches(0.3), Inches(11.1), Inches(4.2))
    tf_h = tb_h.text_frame
    tf_h.word_wrap = True
    
    ph1 = tf_h.paragraphs[0]
    ph1.text = "Distribuição de Humor Identificada:"
    ph1.font.size = Pt(18)
    ph1.font.bold = True
    ph1.font.color.rgb = DARK_SLATE
    
    for h_name, h_count in humores.items():
        pct = round((h_count / max(len(concluidas), 1)) * 100, 1)
        p_item = tf_h.add_paragraph()
        p_item.text = f"• {h_name}: {h_count} chamada(s) ({pct}%)"
        p_item.font.size = Pt(14)
        p_item.font.color.rgb = TEXT_MAIN

    # ----------------------------------------------------
    # SLIDE 4: Diagnóstico Operacional & Treinamento
    # ----------------------------------------------------
    slide4 = prs.slides.add_slide(blank_slide_layout)
    set_background(slide4, LIGHT_BG)
    add_header(slide4, "Diagnóstico Operacional & Recomendações", "Pontos de destaque e plano de capacitação continua")
    
    # Pontos Positivos Box
    box_pos = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(5.6), Inches(4.8))
    box_pos.fill.solid()
    box_pos.fill.fore_color.rgb = CARD_BG
    box_pos.line.color.rgb = BORDER_COLOR
    
    tb_pos = slide4.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(5.2), Inches(4.4))
    tf_pos = tb_pos.text_frame
    tf_pos.word_wrap = True
    p = tf_pos.paragraphs[0]
    p.text = "🌟 Principais Pontos Positivos"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = JADE_GREEN
    
    all_pos = []
    for c in concluidas:
        all_pos.extend(c.get("pontos_positivos") or [])
    for item in (all_pos[:4] if all_pos else ["Cordialidade no atendimento inicial", "Clareza nas orientações prestadas"]):
        p_it = tf_pos.add_paragraph()
        p_it.text = f"✓ {item}"
        p_it.font.size = Pt(12)
        p_it.font.color.rgb = TEXT_MAIN

    # Pontos de Melhoria Box
    box_neg = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.8), Inches(1.8), Inches(5.7), Inches(4.8))
    box_neg.fill.solid()
    box_neg.fill.fore_color.rgb = CARD_BG
    box_neg.line.color.rgb = BORDER_COLOR
    
    tb_neg = slide4.shapes.add_textbox(Inches(7.0), Inches(2.0), Inches(5.3), Inches(4.4))
    tf_neg = tb_neg.text_frame
    tf_neg.word_wrap = True
    p = tf_neg.paragraphs[0]
    p.text = "🎯 Oportunidades de Melhoria & Treinamento"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = DARK_SLATE
    
    all_neg = []
    for c in concluidas:
        all_neg.extend(c.get("pontos_melhoria") or [])
    for item in (all_neg[:4] if all_neg else ["Aprimorar contorno de objeções", "Reduzir tempo de espera em pausa"]):
        p_it = tf_neg.add_paragraph()
        p_it.text = f"⚠ {item}"
        p_it.font.size = Pt(12)
        p_it.font.color.rgb = TEXT_MAIN

    # ----------------------------------------------------
    # SLIDE 5: Tabela Analítica das Chamadas (Máximo 50)
    # ----------------------------------------------------
    slide5 = prs.slides.add_slide(blank_slide_layout)
    set_background(slide5, LIGHT_BG)
    add_header(slide5, "Detalhamento Analítico dos Atendimentos", f"Amostra dos {len(limited_calls)} atendimentos auditados (Limite 50)")
    
    rows = min(len(limited_calls) + 1, 12) # Exibe até 11 chamadas por slide na tabela principal
    cols = 6
    left = Inches(0.8)
    top = Inches(1.6)
    width = Inches(11.733)
    height = Inches(5.2)
    
    table_shape = slide5.shapes.add_table(rows, cols, left, top, width, height)
    table = table_shape.table
    
    table.columns[0].width = Inches(3.5) # Arquivo
    table.columns[1].width = Inches(2.2) # Atendente
    table.columns[2].width = Inches(1.4) # QA Score
    table.columns[3].width = Inches(1.4) # NPS
    table.columns[4].width = Inches(1.833) # Humor
    table.columns[5].width = Inches(1.4) # Erro Crítico
    
    headers = ["Arquivo / Atendimento", "Atendente", "QA Score", "NPS", "Humor Cliente", "Erro Crítico"]
    for col_idx, h_text in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = h_text
        cell.fill.solid()
        cell.fill.fore_color.rgb = DARK_SLATE
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = RGBColor(255, 255, 255)
            p.alignment = PP_ALIGN.CENTER
            
    for row_idx, c in enumerate(limited_calls[:11], start=1):
        filename = c.get("filename") or c.get("arquivo") or "Chamada"
        atendente = c.get("atendente") or c.get("nome_atendente") or "Operador"
        qa = str(c.get("nota") or c.get("nota_geral") or "-")
        nps = str(c.get("nota_sentimento_cliente") or c.get("nps") or "-")
        humor = str(c.get("humor_cliente") or "-")
        erro = "SIM" if c.get("erro_critico") else "Não"
        
        row_values = [filename[:30], atendente, qa, nps, humor, erro]
        for col_idx, val in enumerate(row_values):
            cell = table.cell(row_idx, col_idx)
            cell.text = val
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(241, 245, 249) if row_idx % 2 == 0 else RGBColor(255, 255, 255)
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = TEXT_MAIN
                if col_idx >= 2:
                    p.alignment = PP_ALIGN.CENTER

    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
