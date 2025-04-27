import os
import asyncio
import logging
from aiohttp import web

# Attempt to import telegram libraries
try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler,
        ContextTypes, filters
    )
except ModuleNotFoundError as e:
    raise ImportError("Install required libraries: 'pip install python-telegram-bot aiohttp'") from e

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
PORT = int(os.getenv("PORT", 8080))
APP_URL = os.getenv("APP_URL")  # e.g., https://your-app-name.onrender.com

# ===== LOGGING =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===== WEB SERVER =====
async def healthcheck(request):
    return web.Response(text="✅ Bot is running!")

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", healthcheck)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Web server started on port {PORT}")
    return runner

# ===== BOT HANDLERS =====
async def init_bot_data(context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get("initialized"):
        context.bot_data["rules"] = "Welcome! Be respectful."
        context.bot_data["ban_words"] = ["spam", "scam", "porn"]
        context.bot_data["initialized"] = True

async def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Admin Bot Ready!\n\n"
        "Commands:\n"
        "/setrules - Update group rules\n"
        "/addbanword - Add banned words\n"
        "/listbanwords - Show banned words\n"
        "/rules - Show group rules\n"
        "/help - Show this message"
    )

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Admin only command!")
        return

    new_rules = " ".join(context.args)
    if new_rules:
        context.bot_data["rules"] = new_rules
        await update.message.reply_text("✅ Rules updated!")
    else:
        await update.message.reply_text("Usage: /setrules <new rules>")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Admin only command!")
        return

    words = [w.lower() for w in context.args if w.strip()]
    if words:
        added = []
        already_banned = []

        for word in words:
            if word not in context.bot_data["ban_words"]:
                context.bot_data["ban_words"].append(word)
                added.append(word)
            else:
                already_banned.append(word)

        response = []
        if added:
            response.append(f"✅ Added: {', '.join(added)}")
        if already_banned:
            response.append(f"⚠️ Already banned: {', '.join(already_banned)}")

        await update.message.reply_text("\n".join(response))
    else:
        await update.message.reply_text("Usage: /addbanword <word1> <word2>...")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = context.bot_data.get("ban_words", [])
    response = "🚫 Banned Words:\n" + "\n".join(f"- {word}" for word in words) if words else "No banned words set."
    await update.message.reply_text(response)

async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(context.bot_data.get("rules", "No rules set."))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    chat_id = update.effective_chat.id
    user = update.effective_user

    for word in context.bot_data.get("ban_words", []):
        if word in text:
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ {user.full_name}'s message contained a banned word."
                )
                logger.info(f"Deleted message from {user.id} in chat {chat_id}")
                break
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
                break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(context.bot_data.get("rules", "Welcome!"))

# ===== BOT MAIN =====
async def run_bot():
    if not BOT_TOKEN or not ADMIN_IDS or not APP_URL:
        raise ValueError("BOT_TOKEN, ADMIN_IDS, and APP_URL must be set in environment variables")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Shared data
    app.add_handler(MessageHandler(filters.ALL, init_bot_data), group=-1)

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("setrules", set_rules))
    app.add_handler(CommandHandler("addbanword", add_ban_word))
    app.add_handler(CommandHandler("listbanwords", list_ban_words))
    app.add_handler(CommandHandler("rules", show_rules))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    # Start
    logger.info("🤖 Bot starting...")
    await app.initialize()
    await app.start()

    # Bot commands
    await app.bot.set_my_commands([
        ("start", "Start the bot"),
        ("setrules", "Set group rules"),
        ("addbanword", "Add banned word"),
        ("listbanwords", "Show banned words"),
        ("rules", "Show group rules"),
        ("help", "Show help")
    ])

    # 🚀 Set webhook
    webhook_url = f"{APP_URL}/"  # Important: slash at end
    await app.bot.set_webhook(url=webhook_url)

    return app

async def main():
    web_runner = None
    bot_app = None

    try:
        web_runner = await start_web_server()
        bot_app = await run_bot()

        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        logger.info("👋 Shutting down...")
        if bot_app:
            await bot_app.stop()
            await bot_app.shutdown()
        if web_runner:
            await web_runner.cleanup()
        logger.info("✅ Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutdown by user")
