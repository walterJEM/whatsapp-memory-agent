"""
Session Service — Manages per-user chat history.
Stores the last N messages in PostgreSQL so the agent has conversational context.
"""

from sqlalchemy import select, delete
from datetime import datetime

from app.db.models import ChatHistory
from app.db.session import get_async_session
from app.utils.logger import get_logger

logger = get_logger(__name__)

# How many messages to keep in context per user
MAX_HISTORY_LENGTH = 20


class SessionService:

    async def get_history(self, user_phone: str) -> list[dict]:
        """
        Return the last N messages for a user as a list of dicts.

        Returns:
            [{"role": "user"|"assistant", "content": "..."}]
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.user_phone == user_phone)
                .order_by(ChatHistory.created_at.desc())
                .limit(MAX_HISTORY_LENGTH)
            )
            rows = result.scalars().all()

        # Reverse so oldest messages come first (chronological order)
        rows = list(reversed(rows))

        return [{"role": row.role, "content": row.content} for row in rows]

    async def add_messages(
        self,
        user_phone: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """
        Persist a user message and the agent's response to chat history.
        Automatically trims old messages to keep history lean.
        """
        async with get_async_session() as session:
            now = datetime.now()

            session.add(ChatHistory(
                user_phone=user_phone,
                role="user",
                content=user_message,
                created_at=now,
            ))
            session.add(ChatHistory(
                user_phone=user_phone,
                role="assistant",
                content=assistant_response,
                created_at=now,
            ))

            await session.commit()

        # Trim old messages asynchronously to keep DB clean
        await self._trim_history(user_phone)

    async def clear_history(self, user_phone: str) -> None:
        """
        Wipe all chat history for a user.
        Useful when user says 'olvida todo' or 'nueva sesión'.
        """
        async with get_async_session() as session:
            await session.execute(
                delete(ChatHistory).where(ChatHistory.user_phone == user_phone)
            )
            await session.commit()
        logger.info(f"Chat history cleared for {user_phone}")

    async def get_message_count_today(self, user_phone: str) -> int:
        """
        Count messages sent by the user today.
        Used to enforce free plan daily limits if needed.
        """
        from sqlalchemy import func, and_
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        async with get_async_session() as session:
            result = await session.execute(
                select(func.count(ChatHistory.id)).where(
                    and_(
                        ChatHistory.user_phone == user_phone,
                        ChatHistory.role == "user",
                        ChatHistory.created_at >= today_start,
                    )
                )
            )
            return result.scalar() or 0

    async def _trim_history(self, user_phone: str) -> None:
        """
        Keep only the most recent MAX_HISTORY_LENGTH messages per user.
        Deletes older messages to prevent the table from growing indefinitely.
        """
        async with get_async_session() as session:
            # Get IDs of messages to keep
            result = await session.execute(
                select(ChatHistory.id)
                .where(ChatHistory.user_phone == user_phone)
                .order_by(ChatHistory.created_at.desc())
                .limit(MAX_HISTORY_LENGTH)
            )
            keep_ids = [row[0] for row in result.fetchall()]

            if len(keep_ids) == MAX_HISTORY_LENGTH:
                # Delete everything older than what we're keeping
                await session.execute(
                    delete(ChatHistory).where(
                        and_(
                            ChatHistory.user_phone == user_phone,
                            ChatHistory.id.notin_(keep_ids),
                        )
                    )
                )
                await session.commit()
