"""All database tables (BUILD_PROMPT.md section 11). Importing this module registers them."""
from models.base import Base, new_id, utcnow  # noqa: F401
from models.members import Member, ROLES, STAGES  # noqa: F401
from models.delegates import Delegate, DelegateVersion, Image, TrainingExample  # noqa: F401
from models.practice import Badge, FearMeter, HumanRound, Message, Reaction, Round, Strength  # noqa: F401
from models.room import RoomCheckin, RoomSession  # noqa: F401
from models.misc import (AuditLog, ChangeRequest, DailyCounter, LaughLog, Report, Setting,  # noqa: F401
                         Tip, UploadCode)
