import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ===== CONFIGURATION =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# ===== SETUP =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===== WEB SERVER (FOR HEALTH CHECKS) =====
async def healthcheck(request):
    return web.Response(text="✅ Bot is running!")

async def start_web_server():
    web_app = web.Application()
    web_app.router.add_get("/", healthcheck)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()
    logger.info("🌐 Web server started for health checks")

# ===== BOT HANDLERS =====
async def init_bot_data(context: ContextTypes.DEFAULT_TYPE):
    context.bot_data.setdefault("rules", "Welcome! Be respectful.")
    context.bot_data.setdefault("ban_words", ["spam", "scam"])

async def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Admin Bot Ready!\n"
        "/setrules - Update group rules\n"
        "/addbanword - Add banned words\n"
        "/listbanwords - Show banned words"
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
        
    words = [w.lower() for w in context.args]
    if words:
        added = []
        for word in words:
            if word not in context.bot_data["ban_words"]:
                context.bot_data["ban_words"].append(word)
                added.append(word)
        if added:
            await update.message.reply_text(f"✅ Added: {', '.join(added)}")
        else:
            await update.message.reply_text("⚠️ All words already banned")
    else:
        await update.message.reply_text("Usage: /addbanword <word1> <word2>...")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = context.bot_data.get("ban_words", [])
    await update.message.reply_text(
        "🚫 Banned Words:\n" + "\n".join(words) if words else "No banned words set"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    for word in context.bot_data.get("ban_words", []):
        if word in text:
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⚠️ {update.effective_user.full_name}'s message contained a banned word."
                )
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
            break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(context.bot_data["rules"])

# ===== MAIN APPLICATION =====
async def main():
    if not BOT_TOKEN:
        logger.error("❌ Missing BOT_TOKEN in environment variables")
        return
    if not ADMIN_IDS:
        logger.error("❌ Missing ADMIN_IDS in environment variables")
        return

    try:
        await start_web_server()

        app = ApplicationBuilder().token(BOT_TOKEN).build()

        app.add_handler(MessageHandler(filters.ALL, init_bot_data), group=-1)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("setrules", set_rules))
        app.add_handler(CommandHandler("addbanword", add_ban_word))
        app.add_handler(CommandHandler("listbanwords", list_ban_words))
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

        logger.info("🤖 Starting bot polling...")
        await app.run_polling()

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
