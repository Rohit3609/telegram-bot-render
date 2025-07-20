import os
import re
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ===== CONFIGURATION =====
class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("❌ BOT_TOKEN environment variable is required")

    APP_URL = os.getenv("APP_URL", "").rstrip("/")
    if not APP_URL:
        raise ValueError("❌ APP_URL environment variable is required")

    ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]
    if not ADMIN_IDS:
        raise ValueError("❌ ADMIN_IDS environment variable is required")

    PORT = int(os.getenv("PORT", 10000))
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "your-secret-token")
    MAX_STORED_MESSAGES = 10
    WARNING_LIMIT = 3

    DEFAULT_RULES = (
        "Welcome to our community! Please follow these rules:\n"
        "1. No spamming\n"
        "2. No NSFW content\n"
        "3. Be respectful to others\n"
        "4. No advertising without permission"
    )
    DEFAULT_BAN_WORDS = ["porn", "sex", "nude", "spam", "scam", "http://", "https://"]

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== APPLICATION SETUP =====
flask_app = Flask(__name__)
application = ApplicationBuilder().token(Config.BOT_TOKEN).build()

# ===== HELPER FUNCTIONS =====
def ensure_chat_defaults(chat_data):
    if "rules_text" not in chat_data:
        chat_data["rules_text"] = Config.DEFAULT_RULES
    if "ban_words" not in chat_data:
        chat_data["ban_words"] = Config.DEFAULT_BAN_WORDS.copy()
    if "user_warnings" not in chat_data:
        chat_data["user_warnings"] = {}

async def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id in Config.ADMIN_IDS

async def require_admin(update: Update) -> bool:
    if not await is_admin(update):
        await update.message.reply_text("❌ Admin privileges required")
        return False
    return True

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_chat_defaults(context.chat_data)
    if await is_admin(update):
        await update.message.reply_text(
            "🤖 Admin Bot Active\n\n"
            "Available commands:\n"
            "/setrules - Update group rules\n"
            "/addbanword - Add banned words\n"
            "/listbanwords - Show banned words\n"
            "/warn - Warn a user\n"
            "/help - Show all commands"
        )
    else:
        await update.message.reply_text(context.chat_data["rules_text"])

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    ensure_chat_defaults(context.chat_data)

    new_rules = update.message.text.partition(" ")[2].strip()
    if not new_rules:
        await update.message.reply_text("Usage: /setrules <new rules text>")
        return

    context.chat_data["rules_text"] = new_rules
    await update.message.reply_text("✅ Rules updated successfully!")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    ensure_chat_defaults(context.chat_data)

    words = [w.lower().strip() for w in context.args if w.strip()]
    if not words:
        await update.message.reply_text("Usage: /addbanword <word1> <word2>...")
        return

    ban_words = context.chat_data["ban_words"]
    results = {"added": [], "existing": []}
    for word in words:
        if word not in ban_words:
            ban_words.append(word)
            results["added"].append(word)
        else:
            results["existing"].append(word)

    response = []
    if results["added"]:
        response.append(f"✅ Added: {', '.join(results['added'])}")
    if results["existing"]:
        response.append(f"⚠️ Already banned: {', '.join(results['existing'])}")
    await update.message.reply_text("\n".join(response) or "No words added")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_chat_defaults(context.chat_data)
    words = context.chat_data.get("ban_words", [])
    if not words:
        await update.message.reply_text("No banned words currently set")
        return

    await update.message.reply_text(
        "🚫 Banned Words:\n" + "\n".join(f"• {word}" for word in words)
    )

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    ensure_chat_defaults(context.chat_data)

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message to warn the user")
        return

    warned_user = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    user_warnings = context.chat_data["user_warnings"]

    user_warnings[warned_user.id] = user_warnings.get(warned_user.id, 0) + 1
    warnings = user_warnings[warned_user.id]

    reason = ' '.join(context.args) if context.args else 'Rule violation'

    await update.message.reply_text(
        f"⚠️ Warning {warnings}/{Config.WARNING_LIMIT}\n"
        f"User: {warned_user.full_name}\n"
        f"Reason: {reason}"
    )

    if warnings >= Config.WARNING_LIMIT:
        try:
            await context.bot.ban_chat_member(chat_id, warned_user.id)
            await update.message.reply_text(
                f"🚨 User {warned_user.full_name} has been banned after {warnings} warnings"
            )
        except Exception as e:
            logger.error(f"Failed to ban user: {e}")
            await update.message.reply_text("⚠️ Failed to ban user - check bot permissions")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        ("/start", "Start the bot"),
        ("/setrules <text>", "Set group rules (admin)"),
        ("/addbanword <words>", "Add banned words (admin)"),
        ("/listbanwords", "Show banned words"),
        ("/warn <reason>", "Warn a user (admin, reply to message)"),
        ("/help", "Show this help")
    ]
    await update.message.reply_text(
        "📝 Available Commands:\n\n" +
        "\n".join(f"{cmd} - {desc}" for cmd, desc in commands)
    )

# ===== MESSAGE HANDLERS =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    ensure_chat_defaults(context.chat_data)

    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.lower()

    user_msgs = context.chat_data.setdefault('user_messages', {}).setdefault(user.id, [])
    user_msgs.append(update.message.message_id)
    if len(user_msgs) > Config.MAX_STORED_MESSAGES:
        user_msgs.pop(0)

    for word in context.chat_data["ban_words"]:
        if re.search(rf'\b{re.escape(word)}\b', text):
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != "administrator":
                    await update.message.reply_text("⚠ Bot needs admin rights!")
                    return

                await update.message.delete()
                await context.bot.ban_chat_member(chat.id, user.id)

                for msg_id in user_msgs:
                    try:
                        await context.bot.delete_message(chat.id, msg_id)
                        await asyncio.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Failed to delete message {msg_id}: {e}")

                await context.bot.send_message(
                    chat.id,
                    f"🚨 {user.full_name} was banned for banned content"
                )
                break
            except Exception as e:
                logger.error(f"Ban failed: {e}")
                await update.message.reply_text("⚠ Ban failed - check bot permissions!")
                break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_chat_defaults(context.chat_data)
    if update.message and update.message.new_chat_members:
        await update.message.reply_text(
            f"👋 Welcome to the group!\n\n"
            f"{context.chat_data['rules_text']}\n\n"
            f"Please read and follow these rules."
        )

# ===== FLASK ROUTES =====
@flask_app.route(f"/webhook/{Config.WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != Config.WEBHOOK_SECRET:
        return jsonify({"status": "unauthorized"}), 401

    update = Update.de_json(request.get_json(), application.bot)
    asyncio.run(application.process_update(update))
    return jsonify({"status": "ok"})

@flask_app.route("/health")
def health_check():
    return jsonify({
        "status": "running",
        "service": "telegram-bot",
        "version": "1.0"
    })

# ===== BOT SETUP =====
async def setup_bot():
    await asyncio.sleep(5)  # ⏳ Delay to ensure Render public URL is live before webhook setup

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("setrules", "Set group rules"),
        BotCommand("addbanword", "Add banned word"),
        BotCommand("listbanwords", "Show banned words"),
        BotCommand("warn", "Warn a user"),
        BotCommand("help", "Show help")
    ]
    await application.bot.set_my_commands(commands)

    handlers = [
        CommandHandler("start", start),
        CommandHandler("setrules", set_rules),
        CommandHandler("addbanword", add_ban_word),
        CommandHandler("listbanwords", list_ban_words),
        CommandHandler("warn", warn_user),
        CommandHandler("help", help_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_message),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member)
    ]
    for handler in handlers:
        application.add_handler(handler)

    webhook_url = f"{Config.APP_URL}/webhook/{Config.WEBHOOK_SECRET}"
    await application.bot.set_webhook(
        url=webhook_url,
        secret_token=Config.WEBHOOK_SECRET,
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook configured: {webhook_url}")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(setup_bot())
        flask_app.run(host="0.0.0.0", port=Config.PORT, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("👋 Shutdown by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        loop.close()
