import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("render-telegram-bot")

# ---------- Environment ----------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

# Prefer Render's auto URL if available, otherwise use your own APP_URL
APP_URL = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("APP_URL")
if not APP_URL:
    logger.warning(
        "APP_URL / RENDER_EXTERNAL_URL not set. "
        "Webhook won't be configured automatically."
    )

# Optional admin ids
admin_ids_env = os.getenv("ADMIN_IDS", "")
try:
    ADMIN_IDS = [int(x.strip()) for x in admin_ids_env.split(",") if x.strip()]
except ValueError:
    ADMIN_IDS = []
    logger.warning("ADMIN_IDS contained invalid values; admin list cleared.")

# ---------- Flask ----------
app = Flask(__name__)

# ---------- Telegram Application ----------
application = Application.builder().token(TOKEN).build()

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is online and ready! Admins can use /admin.")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📜 Group Rules:\n"
        "1) Be respectful\n"
        "2) No spam or ads\n"
        "3) No inappropriate requests\n"
        "4) Follow admin instructions"
    )
    await update.message.reply_text(text)

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_html(
            f"👋 Welcome {member.mention_html()}! Please read the rules below."
        )
    await rules(update, context)

async def ban_inappropriate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").lower()
    bad_words = ["18+", "porn", "nude", "sex", "xxx"]
    if any(w in text for w in bad_words):
        try:
            # delete the message
            await update.message.delete()
            # ban the user (use bot API directly for PTB v20)
            await context.bot.ban_chat_member(
                chat_id=update.effective_chat.id,
                user_id=update.effective_user.id,
            )
            logger.info("Banned %s for inappropriate content", update.effective_user.id)
        except Exception as e:
            logger.error("Ban failed: %s", e)

async def admin_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("🚫 You are not allowed to use this command.")
        return
    await update.message.reply_text("✅ Admin command executed!")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("rules", rules))
application.add_handler(CommandHandler("admin", admin_only))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ban_inappropriate))

# ---------- Run PTB in its own event loop thread ----------
loop = asyncio.new_event_loop()

def _run_loop_forever():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=_run_loop_forever, daemon=True).start()

def _run_coro_sync(coro):
    """Run a coroutine on the PTB loop and wait for the result/errors."""
    return asyncio.run_coroutine_threadsafe(coro, loop).result()

# Initialize + start PTB and optionally set webhook
def init_bot_once():
    try:
        _run_coro_sync(application.initialize())
        _run_coro_sync(application.start())
        logger.info("Telegram application started.")
        if APP_URL:
            webhook_url = f"{APP_URL.rstrip('/')}/webhook/{TOKEN}"
            _run_coro_sync(application.bot.set_webhook(webhook_url))
            logger.info("Webhook set to %s", webhook_url)
        else:
            logger.warning("APP_URL/RENDER_EXTERNAL_URL not set -> webhook not configured.")
    except Exception as e:
        logger.exception("Failed to initialize bot: %s", e)

init_bot_once()

# ---------- Flask routes ----------
@app.route("/", methods=["GET"])
def index():
    return "🤖 Telegram bot is running.", 200

@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True, silent=False)
        update = Update.de_json(data, application.bot)
        # Process update inside PTB loop
        asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
        return "ok", 200
    except Exception as e:
        logger.exception("Error processing update: %s", e)
        return "error", 500

@app.route("/init-webhook", methods=["GET"])
def init_webhook():
    """Manually (re)sets the webhook to APP_URL/webhook/TOKEN."""
    if not APP_URL:
        return ("APP_URL/RENDER_EXTERNAL_URL not set on the service.", 400)
    try:
        webhook_url = f"{APP_URL.rstrip('/')}/webhook/{TOKEN}"
        _run_coro_sync(application.bot.set_webhook(webhook_url))
        return jsonify({"status": "ok", "webhook": webhook_url})
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)
        return (f"Failed to set webhook: {e}", 500)

# Gunicorn loads "app"
# No __main__ block required for Render, but keep for local runs.
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
