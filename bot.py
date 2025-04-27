import asyncio
import os
import logging
from aiohttp import web
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Import your handlers
# Assuming you have these functions already defined elsewhere:
# start, set_rules, add_ban_word, list_ban_words, help_command, handle_message, new_member, init_bot_data

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")  # Make sure to set this in Render

# Healthcheck endpoint
async def healthcheck(request):
    return web.Response(text="✅ Bot is running fine!")

async def main():
    if not BOT_TOKEN:
        logging.error("❌ Missing BOT_TOKEN! Please set it in environment variables")
        exit(1)
    if not ADMIN_IDS:
        logging.error("❌ Missing ADMIN_IDS! Please set it in environment variables")
        exit(1)

    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()

        # Initialize bot data
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

        # Start polling
        asyncio.create_task(app.run_polling())

        # Web server for Render healthcheck
        web_app = web.Application()
        web_app.router.add_get('/', healthcheck)

        port = int(os.environ.get("PORT", 8080))  # Render sets the PORT
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        # Keep running
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}")
        exit(1)

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
