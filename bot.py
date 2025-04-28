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
    DEFAULT_RULES = "Welcome! Group Rules:\n1. No spamming\n2. No NSFW content\n3. Be respectful"
    DEFAULT_BAN_WORDS = ["porn", "sex", "nude", "spam", "scam"]
    WARNING_LIMIT = 3  # Number of warnings before ban

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
    application.bot_data.setdefault("user_warnings", {})

async def is_admin(update: Update) -> bool:
    """Check if user is admin"""
    return update.effective_user and update.effective_user.id in Config.ADMIN_IDS

async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check admin status and notify if not admin"""
    if not await is_admin(update):
        await update.message.reply_text(
            "❌ This command requires admin privileges",
            reply_to_message_id=update.message.message_id
        )
        return False
    return True

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
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

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /warn command"""
    if not await require_admin(update, context):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Please reply to a message to warn the user")
        return

    warned_user = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    
    # Initialize warnings tracking
    if "user_warnings" not in context.bot_data:
        context.bot_data["user_warnings"] = {}
    if chat_id not in context.bot_data["user_warnings"]:
        context.bot_data["user_warnings"][chat_id] = {}
    if warned_user.id not in context.bot_data["user_warnings"][chat_id]:
        context.bot_data["user_warnings"][chat_id][warned_user.id] = 0

    # Increment warning count
    context.bot_data["user_warnings"][chat_id][warned_user.id] += 1
    warnings = context.bot_data["user_warnings"][chat_id][warned_user.id]
    
    warning_msg = (
        f"⚠️ Warning {warnings}/{Config.WARNING_LIMIT}\n"
        f"User: {warned_user.full_name}\n"
        f"Reason: {context.args[0] if context.args else 'Violation of group rules'}"
    )
    
    await update.message.reply_text(warning_msg)
    
    # Check if user should be banned
    if warnings >= Config.WARNING_LIMIT:
        try:
            await context.bot.ban_chat_member(chat_id, warned_user.id)
            await update.message.reply_text(
                f"🚨 User {warned_user.full_name} has been banned "
                f"after {warnings} warnings"
            )
        except Exception as e:
            logger.error(f"Failed to ban user: {e}")
            await update.message.reply_text("⚠️ Failed to ban user - check bot permissions")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    commands = [
        ("/start", "Start the bot"),
        ("/setrules <text>", "Set group rules (admin only)"),
        ("/addbanword <word>", "Add banned word (admin only)"),
        ("/listbanwords", "Show banned words"),
        ("/warn <reason>", "Warn a user (admin only, reply to message)"),
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

    # Initialize message tracking
    if 'user_messages' not in context.chat_data:
        context.chat_data['user_messages'] = {}
    if user.id not in context.chat_data['user_messages']:
        context.chat_data['user_messages'][user.id] = []

    # Store message ID
    context.chat_data['user_messages'][user.id].append(update.message.message_id)
    if len(context.chat_data['user_messages'][user.id]) > Config.MAX_STORED_MESSAGES:
        context.chat_data['user_messages'][user.id].pop(0)

    # Check for banned words
    for word in context.bot_data.get('ban_words', []):
        if word in text:
            try:
                # Verify bot has admin privileges
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != "administrator":
                    await update.message.reply_text("⚠ I need admin rights to moderate!")
                    return

                # Delete offending message
                await update.message.delete()

                # Ban user
                await context.bot.ban_chat_member(chat.id, user.id)

                # Clean up user's previous messages
                for msg_id in context.chat_data['user_messages'][user.id]:
                    try:
                        await context.bot.delete_message(chat.id, msg_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete message {msg_id}: {e}")

                # Notify group
                await context.bot.send_message(
                    chat.id,
                    f"🚨 User {user.full_name} was banned for using banned word: '{word}'"
                )
                
                logger.info(f"Banned user {user.id} in chat {chat.id} for word: {word}")
                break

            except Exception as e:
                logger.error(f"Ban failed for user {user.id}: {e}")
                await update.message.reply_text("⚠ Failed to ban user - check bot permissions!")
                break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members with rules"""
    if update.message and update.message.new_chat_members:
        welcome_text = (
            f"👋 Welcome to the group!\n\n"
            f"{context.bot_data['rules_text']}\n\n"
            f"Please read and follow these rules."
        )
        await update.message.reply_text(welcome_text)

# ===== FLASK ROUTES =====
@flask_app.route(f"/webhook/{Config.BOT_TOKEN}", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates"""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.create_task(application.process_update(update))
        return jsonify({"status": "ok", "code": 200})

@flask_app.route("/")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "service": "telegram-bot",
        "version": "1.0"
    })

# ===== MAIN SETUP =====
async def setup_bot():
    """Configure and start the bot"""
    await init_bot_data(application)

    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("setrules", "Set group rules (admin)"),
        BotCommand("addbanword", "Add banned word (admin)"),
        BotCommand("listbanwords", "Show banned words"),
        BotCommand("warn", "Warn a user (admin)"),
        BotCommand("help", "Show help")
    ]
    await application.bot.set_my_commands(commands)

    # Add handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("setrules", set_rules),
        CommandHandler("addbanword", add_ban_word),
        CommandHandler("listbanwords", list_ban_words),
        CommandHandler("warn", warn_user),
        CommandHandler("help", help_command),
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    # Set webhook
    webhook_url = f"{Config.APP_URL}/webhook/{Config.BOT_TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    logger.info(f"Webhook set to: {webhook_url}")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    # Validate environment variables
    required_vars = ["BOT_TOKEN", "APP_URL", "ADMIN_IDS"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Create event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run bot setup
        loop.run_until_complete(setup_bot())
        
        # Start Flask server
        flask_app.run(
            host="0.0.0.0",
            port=Config.PORT,
            use_reloader=False
        )
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        loop.close()
