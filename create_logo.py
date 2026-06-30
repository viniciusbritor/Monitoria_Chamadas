from PIL import Image, ImageDraw, ImageFont
import os

def create_logo():
    # WhatsApp logo recommended size is usually 1024x1024
    size = 1024
    
    # Create white background with a subtle gray border to simulate depth
    img = Image.new('RGB', (size, size), color='#f9fafb')
    draw = ImageDraw.Draw(img)
    
    # Draw a subtle circle for the avatar frame context (optional, but good for aesthetics)
    # Actually, we can just leave it solid background and let whatsapp crop it.
    
    # Load Coherence Logo
    logo_path = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\frontend\public\logo.png"
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        # Resize logo to fit well. Usually width around 600px
        basewidth = 700
        wpercent = (basewidth / float(logo.size[0]))
        hsize = int((float(logo.size[1]) * float(wpercent)))
        logo = logo.resize((basewidth, hsize), Image.LANCZOS)
        
        # Calculate position to center it horizontally, slightly above center vertically
        logo_x = (size - basewidth) // 2
        logo_y = (size - hsize) // 2 - 80  # Shifted up a bit
        
        # Paste logo
        img.paste(logo, (logo_x, logo_y), logo)
    
    # Try to load a nice font, fallback to default if needed
    try:
        font = ImageFont.truetype("arialbd.ttf", 90) # Arial Bold
    except:
        font = ImageFont.load_default()
    
    # Draw "Omnichannel" text
    text = "Omnichannel"
    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    
    text_x = (size - text_width) // 2
    text_y = logo_y + hsize + 60 # 60px padding below the logo
    
    draw.text((text_x, text_y), text, font=font, fill="#171717")
    
    # Save the output
    out_path = r"C:\Users\vinic\workspace_antigravity\Monitoria_Chamadas\omnichannel_perfect_logo.png"
    img.save(out_path)
    print("Saved to", out_path)

if __name__ == "__main__":
    create_logo()
