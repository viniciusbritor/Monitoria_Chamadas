import os
import sys
import subprocess

# Instala fpdf2 se necessário
try:
    from fpdf import FPDF
except ImportError:
    print("fpdf2 não encontrado. Instalando via pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

class MarkdownPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", align="C")

def clean_text(text):
    # Remove emojis e caracteres não compatíveis com latin-1
    return text.encode('latin-1', 'ignore').decode('latin-1')

def convert_md_to_pdf(md_path, pdf_path):
    print(f"Convertendo {os.path.basename(md_path)} -> {os.path.basename(pdf_path)}...")
    pdf = MarkdownPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Adicionar fontes padrão helvetica
    pdf.set_font("helvetica", size=10)
    
    with open(md_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    in_code_block = False
    
    for line in lines:
        cleaned_line = clean_text(line)
        stripped = cleaned_line.strip()
        
        # Ignorar frontmatter (YAML)
        if stripped == "---":
            continue
            
        # Bloco de código
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
            
        if in_code_block:
            pdf.set_font("courier", size=9)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, cleaned_line.replace("\n", ""))
            continue
            
        # Restaura fonte normal após bloco de código
        pdf.set_font("helvetica", size=10)
        
        # Headings
        if stripped.startswith("# "):
            title = stripped[2:]
            pdf.ln(5)
            pdf.set_font("helvetica", "B", 18)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 10, title)
            pdf.ln(3)
        elif stripped.startswith("## "):
            title = stripped[3:]
            pdf.ln(4)
            pdf.set_font("helvetica", "B", 14)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 8, title)
            pdf.ln(2)
        elif stripped.startswith("### "):
            title = stripped[4:]
            pdf.ln(3)
            pdf.set_font("helvetica", "B", 11)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, title)
            pdf.ln(1)
        # Bullet points
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            pdf.set_font("helvetica", size=10)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(0, 5, f"- {text}")
        elif stripped.startswith("1. "):
            text = stripped[3:]
            pdf.set_font("helvetica", size=10)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(0, 5, f"1. {text}")
        elif stripped == "":
            pdf.set_x(pdf.l_margin)
            pdf.ln(3)
        # Linha normal
        else:
            pdf.set_font("helvetica", size=10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 5, stripped)
            
    pdf.output(pdf_path)
    print(f"Sucesso: {pdf_path}")

def main():
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    files = [f for f in os.listdir(docs_dir) if f.endswith(".md")]
    
    for f in files:
        md_path = os.path.join(docs_dir, f)
        pdf_name = f.replace(".md", ".pdf")
        pdf_path = os.path.join(docs_dir, pdf_name)
        
        try:
            convert_md_to_pdf(md_path, pdf_path)
        except Exception as e:
            print(f"Erro ao converter {f}: {e}")

if __name__ == "__main__":
    main()
