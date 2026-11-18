import re
import time
from typing import Optional, Dict, Any
import httpx

from core.scraper import WebScraper
from core.packager import ZipPackager

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

URL_REGEX = re.compile(
    r"""(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’]))"""
)


class TelegramBotClient:
    """Async Client for Telegram Bot API."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token.strip()
        self.api_url = f"{TELEGRAM_API_BASE}{self.bot_token}"

    async def send_message(self, chat_id: int | str, text: str, reply_to_message_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, json=payload, timeout=10.0)
                if r.status_code == 200:
                    return r.json().get("result")
            except Exception:
                pass
        return None

    async def edit_message(self, chat_id: int | str, message_id: int, text: str) -> None:
        url = f"{self.api_url}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=payload, timeout=10.0)
            except Exception:
                pass

    async def send_document(
        self,
        chat_id: int | str,
        file_bytes: bytes,
        filename: str,
        caption: str,
        reply_to_message_id: Optional[int] = None
    ) -> bool:
        url = f"{self.api_url}/sendDocument"
        data = {
            "chat_id": str(chat_id),
            "caption": caption,
            "parse_mode": "HTML"
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = str(reply_to_message_id)

        files = {
            "document": (filename, file_bytes, "application/zip")
        }

        # Telegram upload can take up to 20-30s depending on file size
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, data=data, files=files, timeout=40.0)
                return r.status_code == 200
            except Exception as e:
                print(f"Error sending document: {e}")
                return False


async def handle_update(bot_token: str, update: Dict[str, Any]) -> None:
    """Processes incoming Telegram updates."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")

    if not chat_id or not text:
        return

    bot = TelegramBotClient(bot_token)

    # 1. Handle /start and /help commands
    if text.startswith(("/start", "/help")):
        welcome_text = (
            "🚀 <b>Welcome to Advance WebSource &amp; Intel Bot!</b>\n\n"
            "Main kisi bhi website ka <b>Full Source Code + A to Z Embedded APIs</b> extract karke single ZIP file me provide karta hoon.\n\n"
            "✨ <b>Features:</b>\n"
            "• 🌐 Full Source (HTML, CSS, JS, Images, Fonts)\n"
            "• 🔌 <b>A-to-Z API Extraction</b> (Relative routes, Backend APIs, WebSockets)\n"
            "• 🔑 <b>Secrets &amp; Config Scanner</b> (Firebase, Razorpay, Tokens)\n"
            "• 📦 <b>Offline-Ready ZIP</b> (Links locally rewritten)\n\n"
            "📌 <b>How to use:</b>\n"
            "Send command: <code>/ws https://example.com</code>\n"
            "or simply send any website link directly!"
        )
        await bot.send_message(chat_id, welcome_text, reply_to_message_id=msg_id)
        return

    # 2. Extract URL from text or /ws command
    target_url = None
    if text.startswith("/ws"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            target_url = parts[1].strip()
        else:
            await bot.send_message(
                chat_id,
                "⚠️ <b>Please provide a website URL!</b>\n\nExample:\n<code>/ws https://goagamea.com</code>",
                reply_to_message_id=msg_id
            )
            return
    else:
        # Check if message contains a valid URL
        match = URL_REGEX.search(text)
        if match:
            target_url = match.group(0).strip()

    if not target_url:
        return

    # Normalize URL scheme
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    # 3. Send initial progress message
    status_msg = await bot.send_message(
        chat_id,
        f"⚡ <b>Cloning website &amp; extracting A to Z APIs...</b>\n\n"
        f"🌐 <b>Target:</b> <code>{target_url}</code>\n"
        f"⏳ <i>Please wait 3-5 seconds...</i>",
        reply_to_message_id=msg_id
    )
    status_id = status_msg.get("message_id") if status_msg else None

    start_time = time.time()

    # 4. Perform Scraping and Intel Analysis
    try:
        scraper = WebScraper(target_url=target_url, timeout=7.0, max_concurrency=25)
        html_code, files_map, intel = await scraper.clone_website()

        # Build in-memory ZIP
        zip_buf, zip_name, stats = ZipPackager.build_zip(
            domain=scraper.domain,
            files_map=files_map,
            intel=intel
        )

        elapsed_time = round(time.time() - start_time, 2)

        # 5. Build Result Caption
        caption = (
            f"╭────────────────────────╮\n"
            f"     ✅ <b>Download Complete</b>\n"
            f"╰────────────────────────╯\n\n"
            f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
            f"📦 <b>Size</b> ›  {stats['size_str']}\n"
            f"📁 <b>Files</b> ›  {stats['total_files']}\n"
            f"🔌 <b>APIs Found</b> ›  {stats['total_apis']} Endpoints\n"
            f"🔑 <b>Configs/Keys</b> ›  {stats['keys_count']} Detected\n"
            f"⏱ <b>Time</b> ›  {elapsed_time}s\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <i>Advance WebSource &amp; Intel Bot</i>\n"
            f"📁 <i>Check <code>INTEL_REPORT/</code> folder inside ZIP for all APIs!</i>"
        )

        # 6. Upload ZIP to Telegram
        success = await bot.send_document(
            chat_id=chat_id,
            file_bytes=zip_buf.getvalue(),
            filename=zip_name,
            caption=caption,
            reply_to_message_id=msg_id
        )

        # Delete or update status message
        if status_id:
            if not success:
                await bot.edit_message(
                    chat_id,
                    status_id,
                    "⚠️ <i>ZIP file created but Telegram failed to receive it (file might be too large).</i>"
                )
            else:
                await bot.edit_message(
                    chat_id,
                    status_id,
                    f"✅ <b>Done!</b> Processed in {elapsed_time}s."
                )

    except Exception as e:
        error_msg = f"❌ <b>Error processing website:</b>\n<code>{str(e)}</code>"
        if status_id:
            await bot.edit_message(chat_id, status_id, error_msg)
        else:
            await bot.send_message(chat_id, error_msg, reply_to_message_id=msg_id)
