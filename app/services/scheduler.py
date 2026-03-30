"""
Reminder Scheduler — Celery tasks for sending reminders and weekly summaries.
Run with: celery -A app.services.scheduler worker --beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab
from datetime import datetime
import os

from app.utils.logger import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "memory_agent",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)

celery_app.conf.beat_schedule = {
    # Check and send pending reminders every minute
    "send-pending-reminders": {
        "task": "app.services.scheduler.send_pending_reminders",
        "schedule": 60.0,
    },
    # Weekly summary every Sunday at 8pm Peru time (UTC-5 = 01:00 UTC Monday)
    "weekly-summary": {
        "task": "app.services.scheduler.send_weekly_summaries",
        "schedule": crontab(hour=1, minute=0, day_of_week=1),
    },
    # Daily "what was important today?" message at 9pm Peru time
    "daily-checkin": {
        "task": "app.services.scheduler.send_daily_checkin",
        "schedule": crontab(hour=2, minute=0),  # 9pm Peru = 2am UTC
    },
}


@celery_app.task(name="app.services.scheduler.send_pending_reminders")
def send_pending_reminders():
    """Find all reminders due now and send them via WhatsApp."""
    import asyncio
    asyncio.run(_async_send_reminders())


async def _async_send_reminders():
    from app.db.session import get_async_session
    from app.db.models import Reminder
    from app.services.whatsapp_service import WhatsAppService
    from sqlalchemy import select, and_

    whatsapp = WhatsAppService()

    async with get_async_session() as session:
        now = datetime.now()
        stmt = select(Reminder).where(
            and_(
                Reminder.sent == False,
                Reminder.remind_at <= now,
            )
        )
        result = await session.execute(stmt)
        reminders = result.scalars().all()

        for reminder in reminders:
            try:
                message = f"⏰ Recordatorio:\n{reminder.content}"
                await whatsapp.send_message(reminder.user_phone, message)
                reminder.sent = True
                logger.info(f"Sent reminder {reminder.id} to {reminder.user_phone}")
            except Exception as e:
                logger.error(f"Failed to send reminder {reminder.id}: {e}")

        await session.commit()


@celery_app.task(name="app.services.scheduler.send_weekly_summaries")
def send_weekly_summaries():
    """Send weekly summaries to all active users."""
    import asyncio
    asyncio.run(_async_weekly_summaries())


async def _async_weekly_summaries():
    from app.db.session import get_async_session
    from app.db.models import User
    from app.db.repositories import NoteRepository
    from app.services.whatsapp_service import WhatsAppService
    from sqlalchemy import select

    whatsapp = WhatsAppService()
    note_repo = NoteRepository()

    async with get_async_session() as session:
        result = await session.execute(
            select(User).where(User.is_active == True)
        )
        users = result.scalars().all()

        for user in users:
            try:
                summary = await _build_weekly_summary(user.phone, note_repo)
                await whatsapp.send_message(user.phone, summary)
            except Exception as e:
                logger.error(f"Weekly summary failed for {user.phone}: {e}")


async def _build_weekly_summary(user_phone: str, repo) -> str:
    expenses = await repo.get_expenses_summary(user_phone, "this_week")
    tasks = await repo.get_notes_count(user_phone, "tarea", "this_week")
    ideas = await repo.get_notes_count(user_phone, "idea", "this_week")
    docs = await repo.get_notes_count(user_phone, "documento", "this_week")

    from datetime import datetime, timedelta
    week_start = (datetime.now() - timedelta(days=7)).strftime("%d/%m")
    week_end = datetime.now().strftime("%d/%m")

    lines = [
        f"📋 *Tu semana en resumen* — {week_start} al {week_end}",
        "",
        f"✅ Tareas guardadas: {tasks}",
        f"💰 Gastos totales: S/{expenses.get('total', 0):.2f}",
        f"💡 Ideas anotadas: {ideas}",
        f"📄 Documentos escaneados: {docs}",
    ]

    if expenses.get("by_category"):
        lines.append("")
        lines.append("💳 Gastos por categoría:")
        for cat, amount in expenses["by_category"].items():
            lines.append(f"  • {cat}: S/{amount:.2f}")

    lines.append("")
    lines.append("¿Qué fue lo más importante de tu semana? Cuéntame 👇")

    return "\n".join(lines)


@celery_app.task(name="app.services.scheduler.send_daily_checkin")
def send_daily_checkin():
    """Send daily check-in message to engaged users (sent messages today)."""
    import asyncio
    asyncio.run(_async_daily_checkin())


async def _async_daily_checkin():
    from app.db.session import get_async_session
    from app.db.models import ChatHistory
    from app.services.whatsapp_service import WhatsAppService
    from sqlalchemy import select, distinct
    from datetime import datetime, timedelta

    whatsapp = WhatsAppService()
    today_start = datetime.now().replace(hour=0, minute=0, second=0)

    async with get_async_session() as session:
        result = await session.execute(
            select(distinct(ChatHistory.user_phone)).where(
                ChatHistory.created_at >= today_start,
                ChatHistory.role == "user",
            )
        )
        active_phones = result.scalars().all()

        for phone in active_phones:
            try:
                await whatsapp.send_message(
                    phone,
                    "🌙 ¿Qué fue lo más importante que hiciste hoy?\n\nEscríbeme en una frase y lo guardo en tu memoria 📝"
                )
            except Exception as e:
                logger.error(f"Daily checkin failed for {phone}: {e}")
