"""Smaller tables: tips, requests, reports, settings, counters, audit log, and more."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, CreatedMixin, TimestampMixin, new_id, utcnow


class Tip(TimestampMixin, Base):
    __tablename__ = "tips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    delegate_id: Mapped[str] = mapped_column(String(64), ForeignKey("delegates.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=True)
    text: Mapped[str] = mapped_column(String(200))
    credit: Mapped[str] = mapped_column(String(20), default="name")
    status: Mapped[str] = mapped_column(String(20), default="visible")  # visible / hidden / flagged


class ChangeRequest(TimestampMixin, Base):
    """'Suggest a change' ideas and bug reports (table name: requests)."""
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), default="idea")  # idea / bug
    what_happened: Mapped[str] = mapped_column(Text, default="")
    what_should_happen: Mapped[str] = mapped_column(Text, default="")
    page: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new / planned / done / wont_do
    reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Set when someone suggests a change to one specific nightmare (it goes to the owner).
    delegate_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    credit_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)


class Report(CreatedMixin, Base):
    """A 'Report' click. Feeds the moderation queue."""
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    target_type: Mapped[str] = mapped_column(String(20))  # delegate / tip
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    reporter_key: Mapped[str] = mapped_column(String(64))  # member:<id> or guest:<id>, never an IP
    reason: Mapped[str] = mapped_column(String(300), default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class LaughLog(CreatedMixin, Base):
    __tablename__ = "laugh_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id", ondelete="CASCADE"))
    member_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class UploadCode(CreatedMixin, Base):
    __tablename__ = "upload_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    created_by_session: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    image_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(nullable=True)  # any JSON value
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DailyCounter(Base):
    """Anonymous totals only (Club Pulse, usage chart). Never who did what."""
    __tablename__ = "daily_counters"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
    meeting_day: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditLog(CreatedMixin, Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(nullable=True)
