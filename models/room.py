"""Today's Room: meeting check-in and pairing (Phase 2 builds the screens)."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin, new_id, utcnow


class RoomSession(TimestampMixin, Base):
    __tablename__ = "room_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    date: Mapped[date] = mapped_column(Date)
    started_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open / closed
    checkin_code: Mapped[str] = mapped_column(String(10), default="")
    mode: Mapped[str] = mapped_column(String(20), default="random")
    odd_mode: Mapped[str] = mapped_column(String(20), default="bot_slot")
    pairs: Mapped[list] = mapped_column(default=list)
    topic_of_day: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RoomCheckin(Base):
    __tablename__ = "room_checkins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("room_sessions.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(40))
    human_only: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
