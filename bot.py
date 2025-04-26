import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# Configuration - loaded from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN')  # Fallback for local testing
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '123456789').split(',') if id.strip()]
MAX_STORED_MESSAGES = 10

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize bot_data (persists during runtime)
async def init_bot_data(context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context.bot_data, 'rules_text'):
        context.bot_data['rules_text'] = "Welcome! Group Rules: No spamming. No NSFW. Be respectful."
    if not hasattr(context.bot_data, 'ban_words'):
        context.bot_data['ban_words'] = ["porn", "sex", "nude"]

# Admin check
async def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! I'm your bot. Type /help to see available commands.")

async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Only admins can set the rules.")
        return
    rules_text = ' '.join(context.args)
    if rules_text:
        context.bot_data['rules_text'] = rules_text
        await update.message.reply_text("Rules updated successfully!")
    else:
        await update.message.reply_text("Usage: /setrules <your rules>")

async def add_ban_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        await update.message.reply_text("Only admins can add banned words.")
        return
    word = ' '.join(context.args).lower()
    if word:
        context.bot_data['ban_words'].append(word)
        await update.message.reply_text(f"Word '{word}' added to banned list.")
    else:
        await update.message.reply_text("Usage: /addbanword <word>")

async def list_ban_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    banned_words = context.bot_data.get('ban_words', [])
    await update.message.reply_text("Banned Words:\n" + ', '.join(banned_words))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/setrules - Set group rules (admin only)\n"
        "/addbanword - Add a word to banned list (admin only)\n"
        "/listbanwords - Show banned words\n"
    )
    await update.message.reply_text(help_text)

# Message Handlers
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    banned_words = context.bot_data.get('ban_words', [])
    if any(word in text for word in banned_words):
        await update.message.delete()
        await update.message.reply_text("Your message contained a banned word and was removed.")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(context.bot_data.get('rules_text', "Welcome to the group!"))

# Main App
if __name__ == '__main__':
    # Validate configuration
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN':
        logging.error("Missing BOT_TOKEN! Please set it in environment variables")
        exit(1)
    if not ADMIN_IDS or ADMIN_IDS == [123456789]:
        logging.error("Missing ADMIN_IDS! Please set it in environment variables")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Initialize bot_data
    app.add_handler(MessageHandler(filters.ALL, init_bot_data), group=-1)

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setrules", set_rules))
    app.add_handler(CommandHandler("addbanword", add_ban_word))
    app.add_handler(CommandHandler("listbanwords", list_ban_words))
    app.add_handler(CommandHandler("help", help_command))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, handle_message))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))

    logging.info("Bot is starting...")
    app.run_polling()

