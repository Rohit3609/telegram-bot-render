import os  # <--- ADD this
import asyncio
import logging  # <--- ADD this if missing
from aiohttp import web
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters  # ADD imports if not already
# Also your other necessary imports...

# Fetch the environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")

async def healthcheck(request):
    return web.Response(text="✅ Bot is running fine!")

async def main():
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

        # Start the polling in background
        asyncio.create_task(app.run_polling())

        # Start a tiny web server for Render
        web_app = web.Application()
        web_app.router.add_get('/', healthcheck)

        port = int(os.environ.get("PORT", 8080))  # Render sets the PORT
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        # Keep running forever
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
