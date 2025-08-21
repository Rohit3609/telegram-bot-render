import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ==========================
# Flask app for Render
# ==========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running ✅"

# ==========================
# Telegram Bot
# ==========================
TOKEN = os.getenv("BOT_TOKEN")

# Store user messages for later deletion
user_messages = {}

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am your group manager bot 🚀")

# Welcome new members with rules
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"Welcome {member.mention_html()}! Please follow the group rules ✅",
            parse_mode="HTML"
        )

# Track messages (store for deletion if banned later)
async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    msg_id = update.message.message_id
    if user_id not in user_messages:
        user_messages[user_id] = []
    user_messages[user_id].append(msg_id)

# Ban inappropriate messages and delete history
BAD_WORDS = ["badword1", "badword2", "inappropriate"]

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    if any(bad in text for bad in BAD_WORDS):
        # Ban the user
        await context.bot.ban_chat_member(chat_id, user_id)
        await update.message.reply_text("⚠️ User has been banned for inappropriate content.")

        # Delete their old messages
        if user_id in user_messages:
            for msg_id in user_messages[user_id]:
                try:
                    await context.bot.delete_message(chat_id, msg_id)
                except Exception:
                    pass
            del user_messages[user_id]

# ==========================
# Bot Runner
# ==========================
def run_bot():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate))

    print("Bot running...")
    application.run_polling()

# Run bot in background thread
threading.Thread(target=run_bot).start()

# ==========================
# Run Flask App
# ==========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
