"""Meeting schedule math: is it meeting time right now, in the club's time zone?"""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(text, fallback):
    try:
        h, m = str(text).split(":")
        return time(int(h), int(m))
    except (ValueError, TypeError):
        return fallback


def to_local(now_utc, tz_name):
    """now_utc is a naive UTC datetime (how we store times)."""
    aware = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/New_York")
    return aware.astimezone(tz)


def is_meeting_day(local_date, schedule):
    days = [d.lower()[:3] for d in (schedule or {}).get("days", [])]
    return DAY_KEYS[local_date.weekday()] in days


def in_meeting(now_utc, schedule, tz_name):
    """True during a scheduled meeting (start <= now < end on a meeting day)."""
    local = to_local(now_utc, tz_name)
    if not is_meeting_day(local.date(), schedule):
        return False
    start = _parse_hhmm((schedule or {}).get("start"), time(15, 0))
    end = _parse_hhmm((schedule or {}).get("end"), time(16, 30))
    return start <= local.time().replace(tzinfo=None) < end


def local_today(now_utc, tz_name):
    return to_local(now_utc, tz_name).date()


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
