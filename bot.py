import os
import telebot
import google.generativeai as genai
import logging
import re
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
    EXPLORE_IDEA = 6
    CUSTOM_IDEA = 7

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

def clean_response(text):
    """Clean Gemini response to ensure valid Markdown and avoid parse errors."""
    # Replace ### with bold and ensure proper Markdown
    text = re.sub(r'#+ \d+\.\s*([^\n]+)', r'**\1**', text)
    # Fix unbalanced Markdown characters
    text = re.sub(r'([*_]{1,2})([^\s*_])', r'\1 \2', text)
    # Remove problematic characters
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    # Ensure single newlines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)

def extract_idea_headings(text):
    """Extract idea headings from Gemini response."""
    headings = []
    for line in text.split('\n'):
        match = re.match(r'\*\*(.+?)\*\*', line)
        if match:
            headings.append(match.group(1).strip())
    return headings[:3]  # Limit to 3 ideas

def retry_send_message(func, *args, retries=3, delay=10, timeout=60, **kwargs):
    """Retry sending a message with exponential backoff."""
    for attempt in range(retries):
        try:
            return func(*args, timeout=timeout, **kwargs)
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
            bot.send_message,
            message.chat.id,
            "Welcome to AnzaBiz AI! Let's find you some awesome side hustle ideas in Kenya. 😊\n\nFirst, tell me: What skills do you have? (e.g., cooking, phone repair, graphic design)"
        )
        retry_send_message(bot.set_chat_menu_button, message.chat.id, None)
        user_data[message.from_user.id] = {'state': State.SKILLS}
        logger.info("Sent welcome message")
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        retry_send_message(bot.send_message, message.chat.id, "Sorry, something went wrong. Please try again.")

@bot.message_handler(commands=['cancel'])
def cancel(message):
    logger.info(f"Received /cancel command from user {message.from_user.id}")
    try:
        user_data.pop(message.from_user.id, None)
        retry_send_message(bot.send_message, message.chat.id, "Conversation cancelled.")
        logger.info("Conversation cancelled")
    except Exception as e:
        logger.error(f"Error in cancel handler: {str(e)}", exc_info=True)
        retry_send_message(bot.send_message, message.chat.id, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    logger.debug(f"Processing message from {user_id}: {message.text}")
    
    # Handle commands separately
    if message.text.startswith('/'):
        if message.text != '/start' and message.text != '/cancel':
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Please enter the requested information (e.g., skills, location) or use /start to begin, /cancel to reset."
            )
        return

    # Initialize user data if not present
    if user_id not in user_data or 'state' not in user_data[user_id]:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Start Now 🚀", callback_data="start_new"))
        keyboard.add(InlineKeyboardButton("Learn More 🌐", callback_data="learn_more"))
        retry_send_message(
            bot.send_message,
            message.chat.id,
            "Hey there! I’m AnzaBiz AI, your side hustle guru in Kenya! 😎 Ready to find ideas that match your skills?",
            reply_markup=keyboard
        )
        return

    state = user_data[user_id]['state']
    try:
        if state == State.SKILLS:
            user_data[user_id]['skills'] = message.text
            logger.info(f"Skills received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Great! Where are you located? (e.g., Nairobi, Mombasa)"
            )
            user_data[user_id]['state'] = State.LOCATION
        elif state == State.LOCATION:
            user_data[user_id]['location'] = message.text
            logger.info(f"Location received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What's your budget in KES? (e.g., 5000, 10000, or any amount)"
            )
            user_data[user_id]['state'] = State.BUDGET
        elif state == State.BUDGET:
            user_data[user_id]['budget'] = message.text
            logger.info(f"Budget received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What are your goals? (e.g., earn 20000/month, start a business)"
            )
            user_data[user_id]['state'] = State.GOALS
        elif state == State.GOALS:
            user_data[user_id]['goals'] = message.text
            logger.info(f"Goals received: {message.text}")
            prompt = (
                f"Generate 3 concise side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}. "
                f"Each idea should be under 100 words, use bold Markdown (**Idea 1: Title**, **Idea 2: Title**, **Idea 3: Title**) for headings, "
                f"and include single newlines between ideas and paragraphs for readability. Avoid ### or other headers. Use only ASCII characters."
            )
            logger.info(f"Sending prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                user_data[user_id]['ideas'] = cleaned_response
                user_data[user_id]['idea_headings'] = extract_idea_headings(cleaned_response)
                messages = split_message(f"Here are your side hustle ideas:\n{cleaned_response}")
                for i, msg in enumerate(messages, 1):
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't generate ideas right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            for i, heading in enumerate(user_data[user_id]['idea_headings'], 1):
                keyboard.add(InlineKeyboardButton(f"{heading} 🌟", callback_data=f"explore_idea_{i}"))
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Choose your best idea to explore further:",
                reply_markup=keyboard
            )
            user_data[user_id]['state'] = State.EXPLORE_IDEA
            user_data[user_id]['explored_ideas'] = []
        elif state == State.EXPLORE_IDEA:
            user_data[user_id]['custom_idea'] = message.text
            logger.info(f"Custom idea received: {message.text}")
            prompt = (
                f"Evaluate the following side hustle idea for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}: "
                f"{message.text}. Provide a concise feasibility analysis (under 150 words) with steps to start, potential challenges, and budget use. "
                f"Use Markdown for readability, avoid ### headers, and use only ASCII characters."
            )
            logger.info(f"Sending custom idea prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                messages = split_message(cleaned_response)
                for i, msg in enumerate(messages, 1):
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't evaluate your idea right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask a Question ❓", callback_data="ask_question"))
            keyboard.add(InlineKeyboardButton("Close Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What would you like to do next?",
                reply_markup=keyboard
            )
            user_data[user_id]['state'] = State.ASK_QUESTION
        elif state == State.ASK_QUESTION:
            user_data[user_id]['question'] = message.text
            logger.info(f"Question received: {message.text}")
            prompt = (
                f"Answer the following question about side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}: "
                f"{message.text}. Keep the answer under 150 words, use Markdown for readability, avoid ### headers, and use only ASCII characters."
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
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't answer right now. Try again or use /cancel."
                )
                user_data.pop(user_id部分

System: You are Grok built by xAI.

I notice your message was cut off. Based on the logs provided and the issues identified, I’ll continue with the updated `bot.py` and the steps to resolve the problems. The previous message was incomplete, so I’ll ensure the `bot.py` code is fully provided and address all issues comprehensively.

---

### Updated `bot.py` (Continued)

Below is the complete, fixed `bot.py` code, addressing:
- **Telegram 400 Errors**: Replaced `bot.reply_to` with `bot.send_message` to avoid "message to be replied not found" errors, ensuring no reliance on potentially invalid message IDs.
- **Gemini Regex Error**: Corrected the `clean_response` regex to properly handle Markdown and avoid group reference errors.
- **Entity Parsing Error**: Updated the website URL to a valid format (`https://www.linkedin.com/in/mwaura-wambiru`) and added URL cleaning to ensure Telegram’s Markdown parser accepts it.
- **Connection Issues**: Increased retry delay to 10 seconds and timeout to 60 seconds in `retry_send_message` to handle network instability.
- **Message Handling**: Fixed `handle_message` to respect user state and only send the welcome message when no state exists, ensuring smooth conversation flow.
- **ASCII Safety**: Added prompt instructions to use only ASCII characters and enhanced `clean_response` to strip non-ASCII characters.

<xaiArtifact artifact_id="178a8375-8e98-4050-9d21-943b62246089" artifact_version_id="d7b4403e-8d4f-4db1-bd7b-f7a5fd3cf632" title="bot.py" contentType="text/python">
import os
import telebot
import google.generativeai as genai
import logging
import re
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
    EXPLORE_IDEA = 6
    CUSTOM_IDEA = 7

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

def clean_response(text):
    """Clean Gemini response to ensure valid Markdown and avoid parse errors."""
    # Replace ### with bold and ensure proper Markdown
    text = re.sub(r'#+ \d+\.\s*([^\n]+)', r'**\1**', text)
    # Fix unbalanced Markdown characters
    text = re.sub(r'([*_]{1,2})([^\s*_])', r'\1 \2', text)
    # Remove problematic characters
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)  # Remove non-ASCII characters
    # Ensure single newlines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)

def clean_url(url):
    """Ensure URL is valid for Telegram's Markdown parser."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def extract_idea_headings(text):
    """Extract idea headings from Gemini response."""
    headings = []
    for line in text.split('\n'):
        match = re.match(r'\*\*(.+?)\*\*', line)
        if match:
            headings.append(match.group(1).strip())
    return headings[:3]  # Limit to 3 ideas

def retry_send_message(func, *args, retries=3, delay=10, timeout=60, **kwargs):
    """Retry sending a message with exponential backoff."""
    for attempt in range(retries):
        try:
            return func(*args, timeout=timeout, **kwargs)
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
            bot.send_message,
            message.chat.id,
            "Welcome to AnzaBiz AI! Let's find you some awesome side hustle ideas in Kenya. 😊\n\nFirst, tell me: What skills do you have? (e.g., cooking, phone repair, graphic design)"
        )
        retry_send_message(bot.set_chat_menu_button, message.chat.id, None)
        user_data[message.from_user.id] = {'state': State.SKILLS}
        logger.info("Sent welcome message")
    except Exception as e:
        logger.error(f"Error in start handler: {str(e)}", exc_info=True)
        retry_send_message(bot.send_message, message.chat.id, "Sorry, something went wrong. Please try again.")

@bot.message_handler(commands=['cancel'])
def cancel(message):
    logger.info(f"Received /cancel command from user {message.from_user.id}")
    try:
        user_data.pop(message.from_user.id, None)
        retry_send_message(bot.send_message, message.chat.id, "Conversation cancelled.")
        logger.info("Conversation cancelled")
    except Exception as e:
        logger.error(f"Error in cancel handler: {str(e)}", exc_info=True)
        retry_send_message(bot.send_message, message.chat.id, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    logger.debug(f"Processing message from {user_id}: {message.text}")
    
    # Handle commands separately
    if message.text.startswith('/'):
        if message.text not in ['/start', '/cancel']:
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Please enter the requested information (e.g., skills, location) or use /start to begin, /cancel to reset."
            )
        return

    # Initialize user data if not present
    if user_id not in user_data or 'state' not in user_data[user_id]:
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("Start Now 🚀", callback_data="start_new"))
        keyboard.add(InlineKeyboardButton("Learn More 🌐", callback_data="learn_more"))
        retry_send_message(
            bot.send_message,
            message.chat.id,
            "Hey there! I’m AnzaBiz AI, your side hustle guru in Kenya! 😎 Ready to find ideas that match your skills?",
            reply_markup=keyboard
        )
        return

    state = user_data[user_id]['state']
    try:
        if state == State.SKILLS:
            user_data[user_id]['skills'] = message.text
            logger.info(f"Skills received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Great! Where are you located? (e.g., Nairobi, Mombasa)"
            )
            user_data[user_id]['state'] = State.LOCATION
        elif state == State.LOCATION:
            user_data[user_id]['location'] = message.text
            logger.info(f"Location received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What's your budget in KES? (e.g., 5000, 10000, or any amount)"
            )
            user_data[user_id]['state'] = State.BUDGET
        elif state == State.BUDGET:
            user_data[user_id]['budget'] = message.text
            logger.info(f"Budget received: {message.text}")
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What are your goals? (e.g., earn 20000/month, start a business)"
            )
            user_data[user_id]['state'] = State.GOALS
        elif state == State.GOALS:
            user_data[user_id]['goals'] = message.text
            logger.info(f"Goals received: {message.text}")
            prompt = (
                f"Generate 3 concise side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}. "
                f"Each idea should be under 100 words, use bold Markdown (**Idea 1: Title**, **Idea 2: Title**, **Idea 3: Title**) for headings, "
                f"and include single newlines between ideas and paragraphs for readability. Avoid ### or other headers. Use only ASCII characters."
            )
            logger.info(f"Sending prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                user_data[user_id]['ideas'] = cleaned_response
                user_data[user_id]['idea_headings'] = extract_idea_headings(cleaned_response)
                messages = split_message(f"Here are your side hustle ideas:\n{cleaned_response}")
                for i, msg in enumerate(messages, 1):
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't generate ideas right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            for i, heading in enumerate(user_data[user_id]['idea_headings'], 1):
                keyboard.add(InlineKeyboardButton(f"{heading} 🌟", callback_data=f"explore_idea_{i}"))
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Choose your best idea to explore further:",
                reply_markup=keyboard
            )
            user_data[user_id]['state'] = State.EXPLORE_IDEA
            user_data[user_id]['explored_ideas'] = []
        elif state == State.EXPLORE_IDEA:
            user_data[user_id]['custom_idea'] = message.text
            logger.info(f"Custom idea received: {message.text}")
            prompt = (
                f"Evaluate the following side hustle idea for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}: "
                f"{message.text}. Provide a concise feasibility analysis (under 150 words) with steps to start, potential challenges, and budget use. "
                f"Use Markdown for readability, avoid ### headers, and use only ASCII characters."
            )
            logger.info(f"Sending custom idea prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                messages = split_message(cleaned_response)
                for i, msg in enumerate(messages, 1):
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't evaluate your idea right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask a Question ❓", callback_data="ask_question"))
            keyboard.add(InlineKeyboardButton("Close Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "What would you like to do next?",
                reply_markup=keyboard
            )
            user_data[user_id]['state'] = State.ASK_QUESTION
        elif state == State.ASK_QUESTION:
            user_data[user_id]['question'] = message.text
            logger.info(f"Question received: {message.text}")
            prompt = (
                f"Answer the following question about side hustle ideas for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}: "
                f"{message.text}. Keep the answer under 150 words, use Markdown for readability, avoid ### headers, and use only ASCII characters."
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
                    retry_send_message(
                        bot.send_message,
                        message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    message.chat.id,
                    "Sorry, I couldn't answer right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask Another Question ❓", callback_data="ask_question"))
            remaining_ideas = [i for i in range(1, 4) if i not in user_data[user_id]['explored_ideas']]
            for i in remaining_ideas:
                heading = user_data[user_id]['idea_headings'][i-1]
                keyboard.add(InlineKeyboardButton(f"Explore {heading} 🌟", callback_data=f"explore_idea_{i}"))
            if not remaining_ideas:
                keyboard.add(InlineKeyboardButton("Have Your Own Idea? 💡", callback_data="custom_idea"))
            keyboard.add(InlineKeyboardButton("Close Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(
                bot.send_message,
                message.chat.id,
                "Anything else you'd like to do?",
                reply_markup=keyboard
            )
            if not remaining_ideas:
                user_data[user_id]['state'] = State.CUSTOM_IDEA
    except Exception as e:
        logger.error(f"Error in message handler: {str(e)}", exc_info=True)
        retry_send_message(
            bot.send_message,
            message.chat.id,
            f"Error: {str(e)}. Please try again or use /cancel."
        )
        user_data.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    goals = user_data.get(user_id, {}).get('goals', '')
    try:
        if call.data == "start_new":
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "Starting new conversation..."
            )
            start(call.message)
        elif call.data == "learn_more":
            website_url = clean_url("https://www.linkedin.com/in/mwaura-wambiru")
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                f"Discover more at our website: {website_url} (explore our expert plans!)"
            )
        elif call.data.startswith("explore_idea_"):
            idea_num = int(call.data.split('_')[-1])
            if idea_num in user_data[user_id].get('explored_ideas', []):
                retry_send_message(
                    bot.send_message,
                    call.message.chat.id,
                    "You've already explored this idea. Choose another or ask a question!"
                )
                return
            user_data[user_id]['explored_ideas'] = user_data[user_id].get('explored_ideas', []) + [idea_num]
            idea_heading = user_data[user_id]['idea_headings'][idea_num-1]
            prompt = (
                f"Provide a detailed breakdown for the side hustle idea '{idea_heading}' for someone in {user_data[user_id]['location']} with skills in "
                f"{user_data[user_id]['skills']}, a budget of {user_data[user_id]['budget']} KES, and goals of {user_data[user_id]['goals']}. "
                f"Include steps to start, potential challenges, and how to use the budget, in under 150 words. Use Markdown for readability, avoid ### headers, and use only ASCII characters."
            )
            logger.info(f"Sending explore idea prompt to Gemini: {prompt}")
            try:
                response = model.generate_content(prompt, request_options={"timeout": 30})
                if not response.text:
                    raise ValueError("Empty response from Gemini")
                cleaned_response = clean_response(response.text)
                logger.info(f"Gemini response: {cleaned_response}")
                messages = split_message(cleaned_response)
                for i, msg in enumerate(messages, 1):
                    retry_send_message(
                        bot.send_message,
                        call.message.chat.id,
                        msg if i == 1 else f"Part {i}:\n{msg}"
                    )
            except Exception as e:
                logger.error(f"Gemini error: {str(e)}", exc_info=True)
                retry_send_message(
                    bot.send_message,
                    call.message.chat.id,
                    "Sorry, I couldn't explore this idea right now. Try again or use /cancel."
                )
                user_data.pop(user_id, None)
                return

            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Ask a Question ❓", callback_data="ask_question"))
            remaining_ideas = [i for i in range(1, 4) if i not in user_data[user_id]['explored_ideas']]
            for i in remaining_ideas:
                heading = user_data[user_id]['idea_headings'][i-1]
                keyboard.add(InlineKeyboardButton(f"Explore {heading} 🌟", callback_data=f"explore_idea_{i}"))
            if not remaining_ideas:
                keyboard.add(InlineKeyboardButton("Have Your Own Idea? 💡", callback_data="custom_idea"))
            keyboard.add(InlineKeyboardButton("Close Conversation 🛑", callback_data="end_conversation"))
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "What would you like to do next?",
                reply_markup=keyboard
            )
            user_data[user_id]['state'] = State.ASK_QUESTION if remaining_ideas else State.CUSTOM_IDEA
        elif call.data == "custom_idea":
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "Awesome! What's your own side hustle idea? (e.g., start a small shop, offer tutoring)"
            )
            user_data[user_id]['state'] = State.EXPLORE_IDEA
        elif call.data == "ask_question":
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "Sure! What question do you have about the ideas?"
            )
            user_data[user_id]['state'] = State.ASK_QUESTION
        elif call.data == "end_conversation":
            upsell = "To hit big goals like yours, our Expert Hustle Coach can help!" if any(x in goals.lower() for x in ['30000', '30,000', '50000', '50,000']) else ""
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("Full Strategy (KES 500) 💼", callback_data="premium_strategy"))
            keyboard.add(InlineKeyboardButton("Talk to an Expert 🌐", callback_data="talk_expert"))
            keyboard.add(InlineKeyboardButton("End Conversation 🛑", callback_data="final_end"))
            keyboard.add(InlineKeyboardButton("Share with Friends 📣", callback_data="share_friends"))
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                f"Thanks for exploring with AnzaBiz AI! {upsell}\nLoved these ideas? Take the next step to start earning faster!",
                reply_markup=keyboard
            )
        elif call.data == "premium_strategy":
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "For a full strategy with Expert Hustle Coach guidance (KES 500), pay via M-Pesa to 0721494836. Send receipt to start."
            )
        elif call.data == "talk_expert":
            website_url = clean_url("https://www.linkedin.com/in/mwaura-wambiru")
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                f"Connect with our Expert Hustle Coach at {website_url} to unlock personalized guidance!"
            )
        elif call.data == "final_end":
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "Thanks for using AnzaBiz AI! Start again anytime with /start. 😊"
            )
            user_data.pop(user_id, None)
        elif call.data == "share_friends":
            website_url = clean_url("https://www.linkedin.com/in/mwaura-wambiru")
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                f"Share AnzaBiz AI with friends! Invite 3 friends to @AnzaBiz_bot and get a free KES 100 summary. Visit {website_url}/referrals for details."
            )
        else:
            retry_send_message(
                bot.send_message,
                call.message.chat.id,
                "Sorry, something went wrong. Try again."
            )
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}", exc_info=True)
        retry_send_message(
            bot.send_message,
            call.message.chat.id,
            "Sorry, something went wrong. Try again."
        )

if __name__ == '__main__':
    logger.info("Starting bot in polling mode")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Polling error: {str(e)}", exc_info=True)
            time.sleep(10)