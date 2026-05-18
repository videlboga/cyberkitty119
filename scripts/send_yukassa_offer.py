"""
Send a YooKassa purchase button to a specific Telegram user.

Usage:
  python scripts/send_yukassa_offer.py --user 648981358 --plan unlimited_year --amount 1

Requires env:
  - BOT_TOKEN
  - YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY
Optional:
  - USE_LOCAL_BOT_API, LOCAL_BOT_API_URL
"""

from __future__ import annotations

import argparse
import asyncio
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram import Bot

from transkribator_modules.config import (
    BOT_TOKEN,
    USE_LOCAL_BOT_API,
    LOCAL_BOT_API_URL,
    logger,
)
from transkribator_modules.payments.yukassa import YukassaPaymentService


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send YooKassa offer button to a Telegram user")
    parser.add_argument("--user", type=int, required=True, help="Telegram user ID (chat id)")
    parser.add_argument("--plan", type=str, required=True, help="Plan identifier (e.g., unlimited_year)")
    parser.add_argument("--amount", type=float, required=True, help="Amount in RUB (e.g., 1.0)")
    parser.add_argument("--title", type=str, default="Годовой безлимит", help="Display title")
    args = parser.parse_args()

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    request = HTTPXRequest(connect_timeout=30, read_timeout=60)
    base_url = None
    if USE_LOCAL_BOT_API and LOCAL_BOT_API_URL:
        base_url = LOCAL_BOT_API_URL.rstrip("/") + "/bot"
    if base_url:
        bot = Bot(BOT_TOKEN, request=request, base_url=base_url)
    else:
        bot = Bot(BOT_TOKEN, request=request)

    # Create YooKassa payment
    yk = YukassaPaymentService()
    payment = yk.create_payment(
        user_id=args.user,
        plan_type=args.plan,
        amount=float(args.amount),
        description=f"Подписка {args.title} - CyberKitty Transkribator",
    )

    url = payment["confirmation_url"]
    text = (
        f"💳 <b>Оплата через ЮКассу</b>\n\n"
        f"📦 <b>План:</b> {args.title}\n"
        f"💰 <b>Сумма:</b> {int(args.amount)} ₽\n\n"
        f"🔗 <b>Ссылка для оплаты:</b>\n{url}\n\n"
        f"⚠️ После платежа подписка активируется автоматически."
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💳 Перейти к оплате", url=url)]]
    )

    await bot.send_message(chat_id=args.user, text=text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    logger.info("YooKassa offer sent", extra={"user": args.user, "plan": args.plan, "amount": args.amount})


if __name__ == "__main__":
    asyncio.run(main())
