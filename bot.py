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
    ASK_QUESTION = 5

# Store user data
user_data = {}

def split_message(text, max_length=4000):
    """Split a long message into parts under max_length, preserving formatting."""
    lines = text.split('\n')
    parts = []
    current_part = []
    current_length = 0

    for line in lines:
        if current_length + len(line) + 2 > max_length:
            parts.append('\n\n'.join(current_part))
            current_part = [line]
            current_length = len(line) + 2
        else:
            current_part.append(line)
            current_length += len(line) + 2
    if current_part:
        parts.append('\n\n'.join(current_part))
    return parts

def clean_response(text):
    """Clean Gemini response to use bold Markdown and ensure spacing."""
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.replace('### ', '**').replace('## ', '**')
        if line.startswith('**'):
            line += '**'
        cleaned_lines.append(line)
    return '\n\n'.join(cleaned_lines)

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
        if message.text.startswith('/'):
            return
        else:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Start Now 🚀", callback_data="start_new"))
            keyboard.add(InlineKeyboardButton("Learn More 🌐", callback_data="learn_more"))
            retry_send_message(bot.reply_to, message, "Hey there! I’m HustleForge AI, your side hustle guru in Kenya! 😎 Ready to find ideas that match your skills?", reply_markup=keyboard)
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
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}. "
                f"Each idea should be under 100 words, use bold Markdown (**Idea 1**, **Idea 2**, **Idea 3**) for headings, "
                f"and include clear spacing between ideas. Avoid using ### or other headers."
            )
            logger.info(f"Sending prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                messages = split_message(f"Here are your side hustle ideas:\n\n{cleaned_response}")
                for i, msg in enumerate(messages, 1):
                    retry_send_message(bot.reply_to, message, msg if i == 1 else f"Part {i}:\n\n{msg}")
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(bot.reply_to, message, "Sorry, I couldn't generate ideas right now. Try again or use /cancel.")
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask a Question ❓", callback_data="ask_question"))
            keyboard.add(InlineKeyboardButton("End Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(bot.reply_to, message, "What would you like to do next?", reply_markup=keyboard)
            user_data[user_id]['state'] = State.ASK_QUESTION
        elif state == State.ASK_QUESTION:
            user_data[user_id]['question'] = message.text
            logger.info(f"Question received: {message.text}")
            prompt = (
                f"Answer the following question about side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}: "
                f"{message.text}. Keep the answer under 150 words, use Markdown for readability, and avoid ### headers."
            )
            logger.info(f"Sending question prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                messages = split_message(cleaned_response)
                for i, msg in enumerate(messages, 1):
                    retry_send_message(bot.reply_to, message, msg if i == 1 else f"Part {i}:\n\n{msg}")
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(bot.reply_to, message, "Sorry, I couldn't answer right now. Try again or use /cancel.")
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask Another Question ❓", callback_data="ask_question"))
            keyboard.add(InlineKeyboardButton("End Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(bot.reply_to, message, "Anything else you'd like to know?", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error in message handler: {str(e)}", exc_info=True)
        retry_send_message(bot.reply_to, message, f"Error: {str(e)}. Please try again or use /cancel.")
        user_data.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    goals = user_data.get(user_id, {}).get('goals', '')
    try:
        if call.data == "start_new":
            retry_send_message(bot.reply_to, call.message, "Starting new conversation...")
            start(call.message)
        elif call.data == "learn_more":
            retry_send_message(bot.reply_to, call.message, "Discover more at our website: https://linkedin/in/mwaura-wambiru?utm_source=telegram (explore our expert plans!)")
        elif call.data == "ask_question":
            retry_send_message(bot.reply_to, call.message, "Sure! What question do you have about the ideas?")
            user_data[user_id]['state'] = State.ASK_QUESTION
        elif call.data == "end_conversation":
            upsell = "To hit big goals like yours, our Expert Hustle Coach can help!" if "30000" in goals.lower() else ""
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Full Strategy (KES 500) 💼", callback_data="premium_strategy"))
            keyboard.add(InlineKeyboardButton("Talk to an Expert 🌐", callback_data="talk_expert"))
            keyboard.add(InlineKeyboardButton("End Conversation 🛑", callback_data="final_end"))
            keyboard.add(InlineKeyboardButton("Share with Friends 📣", callback_data="share_friends"))
            retry_send_message(bot.reply_to, call.message, f"Thanks for exploring with HustleForge AI! {upsell}\n\nReady to take the next step?", reply_markup=keyboard)
        elif call.data == "premium_strategy":
            retry_send_message(bot.reply_to, call.message, "For a full strategy with Expert Hustle Coach guidance (KES 500), pay via M-Pesa to 0721-49-48-36. Send receipt to start.")
        elif call.data == "talk_expert":
            retry_send_message(bot.reply_to, call.message, "Connect with our Expert Hustle Coach at https://linkedin/in/mwaura-wambiru?utm_source=telegram to unlock personalized guidance!")
        elif call.data == "final_end":
            retry_send_message(bot.reply_to, call.message, "Thanks for using HustleForge AI! Start again anytime with /start. 😊")
            user_data.pop(user_id, None)
        elif call.data == "share_friends":
            retry_send_message(bot.reply_to, call.message, "Share HustleForge AI with friends! Invite them to @AnzaBiz_bot and get a free KES 100 summary after 3 referrals. Visit https://linkedin/in/mwaura-wambiru?utm_source=telegram for details.")
        else:
            retry_send_message(bot.reply_to, call.message, "Sorry, something went wrong. Try again.")
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}", exc_info=True)
        retry_send_message(bot.reply_to, call.message, "Sorry, something went wrong. Try again.")

if __name__ == '__main__':
    logger.info("Starting bot in polling mode")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {str(e)}", exc_info=True)
            time.sleep(10)