import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.db import init_db
from bot.handlers import (
    start_command, registrar_command, jugadores_command,
    resultado_command, equipos_command, historial_command,
    alias_command, stats_command, tabla_command, analisis_command,
    handle_message
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "8080"))


async def post_init(application):
    await init_db()
    logger.info("Base de datos inicializada.")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN no está configurado")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("registrar", registrar_command))
    app.add_handler(CommandHandler("jugadores", jugadores_command))
    app.add_handler(CommandHandler("elo", jugadores_command))
    app.add_handler(CommandHandler("resultado", resultado_command))
    app.add_handler(CommandHandler("equipos", equipos_command))
    app.add_handler(CommandHandler("historial", historial_command))
    app.add_handler(CommandHandler("alias", alias_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("tabla", tabla_command))
    app.add_handler(CommandHandler("analisis", analisis_command))

    # Mensajes de texto (no comandos)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Modo webhook para producción, polling para desarrollo
    if WEBHOOK_URL:
        logger.info(f"Arrancando en modo webhook: {WEBHOOK_URL}/webhook")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook",
        )
    else:
        logger.info("Arrancando en modo polling (desarrollo)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    if sys.version_info >= (3, 12):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    main()
