import os
from telegram.ext import Application, CommandHandler
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def start(update, context):
    logger.info(f"Received /start command from user {update.effective_user.id}")
    try:
        await update.message.reply_text("Basic bot test: Hello from HustleForge!")
        logger.info("Sent basic start response")
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)

async def error_handler(update, context):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=True)

def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    logger.info("Building Telegram Application")
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_error_handler(error_handler)
    logger.info("Handlers registered successfully")
    return application