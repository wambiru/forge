import os
import telebot
import google.generativeai as genai
import logging
from enum import Enum
from dotenv import load_dotenv
import requests
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Load .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
ENV = os.getenv('ENV', 'development')

# Validate environment variables
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    raise ValueError("TELEGRAM_BOT_TOKEN not set")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not set")
    raise ValueError("GEMINI_API_KEY not set")

# Initialize bot with custom timeout
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='Markdown')

# Gemini setup
try:
    logger.info("Configuring Gemini API")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Gemini API configured successfully")
except Exception as e:
    logger.error(f"Gemini initialization error: {str(e)}", exc_info=True)
    raise

# Conversation states
class State(Enum):
    SKILLS = 1
    LOCATION = 2
    BUDGET = 3
    GOALS = 4

# Store user data
user_data = {}

def split_message(text, max_length=4000):
    """Split a long message into parts under max_length, preserving formatting."""
    lines = text.split('\n')
    parts = []
    current_part = []
    current_length = 0

    for line in lines:
        if current_length + len(line) + 1 > max_length:
            parts.append('\n'.join(current_part))
            current_part = [line]
            current_length = len(line) + 1
        else:
            current_part.append(line)
            current_length += len(line) + 1
    if current_part:
        parts.append('\n'.join(current_part))
    return parts

def retry_send_message(func, *args, retries=3, delay=5, **kwargs):
    """Retry sending a message with exponential backoff."""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except (requests.exceptions.RequestException, telebot.apihelper.ApiTelegramException) as e:
            logger.warning(f"Attempt {attempt+1}/{retries} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                logger.error(f"Failed after {retries} attempts: {str(e)}")
                raise

@bot.message_handler(commands=['start'])
def start(message):
    logger.info(f"Received /start command from user {message.from_user.id}")
    try:
        # Clear any existing state
        user_data.pop(message.from_user.id, None)
        retry_send_message(
            bot.reply_to,
            message,
            "Welcome to HustleForge AI! Let's find you some awesome side hustle ideas in Kenya. 😊\n\nFirst, tell me: What skills do you have? (e.g., cooking, phone repair, graphic design)"
        )
        retry_send_message(bot.set_chat_menu_button, message.chat.id, None)
        user_data[message.from_user.id] = {'state': State.SKILLS}
        logger.info("Sent welcome message")
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        retry_send_message(bot.reply_to, message, "Sorry, something went wrong. Please try again.")

@bot.message_handler(commands=['cancel'])
def cancel(message):
    logger.info(f"Received /cancel command from user {message.from_user.id}")
    try:
        user_data.pop(message.from_user.id, None)
        retry_send_message(bot.reply_to, message, "Conversation cancelled.")
        logger.info("Conversation cancelled")
    except Exception as e:
        logger.error(f"Error in cancel handler: {str(e)}", exc_info=True)
        retry_send_message(bot.reply_to, message, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    logger.debug(f"Processing message from {user_id}: {message.text}")
    if user_id not in user_data or 'state' not in user_data[user_id]:
        retry_send_message(bot.reply_to, message, "Please start with /start.")
        return

    state = user_data[user_id]['state']
    try:
        if state == State.SKILLS:
            if message.text.startswith('/'):
                retry_send_message(bot.reply_to, message, "Please enter your skills (e.g., cooking), not a command. Use /cancel to reset.")
                return
            user_data[user_id]['skills'] = message.text
            logger.info(f"Skills received: {message.text}")
            retry_send_message(bot.reply_to, message, "Great! Where are you located? (e.g., Nairobi, Mombasa)")
            user_data[user_id]['state'] = State.LOCATION
        elif state == State.LOCATION:
            user_data[user_id]['location'] = message.text
            logger.info(f"Location received: {message.text}")
            retry_send_message(bot.reply_to, message, "What's your budget in KES? (e.g., 5000)")
            user_data[user_id]['state'] = State.BUDGET
        elif state == State.BUDGET:
            user_data[user_id]['budget'] = message.text
            logger.info(f"Budget received: {message.text}")
            retry_send_message(bot.reply_to, message, "What are your goals? (e.g., earn 20,000/month)")
            user_data[user_id]['state'] = State.GOALS
        elif state == State.GOALS:
            user_data[user_id]['goals'] = message.text
            logger.info(f"Goals received: {message.text}")
            prompt = (
                f"Generate 3 concise side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}. Keep each idea under 100 words, with formatting for readability."
            )
            logger.info(f"Sending prompt to Gemini: {prompt}")
            response = model.generate_content(prompt)
            logger.info(f"Gemini response: {response.text}")
            # Split the response into parts
            messages = split_message(f"Here are your side hustle ideas:\n{response.text}")
            for i, msg in enumerate(messages, 1):
                retry_send_message(bot.reply_to, message, msg if i == 1 else f"Part {i}:\n{msg}")

            # Add options for further questions and monetization
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask a Question", callback_data="ask_question"))
            keyboard.add(InlineKeyboardButton("Get Full Strategy (KES 500)", callback_data="premium_strategy"))
            keyboard.add(InlineKeyboardButton("Start New", callback_data="start_new"))
            retry_send_message(bot.reply_to, message, "What next?", reply_markup=keyboard)
            user_data.pop(user_id, None)
    except Exception as e:
        logger.error(f"Error in message handler: {str(e)}", exc_info=True)
        retry_send_message(bot.reply_to, message, f"Error: {str(e)}. Please try again or use /cancel.")
        user_data.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    if call.data == "ask_question":
        retry_send_message(bot.reply_to, call.message, "Sure! What question do you have about the ideas?")
    elif call.data == "premium_strategy":
        retry_send_message(bot.reply_to, call.message, "For a full strategy with human guidance, pay KES 500 via M-Pesa to [your M-Pesa number]. Send receipt to start.")
    elif call.data == "start_new":
        retry_send_message(bot.reply_to, call.message, "Starting new conversation...")
        start(call.message)

if __name__ == '__main__':
    logger.info("Starting bot in polling mode")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {str(e)}", exc_info=True)
            time.sleep(10)