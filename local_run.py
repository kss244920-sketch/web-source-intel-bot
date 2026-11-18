import asyncio
import os
import httpx
from dotenv import load_dotenv

from bot_logic import handle_update

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


async def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN is empty! Please set BOT_TOKEN in .env file.")
        return

    print("🚀 Starting WebSource & Intel Bot locally (Polling mode)...")

    # Clear any existing webhook
    async with httpx.AsyncClient() as client:
        await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        bot_info = (await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")).json()
        if bot_info.get("ok"):
            print(f"🤖 Connected as @{bot_info['result']['username']} ({bot_info['result']['first_name']})")
        else:
            print("❌ Invalid BOT_TOKEN! Please check your token.")
            return

    offset = 0
    print("✨ Bot is live and listening for commands (/ws <url> or direct URLs)... Press Ctrl+C to stop.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        # Handle update asynchronously
                        asyncio.create_task(handle_update(BOT_TOKEN, update))
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Polling warning: {e}")
                await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")
