"""Utilities for processing beta backlog reminders."""

from datetime import datetime
from typing import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, NoteService, UserService
from transkribator_modules.db.models import Reminder, NoteStatus

REMINDER_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Да", callback_data="beta:reminder:accept"),
            InlineKeyboardButton("Завтра", callback_data="beta:reminder:tomorrow"),
        ],
        [InlineKeyboardButton("Выключить на неделю", callback_data="beta:reminder:snooze_week")],
    ]
)


def fetch_due_reminders(session) -> Iterable[Reminder]:
    now = datetime.utcnow()
    return (
        session.query(Reminder)
        .filter(Reminder.fire_ts <= now, Reminder.sent_at.is_(None))
        .order_by(Reminder.fire_ts.asc())
        .all()
    )


async def process_reminders(app: Application) -> None:
    session = SessionLocal()
    try:
        reminders = fetch_due_reminders(session)
        note_service = NoteService(session)
        user_service = UserService(session)

        for reminder in reminders:
            user = user_service.get_or_create_user(reminder.user.telegram_id)
            backlog_notes = note_service.list_backlog(user, limit=5)

            if not backlog_notes:
                reminder.sent_at = datetime.utcnow()
                session.commit()
                continue

            note_lines = [f"• {note.text[:80]}" for note in backlog_notes]
            text = (
                "У тебя есть заметки в бэклоге. Разберём 5 сейчас?\n\n" + "\n".join(note_lines)
            )

            try:
                await app.bot.send_message(
                    chat_id=user.telegram_id,
                    text=text,
                    reply_markup=REMINDER_KEYBOARD,
                )
                reminder.sent_at = datetime.utcnow()
                session.commit()
            except Exception as exc:
                logger.error("Failed to send reminder", extra={"error": str(exc)})
    finally:
        session.close()


def schedule_jobs(application: Application) -> None:
    """Register reminder processor on the job queue."""

    async def _job_callback(context):
        await process_reminders(application)

    application.job_queue.run_repeating(
        _job_callback,
        interval=1800,
        first=30,
        name="beta_backlog_reminders",
    )
