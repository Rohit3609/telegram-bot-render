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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize bot_data (persists during runtime)
async def init_bot_data(context: ContextTypes.DEFAULT_TYPE):
    if not hasattr(context.bot_data, 'rules_text'):
        context.bot_data.rules_text = "Welcome! Group Rules: No spamming. No NSFW. Be respectful."
    if not hasattr(context.bot_data, 'ban_words'):
        context.bot_data.ban_words = ["porn", "sex", "nude"]

# Admin check
async def is_admin(update: Update):
    return update.effective_user.id in ADMIN_IDS

# [All your existing command and message handler functions remain exactly the same]

if __name__ == '__main__':  # Fixed the underscore issue here
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
