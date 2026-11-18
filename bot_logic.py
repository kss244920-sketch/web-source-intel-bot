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
    """Async Client for Telegram Bot API with Inline Keyboard & Document support."""

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


def get_force_join_keyboard() -> Dict[str, Any]:
    """Generates Force Join inline buttons with color badges."""
    return {
        "inline_keyboard": [
            [
                {"text": "🟢 📢 Join Official Channel", "url": f"https://t.me/{FORCE_CHANNEL_USERNAME}"}
            ],
            [
                {"text": "👑 Contact Owner", "url": f"https://t.me/{OWNER_USERNAME}"},
                {"text": "🔄 Joined / Verify", "callback_data": "check_join"}
            ]
        ]
    }


def get_home_keyboard() -> Dict[str, Any]:
    """Generates Main Menu inline buttons with color badges."""
    return {
        "inline_keyboard": [
            [
                {"text": "🟢 📢 Updates Channel", "url": f"https://t.me/{FORCE_CHANNEL_USERNAME}"},
                {"text": "👑 Bot Owner", "url": f"https://t.me/{OWNER_USERNAME}"}
            ],
            [
                {"text": "ℹ️ Help & Features Guide", "callback_data": "help_info"}
            ]
        ]
    }


def get_action_selection_keyboard(url_hash: str) -> Dict[str, Any]:
    """Generates Vibrant Colored Buttons for Specific File / Package selection."""
    return {
        "inline_keyboard": [
            [
                {"text": "🟢 📦 Full Website ZIP (All in One)", "callback_data": f"dl_full:{url_hash}"}
            ],
            [
                {"text": "🔵 🔌 Only APIs & Secrets (.TXT)", "callback_data": f"dl_api:{url_hash}"}
            ],
            [
                {"text": "🟡 📜 JavaScript Files (.JS)", "callback_data": f"dl_js:{url_hash}"},
                {"text": "🔴 🎨 CSS Stylesheets (.CSS)", "callback_data": f"dl_css:{url_hash}"}
            ],
            [
                {"text": "📄 Single Clean HTML", "callback_data": f"dl_html:{url_hash}"},
                {"text": "🖼 Images & Media", "callback_data": f"dl_img:{url_hash}"}
            ],
            [
                {"text": "👑 Owner: @owAtom", "url": f"https://t.me/{OWNER_USERNAME}"},
                {"text": "📢 Channel", "url": f"https://t.me/{FORCE_CHANNEL_USERNAME}"}
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
    """Clones and delivers with real-time multi-stage visual progress bars."""
    start_time = time.time()
    try:
        # Stage 1: Connecting & Bypassing (25%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"⚡ <b>Stage 1/4: Connecting to Domain...</b>\n"
                f"{render_progress_bar(25)}\n\n"
                f"🌐 <b>Target:</b> <code>{target_url}</code>\n"
                f"⏳ <i>Bypassing WAF &amp; fetching HTML structure...</i>"
            )

        scraper = WebScraper(target_url=target_url, timeout=7.0, max_concurrency=25)
        html_code, files_map, intel = await scraper.clone_website()

        # Stage 2: Assets Downloaded (65%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"📥 <b>Stage 2/4: Assets Captured!</b>\n"
                f"{render_progress_bar(65)}\n\n"
                f"📁 <b>Files Downloaded:</b> {len(files_map)} assets\n"
                f"🔍 <i>Extracting embedded APIs &amp; secrets...</i>"
            )

        summary = intel.get_summary_report()
        total_apis = summary["statistics"]["total_relative_apis"] + summary["statistics"]["total_external_apis"]
        total_keys = summary["statistics"].get("total_secrets_detected", 0)

        # Stage 3: Packaging & Compiling (90%)
        if status_id:
            await bot.edit_message(
                chat_id, status_id,
                f"📦 <b>Stage 3/4: Compiling Package...</b>\n"
                f"{render_progress_bar(90)}\n\n"
                f"🔌 <b>APIs Identified:</b> {total_apis} routes\n"
                f"🔑 <b>Keys Detected:</b> {total_keys}\n"
                f"🚀 <i>Packaging &amp; uploading to Telegram...</i>"
            )

        elapsed_time = round(time.time() - start_time, 2)

        # 1. ONLY APIs & SECRETS (Sends as instant TXT document)
        if category == "api":
            text_report = intel.generate_text_report()
            txt_bytes = text_report.encode("utf-8")
            filename = f"apis_{scraper.domain.replace('.', '_')}.txt"

            caption = (
                f"╭────────────────────────╮\n"
                f"     🔵 <b>APIs &amp; Secrets Extracted</b>\n"
                f"╰────────────────────────╯\n\n"
                f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
                f"🔌 <b>APIs Found</b> ›  {total_apis} Endpoints\n"
                f"🔑 <b>Keys Detected</b> ›  {total_keys}\n"
                f"⏱ <b>Time</b> ›  {elapsed_time}s\n"
                f"📊 <b>Progress</b> ›  {render_progress_bar(100)}\n\n"
                f"📄 <i>Open the file above directly to view all discovered API routes &amp; tokens!</i>\n\n"
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

        # 2. ONLY HTML (Sends single HTML file directly)
        elif category == "html":
            html_bytes = html_code.encode("utf-8")
            filename = f"source_{scraper.domain.replace('.', '_')}.html"
            caption = (
                f"╭────────────────────────╮\n"
                f"     📄 <b>HTML Source Ready</b>\n"
                f"╰────────────────────────╯\n\n"
                f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
                f"📦 <b>Size</b> ›  {round(len(html_bytes)/1024, 1)} KB\n"
                f"⏱ <b>Time</b> ›  {elapsed_time}s\n"
                f"📊 <b>Progress</b> ›  {render_progress_bar(100)}\n\n"
                f"📄 <i>Single clean HTML file (Open in any browser or editor).</i>\n\n"
                f"👑 <b>Owner:</b> @{OWNER_USERNAME}"
            )
            await bot.send_document(
                chat_id=chat_id,
                file_bytes=html_bytes,
                filename=filename,
                caption=caption,
                mime_type="text/html",
                reply_to_message_id=reply_to_msg_id,
                reply_markup=get_home_keyboard()
            )

        # 3. ZIP PACKAGES (Full, JS only, CSS only, or Images only)
        else:
            zip_buf, zip_name, stats = ZipPackager.build_zip(
                domain=scraper.domain,
                files_map=files_map,
                intel=intel,
                category=category
            )
            category_titles = {
                "all": "🟢 <b>Full Website Source Complete</b>",
                "js": "🟡 <b>JavaScript Files Package</b>",
                "css": "🔴 <b>CSS Stylesheets Package</b>",
                "images": "🖼 <b>Images &amp; Media Package</b>"
            }
            title = category_titles.get(category, "✅ <b>Download Complete</b>")

            caption = (
                f"╭────────────────────────╮\n"
                f"     {title}\n"
                f"╰────────────────────────╯\n\n"
                f"🌐 <b>Domain</b> ›  <code>{scraper.domain}</code>\n"
                f"📦 <b>Size</b> ›  {stats['size_str']}\n"
                f"📁 <b>Files</b> ›  {stats['total_files']}\n"
                f"🔌 <b>APIs Found</b> ›  {stats['total_apis']} Endpoints\n"
                f"🔑 <b>Configs/Keys</b> ›  {stats['keys_count']} Detected\n"
                f"⏱ <b>Time</b> ›  {elapsed_time}s\n"
                f"📊 <b>Progress</b> ›  {render_progress_bar(100)}\n\n"
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
                f"{render_progress_bar(100)}\n\n"
                f"👉 Need another file? Choose above or send a new domain!"
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

    # 1. Handle Callback Query (e.g. clicking Colored Buttons)
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
                await bot.answer_callback_query(cb_id, "✅ Verified! Ab aap koi bhi link bhej sakte hain.", show_alert=False)
                verified_text = (
                    "🎉 <b>Channel Verification Successful!</b>\n\n"
                    "Ab aap hamare **Smart WebSource &amp; Intel Bot** ko freely use kar sakte hain.\n\n"
                    "👉 <b>Bas koi bhi link ya domain yahan bhejein:</b>\n"
                    "<code>goagamea.com</code> ya <code>https://example.com</code>"
                )
                if chat_id and msg_id:
                    await bot.edit_message(chat_id, msg_id, verified_text, reply_markup=get_home_keyboard())
            else:
                await bot.answer_callback_query(
                    cb_id,
                    f"❌ Aapne abhi tak @{FORCE_CHANNEL_USERNAME} join nahi kiya hai! Pehle channel join karein aur phir click karein.",
                    show_alert=True
                )
            return

        elif cb_data == "help_info":
            help_text = (
                "📖 <b>How to Use &amp; Features:</b>\n\n"
                "1️⃣ <b>Zero Command:</b> Koi command likhne ki zaroorat nahi hai. Bas direct domain ya URL bhejo.\n"
                "2️⃣ <b>Select Your Need:</b> Link bhejte hi colored buttons aayenge (Full ZIP, Only APIs, Only JS, Only CSS, ya Single HTML).\n"
                "3️⃣ <b>Live Progress Bar:</b> Real-time <code>[▰▰▰▰▱▱▱▱]</code> progress status dikhta hai.\n"
                "4️⃣ <b>A-to-Z API Extractor:</b> Website ke saare hidden routes aur keys 1 second me .TXT file me nikal sakte ho bina zip khole!\n\n"
                f"👤 <b>Developer / Owner:</b> @{OWNER_USERNAME}\n"
                f"📢 <b>Updates Channel:</b> @{FORCE_CHANNEL_USERNAME}"
            )
            await bot.answer_callback_query(cb_id)
            if chat_id and msg_id:
                await bot.edit_message(chat_id, msg_id, help_text, reply_markup=get_home_keyboard())
            return

        # Specific file download callbacks (dl_full, dl_api, dl_js, dl_css, dl_html, dl_img)
        elif cb_data.startswith(("dl_full:", "dl_api:", "dl_js:", "dl_css:", "dl_html:", "dl_img:")):
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
            category_map = {
                "dl_full": "all",
                "dl_api": "api",
                "dl_js": "js",
                "dl_css": "css",
                "dl_html": "html",
                "dl_img": "images"
            }
            category = category_map.get(action, "all")

            status_msg = await bot.send_message(
                chat_id,
                f"⚡ <b>Initializing Smart Engine...</b>\n"
                f"{render_progress_bar(10)}\n\n"
                f"🌐 <b>Target:</b> <code>{target_url}</code>\n"
                f"📁 <i>Preparing {category.upper()} stream...</i>",
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
            f"🔒 <b>Access Locked! Force Join Required</b>\n\n"
            f"Hamare bot ko use karne ke liye aapko hamara official channel join karna zaroori hai:\n\n"
            f"📢 <b>Channel:</b> @{FORCE_CHANNEL_USERNAME}\n"
            f"👑 <b>Owner:</b> @{OWNER_USERNAME}\n\n"
            f"👉 Pehle neeche diye gaye <b>Join Channel</b> button par click karke channel join karein, "
            f"phir <b>Joined / Verify</b> par click karein!"
        )
        await bot.send_message(
            chat_id,
            lock_text,
            reply_to_message_id=msg_id,
            reply_markup=get_force_join_keyboard()
        )
        return

    # 4. Handle /start and /help commands
    if text.startswith(("/start", "/help")):
        welcome_text = (
            "🚀 <b>Smart WebSource &amp; Intel Extractor Bot</b>\n\n"
            "Koi command likhne ki zaroorat nahi hai! Bas kisi bhi website ka link ya domain seedha yahan bhej dijiye.\n\n"
            "✨ <b>Available Download Options:</b>\n"
            "• 🟢 <b>Full Website ZIP:</b> Code, Assets, Images &amp; APIs\n"
            "• 🔵 <b>Only APIs &amp; Secrets:</b> Direct .TXT file without zip\n"
            "• 🟡 <b>JavaScript Files:</b> Only JS scripts &amp; logic\n"
            "• 🔴 <b>CSS Stylesheets:</b> Only styles &amp; fonts\n"
            "• 📄 <b>Single HTML:</b> Pure HTML code for easy viewing\n\n"
            f"👑 <b>Owner:</b> @{OWNER_USERNAME}\n"
            f"📢 <b>Channel:</b> @{FORCE_CHANNEL_USERNAME}\n\n"
            "👉 <b>Try it now:</b> Send any link directly:\n"
            "<code>goagamea.com</code> ya <code>https://example.com</code>"
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
            "Example:\n<code>goagamea.com</code>\nya\n<code>https://example.com</code>",
            reply_to_message_id=msg_id,
            reply_markup=get_home_keyboard()
        )
        return

    # 6. Generate Short URL Hash & Show Interactive Colored Action Menu!
    url_hash = make_url_hash(target_url)

    menu_text = (
        f"╭────────────────────────╮\n"
        f"     🌐 <b>Website Detected</b>\n"
        f"╰────────────────────────╯\n\n"
        f"🔗 <b>Target:</b> <code>{target_url}</code>\n\n"
        f"⚡ <i>Aapko kya download karna hai? Neeche diye gaye button par click karein:</i>"
    )
    await bot.send_message(
        chat_id,
        menu_text,
        reply_to_message_id=msg_id,
        reply_markup=get_action_selection_keyboard(url_hash)
    )
