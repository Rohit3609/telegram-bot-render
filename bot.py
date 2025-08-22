import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

APP_URL = os.getenv("APP_URL")   # e.g. https://your-app.onrender.com
if not APP_URL:
    logger.warning("APP_URL environment variable not set, webhook won't work properly")

# Handle ADMIN_IDS with error checking
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
if admin_ids_str:
    try:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    except ValueError:
        logger.warning("ADMIN_IDS contains invalid values. Ignoring admin IDs.")
        ADMIN_IDS = []

# --- Flask App for Render ---
app = Flask(__name__)

# --- Telegram Application ---
application = Application.builder().token(TOKEN).build()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is online and ready!")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 Group Rules:\n"
        "1. Be respectful\n"
        "2. No spam or ads\n"
        "3. No inappropriate requests\n"
        "4. Follow admin instructions"
    )
    await update.message.reply_text(text)

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_html(
            f"👋 Welcome {member.mention_html()}! Please follow the group rules."
        )
        await rules(update, context)

async def ban_inappropriate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    bad_words = ["18+", "porn", "nude", "sex", "xxx"]

    if any(word in text for word in bad_words):
        try:
            await update.message.delete()
            await update.effective_chat.ban_member(update.message.from_user.id)
            logger.info(f"Banned {update.message.from_user.id} for inappropriate content")
        except Exception as e:
            logger.error(f"Ban failed: {e}")

async def admin_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    await update.message.reply_text("✅ Admin command executed!")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("rules", rules))
application.add_handler(CommandHandler("admin", admin_only))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ban_inappropriate))

# --- Webhook route ---
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
        return "ok"
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return "error", 500

# --- Health Check ---
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

# --- Initialize webhook on startup ---
@app.route("/init-webhook", methods=["GET"])
def init_webhook():
    if not APP_URL:
        return "APP_URL not set", 400
    
    webhook_url = f"{APP_URL}/webhook/{TOKEN}"
    try:
        # Use asyncio.run instead of create_task for synchronous context
        asyncio.run(application.bot.set_webhook(webhook_url))
        logger.info(f"Webhook set to {webhook_url}")
        return f"Webhook set to {webhook_url}"
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return f"Failed to set webhook: {e}", 500

# --- Run the app ---
if __name__ == "__main__":
    # Initialize webhook when running locally
    if APP_URL:
        try:
            webhook_url = f"{APP_URL}/webhook/{TOKEN}"
            asyncio.run(application.bot.set_webhook(webhook_url))
            logger.info(f"Webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
