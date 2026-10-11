"""Nightmare delegates, their drawings, versions, and training examples."""
from typing import Optional

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, CreatedMixin, TimestampMixin, new_id


class Image(CreatedMixin, Base):
    """Drawings are stored in the database (not on disk) so free hosts that wipe files don't lose them."""
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True)
    guest_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="temp")  # drawing / portrait / seed / temp
    mime: Mapped[str] = mapped_column(String(40), default="image/jpeg")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    thumb: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)


class Delegate(TimestampMixin, Base):
    __tablename__ = "delegates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    owner_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("members.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="photo")  # photo / canvas / blank / description / seed
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active / hidden / flagged / pending
    visibility: Mapped[str] = mapped_column(String(20), default="public")  # public / private
    credit: Mapped[str] = mapped_column(String(20), default="name")  # name / anonymous
    story: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    drawing_image_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    portrait_image_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    persona: Mapped[dict] = mapped_column(default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[Optional[list]] = mapped_column(nullable=True)
    times_practiced: Mapped[int] = mapped_column(Integer, default=0)
    befriended_count: Mapped[int] = mapped_column(Integer, default=0)
    pack: Mapped[str] = mapped_column(String(20), default="mun")

    @property
    def is_seed(self):
        return self.source == "seed"


class DelegateVersion(CreatedMixin, Base):
    __tablename__ = "delegate_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    delegate_id: Mapped[str] = mapped_column(String(64), ForeignKey("delegates.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    persona: Mapped[dict] = mapped_column(default=dict)
    summary: Mapped[str] = mapped_column(String(200), default="")
    changed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class TrainingExample(TimestampMixin, Base):
    __tablename__ = "training_examples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    delegate_id: Mapped[str] = mapped_column(String(64), ForeignKey("delegates.id", ondelete="CASCADE"), index=True)
    student_text: Mapped[str] = mapped_column(Text, default="")
    ideal_reply: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual / thumbs_down / session
    suggested_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / approved / rejected
    message_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
