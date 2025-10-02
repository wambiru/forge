import os
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters
from telegram import Update
import google.generativeai as genai
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ENV = os.getenv('ENV', 'development')

# Gemini setup
try:
    logger.info("Configuring Gemini API")
    genai.configure(api_key=OPENAI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("Gemini API configured successfully")
except Exception as e:
    logger.error(f"Gemini initialization error: {str(e)}", exc_info=True)
    raise

# Conversation states
SKILLS, LOCATION, BUDGET, GOALS = range(4)

async def start(update: Update, context):
    logger.info(f"Received /start command from user {update.effective_user.id}")
    try:
        await update.message.reply_text(
            "Welcome to HustleForge AI! I'm here to help you find side hustle ideas in Kenya.\n"
            "What skills do you have? (e.g., cooking, phone repair, graphic design)"
        )
        logger.info("Sent welcome message")
        return SKILLS
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        return ConversationHandler.END

async def test_command(update: Update, context):
    logger.info(f"Received /test command from user {update.effective_user.id}")
    try:
        await update.message.reply_text("Test command received! The bot is working.")
        logger.info("Sent test command response")
    except Exception as e:
        logger.error(f"Error in test command: {str(e)}", exc_info=True)

async def skills(update: Update, context):
    context.user_data['skills'] = update.message.text
    logger.info(f"Skills received: {context.user_data['skills']}")
    await update.message.reply_text("Great! Where are you located? (e.g., Nairobi, Mombasa)")
    return LOCATION

async def location(update: Update, context):
    context.user_data['location'] = update.message.text
    logger.info(f"Location received: {context.user_data['location']}")
    await update.message.reply_text("What's your budget in KES? (e.g., 5000)")
    return BUDGET

async def budget(update: Update, context):
    context.user_data['budget'] = update.message.text
    logger.info(f"Budget received: {context.user_data['budget']}")
    await update.message.reply_text("What are your goals? (e.g., earn 20,000/month)")
    return GOALS

async def goals(update: Update, context):
    context.user_data['goals'] = update.message.text
    user_data = context.user_data
    prompt = (
        f"Generate side hustle ideas for someone in {user_data['location']} with skills in "
        f"{user_data['skills']}, a budget of {user_data['budget']} KES, and goals of {user_data['goals']}."
    )
    try:
        logger.info(f"Sending prompt to Gemini: {prompt}")
        response = model.generate_content(prompt)
        logger.info(f"Gemini response: {response.text}")
        await update.message.reply_text(f"Here are your side hustle ideas:\n{response.text}")
    except Exception as e:
        logger.error(f"Gemini error: {str(e)}", exc_info=True)
        await update.message.reply_text(f"Error generating ideas: {str(e)}")
    return ConversationHandler.END

async def cancel(update: Update, context):
    logger.info("Received /cancel command")
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

async def error_handler(update: Update, context):
    logger.error(f"Update {update} caused error: {context.error}", exc_info=True)

def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set")
        raise ValueError("OPENAI_API_KEY not set")

    logger.info("Building Telegram Application")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    logger.info("Registering handlers")
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SKILLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, skills)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, location)],
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget)],
            GOALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, goals)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Add standalone test command handler
    application.add_handler(CommandHandler('test', test_command))
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    logger.info("Handlers registered successfully")
    return application