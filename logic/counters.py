"""Anonymous daily totals (Club Pulse and the admin usage chart). Never stores who did what."""
import hashlib
import secrets
import threading
from datetime import timedelta

from sqlalchemy import select

from extensions import db
from logic import schedule, settings
from models import DailyCounter

# Unique visits: a hash of the session id with a salt that changes every day,
# kept in memory only. So we can count "unique visitors today" without tracking anyone.
_visit_lock = threading.Lock()
_visit_state = {"day": None, "salt": None, "seen": set()}


def today():
    return schedule.local_today(schedule.utc_now(), settings.get("timezone"))


def is_meeting_day(day):
    return schedule.is_meeting_day(day, settings.get("meeting_schedule"))


def bump(key, amount=1, day=None):
    day = day or today()
    row = db.session.get(DailyCounter, (day, key))
    if row is None:
        row = DailyCounter(date=day, key=key, value=0, meeting_day=is_meeting_day(day))
        db.session.add(row)
    row.value = (row.value or 0) + amount


def get_count(key, day=None):
    row = db.session.get(DailyCounter, (day or today(), key))
    return row.value if row else 0


def record_visit(session_id):
    day = today()
    with _visit_lock:
        if _visit_state["day"] != day:
            _visit_state.update(day=day, salt=secrets.token_hex(16), seen=set())
        digest = hashlib.sha256((_visit_state["salt"] + str(session_id)).encode()).hexdigest()
        if digest in _visit_state["seen"]:
            return
        _visit_state["seen"].add(digest)
    bump("visits")
    db.session.commit()


def week_totals():
    """Totals since Monday of this week (club time zone)."""
    day = today()
    start = day - timedelta(days=day.weekday())
    rows = db.session.execute(select(DailyCounter).where(DailyCounter.date >= start)).scalars().all()
    totals = {"rounds": 0, "human_rounds": 0, "befriended": 0, "offday_rounds": 0, "delegates_created": 0}
    for r in rows:
        if r.key in totals:
            totals[r.key] += r.value
        if r.key == "rounds" and not r.meeting_day:
            totals["offday_rounds"] += r.value
    return totals


def daily_series(days=30):
    day = today()
    start = day - timedelta(days=days - 1)
    rows = db.session.execute(select(DailyCounter).where(DailyCounter.date >= start)).scalars().all()
    by_day = {}
    for r in rows:
        entry = by_day.setdefault(r.date.isoformat(), {"date": r.date.isoformat(), "meeting_day": r.meeting_day})
        entry[r.key] = r.value
    out = []
    for i in range(days):
        d = start + timedelta(days=i)
        out.append(by_day.get(d.isoformat(), {"date": d.isoformat(), "meeting_day": is_meeting_day(d)}))
    return out
