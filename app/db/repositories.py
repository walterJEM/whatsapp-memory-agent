"""
Repositories — Data Access Layer.
Toda la lógica de base de datos en un solo lugar.
El agente nunca habla directamente con la DB, siempre pasa por aquí.
"""

from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from app.db.models import Note, Reminder, User
from app.db.session import get_async_session
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─── User Repository ──────────────────────────────────────────────────────────

class UserRepository:

    async def get_or_create(self, phone: str) -> User:
        """Get existing user or create a new one on first message."""
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.phone == phone)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(phone=phone)
                session.add(user)
                await session.commit()
                await session.refresh(user)
                logger.info(f"New user created: {phone}")

            return user

    async def get_plan(self, phone: str) -> str:
        """Return user's current plan: free | pro | freelancer_pro"""
        async with get_async_session() as session:
            result = await session.execute(
                select(User.plan).where(User.phone == phone)
            )
            plan = result.scalar_one_or_none()
            return plan or "free"

    async def update_plan(self, phone: str, plan: str) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(User).where(User.phone == phone)
            )
            user = result.scalar_one_or_none()
            if user:
                user.plan = plan
                await session.commit()


# ─── Note Repository ──────────────────────────────────────────────────────────

class NoteRepository:

    async def create(
        self,
        user_phone: str,
        content: str,
        category: str,
        amount: Optional[float] = None,
        expense_category: Optional[str] = None,
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
        created_at: Optional[datetime] = None,
    ) -> Note:
        """Save a new note to the database."""
        async with get_async_session() as session:
            note = Note(
                user_phone=user_phone,
                content=content,
                category=category,
                amount=amount,
                expense_category=expense_category,
                tags=tags or [],
                metadata=metadata or {},
                created_at=created_at or datetime.now(),
            )
            session.add(note)
            await session.commit()
            await session.refresh(note)
            logger.info(f"Note {note.id} saved for {user_phone} [{category}]")
            return note

    async def get_by_id(self, note_id: UUID) -> Optional[Note]:
        async with get_async_session() as session:
            result = await session.execute(
                select(Note).where(Note.id == note_id, Note.is_deleted == False)
            )
            return result.scalar_one_or_none()

    async def get_recent(
        self,
        user_phone: str,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> list[Note]:
        """Get most recent notes for a user."""
        async with get_async_session() as session:
            stmt = select(Note).where(
                Note.user_phone == user_phone,
                Note.is_deleted == False,
            )
            if category:
                stmt = stmt.where(Note.category == category)

            stmt = stmt.order_by(Note.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_expenses_summary(
        self,
        user_phone: str,
        period: str,
        category: Optional[str] = None,
    ) -> dict:
        """
        Return expense totals grouped by subcategory.

        period: 'today' | 'this_week' | 'this_month' | 'last_month'
        """
        start, end = self._period_to_range(period)

        async with get_async_session() as session:
            stmt = select(Note).where(
                and_(
                    Note.user_phone == user_phone,
                    Note.category == "gasto",
                    Note.is_deleted == False,
                    Note.created_at >= start,
                    Note.created_at <= end,
                    Note.amount.isnot(None),
                )
            )
            if category:
                stmt = stmt.where(Note.expense_category == category)

            result = await session.execute(stmt)
            notes = result.scalars().all()

            if not notes:
                return {"total": 0.0, "by_category": {}, "items": []}

            by_category: dict[str, float] = {}
            for note in notes:
                cat = note.expense_category or "otros"
                by_category[cat] = by_category.get(cat, 0.0) + (note.amount or 0)

            return {
                "total": sum(by_category.values()),
                "by_category": by_category,
                "items": [
                    {
                        "id": str(note.id),
                        "content": note.content,
                        "amount": note.amount,
                        "expense_category": note.expense_category,
                        "created_at": note.created_at.isoformat(),
                    }
                    for note in notes
                ],
            }

    async def get_notes_count(
        self,
        user_phone: str,
        category: str,
        period: str,
    ) -> int:
        """Count notes in a category for a given period."""
        start, end = self._period_to_range(period)

        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(Note.id)).where(
                    and_(
                        Note.user_phone == user_phone,
                        Note.category == category,
                        Note.is_deleted == False,
                        Note.created_at >= start,
                        Note.created_at <= end,
                    )
                )
            )
            return result.scalar() or 0

    async def get_monthly_count(self, user_phone: str) -> int:
        """Count total notes this month — used to enforce free plan limits."""
        start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(Note.id)).where(
                    and_(
                        Note.user_phone == user_phone,
                        Note.is_deleted == False,
                        Note.created_at >= start,
                    )
                )
            )
            return result.scalar() or 0

    async def soft_delete(self, note_id: UUID) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(Note).where(Note.id == note_id)
            )
            note = result.scalar_one_or_none()
            if note:
                note.is_deleted = True
                await session.commit()

    def _period_to_range(self, period: str) -> tuple[datetime, datetime]:
        """Convert a period string to a (start, end) datetime tuple."""
        now = datetime.now()

        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "this_week":
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = now
        elif period == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "last_month":
            first_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = first_this_month - timedelta(seconds=1)
            start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default: last 30 days
            start = now - timedelta(days=30)
            end = now

        return start, end


# ─── Reminder Repository ──────────────────────────────────────────────────────

class ReminderRepository:

    async def create(
        self,
        user_phone: str,
        content: str,
        remind_at: datetime,
        original_text: str = "",
    ) -> Reminder:
        """Create a new reminder."""
        async with get_async_session() as session:
            reminder = Reminder(
                user_phone=user_phone,
                content=content,
                remind_at=remind_at,
                original_text=original_text,
            )
            session.add(reminder)
            await session.commit()
            await session.refresh(reminder)
            logger.info(f"Reminder {reminder.id} set for {user_phone} at {remind_at}")
            return reminder

    async def get_pending(self, user_phone: str) -> list[Reminder]:
        """Get all pending (not yet sent) reminders for a user."""
        async with get_async_session() as session:
            result = await session.execute(
                select(Reminder).where(
                    and_(
                        Reminder.user_phone == user_phone,
                        Reminder.sent == False,
                        Reminder.remind_at > datetime.now(),
                    )
                ).order_by(Reminder.remind_at.asc())
            )
            return result.scalars().all()

    async def get_due_now(self) -> list[Reminder]:
        """Get all reminders that are due now (used by Celery scheduler)."""
        async with get_async_session() as session:
            result = await session.execute(
                select(Reminder).where(
                    and_(
                        Reminder.sent == False,
                        Reminder.remind_at <= datetime.now(),
                    )
                )
            )
            return result.scalars().all()

    async def mark_sent(self, reminder_id: UUID) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(Reminder).where(Reminder.id == reminder_id)
            )
            reminder = result.scalar_one_or_none()
            if reminder:
                reminder.sent = True
                await session.commit()

    async def count_active(self, user_phone: str) -> int:
        """Count active reminders — used to enforce free plan limit."""
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(Reminder.id)).where(
                    and_(
                        Reminder.user_phone == user_phone,
                        Reminder.sent == False,
                        Reminder.remind_at > datetime.now(),
                    )
                )
            )
            return result.scalar() or 0
