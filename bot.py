import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")

# Enable Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Simple healthcheck for Render
async def healthcheck(request):
    return web.Response(text="✅ Bot is running fine!")

# Initialize bot_data when a user sends a message
async def init_bot_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else None
    if user_id and user_id not in context.bot_data:
        context.bot_data[user_id] = {"messages": 0}
    if user_id:
        context.bot_data[user_id]["messages"] += 1
    logging.info(f"User {user_id} has sent {context.bot_data[user_id]['messages']} messages.")

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! I'm alive and ready!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Help: Available commands are /start and /help.")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Rules are set!")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Added a banned word!")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Listing banned words...")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📩 Message received!")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(f"👋 Welcome {member.full_name}!")

# Main function
async def main():
    if not BOT_TOKEN:
        logging.error("❌ Missing BOT_TOKEN! Please set it in environment variables")
        exit(1)
    if not ADMIN_IDS:
        logging.error("❌ Missing ADMIN_IDS! Please set it in environment variables")
        exit(1)

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Set up handlers
        app.add_handler(MessageHandler(filters.ALL, init_bot_data), group=-1)  # First, init data
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("setrules", set_rules))
        app.add_handler(CommandHandler("addbanword", add_ban_word))
        app.add_handler(CommandHandler("listbanwords", list_ban_words))
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

        logging.info("🤖 Bot is starting...")

        # Start polling
        asyncio.create_task(app.run_polling())

        # Small Webserver for Render
        web_app = web.Application()
        web_app.router.add_get("/", healthcheck)

        port = int(os.environ.get("PORT", 8080))
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}")
        exit(1)

# Entrypoint
if __name__ == '__main__':
    asyncio.run(main())
