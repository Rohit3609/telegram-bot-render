import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Configuration - loaded from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
MAX_STORED_MESSAGES = 10

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize bot_data (persists during runtime)
async def init_bot_data(context: ContextTypes.DEFAULT_TYPE):
    context.bot_data.setdefault('rules_text', "Welcome! Group Rules: No spamming. No NSFW. Be respectful.")
    context.bot_data.setdefault('ban_words', ["porn", "sex", "nude"])

# Admin check
async def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your bot. Type /help to see available commands.")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins can set the rules.")
        return
    rules_text = ' '.join(context.args)
    if rules_text:
        context.bot_data['rules_text'] = rules_text
        await update.message.reply_text("✅ Rules updated successfully!")
    else:
        await update.message.reply_text("Usage: /setrules <your rules>")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("❌ Only admins can add banned words.")
        return
    word = ' '.join(context.args).lower()
    if word:
        if word not in context.bot_data['ban_words']:
            context.bot_data['ban_words'].append(word)
            await update.message.reply_text(f"✅ Word '{word}' added to banned list.")
        else:
            await update.message.reply_text(f"⚠️ Word '{word}' is already banned.")
    else:
        await update.message.reply_text("Usage: /addbanword <word>")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    banned_words = context.bot_data.get('ban_words', [])
    await update.message.reply_text("🚫 Banned Words:\n" + '\n'.join(banned_words) if banned_words else "No banned words set.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🤖 Available Commands:
/start - Start the bot
/help - Show this help message
/setrules <text> - Set group rules (admin only)
/addbanword <word> - Add a word to banned list (admin only)
/listbanwords - Show banned words
"""
    await update.message.reply_text(help_text)

# Message Handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    banned_words = context.bot_data.get('ban_words', [])
    
    if any(bad_word in text for bad_word in banned_words):
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"⚠️ Message from {update.effective_user.full_name} contained banned content and was removed."
            )
        except Exception as e:
            logging.error(f"Failed to handle message: {e}")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = context.bot_data.get('rules_text', "Welcome to the group! Please read the rules.")
    await update.message.reply_text(welcome_message)

def main():
    # Validate configuration
    if not BOT_TOKEN:
        logging.error("❌ Missing BOT_TOKEN! Please set it in environment variables")
        exit(1)
    if not ADMIN_IDS:
        logging.error("❌ Missing ADMIN_IDS! Please set it in environment variables")
        exit(1)

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Initialize bot_data
        app.add_handler(MessageHandler(filters.ALL, init_bot_data), group=-1)

        # Command handlers
        commands = [
            ("start", start),
            ("setrules", set_rules),
            ("addbanword", add_ban_word),
            ("listbanwords", list_ban_words),
            ("help", help_command)
        ]
        
        for cmd, handler in commands:
            app.add_handler(CommandHandler(cmd, handler))

        # Message handlers
        app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
        app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

        logging.info("🤖 Bot is starting...")
        app.run_polling()

    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}")
        exit(1)

if __name__ == '__main__':
    main()

