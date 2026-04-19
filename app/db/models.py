"""
Database Models — SQLAlchemy ORM models for PostgreSQL.
"""

from sqlalchemy import Column, String, Float, DateTime, JSON, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    plan = Column(String(20), default="free")  # free | pro | freelancer_pro
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

    notes = relationship("Note", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")

    @property
    def monthly_note_count(self):
        """Used to enforce free plan limits."""
        from datetime import timedelta
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        return sum(1 for n in self.notes if n.created_at >= month_start)


class Note(Base):
    __tablename__ = "notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_phone = Column(String(20), ForeignKey("users.phone"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)       # gasto, tarea, idea, etc.
    amount = Column(Float, nullable=True)                # for expenses
    expense_category = Column(String(50), nullable=True) # transporte, comida, etc.
    tags = Column(JSON, default=list)
    extra_data = Column(JSON, default=dict)               # OCR data, etc.
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="notes")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_phone = Column(String(20), ForeignKey("users.phone"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    original_text = Column(Text, nullable=True)
    remind_at = Column(DateTime, nullable=False, index=True)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="reminders")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_phone = Column(String(20), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
