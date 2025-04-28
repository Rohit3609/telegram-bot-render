import os
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
        raise ValueError("❌ BOT_TOKEN environment variable is missing!")

    APP_URL = os.getenv("APP_URL", "").rstrip("/")
    if not APP_URL:
        raise ValueError("❌ APP_URL environment variable is missing!")

    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split()))
    PORT = int(os.getenv("PORT", 10000))
    MAX_STORED_MESSAGES = 10
    DEFAULT_RULES = "Welcome! Group Rules: No spamming. No NSFW. Be respectful."
    DEFAULT_BAN_WORDS = ["porn", "sex", "nude", "spam"]

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== FLASK APP =====
flask_app = Flask(__name__)

# ===== BOT APPLICATION =====
application = ApplicationBuilder().token(Config.BOT_TOKEN).build()

# ===== HELPER FUNCTIONS =====
async def init_bot_data(application):
    """Initialize bot data with default values"""
    application.bot_data.setdefault("rules_text", Config.DEFAULT_RULES)
    application.bot_data.setdefault("ban_words", Config.DEFAULT_BAN_WORDS.copy())

async def is_admin(update: Update) -> bool:
    """Check if user is admin"""
    return update.effective_user and update.effective_user.id in Config.ADMIN_IDS

async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Decorator to check admin status"""
    if not await is_admin(update):
        await update.message.reply_text("❌ Admin privileges required")
        return False
    return True

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if await is_admin(update):
        await update.message.reply_text("🤖 Admin Bot Active\n\nUse /help for commands")
    else:
        await update.message.reply_text(context.bot_data["rules_text"])

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setrules command"""
    if not await require_admin(update, context):
        return
        
    new_rules = ' '.join(context.args)
    if not new_rules:
        await update.message.reply_text("Usage: /setrules <new rules text>")
        return

    context.bot_data["rules_text"] = new_rules
    await update.message.reply_text("✅ Rules updated successfully!")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addbanword command"""
    if not await require_admin(update, context):
        return
        
    words = [w.lower() for w in context.args if w.strip()]
    if not words:
        await update.message.reply_text("Usage: /addbanword <word1> <word2>...")
        return

    added = []
    existing = []
    for word in words:
        if word not in context.bot_data["ban_words"]:
            context.bot_data["ban_words"].append(word)
            added.append(word)
        else:
            existing.append(word)

    response = []
    if added:
        response.append(f"✅ Added: {', '.join(added)}")
    if existing:
        response.append(f"⚠️ Already banned: {', '.join(existing)}")

    await update.message.reply_text("\n".join(response) if response else "No words added")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listbanwords command"""
    words = context.bot_data.get("ban_words", [])
    if not words:
        await update.message.reply_text("No banned words currently set")
        return

    await update.message.reply_text(
        "🚫 Banned Words:\n" + "\n".join(f"• {word}" for word in words)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    commands = [
        ("/start", "Start the bot"),
        ("/setrules <text>", "Set group rules (admin only)"),
        ("/addbanword <word>", "Add banned word (admin only)"),
        ("/listbanwords", "Show banned words"),
        ("/help", "Show this help message")
    ]
    
    message = "📝 Available Commands:\n\n" + \
              "\n".join(f"{cmd} - {desc}" for cmd, desc in commands)
    
    await update.message.reply_text(message)

# ===== MESSAGE HANDLERS =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all group messages"""
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.lower()

    if 'user_messages' not in context.chat_data:
        context.chat_data['user_messages'] = {}
    if user.id not in context.chat_data['user_messages']:
        context.chat_data['user_messages'][user.id] = []

    context.chat_data['user_messages'][user.id].append(update.message.message_id)
    if len(context.chat_data['user_messages'][user.id]) > Config.MAX_STORED_MESSAGES:
        context.chat_data['user_messages'][user.id].pop(0)

    for word in context.bot_data.get('ban_words', []):
        if word in text:
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != "administrator":
                    await update.message.reply_text("⚠ I need admin rights to moderate!")
                    return

                await update.message.delete()

                await context.bot.ban_chat_member(
                    chat_id=chat.id,
                    user_id=user.id
                )

                for msg_id in context.chat_data['user_messages'][user.id]:
                    try:
                        await context.bot.delete_message(
                            chat_id=chat.id,
                            message_id=msg_id
                        )
                    except Exception as e:
                        logger.warning(f"Failed to delete message {msg_id}: {e}")

                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🚨 User {user.full_name} was banned for inappropriate content."
                )
                
                logger.info(f"Banned user {user.id} in chat {chat.id} for word: {word}")
                break

            except Exception as e:
                logger.error(f"Ban failed for user {user.id}: {e}")
                await update.message.reply_text("⚠ Failed to ban user - check bot permissions!")
                break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members"""
    if update.message and update.message.new_chat_members:
        await update.message.reply_text(context.bot_data["rules_text"])

# ===== FLASK ROUTES =====
@flask_app.route(f"/webhook/{os.getenv('BOT_TOKEN')}", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.create_task(application.process_update(update))
        return jsonify({"status": "ok"})

@flask_app.route("/")
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "running", "service": "telegram-bot"})

# ===== MAIN SETUP =====
async def setup_bot():
    """Configure and start the bot"""
    await init_bot_data(application)

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("setrules", "Set group rules (admin)"),
        BotCommand("addbanword", "Add banned word (admin)"),
        BotCommand("listbanwords", "Show banned words"),
        BotCommand("help", "Show help")
    ]
    await application.bot.set_my_commands(commands)

    handlers = [
        CommandHandler("start", start),
        CommandHandler("setrules", set_rules),
        CommandHandler("addbanword", add_ban_word),
        CommandHandler("listbanwords", list_ban_words),
        CommandHandler("help", help_command),
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    webhook_url = f"{Config.APP_URL}/webhook/{Config.BOT_TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_bot())

    flask_app.run(
        host="0.0.0.0",
        port=Config.PORT,
        use_reloader=False
    )
