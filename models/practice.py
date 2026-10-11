"""Practice rounds, their messages, fear meters, human rounds, strengths, and badges."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, CreatedMixin, TimestampMixin, new_id, utcnow


class Round(CreatedMixin, Base):
    __tablename__ = "rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=True, index=True)
    guest_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    delegate_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("delegates.id", ondelete="SET NULL"), nullable=True, index=True)
    delegate_version: Mapped[int] = mapped_column(Integer, default=1)
    # A copy of the persona at the start, so editing the delegate mid-round can't confuse it.
    persona_snapshot: Mapped[dict] = mapped_column(default=dict)
    settings: Mapped[dict] = mapped_column(default=dict)
    opening: Mapped[dict] = mapped_column(default=dict)
    heat: Mapped[int] = mapped_column(Integer, default=2)
    heat_trace: Mapped[list] = mapped_column(default=list)
    labels: Mapped[list] = mapped_column(default=list)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    hint_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    switched_sides: Mapped[bool] = mapped_column(Boolean, default=False)
    switch_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    exchanges: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    abandoned: Mapped[bool] = mapped_column(Boolean, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)  # break-character pause
    feedback: Mapped[Optional[dict]] = mapped_column(nullable=True)
    delivery: Mapped[Optional[dict]] = mapped_column(nullable=True)
    fear_change: Mapped[Optional[dict]] = mapped_column(nullable=True)
    handoff: Mapped[Optional[dict]] = mapped_column(nullable=True)
    is_overtime: Mapped[bool] = mapped_column(Boolean, default=False)
    is_home: Mapped[bool] = mapped_column(Boolean, default=False)


class Message(CreatedMixin, Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    round_id: Mapped[str] = mapped_column(String(36), ForeignKey("rounds.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(20))  # delegate / student / system
    text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(default=dict)


class Reaction(CreatedMixin, Base):
    __tablename__ = "reactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))  # up / down / laugh
    suggestion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FearMeter(Base):
    __tablename__ = "fear_meters"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    delegate_id: Mapped[str] = mapped_column(String(64), ForeignKey("delegates.id", ondelete="CASCADE"), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=100)
    befriended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class HumanRound(CreatedMixin, Base):
    __tablename__ = "human_rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), index=True)
    partner_member_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    partner_name: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    topic: Mapped[str] = mapped_column(String(200), default="")
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    source_round_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class Strength(CreatedMixin, Base):
    __tablename__ = "strengths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), index=True)
    round_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")


class Badge(Base):
    __tablename__ = "badges"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    badge_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
