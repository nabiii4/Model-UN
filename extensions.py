"""Flask extensions live here so any file can import them without circular imports."""
from flask import g, request, session
from flask_limiter import Limiter
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from models.base import Base

# Our tables subclass models.base.Base (plain SQLAlchemy 2), so they can be imported
# without Flask. Flask-SQLAlchemy just manages the session and create_all().
db = SQLAlchemy(metadata=Base.metadata)
csrf = CSRFProtect()


def rate_key():
    """Who is making this request, for rate limits.

    Members are limited per member, guests per device (a random id in their cookie).
    IP addresses are only used as a last resort and are never stored (memory only).
    """
    member_id = session.get("member_id")
    if member_id:
        return f"member:{member_id}"
    guest_id = session.get("guest_id")
    if guest_id:
        return f"guest:{guest_id}"
    return f"ip:{request.remote_addr or 'unknown'}"


# In-memory storage: the app runs as a single worker, so limits stay consistent.
limiter = Limiter(key_func=rate_key, storage_uri="memory://", default_limits=[])
