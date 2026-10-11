"""Rate limits for AI features (BUILD_PROMPT.md section 9.4) and who may use AI at all."""
from flask import session

from extensions import limiter, rate_key
from logic import settings
from logic.security import current_member
from routes.helpers import error


def _ai_limit():
    """Members: 40 AI calls per 10 minutes and 300 per day. Guests (if allowed): the daily quota per device."""
    if session.get("member_id"):
        return "40 per 10 minutes;300 per day"
    quota = settings.get("guest_ai").get("daily_quota", 15)
    try:
        quota = max(1, int(quota))
    except (TypeError, ValueError):
        quota = 15
    return f"{quota} per day"


# One shared bucket for every AI endpoint, so the limits count AI calls across the whole site.
ai_limit = limiter.shared_limit(_ai_limit, scope="ai", key_func=rate_key)


def ai_access_denied():
    """None if this person may use AI features, else a friendly error response."""
    if current_member() is not None:
        return None
    if settings.get("guest_ai").get("enabled"):
        return None
    return error("guest_ai_off", settings.copy_text("error.guest_ai_off"), 403, join_url="/join")
