# SikaSwift ⚡💸
> An AI-powered WhatsApp Fintech Assistant for Ghana, built with FastAPI, Paystack, and the Meta Cloud API.

## 📋 Overview
SikaSwift replaces complex USSD menus (*170#) with natural language. Users can send money, pay bills, and manage finances simply by chatting on WhatsApp.

**Example:** > *User:* "Send 50 cedis to Kofi."  
> *SikaSwift:* "Initiating transfer to Kofi (0555...). Check your phone for the PIN prompt."

## 🚀 Tech Stack
* **Backend:** Python (FastAPI)
* **Database:** PostgreSQL (via SQLModel)
* **Whatsapp Integration:** Meta Cloud API (Direct)
* **Payments:** Paystack API (Collections & Disbursements)
* **Tunneling:** Ngrok (For local development webhooks)

## 🛠️ Architecture
The system operates on a **Two-Phase Commit** model to ensure safety:
1.  **Ingest:** NLP parser extracts intent (`SEND_MONEY`) and entities (`50 GHS`, `Recipient`).
2.  **Phase 1 (Debit):** Triggers Paystack `Charge` API to debit User A via mobile money prompt.
3.  **Phase 2 (Credit):** Upon `charge.success` webhook, automatically triggers Paystack `Transfer` API to credit User B.

## 📦 Setup & Installation

### 1. Prerequisites
* Python 3.9+
* Paystack Account (Starter Business)
* Meta Developer Account (WhatsApp Product)

### 2. Installation
```bash
# Clone the repo
git clone [https://github.com/semekork/sikaswift.git](https://github.com/semekork/sikaswift.git)
cd sikaswift

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt