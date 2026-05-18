#!/usr/bin/env python3
"""
Абсолютно минимальный бот для проверки.
"""

import os
import sys

print("START", flush=True)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
print(f"BOT_TOKEN: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "NO BOT_TOKEN", flush=True)

if not BOT_TOKEN:
    try:
        with open(".env") as f:
            for line in f:
                if line.startswith("BOT_TOKEN="):
                    BOT_TOKEN = line.split("=", 1)[1].strip()
                    print(f"Loaded from .env: {BOT_TOKEN[:10]}...", flush=True)
                    break
    except:
        pass

if not BOT_TOKEN:
    print("FATAL: No BOT_TOKEN", flush=True)
    sys.exit(1)

print("Importing telegram...", flush=True)
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

print("Creating application...", flush=True)
app = ApplicationBuilder().token(BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"START COMMAND from {update.message.from_user.id}", flush=True)
    await update.message.reply_text("Hello!")

print("Adding handler...", flush=True)
app.add_handler(CommandHandler("start", start))

print("Starting polling...", flush=True)
try:
    app.run_polling(drop_pending_updates=False)
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)
