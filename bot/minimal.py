#!/usr/bin/env python3
"""
Самый простой возможный бот для отладки.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Логирование в stderr
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("minimal_bot")

print("STARTING MINIMAL BOT", flush=True)
logger.info("Starting minimal bot...")

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        BOT_TOKEN = os.environ["BOT_TOKEN"]
    except:
        print("ERROR: No BOT_TOKEN", flush=True)
        sys.exit(1)

print(f"BOT_TOKEN: {BOT_TOKEN[:15]}...", flush=True)
logger.info(f"BOT_TOKEN loaded: {BOT_TOKEN[:15]}...")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"START COMMAND from {update.message.from_user.id}", flush=True)
    logger.info(f"START from {update.message.from_user.id}")
    await update.message.reply_text("Hello! This is a minimal bot.")
    print(f"REPLY SENT to {update.message.from_user.id}", flush=True)


async def main():
    print("Building app...", flush=True)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    print("Adding handler...", flush=True)
    app.add_handler(CommandHandler("start", handle_start))
    
    print("Starting polling...", flush=True)
    logger.info("Starting polling...")
    
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)
    except KeyboardInterrupt:
        print("INTERRUPTED", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        logger.exception("Error in polling:")
        sys.exit(1)


if __name__ == "__main__":
    main()
