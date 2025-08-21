import os
import re
import logging
import asyncio
import sqlite3
import json
from threading import Lock
from urllib.parse import urlparse
from datetime import datetime, timedelta
from collections import defaultdict

from flask import Flask, request, jsonify
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError, BadRequest, Forbidden

# ===== CONFIGURATION =====
class Config:
    # Bot token with validation but not immediate exit
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # App URL with validation
    APP_URL = os.getenv("APP_URL", "").rstrip("/")
    
    # Admin IDs with safe parsing
    ADMIN_IDS = []
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if admin_ids_str:
        try:
            ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        except ValueError:
            pass  # Handled in validation
    
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
    
    # Database path
    DB_PATH = os.getenv("DB_PATH", "chat_data.db")
    
    # Rate limiting settings
    RATE_LIMITS = {
        "warn": (5, 60),  # 5 warns per 60 seconds
        "ban": (3, 300),  # 3 bans per 5 minutes
        "message": (20, 10)  # 20 messages per 10 seconds
    }

# ===== VALIDATION =====
def validate_config():
    """Validate configuration and return errors"""
    errors = []
    
    if not Config.BOT_TOKEN:
        errors.append("BOT_TOKEN environment variable is required")
    
    if not Config.APP_URL:
        errors.append("APP_URL environment variable is required")
    elif not validate_app_url(Config.APP_URL):
        errors.append("APP_URL must be a valid HTTP/HTTPS URL")
    
    if not Config.ADMIN_IDS:
        errors.append("ADMIN_IDS environment variable is required with at least one valid ID")
    
    return errors

def validate_app_url(url):
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== DATABASE SETUP =====
class ChatDataDB:
    def __init__(self, db_path="chat_data.db"):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()
    
    def _init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_data (
                    chat_id INTEGER PRIMARY KEY,
                    rules_text TEXT,
                    ban_words TEXT,
                    user_warnings TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
    
    def get_chat_data(self, chat_id):
        """Retrieve chat data from database"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rules_text, ban_words, user_warnings FROM chat_data WHERE chat_id = ?",
                (chat_id,)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row:
                rules_text, ban_words_json, user_warnings_json = row
                return {
                    "rules_text": rules_text,
                    "ban_words": json.loads(ban_words_json) if ban_words_json else [],
                    "user_warnings": json.loads(user_warnings_json) if user_warnings_json else {}
                }
            return None
    
    def update_chat_data(self, chat_id, data):
        """Update chat data in database"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            # Convert data to JSON strings
            ban_words_json = json.dumps(data.get("ban_words", []))
            user_warnings_json = json.dumps(data.get("user_warnings", {}))
            
            # Check if record exists
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM chat_data WHERE chat_id = ?", (chat_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing record
                conn.execute(
                    "UPDATE chat_data SET rules_text = ?, ban_words = ?, user_warnings = ?, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                    (data.get("rules_text", ""), ban_words_json, user_warnings_json, chat_id)
                )
            else:
                # Insert new record
                conn.execute(
                    "INSERT INTO chat_data (chat_id, rules_text, ban_words, user_warnings) VALUES (?, ?, ?, ?)",
                    (chat_id, data.get("rules_text", ""), ban_words_json, user_warnings_json)
                )
            
            conn.commit()
            conn.close()

# Initialize database
db = ChatDataDB(Config.DB_PATH)

# ===== RATE LIMITING =====
class RateLimiter:
    def __init__(self):
        self.user_actions = defaultdict(list)
    
    def check_rate_limit(self, user_id, action_type, limit, time_window):
        now = datetime.now()
        # Remove old actions
        self.user_actions[user_id] = [
            time for time in self.user_actions[user_id] 
            if now - time < timedelta(seconds=time_window)
        ]
        
        if len(self.user_actions[user_id]) >= limit:
            return False
        
        self.user_actions[user_id].append(now)
        return True

# Initialize rate limiter
rate_limiter = RateLimiter()

# ===== LOCALIZATION =====
class Localization:
    def __init__(self):
        self.strings = {
            'en': {
                'welcome': 'Welcome to our community!',
                'rules_updated': 'Rules updated successfully!',
                'ban_word_added': 'Added: {words}',
                'ban_word_exists': 'Already banned: {words}',
                'ban_word_removed': 'Removed: {words}',
                'ban_word_not_found': 'Not found: {words}',
                'warn_user': 'Warning {current}/{limit}\nUser: {user}\nReason: {reason}',
                'user_banned': 'User {user} has been banned after {warnings} warnings',
                'no_bot_permissions': 'Bot needs admin permissions to {action}',
                'admin_required': 'Admin privileges required',
                'reply_to_warn': 'Reply to a message to warn the user',
                'reply_to_clear': 'Reply to a message to clear user warnings',
                'no_warnings': 'User has no warnings to clear',
                'warnings_cleared': 'Cleared warnings for {user}',
                'user_joined': 'Welcome {users}!\n\n{rules}\n\nPlease read and follow these rules!',
                'banned_content': 'User was banned for using banned content\nCleaned up {count} recent messages',
                'rate_limited': 'Too many requests, please wait',
            }
        }
    
    def get_string(self, key, lang='en', **kwargs):
        text = self.strings.get(lang, {}).get(key, self.strings['en'].get(key, key))
        return text.format(**kwargs) if kwargs else text

# Initialize localization
i18n = Localization()

# ===== APPLICATION SETUP =====
flask_app = Flask(__name__)

# Validate configuration
config_errors = validate_config()
if config_errors:
    for error in config_errors:
        logger.error(error)
    # Don't exit immediately for better container management
    # You might want to handle this differently in production

application = ApplicationBuilder().token(Config.BOT_TOKEN).build()

# ===== HELPER FUNCTIONS =====
def ensure_chat_defaults(chat_data, chat_id):
    """Initialize default values for chat data with database fallback"""
    if not chat_data.get("initialized", False):
        # Try to load from database first
        db_data = db.get_chat_data(chat_id)
        if db_data:
            chat_data.update(db_data)
        else:
            # Set defaults
            chat_data["rules_text"] = Config.DEFAULT_RULES
            chat_data["ban_words"] = Config.DEFAULT_BAN_WORDS.copy()
            chat_data["user_warnings"] = {}
            # Save to database
            db.update_chat_data(chat_id, chat_data)
        
        chat_data["user_messages"] = {}
        chat_data["initialized"] = True

def log_moderation_action(action, user_id, chat_id, details=None):
    """Log moderation actions for auditing"""
    logger.info(
        f"Moderation Action: {action} | "
        f"User: {user_id} | "
        f"Chat: {chat_id} | "
        f"Details: {details or 'None'}"
    )

def contains_banned_word(text, banned_words):
    """Check if text contains any banned words with word boundary matching"""
    text = text.lower()
    for word in banned_words:
        if re.search(rf'\b{re.escape(word)}\b', text):
            return True
    return False

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
        await update.message.reply_text(i18n.get_string('admin_required'))
        return False
    return True

async def check_bot_permissions(context: ContextTypes.DEFAULT_TYPE, chat_id: int, action: str = "moderate") -> bool:
    """Check if bot has necessary permissions"""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if action == "moderate":
            return (bot_member.status == "administrator" and 
                    bot_member.can_delete_messages and 
                    bot_member.can_restrict_members)
        elif action == "delete":
            return bot_member.status == "administrator" and bot_member.can_delete_messages
        else:
            return bot_member.status == "administrator"
    except TelegramError:
        return False

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)
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
    
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

    new_rules = update.message.text.partition(" ")[2].strip()
    if not new_rules:
        current_rules = context.chat_data["rules_text"]
        await update.message.reply_text(
            f"📝 Current rules:\n{current_rules}\n\n"
            "Usage: /setrules <new rules text>"
        )
        return

    context.chat_data["rules_text"] = new_rules
    # Update database
    db.update_chat_data(update.effective_chat.id, context.chat_data)
    
    await update.message.reply_text(i18n.get_string('rules_updated'))
    log_moderation_action("rules_updated", update.effective_user.id, 
                         update.effective_chat.id, f"New rules: {new_rules[:50]}...")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add words to ban list"""
    if not await require_admin(update, context):
        return
    
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

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
        response.append(i18n.get_string('ban_word_added', words=', '.join(results['added'])))
    if results["existing"]:
        response.append(i18n.get_string('ban_word_exists', words=', '.join(results['existing'])))
    
    # Update database
    db.update_chat_data(update.effective_chat.id, context.chat_data)
    
    await update.message.reply_text("\n".join(response) or "No words added")
    log_moderation_action("ban_words_added", update.effective_user.id, 
                         update.effective_chat.id, f"Words: {', '.join(words)}")

async def remove_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove words from ban list"""
    if not await require_admin(update, context):
        return
    
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

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
        response.append(i18n.get_string('ban_word_removed', words=', '.join(results['removed'])))
    if results["not_found"]:
        response.append(i18n.get_string('ban_word_not_found', words=', '.join(results['not_found'])))
    
    # Update database
    db.update_chat_data(update.effective_chat.id, context.chat_data)
    
    await update.message.reply_text("\n".join(response) or "No words removed")
    log_moderation_action("ban_words_removed", update.effective_user.id, 
                         update.effective_chat.id, f"Words: {', '.join(words)}")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all banned words"""
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)
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
    
    # Rate limiting
    if not rate_limiter.check_rate_limit(update.effective_user.id, "warn", *Config.RATE_LIMITS["warn"]):
        await update.message.reply_text(i18n.get_string('rate_limited'))
        return
    
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

    if not update.message.reply_to_message:
        await update.message.reply_text(i18n.get_string('reply_to_warn'))
        return

    warned_user = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    user_warnings = context.chat_data["user_warnings"]

    user_warnings[warned_user.id] = user_warnings.get(warned_user.id, 0) + 1
    warnings = user_warnings[warned_user.id]

    reason = ' '.join(context.args) if context.args else 'Rule violation'

    await update.message.reply_text(
        i18n.get_string('warn_user', 
                       current=warnings, 
                       limit=Config.WARNING_LIMIT,
                       user=warned_user.full_name,
                       reason=reason)
    )
    
    # Update database
    db.update_chat_data(update.effective_chat.id, context.chat_data)
    
    log_moderation_action("user_warned", update.effective_user.id, 
                         update.effective_chat.id, 
                         f"Warned user: {warned_user.id}, Count: {warnings}, Reason: {reason}")

    if warnings >= Config.WARNING_LIMIT:
        if not await check_bot_permissions(context, chat_id, "moderate"):
            await update.message.reply_text(
                i18n.get_string('no_bot_permissions', action="ban users")
            )
            return
        
        try:
            await context.bot.ban_chat_member(chat_id, warned_user.id)
            await update.message.reply_text(
                i18n.get_string('user_banned', 
                               user=warned_user.full_name, 
                               warnings=warnings)
            )
            log_moderation_action("user_banned", update.effective_user.id, 
                                update.effective_chat.id, 
                                f"Banned user: {warned_user.id} after {warnings} warnings")
        except Forbidden:
            await update.message.reply_text("⚠️ Cannot ban this user (admin or owner)")
        except TelegramError as e:
            logger.error(f"Failed to ban user {warned_user.id}: {e}")
            await update.message.reply_text("⚠️ Failed to ban user - check bot permissions")

async def clear_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear warnings for a user"""
    if not await require_admin(update, context):
        return
    
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

    if not update.message.reply_to_message:
        await update.message.reply_text(i18n.get_string('reply_to_clear'))
        return

    user = update.message.reply_to_message.from_user
    user_warnings = context.chat_data["user_warnings"]
    
    if user.id in user_warnings:
        del user_warnings[user.id]
        # Update database
        db.update_chat_data(update.effective_chat.id, context.chat_data)
        
        await update.message.reply_text(
            i18n.get_string('warnings_cleared', user=user.full_name)
        )
        log_moderation_action("warnings_cleared", update.effective_user.id, 
                            update.effective_chat.id, f"User: {user.id}")
    else:
        await update.message.reply_text(
            i18n.get_string('no_warnings', user=user.full_name)
        )

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
        
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)

    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text

    # Rate limiting for messages
    if not rate_limiter.check_rate_limit(user.id, "message", *Config.RATE_LIMITS["message"]):
        try:
            await update.message.delete()
        except:
            pass  # Ignore errors when deleting rate-limited messages
        return

    # Store message IDs for cleanup
    user_msgs = context.chat_data["user_messages"].setdefault(user.id, [])
    user_msgs.append(update.message.message_id)
    if len(user_msgs) > Config.MAX_STORED_MESSAGES:
        user_msgs.pop(0)

    # Check for banned words
    if contains_banned_word(text, context.chat_data["ban_words"]):
        if not await check_bot_permissions(context, chat.id, "moderate"):
            await update.message.reply_text(
                i18n.get_string('no_bot_permissions', action="moderate")
            )
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
                i18n.get_string('banned_content', count=deleted_count)
            )
            
            log_moderation_action("user_banned_auto", context.bot.id, 
                                chat.id, f"User: {user.id}, Reason: banned word")
                
        except Forbidden:
            await update.message.reply_text(f"⚠️ Cannot ban {user.full_name} (admin or owner)")
        except TelegramError as e:
            logger.error(f"Moderation failed for user {user.id}: {e}")
            await update.message.reply_text("⚠️ Moderation failed - check bot permissions!")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members"""
    ensure_chat_defaults(context.chat_data, update.effective_chat.id)
    if update.message and update.message.new_chat_members:
        new_members = update.message.new_chat_members
        member_names = ", ".join(member.full_name for member in new_members)
        
        await update.message.reply_text(
            i18n.get_string('user_joined', 
                           users=member_names, 
                           rules=context.chat_data["rules_text"])
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
        # Update database
        db.update_chat_data(update.effective_chat.id, context.chat_data)

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
        "admin_count": len(Config.ADMIN_IDS),
        "config_errors": config_errors
    })

@flask_app.route("/")
def index():
    """Basic info endpoint"""
    return jsonify({
        "service": "Telegram Moderation Bot",
        "status": "active" if not config_errors else "config_error",
        "endpoints": {
            "health": "/health",
            "webhook": f"/webhook/{Config.WEBHOOK_SECRET}"
        },
        "config_errors": config_errors
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

    # Configure webhook only if no config errors
    if not config_errors:
        webhook_url = f"{Config.APP_URL}/webhook/{Config.WEBHOOK_SECRET}"
        await application.bot.set_webhook(
            url=webhook_url,
            secret_token=Config.WEBHOOK_SECRET,
            drop_pending_updates=True
        )
        logger.info(f"✅ Bot configured successfully")
        logger.info(f"✅ Webhook URL: {webhook_url}")
        logger.info(f"✅ Admin IDs: {Config.ADMIN_IDS}")
    else:
        logger.error("❌ Bot not configured due to configuration errors")

# ===== ENTRY POINT =====
if __name__ == "__main__":
    # Log configuration errors
    if config_errors:
        logger.error("Configuration errors found:")
        for error in config_errors:
            logger.error(f"  - {error}")
        logger.error("Bot may not function properly until these issues are resolved")
    
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
