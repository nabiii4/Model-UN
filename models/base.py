"""Shared pieces for every database table."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id():
    """IDs are random UUID strings, so they can't be guessed or counted."""
    return str(uuid.uuid4())


def utcnow():
    """All times are stored in UTC without a time zone attached (works on SQLite and Postgres)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    # dict/list columns are stored as JSON (TEXT in SQLite, JSONB-compatible in Postgres).
    type_annotation_map = {dict: JSON, list: JSON}


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class TimestampMixin(CreatedMixin):
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
