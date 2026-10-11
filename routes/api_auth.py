"""Join, log in, log out, and 'my stuff' (profile, comfort settings, my data)."""
import json
import re

from flask import Blueprint, Response, jsonify, request, session
from sqlalchemy import delete, select, update
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, limiter
from logic import journey, settings
from logic.security import (clean_text, current_member, guest_id, log_in, log_out, member_required,
                            valid_display_name)
from models import (Badge, ChangeRequest, Delegate, FearMeter, HumanRound, Image, Member, Reaction, Round,
                    Strength, Tip, TrainingExample)
from routes.helpers import as_bool, audit, body, error

bp = Blueprint("auth", __name__)

COMFORT_DEFAULTS = {
    "gentle": False, "default_mode": "type", "camera_off": True, "interruptions": True,
    "dramatic_silence": True, "timers": True, "auto_hints": False, "ai_voice": True, "voice_speed": 1.0,
    "reduced_motion": False, "text_size": 100, "readable_font": False, "default_length": "quick",
}


def comfort_for(member):
    merged = dict(COMFORT_DEFAULTS)
    merged.update((member.comfort or {}) if member else session.get("guest_comfort", {}))
    return merged


def comfort_from_answers(answers, comfort):
    """The 3 questions set comfort defaults (section 6.2 C)."""
    c = dict(comfort)
    picked = set((answers or {}).get("comfortable") or [])
    if "No timer" in picked:
        c["timers"] = False
    if "Typing first" in picked:
        c["default_mode"] = "type"
    if "A slower opponent" in picked:
        c["gentle"] = True
    if "Short rounds" in picked:
        c["default_length"] = "quick"
    if "Hints" in picked:
        c["auto_hints"] = True
    return c


def clean_answers(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key in ("nervous", "comfortable", "try_again"):
        items = raw.get(key) or []
        if not isinstance(items, list):
            items = []
        out[key] = [clean_text(i, 60, single_line=True) for i in items[:12] if clean_text(i, 60)]
        out[f"{key}_other"] = clean_text(raw.get(f"{key}_other"), 100, single_line=True)
    return out


def _login_key():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip().lower()[:40]
    return f"login:{name}:{request.remote_addr or 'unknown'}"


def _join_key():
    return f"join:{request.remote_addr or 'unknown'}"


def _member_json(m):
    return {"id": m.id, "name": m.display_name, "role": m.role, "stage": m.stage, "comfort": comfort_for(m),
            "show_up_days": m.show_up_days, "credit_opt_in": m.credit_opt_in}


@bp.post("/api/auth/join")
@limiter.limit("10 per 10 minutes", key_func=_join_key, deduct_when=lambda r: r.status_code != 200)
def join():
    data = body()
    code = clean_text(data.get("club_code"), 60, single_line=True)
    name = clean_text(data.get("name"), 30, single_line=True)
    pin = str(data.get("pin", "")).strip()
    shared = as_bool(data.get("shared_device", True))
    if code.lower() != str(settings.get("club_code")).strip().lower():
        return error("bad_code", "That club code didn't work. Ask an officer for this year's code.")
    if not valid_display_name(name):
        return error("bad_name", "Use your first name or a nickname (start with a letter, up to 30 characters).")
    if not re.fullmatch(r"\d{4}", pin):
        return error("bad_pin", "Your PIN is 4 numbers, like 2580.")
    if db.session.execute(select(Member.id).where(Member.name_key == name.lower())).first():
        return error("name_taken", f"Someone already uses “{name}”. Try adding a last initial, like “{name} K”.", 409)
    answers = clean_answers(session.get("guest_answers"))
    comfort = comfort_from_answers(answers, dict(COMFORT_DEFAULTS))
    comfort.update(session.get("guest_comfort", {}))
    m = Member(display_name=name, name_key=name.lower(), pin_hash=generate_password_hash(pin), role="member",
               stage=journey.advance_stage("pockets", "joined"), comfort=comfort, answers=answers)
    if session.get("watched_demo"):
        m.stage = journey.advance_stage(m.stage, "watched_demo")
    db.session.add(m)
    db.session.commit()
    log_in(m, shared_device=shared)
    return jsonify({"ok": True, "member": _member_json(m)})


@bp.post("/api/auth/login")
@limiter.limit("5 per 10 minutes", key_func=_login_key, deduct_when=lambda r: r.status_code != 200)
def login():
    data = body()
    name = clean_text(data.get("name"), 30, single_line=True)
    pin = str(data.get("pin", "")).strip()
    shared = as_bool(data.get("shared_device", True))
    m = db.session.execute(select(Member).where(Member.name_key == name.lower())).scalars().first()
    if m is None or not check_password_hash(m.pin_hash, pin):
        return error("bad_login", "That name and PIN don't match. Forgot your PIN? An officer can reset it.", 401)
    log_in(m, shared_device=shared)
    return jsonify({"ok": True, "member": _member_json(m)})


@bp.post("/api/auth/logout")
def logout():
    log_out()
    return jsonify({"ok": True})


@bp.get("/api/me")
@member_required
def me():
    m = current_member()
    strengths = db.session.execute(select(Strength).where(Strength.member_id == m.id)
                                   .order_by(Strength.created_at.desc()).limit(50)).scalars().all()
    rounds = db.session.execute(select(Round).where(Round.member_id == m.id, Round.completed.is_(True))
                                .order_by(Round.ended_at.desc()).limit(30)).scalars().all()
    mine = db.session.execute(select(Delegate).where(Delegate.owner_id == m.id)
                              .order_by(Delegate.created_at.desc())).scalars().all()
    fears = db.session.execute(select(FearMeter).where(FearMeter.member_id == m.id)).scalars().all()
    requests_ = db.session.execute(select(ChangeRequest).where(ChangeRequest.member_id == m.id)
                                   .order_by(ChangeRequest.created_at.desc()).limit(20)).scalars().all()
    badges = db.session.execute(select(Badge).where(Badge.member_id == m.id)).scalars().all()
    human_count = db.session.execute(select(HumanRound.id).where(HumanRound.member_id == m.id)).all()
    delegate_names = {d.id: d.name for d in db.session.execute(
        select(Delegate).where(Delegate.id.in_([r.delegate_id for r in rounds if r.delegate_id] +
                                               [f.delegate_id for f in fears]))).scalars()}
    return jsonify({
        "member": _member_json(m),
        "answers": m.answers or {},
        "strengths": [{"text": s.text, "round_id": s.round_id, "date": s.created_at.date().isoformat()} for s in strengths],
        "rounds": [{"id": r.id, "delegate": delegate_names.get(r.delegate_id) or r.persona_snapshot.get("name", "A nightmare"),
                    "topic": r.settings.get("topic"), "format": r.settings.get("format_name"),
                    "date": (r.ended_at or r.started_at).date().isoformat(), "mode": r.settings.get("mode", "type")}
                   for r in rounds],
        "nightmares": [{"id": d.id, "name": d.name, "visibility": d.visibility, "status": d.status,
                        "image_url": f"/api/images/{d.drawing_image_id}?thumb=1" if d.drawing_image_id else None}
                       for d in mine],
        "fear": [{"delegate_id": f.delegate_id, "name": delegate_names.get(f.delegate_id, "A nightmare"),
                  "value": f.value, "befriended": f.befriended_at is not None} for f in fears],
        "suggestions": [{"what": r.what_happened[:120], "status": r.status, "reply": r.reply,
                         "date": r.created_at.date().isoformat()} for r in requests_],
        "badges": [{"id": b.badge_id, "earned_at": b.earned_at.date().isoformat()} for b in badges],
        "human_rounds": len(human_count),
    })


@bp.patch("/api/me/comfort")
@member_required
def update_comfort():
    m = current_member()
    data = body()
    c = comfort_for(m)
    for key, default in COMFORT_DEFAULTS.items():
        if key not in data:
            continue
        v = data[key]
        if isinstance(default, bool):
            c[key] = as_bool(v)
        elif key == "default_mode":
            c[key] = v if v in ("type", "speak") else "type"
        elif key == "default_length":
            c[key] = v if v in ("quick", "standard", "timed") else "quick"
        elif key == "text_size":
            c[key] = int(v) if str(v) in ("100", "115", "130") else 100
        elif key == "voice_speed":
            try:
                c[key] = max(0.85, min(1.25, float(v)))
            except (TypeError, ValueError):
                pass
    if "credit_opt_in" in data:
        m.credit_opt_in = as_bool(data["credit_opt_in"])
    m.comfort = c
    db.session.commit()
    return jsonify({"ok": True, "comfort": c})


@bp.post("/api/me/answers")
def save_answers():
    """The 3 optional questions. Members: saved + comfort updated. Guests: kept in the session."""
    answers = clean_answers(body().get("answers"))
    m = current_member()
    if m:
        m.answers = answers
        m.comfort = comfort_from_answers(answers, comfort_for(m))
        db.session.commit()
        return jsonify({"ok": True, "comfort": m.comfort})
    guest_id()
    session["guest_answers"] = answers
    session["guest_comfort"] = comfort_from_answers(answers, session.get("guest_comfort", {}))
    return jsonify({"ok": True, "comfort": comfort_for(None)})


@bp.get("/api/me/export")
@member_required
def export_my_data():
    m = current_member()
    rounds = db.session.execute(select(Round).where(Round.member_id == m.id)).scalars().all()
    from models import Message
    out = {
        "about": "Everything Nightmare Delegate stores about you. Your PIN is stored only as a scrambled hash.",
        "member": {"name": m.display_name, "role": m.role, "stage": m.stage, "comfort": m.comfort,
                   "answers": m.answers, "show_up_days": m.show_up_days, "joined": m.created_at.isoformat()},
        "nightmares": [{"id": d.id, "name": d.name, "visibility": d.visibility, "story": d.story, "persona": d.persona}
                       for d in db.session.execute(select(Delegate).where(Delegate.owner_id == m.id)).scalars()],
        "rounds": [{"id": r.id, "settings": r.settings, "feedback": r.feedback, "started_at": r.started_at.isoformat(),
                    "completed": r.completed,
                    "messages": [{"role": x.role, "text": x.text} for x in db.session.execute(
                        select(Message).where(Message.round_id == r.id).order_by(Message.seq)).scalars()]}
                   for r in rounds],
        "strengths": [s.text for s in db.session.execute(select(Strength).where(Strength.member_id == m.id)).scalars()],
        "human_rounds": [{"topic": h.topic, "seconds": h.seconds, "partner": h.partner_name, "date": h.created_at.isoformat()}
                         for h in db.session.execute(select(HumanRound).where(HumanRound.member_id == m.id)).scalars()],
        "fear_meters": [{"delegate_id": f.delegate_id, "value": f.value} for f in
                        db.session.execute(select(FearMeter).where(FearMeter.member_id == m.id)).scalars()],
        "tips": [t.text for t in db.session.execute(select(Tip).where(Tip.member_id == m.id)).scalars()],
        "suggestions": [{"what_happened": r.what_happened, "what_should_happen": r.what_should_happen, "status": r.status}
                        for r in db.session.execute(select(ChangeRequest).where(ChangeRequest.member_id == m.id)).scalars()],
    }
    resp = Response(json.dumps(out, indent=2, ensure_ascii=False, default=str), mimetype="application/json")
    resp.headers["Content-Disposition"] = 'attachment; filename="my-nightmare-delegate-data.json"'
    return resp


def delete_member_data(m, public_delegates="anonymize"):
    """Remove a member and their data. Public nightmares can be kept anonymously."""
    owned = db.session.execute(select(Delegate).where(Delegate.owner_id == m.id)).scalars().all()
    for d in owned:
        if d.visibility == "public" and public_delegates == "anonymize":
            d.owner_id = None
            d.credit = "anonymous"
            if d.drawing_image_id:
                img = db.session.get(Image, d.drawing_image_id)
                if img:
                    img.owner_id = None
        else:
            if d.drawing_image_id:
                db.session.execute(delete(Image).where(Image.id == d.drawing_image_id))
            db.session.delete(d)
    db.session.execute(delete(Image).where(Image.owner_id == m.id))
    round_ids = [r for (r,) in db.session.execute(select(Round.id).where(Round.member_id == m.id))]
    if round_ids:
        from models import Message
        msg_ids = [x for (x,) in db.session.execute(select(Message.id).where(Message.round_id.in_(round_ids)))]
        if msg_ids:
            db.session.execute(delete(Reaction).where(Reaction.message_id.in_(msg_ids)))
        db.session.execute(delete(Message).where(Message.round_id.in_(round_ids)))
        db.session.execute(delete(Round).where(Round.id.in_(round_ids)))
    for model in (FearMeter, HumanRound, Strength, Badge, Reaction, Tip):
        db.session.execute(delete(model).where(model.member_id == m.id))
    db.session.execute(update(TrainingExample).where(TrainingExample.suggested_by == m.id).values(suggested_by=None))
    db.session.execute(update(ChangeRequest).where(ChangeRequest.member_id == m.id).values(member_id=None, credit_name=None))
    db.session.delete(m)


@bp.delete("/api/me")
@member_required
def delete_me():
    m = current_member()
    choice = body().get("public_delegates", "anonymize")
    if choice not in ("delete", "anonymize"):
        choice = "anonymize"
    audit(None, "member_deleted_own_data", "member", None, {"public_delegates": choice})
    delete_member_data(m, choice)
    db.session.commit()
    log_out()
    return jsonify({"ok": True})
