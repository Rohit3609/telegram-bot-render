import os
import logging
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
APP_URL = os.getenv("APP_URL")   # example: https://your-app.onrender.com
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# --- Flask App for Render ---
app = Flask(__name__)

# --- Telegram Application ---
application = Application.builder().token(TOKEN).build()


# --- Features / Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is online and ready! Admins can use commands.")


async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_text = (
        "📜 Group Rules:\n"
        "1. Be respectful\n"
        "2. No spam or ads\n"
        "3. No inappropriate requests\n"
        "4. Follow admin instructions"
    )
    await update.message.reply_text(rules_text)


async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 Welcome {member.mention_html()}! Please follow the group rules.",
            parse_mode="HTML",
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


# --- Admin-only Command Example ---
async def admin_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    await update.message.reply_text("✅ Admin command executed!")


# --- Register Handlers ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("rules", rules))
application.add_handler(CommandHandler("admin", admin_only))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ban_inappropriate))


# --- Flask Route for Telegram Webhook ---
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok"


# --- Health Check ---
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"


# --- Startup Hook: set webhook ---
@app.before_first_request
def init_webhook():
    import asyncio
    webhook_url = f"{APP_URL}/webhook/{TOKEN}"
    asyncio.get_event_loop().create_task(application.bot.set_webhook(webhook_url))
    logger.info(f"Webhook set to {webhook_url}")


# --- Run locally (Render uses gunicorn bot:app) ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
