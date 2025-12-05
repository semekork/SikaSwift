import qrcode
from PIL import Image

def generate_payment_qr(phone_number: str) -> str:
    """
    Generates a QR code that, when scanned, opens SikaSwift 
    and initiates a payment to this phone number.
    """
    # 1. The Deep Link (Replace 'SikaSwiftBot' with your actual bot username)
    # The format is: https://t.me/YOUR_BOT_USERNAME?start=PAYLOAD
    bot_username = "SikaSwiftBot" 
    deep_link = f"https://t.me/{bot_username}?start=pay_{phone_number}"
    
    # 2. Generate QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H, # High error correction (allows logo)
        box_size=10,
        border=4,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # 3. Add Logo (Optional - reuses your receipt logo)
    try:
        logo = Image.open("assets/logo.png")
        # Resize logo
        logo_size = 50
        logo = logo.resize((logo_size, logo_size))
        
        # Calculate position (Center)
        pos = ((img.size[0] - logo_size) // 2, (img.size[1] - logo_size) // 2)
        img.paste(logo, pos, logo)
    except:
        pass # Skip if no logo found

    # 4. Save
    filename = f"qr_{phone_number}.png"
    img.save(filename)
    return filename