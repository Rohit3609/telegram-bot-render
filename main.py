import os
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ⬇️ USE RENDER ENV DIRECTLY (NO dotenv)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

NSFW_KEYWORDS = ["porn", "sex", "nude", "adult"]
WARN_LIMIT = 3

# ---------------- UTILS ----------------

async def is_admin(update: Update) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ("administrator", "creator")

def get_target_user(update: Update):
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    return None

# ---------------- COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot is alive (webhook mode).")

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

    await context.bot.ban_chat_member(update.effective_chat.id, user.id)
    await context.bot.unban_chat_member(update.effective_chat.id, user.id)
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
        ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_send_polls=True,
            can_add_web_page_previews=True,
        ),
    )
    await update.message.reply_text(f"{user.first_name} unmuted.")

# ---------------- AUTO MODERATION ----------------

async def auto_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if not member.is_bot:
            await update.message.reply_text(
                f"Welcome {member.first_name}!\n\n"
                "Rules:\n1. No spam\n2. Be respectful\n3. No NSFW"
            )

async def nsfw_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if await is_admin(update):
        return

    text = update.message.text.lower()
    if any(word in text for word in NSFW_KEYWORDS):
        await update.message.delete()

        warnings = context.chat_data.setdefault("warnings", {})
        uid = update.message.from_user.id
        warnings[uid] = warnings.get(uid, 0) + 1

        if warnings[uid] >= WARN_LIMIT:
            await context.bot.ban_chat_member(update.effective_chat.id, uid)
            await context.bot.send_message(update.effective_chat.id, "User banned after warnings.")
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                f"Warning {warnings[uid]}/{WARN_LIMIT}",
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
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}",
    )

if __name__ == "__main__":
    main()
