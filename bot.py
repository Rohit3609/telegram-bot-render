import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Set up basic logging
logging.basicConfig(level=logging.INFO)

# Load your bot token and admin IDs
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")  # Make sure this is set correctly

# Healthcheck route
async def healthcheck(request):
    return web.Response(text="✅ Bot is running fine!")

# Your command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I am your bot 🤖")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        context.bot_data["rules"] = " ".join(context.args)
        await update.message.reply_text("✅ Rules updated!")
    else:
        await update.message.reply_text("⚡ Usage: /setrules <your rules>")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        context.bot_data["ban_words"].extend(context.args)
        await update.message.reply_text(f"✅ Added ban words: {', '.join(context.args)}")
    else:
        await update.message.reply_text("⚡ Usage: /addbanword <word1> <word2> ...")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ban_words = context.bot_data.get("ban_words", [])
    if ban_words:
        await update.message.reply_text("🚫 Banned words:\n" + "\n".join(ban_words))
    else:
        await update.message.reply_text("🚫 No banned words yet.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start /setrules /addbanword /listbanwords /help")

# Other message handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    for word in context.bot_data.get("ban_words", []):
        if word in text:
            await update.message.delete()
            return

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(context.bot_data.get("rules", "Welcome!"))

# Main entry point
async def main():
    if not BOT_TOKEN:
        logging.error("❌ Missing BOT_TOKEN! Please set it in environment variables.")
        exit(1)
    if not ADMIN_IDS:
        logging.error("❌ Missing ADMIN_IDS! Please set it in environment variables.")
        exit(1)

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # 🌟 Initialize bot shared data directly!
        app.bot_data["ban_words"] = []
        app.bot_data["rules"] = "Default rules: Be kind and respectful!"

        # Register command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("setrules", set_rules))
        app.add_handler(CommandHandler("addbanword", add_ban_word))
        app.add_handler(CommandHandler("listbanwords", list_ban_words))
        app.add_handler(CommandHandler("help", help_command))

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

        logging.info("🤖 Bot is starting...")

        # Start polling in background
        asyncio.create_task(app.run_polling())

        # Healthcheck mini web server
        web_app = web.Application()
        web_app.router.add_get('/', healthcheck)
        port = int(os.environ.get("PORT", 8080))
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        # Keep running
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}")
        exit(1)

# Run it
if __name__ == '__main__':
    asyncio.run(main())
