"""Club members. First name + 4-digit PIN only - no emails, last names, or birthdays (privacy)."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin, new_id

ROLES = ("member", "editor", "maintainer")
STAGES = ("pockets", "keyboard", "microphone")


class Member(TimestampMixin, Base):
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(40), nullable=False)
    # Lower-case copy of the name so "Sam" and "sam" count as the same person.
    name_key: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    stage: Mapped[str] = mapped_column(String(20), default="pockets", nullable=False)
    comfort: Mapped[dict] = mapped_column(default=dict)
    answers: Mapped[dict] = mapped_column(default=dict)
    bot_slot_count: Mapped[int] = mapped_column(Integer, default=0)
    last_bot_slot_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    show_up_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    ai_rounds_today: Mapped[int] = mapped_column(Integer, default=0)
    ai_rounds_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    credit_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # Remembered for the one-click Quick Start button.
    last_round_settings: Mapped[Optional[dict]] = mapped_column(nullable=True)

    @property
    def is_editor(self):
        return self.role in ("editor", "maintainer")

    @property
    def is_maintainer(self):
        return self.role == "maintainer"
