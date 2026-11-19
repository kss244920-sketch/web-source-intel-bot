import re
import time
import hashlib
from typing import Optional, Dict, Any, List
import httpx

from core.scraper import WebScraper
from core.packager import ZipPackager

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

# Configuration
OWNER_USERNAME = "owAtom"
FORCE_CHANNEL_USERNAME = "OwAbyss"
FORCE_CHANNEL_ID = -1003810383682

# In-memory URL cache for callback buttons (stores url_hash -> target_url)
URL_CACHE: Dict[str, str] = {}


def render_progress_bar(percent: int, length: int = 10) -> str:
    """Generates visual high-tech progress meter string."""
    filled = max(0, min(length, int(length * percent / 100)))
    empty = length - filled
    return f"[{'▰' * filled}{'▱' * empty}] {percent}%"


def make_url_hash(url: str) -> str:
    """Creates a short 8-char hash of the URL for Telegram callback data."""
    h = hashlib.md5(url.strip().lower().encode("utf-8")).hexdigest()[:8]
    URL_CACHE[h] = url.strip()
    return h


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
    """Async Client for Telegram Bot API with Native Colored Button Styles."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token.strip()
        self.api_url = f"{TELEGRAM_API_BASE}{self.bot_token}"

    async def is_user_joined(self, user_id: int) -> bool:
        """Verifies if user has joined the required force channel."""
        url = f"{self.api_url}/getChatMember"
        params = {"chat_id": FORCE_CHANNEL_ID, "user_id": user_id}
        async with httpx.AsyncClient() as client:
            try:
                r = await client.get(url, params=params, timeout=6.0)
                if r.status_code == 200:
                    status = r.json().get("result", {}).get("status", "")
                    if status in ["creator", "administrator", "member", "restricted"]:
                        return True
            except Exception:
                pass
        return False

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, json=payload, timeout=10.0)
                if r.status_code == 200:
                    return r.json().get("result")
            except Exception:
                pass
        return None

    async def edit_message(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> None:
        url = f"{self.api_url}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=payload, timeout=10.0)
            except Exception:
                pass

    async def answer_callback_query(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> None:
        url = f"{self.api_url}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert
        }
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=payload, timeout=6.0)
            except Exception:
                pass

    async def send_document(
        self,
        chat_id: int | str,
        file_bytes: bytes,
        filename: str,
        caption: str,
        mime_type: str = "application/zip",
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> bool:
        url = f"{self.api_url}/sendDocument"
        data = {
            "chat_id": str(chat_id),
            "caption": caption,
            "parse_mode": "HTML"
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = str(reply_to_message_id)
        if reply_markup:
            import json
            data["reply_markup"] = json.dumps(reply_markup)

        files = {
            "document": (filename, file_bytes, mime_type)
        }

        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(url, data=data, files=files, timeout=40.0)
                return r.status_code == 200
            except Exception as e:
                print(f"Error sending document: {e}")
                return False


# --- MINIMAL 3 BUTTON KEYBOARDS (TRUE COLOR STYLES: GREEN, BLUE, RED) ---

def get_force_join_keyboard() -> Dict[str, Any]:
    """Minimal 3-button Force Join keyboard."""
    return {
        "inline_keyboard": [
            [
                {"text": "📢 Join Channel (@OwAbyss)", "url": f"https://t.me/{FORCE_CHANNEL_USERNAME}", "style": "primary"}
            ],
            [
                {"text": "🔄 Joined / Verify", "callback_data": "check_join", "style": "success"},
                {"text": "👑 Owner (@owAtom)", "url": f"https://t.me/{OWNER_USERNAME}", "style": "danger"}
            ]
        ]
    }


def get_home_keyboard() -> Dict[str, Any]:
    """Minimal 3-button Home keyboard."""
    return {
        "inline_keyboard": [
            [
                {"text": "📢 Updates Channel", "url": f"https://t.me/{FORCE_CHANNEL_USERNAME}", "style": "primary"},
                {"text": "👑 Owner (@owAtom)", "url": f"https://t.me/{OWNER_USERNAME}", "style": "danger"}
            ],
            [
                {"text": "ℹ️ How to Use", "callback_data": "help_info", "style": "success"}
            ]
        ]
    }


def get_action_selection_keyboard(url_hash: str) -> Dict[str, Any]:
    """Minimal 3-button Action keyboard: Full Source (Green), APIs & Secrets (Blue), Owner (Red)."""
    return {
        "inline_keyboard": [
            [
                {"text": "⚡ Download Full Source (ZIP)", "callback_data": f"dl_full:{url_hash}", "style": "success"}
            ],
            [
                {"text": "🔌 Extract APIs & Client (.TXT)", "callback_data": f"dl_api:{url_hash}", "style": "primary"}
            ],
            [
                {"text": "👑 Owner (@owAtom)", "url": f"https://t.me/{OWNER_USERNAME}", "style": "danger"}
            ]
        ]
    }


async def process_download_request(
    bot: TelegramBotClient,
    chat_id: int | str,
    target_url: str,
    category: str,
    status_id: Optional[int] = None,
    reply_to_msg_id: Optional[int] = None
) -> None:
    """Clones, unpacks sourcemaps, generates API client & delivers with progress bars."""
    start_time = time.time()
    try:
        # Stage 1: Connecting (25%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"⚡ <b>Stage 1/4: Connecting to Target...</b>\n"
                f"{render_progress_bar(25)}\n\n"
                f"🌐 <b>Domain:</b> <code>{target_url}</code>\n"
                f"⏳ <i>Bypassing WAF &amp; fetching HTML structure...</i>"
            )

        scraper = WebScraper(target_url=target_url, timeout=7.0, max_concurrency=25)
        html_code, files_map, intel = await scraper.clone_website()

        # Stage 2: Assets Captured (65%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"📥 <b>Stage 2/4: Assets &amp; Code Captured!</b>\n"
                f"{render_progress_bar(65)}\n\n"
                f"📁 <b>Assets Downloaded:</b> {len(files_map)} files\n"
                f"🔍 <i>Extracting APIs, SPA routes &amp; sourcemaps...</i>"
            )

        summary = intel.get_summary_report()
        total_apis = summary["statistics"]["total_relative_apis"] + summary["statistics"]["total_external_apis"]
        total_spa = summary["statistics"]["total_spa_routes"]
        total_keys = summary["statistics"].get("total_secrets_detected", 0)

        # Stage 3: Packaging & Generating API Client (90%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"📦 <b>Stage 3/4: Building API Client &amp; Prompt...</b>\n"
                f"{render_progress_bar(90)}\n\n"
                f"🔌 <b>APIs Found:</b> {total_apis} routes\n"
                f"🗺️ <b>SPA Routes:</b> {total_spa} screens\n"
                f"🚀 <i>Packaging &amp; uploading to Telegram...</i>"
            )

        elapsed_time = round(time.time() - start_time, 2)

        # 1. ONLY APIs, CLIENT & SECRETS (Sends as instant TXT document)
        if category == "api":
            text_report = intel.generate_text_report()
            # Also attach quick Python API client code at the bottom of the text report
            api_client_py = intel.generate_api_client_py()
            full_txt = text_report + "\n\n" + ("=" * 65) + "\n   AUTO-GENERATED PYTHON API CLIENT\n" + ("=" * 65) + "\n\n" + api_client_py
            txt_bytes = full_txt.encode("utf-8")
            filename = f"apis_client_{scraper.domain.replace('.', '_')}.txt"

            caption = (
                f"╭────────────────────────╮\n"
                f"     🔌 <b>APIs &amp; Client Ready</b>\n"
                f"╰────────────────────────╯\n\n"
                f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
                f"🔌 <b>APIs Found</b> ›  {total_apis} Endpoints\n"
                f"🗺️ <b>SPA Screens</b> ›  {total_spa} Routes\n"
                f"🔑 <b>Keys Detected</b> ›  {total_keys}\n"
                f"⏱ <b>Time</b> ›  {elapsed_time}s\n"
                f"📊 <b>Progress</b> ›  {render_progress_bar(100)}\n\n"
                f"📄 <i>Open file above directly to view all endpoints &amp; Python SDK script!</i>\n\n"
                f"👑 <b>Owner:</b> @{OWNER_USERNAME}"
            )
            await bot.send_document(
                chat_id=chat_id,
                file_bytes=txt_bytes,
                filename=filename,
                caption=caption,
                mime_type="text/plain",
                reply_to_message_id=reply_to_msg_id,
                reply_markup=get_home_keyboard()
            )

        # 2. FULL WEBSITE REVERSE-ENGINEERED ZIP PACKAGE
        else:
            zip_buf, zip_name, stats = ZipPackager.build_zip(
                domain=scraper.domain,
                files_map=files_map,
                intel=intel,
                category="all"
            )
            sourcemap_tag = f"\n🧠 <b>SourceMaps:</b> Unpacked to <code>original_src/</code>" if stats["sourcemaps_unpacked"] > 0 else ""

            caption = (
                f"╭────────────────────────╮\n"
                f"     ⚡ <b>Full Source &amp; Intel Complete</b>\n"
                f"╰────────────────────────╯\n\n"
                f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
                f"📦 <b>Size</b> ›  {stats['size_str']}\n"
                f"📁 <b>Files</b> ›  {stats['total_files']}\n"
                f"🔌 <b>APIs Found</b> ›  {stats['total_apis']} Endpoints\n"
                f"🗺️ <b>SPA Routes</b> ›  {stats['spa_routes_count']} Screens\n"
                f"🔑 <b>Keys Detected</b> ›  {stats['keys_count']}{sourcemap_tag}\n"
                f"⏱ <b>Time</b> ›  {elapsed_time}s\n"
                f"📊 <b>Progress</b> ›  {render_progress_bar(100)}\n\n"
                f"🤖 <i>Includes <code>api_client.py</code> &amp; <code>AI_CLONE_PROMPT.md</code></i>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👑 <b>Owner</b> ›  @{OWNER_USERNAME}\n"
                f"📢 <b>Channel</b> ›  @{FORCE_CHANNEL_USERNAME}"
            )
            await bot.send_document(
                chat_id=chat_id,
                file_bytes=zip_buf.getvalue(),
                filename=zip_name,
                caption=caption,
                mime_type="application/zip",
                reply_to_message_id=reply_to_msg_id,
                reply_markup=get_home_keyboard()
            )

        if status_id:
            await bot.edit_message(
                chat_id,
                status_id,
                f"✅ <b>Delivered 100%!</b> ({elapsed_time}s)\n"
                f"{render_progress_bar(100)}"
            )

    except Exception as e:
        error_msg = f"❌ <b>Error processing website:</b>\n<code>{str(e)}</code>"
        if status_id:
            await bot.edit_message(chat_id, status_id, error_msg, reply_markup=get_home_keyboard())
        else:
            await bot.send_message(chat_id, error_msg, reply_to_message_id=reply_to_msg_id, reply_markup=get_home_keyboard())


async def handle_update(bot_token: str, update: Dict[str, Any]) -> None:
    """Processes incoming Telegram updates (Messages & Callback Queries)."""
    bot = TelegramBotClient(bot_token)

    # 1. Handle Callback Query (Minimal 3 buttons)
    callback_query = update.get("callback_query")
    if callback_query:
        cb_id = callback_query.get("id")
        cb_data = callback_query.get("data") or ""
        user = callback_query.get("from", {})
        user_id = user.get("id")
        msg = callback_query.get("message")
        chat_id = msg.get("chat", {}).get("id") if msg else None
        msg_id = msg.get("message_id") if msg else None

        if cb_data == "check_join":
            is_member = await bot.is_user_joined(user_id)
            if is_member:
                await bot.answer_callback_query(cb_id, "✅ Verified! You can now send any website link.", show_alert=False)
                verified_text = (
                    "🎉 <b>Channel Verification Successful!</b>\n\n"
                    "Now you can freely use <b>Advance WebSource &amp; Intel Bot</b>.\n\n"
                    "📌 <b>Simply send any website URL or domain directly:</b>\n"
                    "<code>goagamea.com</code> or <code>https://example.com</code>"
                )
                if chat_id and msg_id:
                    await bot.edit_message(chat_id, msg_id, verified_text, reply_markup=get_home_keyboard())
            else:
                await bot.answer_callback_query(
                    cb_id,
                    f"❌ You have not joined @{FORCE_CHANNEL_USERNAME} yet! Please join the channel first.",
                    show_alert=True
                )
            return

        elif cb_data == "help_info":
            help_text = (
                "📖 <b>How to Use &amp; Features:</b>\n\n"
                "• <b>Direct Link:</b> Send any domain or URL directly (e.g. <code>goagamea.com</code>).\n"
                "• <b>Full Source (ZIP):</b> Complete HTML, CSS, JS, Images, <code>api_client.py</code> &amp; <code>AI_CLONE_PROMPT.md</code>.\n"
                "• <b>APIs &amp; Client (.TXT):</b> Instant text report of all endpoints, keys &amp; Python SDK script without unzipping.\n\n"
                f"👑 <b>Owner:</b> @{OWNER_USERNAME}\n"
                f"📢 <b>Channel:</b> @{FORCE_CHANNEL_USERNAME}"
            )
            await bot.answer_callback_query(cb_id)
            if chat_id and msg_id:
                await bot.edit_message(chat_id, msg_id, help_text, reply_markup=get_home_keyboard())
            return

        # Specific file download callbacks (dl_full or dl_api)
        elif cb_data.startswith(("dl_full:", "dl_api:")):
            action, url_hash = cb_data.split(":", 1)
            target_url = URL_CACHE.get(url_hash)

            if not target_url:
                await bot.answer_callback_query(
                    cb_id,
                    "⚠️ Session expired! Please send the website link again.",
                    show_alert=True
                )
                return

            await bot.answer_callback_query(cb_id, "⏳ Fetching requested files...")
            category = "api" if action == "dl_api" else "all"

            status_msg = await bot.send_message(
                chat_id,
                f"⚡ <b>Processing Target...</b>\n"
                f"{render_progress_bar(10)}\n\n"
                f"🌐 <b>Domain:</b> <code>{target_url}</code>\n"
                f"📁 <i>Extracting {'APIs & Client' if category == 'api' else 'Full Source Package'}...</i>",
                reply_to_message_id=msg_id
            )
            status_id = status_msg.get("message_id") if status_msg else None

            await process_download_request(
                bot=bot,
                chat_id=chat_id,
                target_url=target_url,
                category=category,
                status_id=status_id,
                reply_to_msg_id=msg_id
            )
            return

    # 2. Handle Incoming Text Messages
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    msg_id = message.get("message_id")
    user = message.get("from", {})
    user_id = user.get("id")

    if not chat_id or not text or not user_id:
        return

    # 3. Check Force-Join Channel Verification before allowing anything
    is_member = await bot.is_user_joined(user_id)
    if not is_member:
        lock_text = (
            f"🔒 <b>Access Locked: Channel Join Required</b>\n\n"
            f"To use this bot, please join our official channel first:\n\n"
            f"📢 <b>Channel:</b> @{FORCE_CHANNEL_USERNAME}\n"
            f"👑 <b>Owner:</b> @{OWNER_USERNAME}\n\n"
            f"Click the button below to join, then tap <b>Joined / Verify</b>!"
        )
        await bot.send_message(
            chat_id,
            lock_text,
            reply_to_message_id=msg_id,
            reply_markup=get_force_join_keyboard()
        )
        return

    # 4. Handle /start and /help commands (Clean, Loved English Format)
    if text.startswith(("/start", "/help")):
        welcome_text = (
            "🚀 <b>Welcome to Advance WebSource &amp; Intel Bot!</b>\n\n"
            "I extract and reverse-engineer any website's <b>Full Source Code + A-to-Z Embedded APIs</b> in a single offline-ready ZIP file.\n\n"
            "✨ <b>Features:</b>\n"
            "• 🌐 <b>Full Source:</b> HTML, CSS, JS, Images &amp; Fonts\n"
            "• 🔌 <b>A-to-Z API Extraction:</b> Relative routes, Backend APIs &amp; WebSockets\n"
            "• 🤖 <b>Auto API Client:</b> Ready-to-use Python SDK script (<code>api_client.py</code>)\n"
            "• 🎯 <b>AI Clone Prompt:</b> Instant blueprint to recreate the app in Cursor/ChatGPT\n"
            "• 🧠 <b>Source Map Unpacker:</b> Reconstructs original unminified developer code\n"
            "• 📦 <b>Offline-Ready ZIP:</b> Assets locally mapped for offline browsing\n\n"
            "📌 <b>How to Use:</b>\n"
            "Simply send any website URL or domain directly!\n"
            "<i>Example: <code>goagamea.com</code> or <code>https://example.com</code></i>"
        )
        await bot.send_message(
            chat_id,
            welcome_text,
            reply_to_message_id=msg_id,
            reply_markup=get_home_keyboard()
        )
        return

    # 5. Smart Auto-Detect Target URL from message
    target_url = extract_target_url(text)

    if not target_url:
        await bot.send_message(
            chat_id,
            "💡 <b>Please send a valid website link or domain!</b>\n\n"
            "Example:\n<code>goagamea.com</code>\nor\n<code>https://example.com</code>",
            reply_to_message_id=msg_id,
            reply_markup=get_home_keyboard()
        )
        return

    # 6. Generate Short URL Hash & Show Minimal 3-Button Action Menu!
    url_hash = make_url_hash(target_url)

    menu_text = (
        f"⚡ <b>Website Detected</b>\n\n"
        f"🌐 <b>Target:</b> <code>{target_url}</code>\n\n"
        f"Choose an option below:"
    )
    await bot.send_message(
        chat_id,
        menu_text,
        reply_to_message_id=msg_id,
        reply_markup=get_action_selection_keyboard(url_hash)
    )
