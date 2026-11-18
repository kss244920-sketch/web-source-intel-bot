import os
import sys
from typing import Dict, Any

# Ensure root directory is in sys.path for Vercel Serverless environment
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
from dotenv import load_dotenv

# Load local environment if available
load_dotenv()

from bot_logic import handle_update

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

app = FastAPI(title="WebSource Telegram Bot on Vercel")


@app.get("/")
@app.get("/api")
async def health_check():
    return {
        "status": "online",
        "service": "Advance WebSource & Intel Bot",
        "configured": bool(BOT_TOKEN)
    }


@app.post("/")
@app.post("/api")
@app.post("/api/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """Webhook endpoint for Telegram bot updates."""
    if not BOT_TOKEN:
        return JSONResponse(status_code=500, content={"error": "BOT_TOKEN not configured in environment"})

    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    # Process in background task so Telegram receives immediate 200 OK
    background_tasks.add_task(handle_update, BOT_TOKEN, update)
    return {"ok": True}


@app.get("/set_webhook")
@app.get("/api/set_webhook")
async def set_webhook(url: str = ""):
    """Convenience helper to set Telegram Webhook."""
    if not BOT_TOKEN:
        return {"error": "BOT_TOKEN is not set"}
    if not url:
        return {"error": "Provide ?url=https://your-vercel-app.vercel.app parameter"}

    webhook_url = f"{url.rstrip('/')}/api/webhook"
    telegram_set_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"

    async with httpx.AsyncClient() as client:
        r = await client.get(telegram_set_url)
        return r.json()
