"""Admin and maintainer dashboard APIs (BUILD_PROMPT.md section 6.18).

Roles: Member < Editor (moderate, edit delegates, site text, requests) < Maintainer (everything).
"""
import hmac
import re
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from extensions import db, limiter
from logic import counters, data, settings
from logic.schedule import DAY_KEYS
from logic.security import clean_text, current_member, editor_required, maintainer_required, member_required
from models import AuditLog, Delegate, Image, Member, Report, Tip
from routes.api_auth import delete_member_data
from routes.helpers import ai, as_bool, as_int, audit, body, error

bp = Blueprint("admin", __name__)
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _admin_key():
    m = current_member()
    return f"admin:{m.id if m else 'anon'}"


@bp.post("/api/admin/login")
@member_required
@limiter.limit("5 per 10 minutes", key_func=_admin_key)
def admin_login():
    cfg = current_app.config["APP_CONFIG"]
    passcode = str(body().get("passcode", ""))
    if not cfg.admin_passcode:
        return error("no_passcode", "The admin passcode isn't set yet. A maintainer must add ADMIN_PASSCODE to .env.", 403)
    if not hmac.compare_digest(passcode.encode(), cfg.admin_passcode.encode()):
        return error("bad_passcode", "That passcode didn't work.", 403)
    m = current_member()
    if m.role != "maintainer":
        m.role = "maintainer"
        audit(m, "became_maintainer_with_passcode", "member", m.id)
    db.session.commit()
    return jsonify({"ok": True, "role": m.role})


# ------------------------------------------------------------------ settings

def _validate_setting(key, v):
    """Returns (ok, cleaned_value_or_message)."""
    if key == "club_name":
        v = clean_text(v, 60, single_line=True)
        return (bool(v), v or "Give the club a name.")
    if key == "club_code":
        v = clean_text(v, 40, single_line=True)
        return (len(v) >= 4, v if len(v) >= 4 else "The club code needs at least 4 characters.")
    if key == "timezone":
        try:
            ZoneInfo(str(v))
            return True, str(v)
        except Exception:
            return False, "That isn't a time zone name (example: America/New_York)."
    if key == "meeting_schedule":
        if not isinstance(v, dict):
            return False, "Schedule is missing."
        days = [d for d in v.get("days", []) if d in DAY_KEYS]
        start, end = str(v.get("start", "")), str(v.get("end", ""))
        if not HHMM.match(start) or not HHMM.match(end) or start >= end:
            return False, "Use times like 15:00 and 16:30 (start before end)."
        return True, {"days": days, "start": start, "end": end}
    if key == "handoff_mode":
        return (v in ("strict", "gentle", "off"), v if v in ("strict", "gentle", "off") else "Pick strict, gentle, or off.")
    if key == "lock_minutes":
        return True, as_int(v, 10, 0, 60)
    if key == "home_cap":
        return True, as_int(v, 5, 0, 50)
    if key in ("handoff_text", "handoff_credit"):
        v = clean_text(v, 80, single_line=True)
        return (bool(v) or key == "handoff_credit", v or "Text can't be empty.")
    if key == "guest_ai":
        if not isinstance(v, dict):
            return False, "Guest AI setting is missing."
        return True, {"enabled": as_bool(v.get("enabled")), "daily_quota": as_int(v.get("daily_quota"), 15, 1, 100)}
    if key == "ai_daily_cap":
        return True, as_int(v, 1500, 0, 100000)
    if key == "wall_moderation":
        return (v in ("auto", "approval"), v if v in ("auto", "approval") else "Pick auto or approval.")
    if key == "features":
        if not isinstance(v, dict):
            return False, "Feature toggles are missing."
        known = settings.defaults()["features"]
        return True, {k: as_bool(v.get(k, known[k])) for k in known}
    if key == "credits":
        if not isinstance(v, list):
            return False, "Credits should be a list."
        return True, [clean_text(x, 80, single_line=True) for x in v[:100] if clean_text(x, 80)]
    return False, "Unknown setting."


@bp.get("/api/admin/settings")
@maintainer_required
def get_settings():
    out = {k: settings.get(k) for k in settings.EDITABLE_BY_MAINTAINER}
    return jsonify({"settings": out, "day_keys": DAY_KEYS})


@bp.patch("/api/admin/settings")
@maintainer_required
def patch_settings():
    m = current_member()
    d = body()
    changed, problems = [], {}
    for key, value in d.items():
        if key not in settings.EDITABLE_BY_MAINTAINER:
            continue
        ok, cleaned = _validate_setting(key, value)
        if not ok:
            problems[key] = cleaned
            continue
        if settings.get(key) != cleaned:
            settings.set(key, cleaned)
            changed.append(key)
    if problems:
        db.session.rollback()
        return error("invalid", "Some settings need fixing.", 400, problems=problems)
    if changed:
        audit(m, "changed_settings", "settings", None, {"keys": changed})
    db.session.commit()
    return jsonify({"ok": True, "changed": changed})


@bp.get("/api/admin/copy")
@editor_required
def get_copy():
    return jsonify({"defaults": data.copy_defaults(), "overrides": settings.get("copy_overrides")})


@bp.patch("/api/admin/copy")
@editor_required
def patch_copy():
    m = current_member()
    d = body()
    defaults = data.copy_defaults()
    overrides = settings.get("copy_overrides")
    changed = []
    for key, value in (d.get("overrides") or {}).items():
        if key not in defaults:
            continue
        text = clean_text(value, 400)
        if not text or text == defaults[key]:
            if key in overrides:
                overrides.pop(key)
                changed.append(key)
        elif overrides.get(key) != text:
            overrides[key] = text
            changed.append(key)
    settings.set("copy_overrides", overrides)
    if changed:
        audit(m, "edited_site_text", "copy", None, {"keys": changed[:50]})
    db.session.commit()
    return jsonify({"ok": True, "changed": changed})


@bp.get("/api/admin/committees")
@editor_required
def get_committees():
    return jsonify({"committees": settings.get("committees")})


@bp.patch("/api/admin/committees")
@editor_required
def patch_committees():
    m = current_member()
    raw = body().get("committees")
    if not isinstance(raw, list) or not raw:
        return error("invalid", "Keep at least one committee.")
    out, seen = [], set()
    for c in raw[:40]:
        name = clean_text((c or {}).get("name"), 80, single_line=True)
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        cid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30] or "committee"
        topics = []
        for t in (c.get("topics") or [])[:30]:
            t = clean_text(t, 120, single_line=True)
            if t and t not in topics:
                topics.append(t)
        out.append({"id": cid, "name": name, "topics": topics})
    if not out:
        return error("invalid", "Keep at least one committee.")
    settings.set("committees", out)
    audit(m, "edited_committees", "settings", None, {"count": len(out)})
    db.session.commit()
    return jsonify({"ok": True, "committees": out})


# ------------------------------------------------------------------ members

@bp.get("/api/admin/members")
@editor_required
def list_members():
    rows = db.session.execute(select(Member).order_by(Member.display_name)).scalars().all()
    return jsonify({"members": [{"id": x.id, "name": x.display_name, "role": x.role, "stage": x.stage,
                                 "joined": x.created_at.date().isoformat()} for x in rows]})


@bp.patch("/api/admin/members/<member_id>")
@editor_required
def patch_member(member_id):
    me = current_member()
    target = db.session.get(Member, member_id)
    if target is None:
        return error("not_found", "Member not found.", 404)
    d = body()
    if "role" in d:
        if not me.is_maintainer:
            return error("forbidden", "Only maintainers can change roles.", 403)
        if d["role"] not in ("member", "editor", "maintainer"):
            return error("invalid", "Pick member, editor, or maintainer.")
        if target.id == me.id and d["role"] != "maintainer":
            others = db.session.execute(select(Member.id).where(Member.role == "maintainer", Member.id != me.id)).first()
            if not others:
                return error("last_maintainer", "You're the only maintainer. Promote someone else first.")
        if target.role != d["role"]:
            audit(me, "changed_role", "member", target.id, {"from": target.role, "to": d["role"]})
            target.role = d["role"]
    if "pin" in d:
        pin = str(d["pin"]).strip()
        if not re.fullmatch(r"\d{4}", pin):
            return error("bad_pin", "A PIN is 4 numbers.")
        if target.is_maintainer and not me.is_maintainer:
            return error("forbidden", "Only maintainers can reset a maintainer's PIN.", 403)
        target.pin_hash = generate_password_hash(pin)
        audit(me, "reset_pin", "member", target.id)
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/api/admin/members/<member_id>")
@maintainer_required
def delete_member(member_id):
    me = current_member()
    target = db.session.get(Member, member_id)
    if target is None:
        return error("not_found", "Member not found.", 404)
    if target.id == me.id:
        return error("self", "Use My Journey > Delete my data to remove yourself.")
    audit(me, "deleted_member", "member", target.id)
    delete_member_data(target, body().get("public_delegates", "anonymize"))
    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ moderation

@bp.get("/api/admin/moderation")
@editor_required
def moderation_queue():
    delegates = db.session.execute(select(Delegate).where(Delegate.status.in_(["pending", "flagged", "hidden"]))
                                   .order_by(Delegate.updated_at.desc())).scalars().all()
    reports = db.session.execute(select(Report).where(Report.resolved.is_(False))).scalars().all()
    reasons = {}
    for r in reports:
        reasons.setdefault((r.target_type, r.target_id), []).append(r.reason or "(no reason given)")
    tips = db.session.execute(select(Tip).where(Tip.status.in_(["flagged", "hidden"]))).scalars().all()
    items = []
    for d in delegates:
        items.append({"type": "delegate", "id": d.id, "status": d.status, "name": d.name, "story": d.story,
                      "one_liner": (d.persona or {}).get("one_liner", ""),
                      "image_url": f"/api/images/{d.drawing_image_id}?thumb=1" if d.drawing_image_id else None,
                      "reports": reasons.get(("delegate", d.id), [])})
    for t in tips:
        items.append({"type": "tip", "id": t.id, "status": t.status, "name": "Tip", "story": t.text,
                      "reports": reasons.get(("tip", t.id), [])})
    return jsonify({"items": items})


@bp.patch("/api/admin/moderation/<kind>/<item_id>")
@editor_required
def moderate(kind, item_id):
    me = current_member()
    action = body().get("action")
    if action not in ("approve", "hide", "delete"):
        return error("invalid", "Pick approve, hide, or delete.")
    if kind == "delegate":
        item = db.session.get(Delegate, item_id)
        if item is None:
            return error("not_found", "Already gone.", 404)
        if action == "delete":
            image_id = item.drawing_image_id
            db.session.delete(item)
            db.session.flush()
            if image_id:
                img = db.session.get(Image, image_id)
                if img is not None and img.kind != "seed":
                    db.session.delete(img)
        else:
            item.status = "active" if action == "approve" else "hidden"
    elif kind == "tip":
        item = db.session.get(Tip, item_id)
        if item is None:
            return error("not_found", "Already gone.", 404)
        if action == "delete":
            db.session.delete(item)
        else:
            item.status = "visible" if action == "approve" else "hidden"
    else:
        return error("invalid", "Unknown item type.")
    for r in db.session.execute(select(Report).where(Report.target_type == kind, Report.target_id == item_id)).scalars():
        r.resolved = True
    audit(me, f"moderation_{action}", kind, item_id)
    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ AI status, usage, audit

@bp.get("/api/admin/ai-status")
@editor_required
def ai_status():
    status = ai().admin_status()
    status["calls_today_db"] = counters.get_count("ai_calls")
    status["cap"] = settings.get("ai_daily_cap")
    return jsonify(status)


@bp.post("/api/admin/ai-test/<feature>")
@maintainer_required
@limiter.limit("20 per hour")
def ai_test(feature):
    client = ai()
    if feature not in ("chat", "vision"):
        return jsonify({"ok": False, "feature": feature,
                        "message": "This feature is built in a later phase, so there's nothing to test yet."})
    if client.mock:
        return jsonify({"ok": True, "feature": feature, "status": "mock",
                        "message": "Demo mode: the AI is pretend, so this always works. Add real keys to .env to test for real."})
    client.probe((feature,))
    db.session.commit()
    st = client.feature_status(feature)
    return jsonify({"ok": st == "ok", "feature": feature, "status": st, "detail": client.admin_status()["rows"]})


@bp.get("/api/admin/usage")
@editor_required
def usage():
    return jsonify({"days": counters.daily_series(30)})


@bp.get("/api/admin/audit")
@maintainer_required
def audit_log():
    rows = db.session.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).scalars().all()
    names = {}
    for r in rows:
        if r.actor_id and r.actor_id not in names:
            who = db.session.get(Member, r.actor_id)
            names[r.actor_id] = who.display_name if who else "(deleted member)"
    return jsonify({"entries": [{"when": r.created_at.isoformat(), "who": names.get(r.actor_id, "system"),
                                 "action": r.action, "target_type": r.target_type, "target_id": r.target_id,
                                 "detail": r.detail} for r in rows]})


@bp.get("/api/admin/export")
@maintainer_required
def export_backup():
    from logic.backup import export_zip
    me = current_member()
    audit(me, "exported_backup")
    db.session.commit()
    blob, name = export_zip()
    resp = Response(blob, mimetype="application/zip")
    resp.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp
