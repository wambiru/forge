from hustleforge_bot import main
from telegram.ext import Application
from fastapi import FastAPI, Request
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
application = None  # Initialize globally

@app.on_event("startup")
async def startup_event():
    global application
    try:
        logger.info("Initializing Telegram Application")
        application = main()  # Create Application
        await application.initialize()  # Initialize async components
        logger.info("Telegram Application initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing application: {str(e)}", exc_info=True)
        raise

@app.get("/")
async def root():
    logger.info("Received GET request to root")
    return {"message": "HustleForge AI Bot is running! Access via Telegram."}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        logger.info("Received webhook request")
        update = await request.json()
        logger.debug(f"Webhook update: {update}")
        await application.process_update(update)
        logger.info("Webhook processed successfully")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}