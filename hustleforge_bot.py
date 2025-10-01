import os
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters
from telegram import Update
import google.generativeai as genai

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ENV = os.getenv('ENV', 'development')

# Gemini setup
genai.configure(api_key=OPENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Conversation states
SKILLS, LOCATION, BUDGET, GOALS = range(4)

async def start(update: Update, context):
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome to HustleForge AI! I'm here to help you find side hustle ideas in Kenya.\n"
        "What skills do you have? (e.g., cooking, phone repair, graphic design)"
    )
    return SKILLS

async def skills(update: Update, context):
    context.user_data['skills'] = update.message.text
    await update.message.reply_text("Great! Where are you located? (e.g., Nairobi, Mombasa)")
    return LOCATION

async def location(update: Update, context):
    context.user_data['location'] = update.message.text
    await update.message.reply_text("What's your budget in KES? (e.g., 5000)")
    return BUDGET

async def budget(update: Update, context):
    context.user_data['budget'] = update.message.text
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
        print(f"Sending prompt to Gemini: {prompt}")  # Log for Render
        response = model.generate_content(prompt)
        print(f"Gemini response: {response.text}")  # Log for Render
        await update.message.reply_text(f"Here are your side hustle ideas:\n{response.text}")
    except Exception as e:
        print(f"Gemini error: {str(e)}")  # Log for Render
        await update.message.reply_text(f"Error generating ideas: {str(e)}")
    return ConversationHandler.END

async def cancel(update: Update, context):
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

def main():
    """Set up and return the Telegram bot application."""
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment variables")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set in environment variables")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

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

    application.add_handler(conv_handler)
    return application  # Always return for webhooks