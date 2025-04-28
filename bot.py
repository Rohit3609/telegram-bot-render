import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split()))
APP_URL = os.getenv("APP_URL")

# App
flask_app = Flask(__name__)

# Telegram Bot
application = ApplicationBuilder().token(BOT_TOKEN).build()

MAX_STORED_MESSAGES = 10

# Initialize bot_data
async def init_bot_data(application):
    if "rules_text" not in application.bot_data:
        application.bot_data["rules_text"] = "Welcome! Group Rules: No spamming. No NSFW. Be respectful."
    if "ban_words" not in application.bot_data:
        application.bot_data["ban_words"] = ["porn", "sex", "nude"]

# Admin check
async def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update):
        await update.message.reply_text("Bot is active. Admin mode enabled.")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update):
        context.bot_data["rules_text"] = ' '.join(context.args)
        await update.message.reply_text("Rules updated!")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update):
        word = ' '.join(context.args).lower()
        if word not in context.bot_data["ban_words"]:
            context.bot_data["ban_words"].append(word)
            await update.message.reply_text(f"Added to ban list: {word}")
        else:
            await update.message.reply_text(f"'{word}' is already banned.")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update):
        await update.message.reply_text(f"Current banned words: {', '.join(context.bot_data['ban_words'])}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update):
        await update.message.reply_text("""Admin Commands:
/setrules <text> - Set group rules
/addbanword <word> - Add a word to banned list
/listbanwords - Show banned words
/help - Show this help
""")

# Handle normal messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower()
    group_id = update.message.chat_id

    if 'user_messages' not in context.chat_data:
        context.chat_data['user_messages'] = {}
    if user_id not in context.chat_data['user_messages']:
        context.chat_data['user_messages'][user_id] = []

    context.chat_data['user_messages'][user_id].append(update.message.message_id)
    if len(context.chat_data['user_messages'][user_id]) > MAX_STORED_MESSAGES:
        context.chat_data['user_messages'][user_id].pop(0)

    # Ban check
    for word in context.bot_data['ban_words']:
        if word in text:
            try:
                bot_member = await context.bot.get_chat_member(group_id, context.bot.id)
                if bot_member.status != "administrator":
                    await update.message.reply_text("⚠ I need admin rights to ban users!")
                    return

                await update.message.delete()
                await context.bot.ban_chat_member(chat_id=group_id, user_id=user_id)

                # Delete past messages
                for msg_id in context.chat_data['user_messages'][user_id]:
                    try:
                        await context.bot.delete_message(chat_id=group_id, message_id=msg_id)
                    except:
                        continue

                await context.bot.send_message(
                    chat_id=group_id,
                    text=f"🚨 User {update.effective_user.full_name} was banned for inappropriate content."
                )
                break
            except Exception as e:
                logger.error(f"Ban failed: {e}")

# New member joins
async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        await update.message.reply_text(context.bot_data["rules_text"])

# Webhook route
@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)

        # Flask cannot await, so we schedule async task manually
        asyncio.create_task(application.process_update(update))
        
        return "ok"

# Home route for Render health check
@flask_app.route("/")
def home():
    return "Bot is running!"

# Set webhook and add handlers
async def main():
    await init_bot_data(application)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setrules", set_rules))
    application.add_handler(CommandHandler("addbanword", add_ban_word))
    application.add_handler(CommandHandler("listbanwords", list_ban_words))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    # Set webhook
    webhook_url = f"{APP_URL}/webhook/{BOT_TOKEN}"
    await application.bot.set_webhook(url=webhook_url)

if __name__ == "__main__":
    asyncio.run(main())
    flask_app.run(host="0.0.0.0", port=10000)
