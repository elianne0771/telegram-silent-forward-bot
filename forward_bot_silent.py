import os
import logging
import asyncio
import json
from asyncio import Queue

from telegram import Bot, Update
from telegram.error import TimedOut, NetworkError
from aiohttp import web

# ============ CONFIG ============
TOKEN_SOURCE = os.getenv("TOKEN_BOT1")
TOKEN_DEST   = os.getenv("TOKEN_BOT2")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://ton-bot.onrender.com/webhook
PORT = int(os.getenv("PORT", 10000))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

queue = Queue()
bot_source = Bot(TOKEN_SOURCE)
bot_dest = Bot(TOKEN_DEST)

# Worker qui forwarde tout
async def worker():
    while True:
        try:
            raw_update = await queue.get()
            update = Update.de_json(raw_update, bot_source)
            if not update or not update.effective_message:
                continue

            msg = update.effective_message
            user = update.effective_user or msg.from_user
            username = user.username or user.full_name or "Inconnu"
            chat_title = update.effective_chat.title or "DM privé"

            prefix = f"✉ De @{username} ({user.id})\n📍 {chat_title}"

            try:
                if msg.text:
                    await bot_dest.send_message(TARGET_CHAT_ID, f"{prefix}\n\n{msg.text}")
                elif msg.photo:
                    await bot_dest.send_photo(TARGET_CHAT_ID, msg.photo[-1].file_id, caption=prefix)
                elif msg.video:
                    await bot_dest.send_video(TARGET_CHAT_ID, msg.video.file_id, caption=prefix)
                elif msg.document:
                    await bot_dest.send_document(TARGET_CHAT_ID, msg.document.file_id, caption=prefix)
                elif msg.voice:
                    await bot_dest.send_voice(TARGET_CHAT_ID, msg.voice.file_id, caption=prefix)
                elif msg.sticker:
                    await bot_dest.send_sticker(TARGET_CHAT_ID, msg.sticker.file_id)
                else:
                    await bot_dest.send_message(TARGET_CHAT_ID, f"{prefix}\n[Type: {msg.content_type}]")

                logger.info(f"Forwardé ← @{username} | {chat_title}")

            except (TimedOut, NetworkError):
                await asyncio.sleep(5)
                await queue.put(raw_update)  # retry
            except Exception as e:
                logger.error(f"Erreur envoi: {e}")

            await asyncio.sleep(0.05)  # ~20 msg/s max
        except Exception as e:
            logger.error(f"Worker crash: {e}")

# Webhook endpoint
async def webhook_handler(request):
    if request.method == "POST":
        try:
            data = await request.json()
            await queue.put(data)  # direct dans la queue
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"Webhook erreur: {e}")
    return web.Response(status=405)

# Setup du webhook Telegram
async def set_webhook():
    if WEBHOOK_URL:
        await bot_source.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook configuré → {WEBHOOK_URL}")
    else:
        logger.warning("WEBHOOK_URL manquant → ajoute-le sur Render")

# Main
async def main():
    await set_webhook()
    asyncio.create_task(worker())

    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info("Bot silencieux 100% opérationnel – tout est forwardé")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    if not all([TOKEN_SOURCE, TOKEN_DEST, TARGET_CHAT_ID]):
        logger.error("Variables manquantes ! Vérifie TOKEN_BOT1 / TOKEN_BOT2 / TARGET_CHAT_ID")
    else:
        asyncio.run(main())
