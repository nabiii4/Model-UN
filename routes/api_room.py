"""Today's Room (Phase 2 builds check-in, pairing, and the projector view).

Phase 1 only needs to know whether a Room session is open, for the overtime rule.
"""
from flask import Blueprint, jsonify
from sqlalchemy import select

from extensions import db
from logic import schedule, settings
from logic.security import current_member
from models import RoomCheckin, RoomSession

bp = Blueprint("room", __name__)


@bp.get("/api/room/today")
def room_today():
    today = schedule.local_today(schedule.utc_now(), settings.get("timezone"))
    session = db.session.execute(select(RoomSession).where(RoomSession.status == "open",
                                                           RoomSession.date == today)).scalars().first()
    if session is None:
        return jsonify({"open": False, "count": 0})
    checkins = db.session.execute(select(RoomCheckin).where(RoomCheckin.session_id == session.id)).scalars().all()
    out = {"open": True, "count": len(checkins)}
    if current_member() is not None:  # names only for logged-in members
        out["names"] = [c.name for c in checkins]
    return jsonify(out)
