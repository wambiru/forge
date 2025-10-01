import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai
from datetime import datetime

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # Gemini key
genai.configure(api_key=OPENAI_API_KEY)

# ... (Your existing constants: KENYAN_DATA, RESOURCE_LINKS, etc.)

# ... (Your existing functions: start, collect_skills, collect_location, collect_budget, collect_goals, generate_hustle_ideas, etc.)

async def webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming webhook updates"""
    await application.process_update(update)

def main():
    """Start the bot with webhook"""
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_skills)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_location)],
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_budget)],
            GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_goals)],
            MENU: [
                CallbackQueryHandler(button_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))

    logger.info("HustleForge AI Bot is starting...")
    return application

if __name__ == '__main__':
    # For local testing, use polling
    if os.getenv('ENV') == 'development':
        main().run_polling(allowed_updates=Update.ALL_TYPES)
    # For production, webhook setup is handled by Render