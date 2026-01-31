import os
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.getenv("PORT", 5000))

NSFW_KEYWORDS = ["porn", "sex", "nude", "adult"]
WARN_LIMIT = 3
user_warnings = {}

WELCOME_MESSAGE = (
    "👋 Welcome to the group!\n\n"
    "Rules:\n"
    "1. No spam\n"
    "2. Be respectful\n"
    "3. No NSFW content"
)

# ---------------- UTILS ----------------

async def is_admin(update: Update) -> bool:
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ("administrator", "creator")

def get_target_user(update: Update):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is alive.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/ban (reply)\n"
        "/kick (reply)\n"
        "/mute (reply)\n"
        "/unmute (reply)"
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.message.reply_text("Admins only.")

    user = get_target_user(update)
    if not user:
        return await update.message.reply_text("Reply to a user.")

    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await update.message.reply_text(f"{user.first_name} banned.")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.message.reply_text("Admins only.")

    user = get_target_user(update)
    if not user:
        return await update.message.reply_text("Reply to a user.")

    await context.bot.ban_chat_member(
        update.effective_chat.id, user.id, until_date=0
    )
    await update.message.reply_text(f"{user.first_name} kicked.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.message.reply_text("Admins only.")

    user = get_target_user(update)
    if not user:
        return await update.message.reply_text("Reply to a user.")

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        ChatPermissions(can_send_messages=False),
    )
    await update.message.reply_text(f"{user.first_name} muted.")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return await update.message.reply_text("Admins only.")

    user = get_target_user(update)
    if not user:
        return await update.message.reply_text("Reply to a user.")

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        user.id,
        ChatPermissions(can_send_messages=True),
    )
    await update.message.reply_text(f"{user.first_name} unmuted.")

# ---------------- AUTO MODERATION ----------------

async def auto_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(
                f"Welcome {member.first_name}!\n\n{WELCOME_MESSAGE}"
            )

async def nsfw_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    if any(word in text for word in NSFW_KEYWORDS):
        user_id = update.message.from_user.id
        await update.message.delete()

        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1

        if user_warnings[user_id] >= WARN_LIMIT:
            await context.bot.ban_chat_member(update.effective_chat.id, user_id)
            await context.bot.send_message(
                update.effective_chat.id, "User banned after warnings."
            )
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                f"Warning {user_warnings[user_id]}/{WARN_LIMIT}",
            )

# ---------------- MAIN ----------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("kick", kick_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, auto_welcome))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, nsfw_filter))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://telegram-bot-render-eu64.onrender.com/{7526325073:AAG2UjAwP-EyY4pyc2F8-s9QGeidJ1b8F3I}",
    )

if __name__ == "__main__":
    main()
