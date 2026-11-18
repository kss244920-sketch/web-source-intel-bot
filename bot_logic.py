import re
import time
from typing import Optional, Dict, Any
import httpx

from core.scraper import WebScraper
from core.packager import ZipPackager

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


def extract_target_url(text: str) -> Optional[str]:
    """Smart auto-detector for URLs, domains, and paths without requiring commands."""
    text = text.strip()
    if text.startswith("/ws"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            text = parts[1].strip()

    # 1. Match full http/https URLs first
    match = re.search(r'https?://[^\s<>"\']+', text, re.IGNORECASE)
    if match:
        return match.group(0).rstrip(".,;!?'\")")

    # 2. Match standard domains (e.g. goagamea.com, www.site.co.in/path)
    domain_match = re.search(
        r'\b(?:www\.)?[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}(?::[0-9]{1,5})?(?:/[^\s<>"\']*)?',
        text,
        re.IGNORECASE
    )
    if domain_match:
        return "https://" + domain_match.group(0).rstrip(".,;!?'\")")

    return None


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

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, data=data, files=files, timeout=40.0)
                return r.status_code == 200
            except Exception as e:
                print(f"Error sending document: {e}")
                return False


async def handle_update(bot_token: str, update: Dict[str, Any]) -> None:
    """Processes incoming Telegram updates with Smart Auto-Detection."""
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
            "🚀 <b>Smart WebSource &amp; Intel Extractor Bot</b>\n\n"
            "Ab kisi bhi command ki zaroorat nahi hai! Bas kisi bhi website ka link ya domain seedha yahan bhej dijiye.\n\n"
            "✨ <b>What this Bot does:</b>\n"
            "• 🌐 <b>Complete Source:</b> HTML, CSS, JS, Images, Fonts &amp; Configs\n"
            "• 🔌 <b>A-to-Z API Extractor:</b> Live Backend routes, REST APIs &amp; WebSockets\n"
            "• 🔑 <b>Secrets Detector:</b> Firebase configs, Payment keys &amp; Auth tokens\n"
            "• 📦 <b>Offline Ready:</b> Unzip karke bina internet ke direct chalao\n\n"
            "👉 <b>Try it now:</b> Send any link directly:\n"
            "<code>goagamea.com</code> ya <code>https://example.com</code>"
        )
        await bot.send_message(chat_id, welcome_text, reply_to_message_id=msg_id)
        return

    # 2. Smart Auto-Detect Target URL from message
    target_url = extract_target_url(text)

    if not target_url:
        # User sent non-URL random text
        await bot.send_message(
            chat_id,
            "💡 <b>Please send a valid website link or domain!</b>\n\n"
            "Example:\n<code>goagamea.com</code>\nya\n<code>https://example.com</code>",
            reply_to_message_id=msg_id
        )
        return

    # 3. Send immediate progress message
    status_msg = await bot.send_message(
        chat_id,
        f"⚡ <b>Smart Engine: Cloning &amp; Extracting APIs...</b>\n\n"
        f"🌐 <b>Target:</b> <code>{target_url}</code>\n"
        f"⏳ <i>Scanning HTML, JS, CSS &amp; Backend Endpoints...</i>",
        reply_to_message_id=msg_id
    )
    status_id = status_msg.get("message_id") if status_msg else None

    start_time = time.time()

    # 4. Perform Smart Scraping and Intel Analysis
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
            f"👤 <b>Downloaded By</b> ›  @ExtractWebScBot 🚀\n"
            f"📁 <i>Check <code>INTEL_REPORT/</code> folder inside ZIP for all extracted APIs!</i>"
        )

        # 6. Upload ZIP to Telegram
        success = await bot.send_document(
            chat_id=chat_id,
            file_bytes=zip_buf.getvalue(),
            filename=zip_name,
            caption=caption,
            reply_to_message_id=msg_id
        )

        if status_id:
            if not success:
                await bot.edit_message(
                    chat_id,
                    status_id,
                    "⚠️ <i>ZIP file created but upload failed (file might be too large for Telegram API).</i>"
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
