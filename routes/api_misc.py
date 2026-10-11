"""Health, Club Pulse, setup data, and 'Suggest a change'."""
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from extensions import db, limiter
from logic import counters, data, settings
from logic.security import clean_text, contains_blocked, current_member, editor_required, requester_key
from models import ChangeRequest, Delegate
from routes.helpers import ai, as_bool, body, error

bp = Blueprint("misc", __name__)


@bp.get("/api/health")
def health():
    """Which features work right now. Never includes keys, endpoints, or deployment names."""
    client = ai()
    client.maybe_probe(current_app._get_current_object())
    return jsonify(client.public_health())


@bp.get("/api/stats/club")
def club_stats():
    """Club Pulse: anonymous weekly totals. Never names, never rankings."""
    return jsonify({"week": counters.week_totals()})


@bp.get("/api/setup-data")
def setup_data():
    """Committees, topics, countries, and formats for the round setup screen."""
    return jsonify({
        "committees": settings.get("committees"),
        "countries": data.countries(),
        "formats": [{"id": f["id"], "name": f["name"], "blurb": f["blurb"], "phase": f["phase"],
                     "exchanges": f["exchanges"], "turn_seconds": f["turn_seconds"], "who_starts": f["who_starts"]}
                    for f in data.formats().values()],
    })


@bp.post("/api/requests")
@limiter.limit("15 per hour", key_func=lambda: "req:" + requester_key())
def create_request():
    d = body()
    what = clean_text(d.get("what_happened"), 1000)
    should = clean_text(d.get("what_should_happen"), 1000)
    if len(what) < 2 and len(should) < 2:
        return error("empty", "Tell us what happened or what should happen.")
    m = current_member()
    credit = None
    if m and d.get("credit") != "anonymous":
        credit = m.display_name
    delegate_id = d.get("delegate_id")
    if delegate_id and db.session.get(Delegate, str(delegate_id)) is None:
        delegate_id = None
    hidden = contains_blocked(what, should)
    req = ChangeRequest(member_id=m.id if m else None, kind="bug" if d.get("kind") == "bug" else "idea",
                        what_happened=what, what_should_happen=should,
                        page=clean_text(d.get("page"), 200, single_line=True), status="wont_do" if hidden else "new",
                        delegate_id=str(delegate_id) if delegate_id else None, credit_name=credit)
    if m and as_bool(d.get("credit_opt_in")):
        m.credit_opt_in = True
    db.session.add(req)
    db.session.commit()
    return jsonify({"ok": True, "message": settings.copy_text("suggest.thanks")})


@bp.get("/api/requests")
@editor_required
def list_requests():
    rows = db.session.execute(select(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(300)).scalars().all()
    return jsonify({"requests": [{
        "id": r.id, "kind": r.kind, "what_happened": r.what_happened, "what_should_happen": r.what_should_happen,
        "page": r.page, "status": r.status, "reply": r.reply, "from": r.credit_name or "Anonymous",
        "delegate_id": r.delegate_id, "date": r.created_at.isoformat()} for r in rows]})


@bp.patch("/api/requests/<req_id>")
@editor_required
def update_request(req_id):
    r = db.session.get(ChangeRequest, req_id)
    if r is None:
        return error("not_found", "That request is gone.", 404)
    d = body()
    if d.get("status") in ("new", "planned", "done", "wont_do"):
        r.status = d["status"]
    if "reply" in d:
        r.reply = clean_text(d.get("reply"), 500) or None
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/api/copy")
def copy_bank():
    return jsonify(settings.all_copy())


@bp.get("/api/demo-round")
def demo_round():
    from logic.security import guest_id
    from flask import session
    guest_id()
    session["watched_demo"] = True
    m = current_member()
    if m is not None:
        from logic import journey
        m.stage = journey.advance_stage(m.stage, "watched_demo")
        db.session.commit()
    demo = data.demo_round()
    d = db.session.get(Delegate, demo.get("delegate_id", ""))
    out = dict(demo)
    out["delegate"] = ({"name": d.name, "look": d.persona.get("look", {}), "quirks": d.persona.get("quirks", []),
                        "image_url": f"/api/images/{d.drawing_image_id}" if d.drawing_image_id else None}
                       if d else {"name": "The Interrupter", "look": {}, "quirks": [], "image_url": None})
    return jsonify(out)
