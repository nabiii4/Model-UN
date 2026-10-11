"""The handoff lock (BUILD_PROMPT.md section 8.9).

"He didn't want the robot smarter. He wanted it to let go."
During meetings (strict mode) the AI rests for a few minutes after each round, so people
go practice with each other. The rules are enforced here on the server, not just in the UI.
"""
from datetime import datetime, timedelta

from sqlalchemy import select

from extensions import db
from logic import schedule, settings
from models import Member, Round, RoomCheckin, RoomSession


def iso(dt):
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def parse_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text).rstrip("Z"))
    except ValueError:
        return None


# ---------------------------------------------------------------- pure rules (unit tested)

def _copy(key, **values):
    """Site text, even outside a request (unit tests)."""
    from flask import has_app_context
    if has_app_context():
        return settings.copy_text(key, **values)
    from logic import data
    text = data.copy_defaults().get(key, "")
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def compute_handoff(*, now, mode, meeting, lock_minutes, home_cap, ai_rounds_today, is_overtime,
                    existing_lock_until=None, overtime_status="confirm"):
    """What happens after a finished AI round. overtime_status: yes / confirm / no."""
    base = {"lock_until": None, "overtime_available": False, "overtime_needs_confirm": False,
            "home_rounds_left": None, "reason": mode if mode == "off" else "", "meeting": meeting}
    if mode == "off":
        base["reason"] = "off"
        return base
    if meeting and mode == "strict":
        if is_overtime:
            # Overtime doesn't start a fresh lock (that would allow endless overtime).
            lock_until = existing_lock_until
            overtime_available = False
        else:
            lock_until = now + timedelta(minutes=lock_minutes)
            overtime_available = overtime_status in ("yes", "confirm")
        base.update(lock_until=iso(lock_until), overtime_available=overtime_available,
                    overtime_needs_confirm=overtime_available and overtime_status == "confirm",
                    reason="meeting")
        return base
    base.update(home_rounds_left=max(0, home_cap - ai_rounds_today), reason="gentle" if meeting else "home")
    return base


def check_start(*, now, mode, meeting, active_lock_until, overtime_used, overtime_requested,
                overtime_status, overtime_confirmed, home_cap, ai_rounds_today):
    """May this person start a new AI round right now?

    Returns (allowed, is_overtime, error). error is a dict for the 423 response.
    """
    if mode == "off":
        return True, False, None
    if meeting and mode == "strict":
        if active_lock_until and active_lock_until > now:
            can_overtime = (not overtime_used) and (
                overtime_status == "yes" or (overtime_status == "confirm" and overtime_confirmed))
            if overtime_requested and can_overtime:
                return True, True, None
            minutes = max(1, int((active_lock_until - now).total_seconds() // 60) + 1)
            return False, False, {
                "error": "locked",
                "lock_until": iso(active_lock_until),
                "minutes_left": minutes,
                "overtime_available": (not overtime_used) and overtime_status != "no",
                "overtime_needs_confirm": overtime_status == "confirm",
                "message": _copy("handoff.lock", n=minutes),
            }
        return True, False, None
    if ai_rounds_today >= home_cap:
        return False, False, {
            "error": "home_cap_reached",
            "home_cap": home_cap,
            "message": f"That's {home_cap} AI rounds today — the most for one day. "
                       "Home practice counts. Bring it to the next meeting.",
        }
    return True, False, None


# ---------------------------------------------------------------- database helpers

def _owner_clause(member_id, guest_id):
    return Round.member_id == member_id if member_id else Round.guest_id == guest_id


def active_lock(member_id, guest_id, now):
    """The newest finished, non-overtime round whose lock hasn't ended yet."""
    rows = db.session.execute(
        select(Round).where(_owner_clause(member_id, guest_id), Round.completed.is_(True),
                            Round.is_overtime.is_(False), Round.handoff.is_not(None))
        .order_by(Round.ended_at.desc()).limit(3)).scalars().all()
    for r in rows:
        until = parse_iso((r.handoff or {}).get("lock_until"))
        if until and until > now:
            return r, until
    return None, None


def overtime_used_since(member_id, guest_id, since):
    if since is None:
        return False
    row = db.session.execute(
        select(Round.id).where(_owner_clause(member_id, guest_id), Round.is_overtime.is_(True),
                               Round.started_at >= since).limit(1)).first()
    return row is not None


def overtime_status(member_id, now):
    """yes = Today's Room shows you in the bot slot or unpaired; confirm = no Room open (ask first);
    no = you have a human partner in today's Room."""
    if not member_id:
        return "confirm"
    today = schedule.local_today(now, settings.get("timezone"))
    session = db.session.execute(
        select(RoomSession).where(RoomSession.status == "open", RoomSession.date == today)).scalars().first()
    if session is None:
        return "confirm"
    checked_in = db.session.execute(
        select(RoomCheckin).where(RoomCheckin.session_id == session.id, RoomCheckin.member_id == member_id)
    ).scalars().first()
    if checked_in is None or not session.pairs:
        return "yes"
    for pair in session.pairs or []:
        ids = [p.get("member_id") for p in pair.get("people", [])]
        if member_id in ids:
            return "yes" if pair.get("bot_slot") else "no"
    return "yes"


def ai_rounds_today(member, guest_id, now):
    today = schedule.local_today(now, settings.get("timezone"))
    if member is not None:
        return member.ai_rounds_today if member.ai_rounds_date == today else 0
    rows = db.session.execute(
        select(Round).where(Round.guest_id == guest_id, Round.completed.is_(True))).scalars().all()
    return sum(1 for r in rows if r.ended_at and schedule.local_today(r.ended_at, settings.get("timezone")) == today)


def count_completed_round(member, now):
    """Bump the member's 'AI rounds today' counter (resets each day)."""
    if member is None:
        return
    today = schedule.local_today(now, settings.get("timezone"))
    if member.ai_rounds_date != today:
        member.ai_rounds_date = today
        member.ai_rounds_today = 0
    member.ai_rounds_today += 1


def state_for(member, guest_id, now):
    """Current handoff state for the handoff screen and round setup."""
    s = settings.get
    mode = s("handoff_mode")
    meeting = schedule.in_meeting(now, s("meeting_schedule"), s("timezone"))
    member_id = member.id if member else None
    lock_round, lock_until = active_lock(member_id, guest_id, now)
    used = overtime_used_since(member_id, guest_id, lock_round.ended_at if lock_round else None)
    status = overtime_status(member_id, now)
    done_today = ai_rounds_today(member, guest_id, now)
    locked = bool(meeting and mode == "strict" and lock_until and lock_until > now)
    return {
        "mode": mode,
        "meeting": meeting,
        "locked": locked,
        "lock_until": iso(lock_until) if locked else None,
        "seconds_left": int((lock_until - now).total_seconds()) if locked else 0,
        "overtime_available": locked and not used and status != "no",
        "overtime_needs_confirm": status == "confirm",
        "overtime_used": used,
        "home_cap": s("home_cap"),
        "ai_rounds_today": done_today,
        "home_rounds_left": max(0, s("home_cap") - done_today) if mode != "off" and not (meeting and mode == "strict") else None,
    }


def member_by_id(member_id):
    return db.session.get(Member, member_id) if member_id else None
