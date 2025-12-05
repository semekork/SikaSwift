# SikaSwift ⚡💸 (Telegram Edition)
> An AI-powered Fintech Assistant for Ghana 🇬🇭, built with FastAPI, Paystack, and Telegram.

## 📋 Overview
SikaSwift replaces complex USSD menus (*170#) with a conversational interface. Users can send money simply by chatting with a Telegram Bot.

Unlike standard bots, SikaSwift includes **Real-time Name Verification** to prevent wrong transfers and uses **Interactive Buttons** for a secure, app-like experience.

**Example Flow:**
> *User:* "Send 50 cedis to 0555123456"
> *Bot:* "🔍 Verifying..."
> *Bot:* "👤 **Recipient Found: CALEB DUSSEY**" [✅ Pay 50 GHS] [❌ Cancel]

## 🚀 Tech Stack
* **Backend:** Python 3.9+ (FastAPI)
* **Database:** PostgreSQL (via SQLModel)
* **Interface:** Telegram Bot API (Webhooks)
* **Payments:** Paystack API (Collections, Disbursements, & Identity)
* **Tunneling:** Ngrok (For local development webhooks)

## 🛠️ Architecture
The system operates on a **Verify-then-Commit** model to ensure safety:

1.  **Ingest:** NLP parser extracts intent (`SEND_MONEY`) and entities (Amount, Phone Number).
2.  **Verification:** Calls Paystack `Resolve Account` API to fetch the registered name of the recipient.
3.  **Confirmation:** Bot presents an Interactive Button with the real name.
4.  **Phase 1 (Debit):** Triggers Paystack `Charge` API to debit the User via Mobile Money prompt.
5.  **Phase 2 (Credit):** Upon `charge.success` webhook, the system automatically creates a transfer recipient and disburses funds to the target number.

## 📦 Setup & Installation

### 1. Prerequisites
* Python 3.9+ installed.
* **Paystack Account:** Active account (Test Mode is fine).
* **Telegram Bot:** Create one via [@BotFather](https://t.me/BotFather) and get your Token.
* **PostgreSQL:** Local installation or cloud URL.

### 2. Clone & Install
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