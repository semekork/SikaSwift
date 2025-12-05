# SikaSwift ⚡💸 (Telegram Edition)
> The AI-powered Fintech Bot for Ghana 🇬🇭. Send money, generate receipts, and pay via QR codes directly inside Telegram.

## 📋 Overview
SikaSwift transforms Telegram into a secure mobile money wallet. It replaces complex USSD menus (*170#) with simple natural language commands.

Unlike basic bots, SikaSwift is a **full-stack fintech product** featuring bank-grade security (PINs), identity verification, and automated receipt generation.

**Example Flow:**
> *User:* "Send 50 cedis to 0555123456"
> *Bot:* "🔍 Verifying..."
> *Bot:* "👤 **Recipient Found: CALEB DUSSEY**"
> *Bot:* "🔒 Enter your 4-digit PIN to confirm."

## ✨ Key Features
* **🗣️ Natural Language Processing:** Understands commands like *"Send 20ghs to 0244..."*.
* **🔐 Bank-Grade Security:**
    * **Transaction PINs:** Hashed (bcrypt) and never stored in plain text.
    * **Auto-Delete:** PIN messages vanish instantly after typing for privacy.
    * **Identity Proof:** Requires SIM-card based verification ("Share Contact") to register or reset PINs.
* **📸 Visual Receipts:** Automatically generates and sends a branded `.png` receipt after every successful transfer.
* **🤳 QR Code Payments:**
    * **Generate:** Users can type `/myqr` to get a personal payment code.
    * **Scan:** Supports Deep Linking (`/start pay_NUMBER`) for one-tap payments.
* **🛡️ Name Verification:** Automatically resolves and verifies the recipient's name via Paystack before money moves.
* **👥 Referral System:** Built-in growth engine tracking who invited whom.

## 🚀 Tech Stack
* **Core:** Python 3.9+, FastAPI
* **Database:** PostgreSQL (via SQLModel/SQLAlchemy)
* **Interface:** Telegram Bot API (Webhooks)
* **Payments:** Paystack API (Collections, Disbursements, Identity)
* **Imaging:** Pillow (PIL) for Receipt & QR generation
* **Security:** Bcrypt (Hashing)

## 🛠️ Architecture
The system follows a **Two-Phase Commit** with a security middleware:

1.  **Ingest:** NLP parses text → Extracts `Intent`, `Amount`, `Recipient`.
2.  **Verify:** Bot calls Paystack to verify Recipient Name.
3.  **Auth:** User enters PIN → Bot validates hash → Bot auto-deletes PIN.
4.  **Phase 1 (Debit):** Triggers Paystack `Charge` to debit User via Mobile Money prompt.
5.  **Phase 2 (Credit):** Webhook listens for `charge.success` → System waits 2s → Auto-transfers funds to Recipient.

## 📦 Setup & Installation

### 1. Prerequisites
* Python 3.9+
* PostgreSQL Database
* **Paystack Account:** Get Secret Key from Dashboard.
* **Telegram Bot:** Get Token from @BotFather.

### 2. Installation
```bash
# Clone the repo
git clone [https://github.com/semekork/sikaswift.git](https://github.com/semekork/sikaswift.git)
cd sikaswift

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the app
Start the Server:

```bash
uvicorn main:app --reload

Start Ngrok (New Terminal):

```bash
ngrok http 8000