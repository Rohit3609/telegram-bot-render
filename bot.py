import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables!")

# Flask app for webhook
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()

# Example command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Your bot is up and running 🚀")

# Register handler
application.add_handler(CommandHandler("start", start))

# Webhook route for Telegram
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok", 200

# Root route
@app.route("/", methods=["GET"])
def index():
    return "Telegram Bot is running with Flask + Render 🚀"

# Run locally for testing (not used in Render, Render uses Gunicorn)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
