import os
import asyncio
import logging
from aiohttp import web
from typing import List, Optional

# Import Telegram libraries with enhanced error handling
try:
    from telegram import Update
    from telegram.constants import ParseMode
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, MessageHandler,
        ContextTypes, filters, Defaults
    )
except ImportError as e:
    raise ImportError(
        "Required packages not found. Install with:\n"
        "pip install python-telegram-bot[webhooks] aiohttp"
    ) from e

# ===== CONFIGURATION =====
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    PORT: int = int(os.getenv("PORT", 8080))
    APP_URL: str = os.getenv("APP_URL", "").rstrip("/")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    BAN_WORDS: List[str] = ["spam", "scam", "porn", "nude"]
    DEFAULT_RULES: str = "Welcome! Please be respectful."

    @classmethod
    def validate(cls):
        """Validate all required configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not cls.ADMIN_IDS:
            raise ValueError("ADMIN_IDS is required")
        if not cls.APP_URL:
            raise ValueError("APP_URL is required")

# ===== LOGGING CONFIG =====
def setup_logging():
    """Configure advanced logging with rotation"""
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("bot.log", encoding='utf-8')
        ]
    )
    # Suppress noisy logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger(__name__)

# ===== WEB SERVER =====
class WebServer:
    @staticmethod
    async def healthcheck(request):
        """Enhanced health check with status information"""
        return web.json_response({
            "status": "operational",
            "service": "telegram-bot",
            "version": "1.0.0"
        })

    @classmethod
    async def start(cls):
        """Start the web server with additional routes"""
        app = web.Application()
        app.router.add_get("/", cls.healthcheck)
        app.router.add_get("/status", cls.healthcheck)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
        await site.start()
        logger.info(f"Web server running on port {Config.PORT}")
        return runner

# ===== BOT HANDLERS =====
class BotHandlers:
    @staticmethod
    async def is_admin(update: Update) -> bool:
        """Check if user is an admin with additional validation"""
        if not update.effective_user:
            return False
        return update.effective_user.id in Config.ADMIN_IDS

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced /start command with markdown formatting"""
        commands = [
            ("/start", "Start the bot"),
            ("/rules", "Show group rules"),
            ("/setrules <text>", "Update rules (admin only)"),
            ("/addbanword <words>", "Add banned words (admin only)"),
            ("/listbanwords", "Show banned words"),
            ("/help", "Show this message")
        ]
        
        message = "🤖 *Admin Bot Commands*\n\n" + \
                  "\n".join(f"• `{cmd}` - {desc}" for cmd, desc in commands)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    @staticmethod
    async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Improved rules setting with input validation"""
        if not await BotHandlers.is_admin(update):
            await update.message.reply_text(
                "❌ *Access Denied*\nAdmin privileges required",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        new_rules = " ".join(context.args).strip()
        if not new_rules:
            await update.message.reply_text(
                "ℹ️ *Usage:* `/setrules <new rules>`\nExample: `/setrules No spam allowed`",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        context.bot_data["rules"] = new_rules
        await update.message.reply_text(
            "✅ *Rules updated successfully!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    @staticmethod
    async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced ban word addition with duplicate handling"""
        if not await BotHandlers.is_admin(update):
            await update.message.reply_text("❌ Admin privileges required")
            return

        words = [w.lower().strip() for w in context.args if w.strip()]
        if not words:
            await update.message.reply_text(
                "ℹ️ *Usage:* `/addbanword <word1> <word2>...`",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Initialize if not exists
        if "ban_words" not in context.bot_data:
            context.bot_data["ban_words"] = Config.BAN_WORDS.copy()

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

        await update.message.reply_text("\n".join(response))

    @staticmethod
    async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Formatted banned words list"""
        words = context.bot_data.get("ban_words", Config.BAN_WORDS)
        if not words:
            await update.message.reply_text("No banned words currently set")
            return

        message = "🚫 *Banned Words*\n\n" + \
                  "\n".join(f"• `{word}`" for word in words)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN_V2
        )

    @staticmethod
    async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display rules with nice formatting"""
        rules = context.bot_data.get("rules", Config.DEFAULT_RULES)
        await update.message.reply_text(
            f"📜 *Group Rules*\n\n{rules}",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    @staticmethod
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Advanced message monitoring with logging"""
        if not update.message or not update.message.text:
            return

        text = update.message.text.lower()
        user = update.effective_user
        chat = update.effective_chat

        # Get current banned words
        banned_words = context.bot_data.get("ban_words", Config.BAN_WORDS)
        
        for word in banned_words:
            if word in text:
                try:
                    # Delete the offending message
                    await update.message.delete()
                    
                    # Send warning to group
                    warning_msg = (
                        f"⚠️ *Message Removed*\n\n"
                        f"User: {user.mention_markdown_v2() if user else 'Unknown'}\n"
                        f"Reason: Contains banned word `{word}`"
                    )
                    
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=warning_msg,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    
                    # Log the action
                    logger.info(
                        f"Deleted message in chat {chat.id} from user {user.id if user else 'unknown'} "
                        f"for banned word: {word}"
                    )
                    break
                except Exception as e:
                    logger.error(f"Failed to delete message: {str(e)}")
                    break

    @staticmethod
    async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced welcome message for new members"""
        rules = context.bot_data.get("rules", Config.DEFAULT_RULES)
        welcome_msg = (
            f"👋 *Welcome to the group!*\n\n"
            f"Please read our rules:\n\n"
            f"{rules}"
        )
        
        await update.message.reply_text(
            welcome_msg,
            parse_mode=ParseMode.MARKDOWN_V2
        )

# ===== BOT SETUP =====
class BotSetup:
    @staticmethod
    async def create_application():
        """Configure and return the bot application"""
        defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
        return ApplicationBuilder() \
            .token(Config.BOT_TOKEN) \
            .defaults(defaults) \
            .post_init(BotSetup.on_bot_startup) \
            .post_stop(BotSetup.on_bot_shutdown) \
            .build()

    @staticmethod
    async def on_bot_startup(app):
        """Actions to perform when bot starts"""
        logger.info("Bot is starting up...")
        
        # Initialize bot data
        app.bot_data.update({
            "rules": Config.DEFAULT_RULES,
            "ban_words": Config.BAN_WORDS.copy(),
            "initialized": True
        })
        
        # Set bot commands for better UX
        commands = [
            ("start", "Start the bot"),
            ("rules", "Show group rules"),
            ("setrules", "Update rules (admin)"),
            ("addbanword", "Add banned word (admin)"),
            ("listbanwords", "Show banned words"),
            ("help", "Show help")
        ]
        await app.bot.set_my_commands(commands)
        
        # Configure webhook
        webhook_url = f"{Config.APP_URL}/{Config.BOT_TOKEN}"
        await app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook configured: {webhook_url}")

    @staticmethod
    async def on_bot_shutdown(app):
        """Cleanup actions when bot stops"""
        logger.info("Bot is shutting down...")
        await app.bot.delete_webhook()
        logger.info("Webhook removed")

    @staticmethod
    async def setup_handlers(app):
        """Register all bot handlers"""
        handlers = [
            CommandHandler("start", BotHandlers.start),
            CommandHandler("help", BotHandlers.start),
            CommandHandler("rules", BotHandlers.show_rules),
            CommandHandler("setrules", BotHandlers.set_rules),
            CommandHandler("addbanword", BotHandlers.add_ban_word),
            CommandHandler("listbanwords", BotHandlers.list_ban_words),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
                BotHandlers.handle_message
            ),
            MessageHandler(
                filters.StatusUpdate.NEW_CHAT_MEMBERS,
                BotHandlers.new_member
            )
        ]
        
        for handler in handlers:
            app.add_handler(handler)

# ===== MAIN APPLICATION =====
async def main():
    """Main application entry point with proper resource management"""
    Config.validate()
    
    web_runner = None
    bot_app = None

    try:
        logger.info("Starting services...")
        
        # Start web server
        web_runner = await WebServer.start()
        
        # Setup and start bot
        bot_app = await BotSetup.create_application()
        await BotSetup.setup_handlers(bot_app)
        
        logger.info("Initializing bot...")
        await bot_app.initialize()
        await bot_app.start()
        
        logger.info("✅ All services started successfully")
        
        # Keep the application running
        while True:
            await asyncio.sleep(3600)

    except asyncio.CancelledError:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
    finally:
        logger.info("Shutting down services...")
        
        # Cleanup bot
        if bot_app:
            await bot_app.stop()
            await bot_app.shutdown()
        
        # Cleanup web server
        if web_runner:
            await web_runner.cleanup()
        
        logger.info("✅ Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutdown by user")
