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
from telegram.error import TelegramError, BadRequest, Forbidden

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
    """Initialize default values for chat data"""
    if "rules_text" not in chat_data:
        chat_data["rules_text"] = Config.DEFAULT_RULES
    if "ban_words" not in chat_data:
        chat_data["ban_words"] = Config.DEFAULT_BAN_WORDS.copy()
    if "user_warnings" not in chat_data:
        chat_data["user_warnings"] = {}
    if "user_messages" not in chat_data:
        chat_data["user_messages"] = {}

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE = None) -> bool:
    """Check if user is bot admin or chat admin"""
    user = update.effective_user
    if not user:
        return False
    
    # Bot admin check
    if user.id in Config.ADMIN_IDS:
        return True
    
    # Chat admin check (if context provided)
    if context and update.effective_chat:
        try:
            chat_member = await context.bot.get_chat_member(
                update.effective_chat.id, 
                user.id
            )
            return chat_member.status in ['administrator', 'creator']
        except (TelegramError, BadRequest):
            logger.warning(f"Failed to check admin status for user {user.id}")
    
    return False

async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check admin privileges and send error if not admin"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Admin privileges required")
        return False
    return True

async def check_bot_permissions(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """Check if bot has necessary permissions"""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return (bot_member.status == "administrator" and 
                bot_member.can_delete_messages and 
                bot_member.can_restrict_members)
    except TelegramError:
        return False

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    ensure_chat_defaults(context.chat_data)
    if await is_admin(update, context):
        await update.message.reply_text(
            "🤖 Admin Bot Active\n\n"
            "Available commands:\n"
            "/setrules - Update group rules\n"
            "/addbanword - Add banned words\n"
            "/removebanword - Remove banned words\n"
            "/listbanwords - Show banned words\n"
            "/warn - Warn a user\n"
            "/clearwarnings - Clear user warnings\n"
            "/help - Show all commands"
        )
    else:
        await update.message.reply_text(context.chat_data["rules_text"])

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set or update group rules"""
    if not await require_admin(update, context):
        return
    ensure_chat_defaults(context.chat_data)

    new_rules = update.message.text.partition(" ")[2].strip()
    if not new_rules:
        current_rules = context.chat_data["rules_text"]
        await update.message.reply_text(
            f"📝 Current rules:\n{current_rules}\n\n"
            "Usage: /setrules <new rules text>"
        )
        return

    context.chat_data["rules_text"] = new_rules
    await update.message.reply_text("✅ Rules updated successfully!")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add words to ban list"""
    if not await require_admin(update, context):
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

async def remove_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove words from ban list"""
    if not await require_admin(update, context):
        return
    ensure_chat_defaults(context.chat_data)

    words = [w.lower().strip() for w in context.args if w.strip()]
    if not words:
        await update.message.reply_text("Usage: /removebanword <word1> <word2>...")
        return

    ban_words = context.chat_data["ban_words"]
    results = {"removed": [], "not_found": []}
    
    for word in words:
        if word in ban_words:
            ban_words.remove(word)
            results["removed"].append(word)
        else:
            results["not_found"].append(word)

    response = []
    if results["removed"]:
        response.append(f"✅ Removed: {', '.join(results['removed'])}")
    if results["not_found"]:
        response.append(f"⚠️ Not found: {', '.join(results['not_found'])}")
    
    await update.message.reply_text("\n".join(response) or "No words removed")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all banned words"""
    ensure_chat_defaults(context.chat_data)
    words = context.chat_data.get("ban_words", [])
    
    if not words:
        await update.message.reply_text("No banned words currently set")
        return

    # Split into chunks if too many words
    word_list = "\n".join(f"• {word}" for word in words)
    if len(word_list) > 4000:  # Telegram message limit consideration
        await update.message.reply_text(f"🚫 Banned Words ({len(words)} total):\n{word_list[:4000]}...")
    else:
        await update.message.reply_text(f"🚫 Banned Words:\n{word_list}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Warn a user (reply to their message)"""
    if not await require_admin(update, context):
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
        if not await check_bot_permissions(context, chat_id):
            await update.message.reply_text("⚠️ Bot needs admin permissions to ban users")
            return
        
        try:
            await context.bot.ban_chat_member(chat_id, warned_user.id)
            await update.message.reply_text(
                f"🚨 User {warned_user.full_name} has been banned after {warnings} warnings"
            )
        except Forbidden:
            await update.message.reply_text("⚠️ Cannot ban this user (admin or owner)")
        except TelegramError as e:
            logger.error(f"Failed to ban user {warned_user.id}: {e}")
            await update.message.reply_text("⚠️ Failed to ban user - check bot permissions")

async def clear_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear warnings for a user"""
    if not await require_admin(update, context):
        return
    ensure_chat_defaults(context.chat_data)

    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message to clear user warnings")
        return

    user = update.message.reply_to_message.from_user
    user_warnings = context.chat_data["user_warnings"]
    
    if user.id in user_warnings:
        del user_warnings[user.id]
        await update.message.reply_text(f"✅ Cleared warnings for {user.full_name}")
    else:
        await update.message.reply_text(f"ℹ️ {user.full_name} has no warnings to clear")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    is_admin_user = await is_admin(update, context)
    
    basic_commands = [
        ("/start", "Start the bot and show rules"),
        ("/listbanwords", "Show banned words"),
        ("/help", "Show this help")
    ]
    
    admin_commands = [
        ("/setrules <text>", "Set group rules"),
        ("/addbanword <words>", "Add banned words"),
        ("/removebanword <words>", "Remove banned words"),
        ("/warn <reason>", "Warn a user (reply to message)"),
        ("/clearwarnings", "Clear user warnings (reply to message)")
    ]
    
    response = "📝 Available Commands:\n\n"
    response += "\n".join(f"{cmd} - {desc}" for cmd, desc in basic_commands)
    
    if is_admin_user:
        response += "\n\n🔧 Admin Commands:\n"
        response += "\n".join(f"{cmd} - {desc}" for cmd, desc in admin_commands)
    
    await update.message.reply_text(response)

# ===== MESSAGE HANDLERS =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages for content filtering"""
    if not update.message or not update.message.text:
        return
    
    # Skip if user is admin
    if await is_admin(update, context):
        return
        
    ensure_chat_defaults(context.chat_data)

    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.lower()

    # Store message IDs for cleanup
    user_msgs = context.chat_data["user_messages"].setdefault(user.id, [])
    user_msgs.append(update.message.message_id)
    if len(user_msgs) > Config.MAX_STORED_MESSAGES:
        user_msgs.pop(0)

    # Check for banned words
    for word in context.chat_data["ban_words"]:
        if re.search(rf'\b{re.escape(word)}\b', text):
            if not await check_bot_permissions(context, chat.id):
                await update.message.reply_text("⚠️ Bot needs admin permissions to moderate!")
                return

            try:
                # Delete the offending message
                await update.message.delete()
                
                # Ban the user
                await context.bot.ban_chat_member(chat.id, user.id)

                # Clean up user's recent messages
                deleted_count = 0
                for msg_id in user_msgs:
                    try:
                        await context.bot.delete_message(chat.id, msg_id)
                        deleted_count += 1
                        await asyncio.sleep(0.1)  # Rate limiting
                    except TelegramError as e:
                        logger.warning(f"Failed to delete message {msg_id}: {e}")

                # Send ban notification
                await context.bot.send_message(
                    chat.id,
                    f"🚨 {user.full_name} was banned for using banned content\n"
                    f"🗑️ Cleaned up {deleted_count} recent messages"
                )
                break
                
            except Forbidden:
                await update.message.reply_text(f"⚠️ Cannot ban {user.full_name} (admin or owner)")
                break
            except TelegramError as e:
                logger.error(f"Moderation failed for user {user.id}: {e}")
                await update.message.reply_text("⚠️ Moderation failed - check bot permissions!")
                break

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members"""
    ensure_chat_defaults(context.chat_data)
    if update.message and update.message.new_chat_members:
        new_members = update.message.new_chat_members
        member_names = ", ".join(member.full_name for member in new_members)
        
        await update.message.reply_text(
            f"👋 Welcome {member_names}!\n\n"
            f"{context.chat_data['rules_text']}\n\n"
            f"Please read and follow these rules to enjoy our community!"
        )

async def left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle member leaving (cleanup)"""
    if update.message and update.message.left_chat_member:
        user_id = update.message.left_chat_member.id
        # Clean up user data
        if user_id in context.chat_data.get("user_warnings", {}):
            del context.chat_data["user_warnings"][user_id]
        if user_id in context.chat_data.get("user_messages", {}):
            del context.chat_data["user_messages"][user_id]

# ===== FLASK ROUTES =====
@flask_app.route(f"/webhook/{Config.WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    """Handle webhook updates from Telegram"""
    # Verify secret token
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != Config.WEBHOOK_SECRET:
        logger.warning("Unauthorized webhook request")
        return jsonify({"status": "unauthorized"}), 401

    try:
        update = Update.de_json(request.get_json(), application.bot)
        if update:
            asyncio.run(application.process_update(update))
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@flask_app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "service": "telegram-moderation-bot",
        "version": "2.0",
        "admin_count": len(Config.ADMIN_IDS)
    })

@flask_app.route("/")
def index():
    """Basic info endpoint"""
    return jsonify({
        "service": "Telegram Moderation Bot",
        "status": "active",
        "endpoints": {
            "health": "/health",
            "webhook": f"/webhook/{Config.WEBHOOK_SECRET}"
        }
    })

# ===== BOT SETUP =====
async def setup_bot():
    """Initialize bot with commands and webhook"""
    await asyncio.sleep(5)  # Wait for service to be fully ready

    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot and show rules"),
        BotCommand("setrules", "Set group rules (admin)"),
        BotCommand("addbanword", "Add banned words (admin)"),
        BotCommand("removebanword", "Remove banned words (admin)"),
        BotCommand("listbanwords", "Show banned words"),
        BotCommand("warn", "Warn a user (admin)"),
        BotCommand("clearwarnings", "Clear user warnings (admin)"),
        BotCommand("help", "Show help")
    ]
    await application.bot.set_my_commands(commands)

    # Add handlers
    handlers = [
        CommandHandler("start", start),
        CommandHandler("setrules", set_rules),
        CommandHandler("addbanword", add_ban_word),
        CommandHandler("removebanword", remove_ban_word),
        CommandHandler("listbanwords", list_ban_words),
        CommandHandler("warn", warn_user),
        CommandHandler("clearwarnings", clear_warnings),
        CommandHandler("help", help_command),
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_message),
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member),
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_member)
    ]
    
    for handler in handlers:
        application.add_handler(handler)

    # Configure webhook
    webhook_url = f"{Config.APP_URL}/webhook/{Config.WEBHOOK_SECRET}"
    await application.bot.set_webhook(
        url=webhook_url,
        secret_token=Config.WEBHOOK_SECRET,
        drop_pending_updates=True
    )
    logger.info(f"✅ Bot configured successfully")
    logger.info(f"✅ Webhook URL: {webhook_url}")
    logger.info(f"✅ Admin IDs: {Config.ADMIN_IDS}")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info("🚀 Starting Telegram Moderation Bot...")
        loop.run_until_complete(setup_bot())
        logger.info(f"🌐 Flask server starting on port {Config.PORT}")
        flask_app.run(host="0.0.0.0", port=Config.PORT, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("👋 Shutdown by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        loop.close()



