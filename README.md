# 🚀 Advance WebSource & Intel Telegram Bot

Ek powerful Telegram bot jo kisi bhi website ka **Full Source Code (HTML, CSS, JS, Images, Fonts)** download karke offline-ready ZIP banata hai, aur website ke andar chhupi **A to Z Embedded APIs, WebSockets aur Secrets** ko deep scan karke nikaalta hai.

---

## ✨ Features
- 🌐 **Full Website Cloner**: Downloads HTML, CSS, JavaScript, Images, SVGs, and Fonts.
- 🔗 **Offline Link Rewriter**: Automatically rewrites asset paths in `index.html` so you can open it offline.
- 🔌 **A to Z API Extractor**:
  - Relative API endpoints (`/api/...`, `/v1/...`, `/auth/...`, etc.)
  - External / Backend URLs & Services
  - WebSockets connections (`wss://...`)
  - Fetch / Axios call destinations
- 🔑 **Public Keys & Configs Detection**: Scans for Firebase configs, Razorpay/Stripe keys, JWT tokens, etc.
- 📦 **In-Memory ZIP Packaging**: Optimized for Vercel Serverless (Runs in RAM, under 10 seconds).
- ⚡ **Dual Deployment**: Can run 24/7 on **Vercel** via Webhook OR locally on your machine via Polling.

---

## 📁 Project Structure
```text
web_source_bot/
├── api/
│   └── index.py            # Vercel Serverless Entrypoint (FastAPI)
├── core/
│   ├── scraper.py          # Fast Async Website & Asset Downloader
│   ├── extractor.py        # A-to-Z API & Intel Extractor
│   └── packager.py         # In-Memory ZIP Packager
├── bot_logic.py            # Telegram Bot handlers & messaging
├── local_run.py            # Local polling test runner
├── vercel.json             # Vercel configuration
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variables template
```

---

## 🛠️ Step 1: Local Test Run

1. Clone or navigate to the folder:
   ```bash
   cd /home/piyush/web_source_bot
   ```

2. Create `.env` file and add your Telegram bot token:
   ```bash
   echo "BOT_TOKEN=123456789:ABCDefgh..." > .env
   ```

3. Run locally:
   ```bash
   python3 local_run.py
   ```
4. Open Telegram and send `/ws https://example.com` to your bot!

---

## ☁️ Step 2: Vercel par Free Deploy Kaise Karein

### Option A: Via GitHub (Recommended - 2 Minutes)
1. Is folder ko apne GitHub repository me push karein:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of WebSource Bot"
   git remote add origin https://github.com/<your-username>/web-source-bot.git
   git push -u origin main
   ```
2. [Vercel Dashboard](https://vercel.com/new) par jayein aur repository ko **Import** karein.
3. **Environment Variables** section me:
   - Key: `BOT_TOKEN`
   - Value: `<Aapka Telegram Bot Token>`
4. **Deploy** button click karein.
5. Deploy hone ke baad aapko Vercel URL milega (e.g. `https://your-bot.vercel.app`).
6. Webhook set karne ke liye browser me yeh link open karein:
   ```text
   https://your-bot.vercel.app/api/set_webhook?url=https://your-bot.vercel.app
   ```
   Aapko screen par `{"ok": true, "result": true, "description": "Webhook was set"}` dikhega.
   **Bot 24/7 Free Live ho gaya!**

---

### Option B: Via Vercel CLI
```bash
npm install -g vercel
vercel login
vercel --prod
```
Deploy ke baad Vercel settings me `BOT_TOKEN` environment variable add kar dijiye.
