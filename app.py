from hustleforge_bot import main
from telegram.ext import Application
from fastapi import FastAPI, Request

app = FastAPI()
application = main()  # Initialize your bot

@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    await application.process_update(update)
    return {"status": "ok"}