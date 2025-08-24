import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Load environment variables from .env file
load_dotenv()

# Get environment variables (you can set this in Render environment)
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Use your bot token here
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

# NSFW keywords (simple example; improve as needed)
NSFW_KEYWORDS = ["porn", "sex", "nude", "adult"]

# Auto Welcome Message and Rules
WELCOME_MESSAGE = "Welcome to the group! Please read the rules below:\n\n1. No spamming\n2. Be respectful\n3. No NSFW content"

def start(update: Update, context: CallbackContext) -> None:
    """Handles /start command."""
    update.message.reply_text("Hello! I'm your friendly bot. Type /help to see available commands.")

def help(update: Update, context: CallbackContext) -> None:
    """Handles /help command."""
    update.message.reply_text("Available commands:\n/start - Start the bot\n/help - Get help\n/ban - Ban a user (admin only)\n/kick - Kick a user (admin only)")

def auto_welcome(update: Update, context: CallbackContext) -> None:
    """Handles new member joining."""
    if update.message.new_chat_members:
        for new_member in update.message.new_chat_members:
            if not new_member.is_bot:
                update.message.reply_text(f"Welcome {new_member.first_name}!\n\n{WELCOME_MESSAGE}")

def check_nsfw(update: Update, context: CallbackContext) -> None:
    """Checks and bans NSFW messages."""
    text = update.message.text.lower()
    if any(keyword in text for keyword in NSFW_KEYWORDS):
        update.message.reply_text("NSFW content detected. Banning you.")
        context.bot.ban_chat_member(update.message.chat_id, update.message.from_user.id)

def admin_only(update: Update, context: CallbackContext) -> None:
    """Checks if the user is an admin before allowing access to commands."""
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return True
    return False

def ban_user(update: Update, context: CallbackContext) -> None:
    """Handles banning users (admin only)."""
    if admin_only(update, context):
        return
    try:
        user_id = int(context.args[0])  # Get user_id from arguments
        context.bot.ban_chat_member(update.message.chat_id, user_id)
        update.message.reply_text(f"User {user_id} has been banned.")
    except (IndexError, ValueError):
        update.message.reply_text("Please provide a user ID to ban.")

def kick_user(update: Update, context: CallbackContext) -> None:
    """Handles kicking users (admin only)."""
    if admin_only(update, context):
        return
    try:
        user_id = int(context.args[0])  # Get user_id from arguments
        context.bot.kick_chat_member(update.message.chat_id, user_id)
        update.message.reply_text(f"User {user_id} has been kicked.")
    except (IndexError, ValueError):
        update.message.reply_text("Please provide a user ID to kick.")

def main() -> None:
    """Main bot function."""
    # Create the Application instance and pass the bot token
    application = Application.builder().token(TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, auto_welcome))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_nsfw))

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
