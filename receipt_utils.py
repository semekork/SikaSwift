from PIL import Image, ImageDraw, ImageFont
import datetime
import os

def generate_receipt(sender: str, recipient: str, amount: float, ref: str) -> str:
    """
    Generates a branded PNG receipt with a logo.
    """
    # 1. Canvas Setup
    width, height = 600, 800
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # 2. Load Fonts (Try/Except for cross-platform compatibility)
    try:
        font_header = ImageFont.truetype("Arial.ttf", 45)
        font_sub = ImageFont.truetype("Arial.ttf", 25)
        font_bold = ImageFont.truetype("Arial.ttf", 30)
    except:
        font_header = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # 3. DRAW THE HEADER (Green Bar)
    draw.rectangle([(0, 0), (width, 120)], fill="#00C853") 
    
    # --- LOGO LOGIC START ---
    try:
        # Load logo
        logo = Image.open("assets/logo.png")
        
        # Resize logo to be small (e.g., 80x80)
        logo = logo.resize((80, 80))
        
        # Paste it (coordinates x=40, y=20)
        # The third argument 'logo' is the "mask" which keeps transparency working!
        img.paste(logo, (40, 20), logo)
        
        # Draw Text next to logo
        draw.text((140, 35), "SikaSwift", fill="white", font=font_header)
    except Exception as e:
        print(f"Logo not found: {e}")
        # Fallback if no logo
        draw.text((40, 35), "SikaSwift", fill="white", font=font_header)
    # --- LOGO LOGIC END ---

    # 4. DRAW TRANSACTION STATUS
    draw.text((200, 180), f"GHS {amount:.2f}", fill="black", font=font_header)
    draw.rectangle([(230, 240), (370, 280)], fill="#E8F5E9", outline="#00C853") # Success Badge
    draw.text((255, 245), "SUCCESS", fill="#00C853", font=font_sub)

    # 5. DRAW DETAILS TABLE
    y_start = 350
    spacing = 80
    
    details = [
        ("Sender", sender),
        ("Recipient", recipient),
        ("Reference", ref),
        ("Date", datetime.datetime.now().strftime("%Y-%m-%d")),
        ("Time", datetime.datetime.now().strftime("%H:%M:%S")),
    ]

    for label, value in details:
        draw.text((50, y_start), label, fill="gray", font=font_sub)
        draw.text((300, y_start), value, fill="black", font=font_bold)
        # Draw a thin divider line
        draw.line([(50, y_start + 40), (550, y_start + 40)], fill="#f0f0f0", width=1)
        y_start += spacing

    # 6. FOOTER
    draw.text((180, 750), "Thank you for using SikaSwift ⚡", fill="gray", font=font_sub)

    # 7. SAVE
    filename = f"receipt_{ref}.png"
    img.save(filename)
    return filename