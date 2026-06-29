import os
from PIL import Image

def main():
    original_path = r"C:\Users\vinic\.gemini\antigravity\brain\3cd89df2-fa5c-4d5c-afbf-36f09b4477d7\media__1782700348332.png"
    if not os.path.exists(original_path):
        print("Original image not found")
        return
        
    img = Image.open(original_path).convert("RGB")
    width, height = img.size
    
    # Do perfil obtido:
    # COHERENCE: Linha 446 a 551
    # Adicionamos uma pequena folga vertical
    start_y = 440
    end_y = 560
    
    # 1. Recortamos a faixa de Y correspondente a COHERENCE
    cropped_vertical = img.crop((0, start_y, width, end_y))
    cv_width, cv_height = cropped_vertical.size
    
    # 2. Identificar limites horizontais (esquerdo e direito)
    start_x = 0
    for x in range(cv_width):
        col_dark = False
        for y in range(cv_height):
            r, g, b = cropped_vertical.getpixel((x, y))
            if r < 240 or g < 240 or b < 240:
                col_dark = True
                break
        if col_dark:
            start_x = x
            break
            
    end_x = cv_width
    for x in range(cv_width - 1, -1, -1):
        col_dark = False
        for y in range(cv_height):
            r, g, b = cropped_vertical.getpixel((x, y))
            if r < 240 or g < 240 or b < 240:
                col_dark = True
                break
        if col_dark:
            end_x = x
            break
            
    print(f"COHERENCE bounds: Y={start_y}:{end_y}, X={start_x}:{end_x}")
    
    # Adicionamos folga horizontal de 15px
    final_start_x = max(0, start_x - 15)
    final_end_x = min(width, end_x + 15)
    
    # Crop final do logotipo limpo
    final_logo = img.crop((final_start_x, start_y, final_end_x, end_y))
    
    # Salvar nos destinos
    destinations = [
        r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\media\logo.png",
        r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\frontend\public\logo-top.png",
        r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\frontend\public\logo.png"
    ]
    
    for dest in destinations:
        dest_dir = os.path.dirname(dest)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        final_logo.save(dest, "PNG")
        print(f"Saved to: {dest}")

if __name__ == "__main__":
    main()
