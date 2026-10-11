"""Nightmare delegates: bring a drawing to life, save it, the Wall, and the delegate page."""
import hashlib
import json
import random
from datetime import timedelta

from flask import Blueprint, Response, jsonify, request, session
from pydantic import ValidationError
from sqlalchemy import delete, select

from ai import persona as P
from ai.client import AIError
from extensions import db, limiter
from logic import counters, data, settings
from logic.security import (ImageRejected, can_delete_delegate, can_edit_delegate, can_view_delegate, clean_text,
                            contains_blocked, current_member, guest_id, member_required, process_image,
                            requester_key)
from models import (ChangeRequest, Delegate, DelegateVersion, FearMeter, Image, Member, Report, Tip,
                    TrainingExample)
from models.base import utcnow
from routes.api_auth import clean_answers, comfort_for, comfort_from_answers
from routes.helpers import ai, ai_error_response, as_int, audit, body, error
from routes.limits import ai_access_denied, ai_limit

bp = Blueprint("delegates", __name__)

UNSAFE_MSG_KEY = "error.unsafe"
SOURCES = ("photo", "canvas", "blank", "description")


# ------------------------------------------------------------------ helpers

def image_url(image_id, thumb=False):
    if not image_id:
        return None
    return f"/api/images/{image_id}" + ("?thumb=1" if thumb else "")


def credit_name(d):
    if d.source == "seed":
        return "Example"
    if d.credit == "name" and d.owner_id:
        owner = db.session.get(Member, d.owner_id)
        if owner:
            return owner.display_name
    return "Anonymous"


def _rotation(delegate_id):
    h = int(hashlib.md5(delegate_id.encode()).hexdigest()[:4], 16)
    return round((h % 400) / 100 - 2, 2)  # -2.00 .. 1.99 degrees


def card_json(d, fear=None):
    persona = d.persona or {}
    tactics = sorted(persona.get("tactics", []), key=lambda t: -t.get("intensity", 0))
    return {
        "id": d.id,
        "name": d.name,
        "nickname": persona.get("nickname", ""),
        "difficulty": persona.get("base_difficulty", 2),
        "tags": [data.label(t["id"]) for t in tactics[:2]],
        "credit": credit_name(d),
        "image_url": image_url(d.drawing_image_id, thumb=True),
        "alt_text": persona.get("alt_text", d.name),
        "is_example": d.source == "seed",
        "opens_blank": bool(persona.get("opens_blank")),
        "source": d.source,
        "rotation": _rotation(d.id),
        "look": persona.get("look", {}),
        "befriended": bool(fear and fear.befriended_at),
        "tried": fear is not None,
    }


def _blocked_persona(persona, story=""):
    texts = [persona.get("name"), persona.get("nickname"), persona.get("one_liner"), story,
             persona.get("weakness", {}).get("description")] + list(persona.get("catchphrases", []))
    texts += [c.get("saw", "") + " " + c.get("means", "") for c in persona.get("clues", [])]
    texts += list(persona.get("training", {}).get("rules", []))
    return contains_blocked(*texts)


def _cleanup_temp_images():
    cutoff = utcnow() - timedelta(hours=24)
    db.session.execute(delete(Image).where(Image.kind == "temp", Image.created_at < cutoff))


def _store_answers(answers):
    m = current_member()
    if m:
        m.answers = answers
        m.comfort = comfort_from_answers(answers, comfort_for(m))
    else:
        session["guest_answers"] = answers
        session["guest_comfort"] = comfort_from_answers(answers, session.get("guest_comfort", {}))


def _parse_answers():
    raw = request.form.get("answers") if request.form else None
    if raw is None:
        raw = body().get("answers")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except ValueError:
            raw = {}
    return clean_answers(raw)


def _draft_response(persona, safety, temp_image_id):
    status = safety.get("status", "ok")
    if status == "not_a_drawing":
        return jsonify({"ok": False, "safety": {"status": status},
                        "message": settings.copy_text("error.not_a_drawing")})
    if status == "unsafe":
        return jsonify({"ok": False, "safety": {"status": status}, "message": settings.copy_text(UNSAFE_MSG_KEY)})
    if _blocked_persona(persona):
        return jsonify({"ok": False, "safety": {"status": "unsafe"}, "message": settings.copy_text(UNSAFE_MSG_KEY)})
    note = settings.copy_text("error.real_person") if safety.get("renamed_from_real_person") else None
    return jsonify({"ok": True, "draft": persona,
                    "safety": {"status": "ok", "renamed_from_real_person": bool(safety.get("renamed_from_real_person"))},
                    "note": note, "temp_image_id": temp_image_id, "image_url": image_url(temp_image_id)})


def _own_temp_image(image_id):
    """A temp image this person uploaded (members, or the guest who just joined)."""
    if not image_id:
        return None
    img = db.session.get(Image, str(image_id))
    if img is None or img.kind != "temp":
        return None
    m = current_member()
    if m and img.owner_id == m.id:
        return img
    if img.guest_id and img.guest_id == session.get("guest_id"):
        return img
    return None


# ------------------------------------------------------------------ bring it to life

@bp.post("/api/delegates/draft-from-image")
@ai_limit
@limiter.limit("10 per day", key_func=lambda: "photo:" + requester_key())
def draft_from_image():
    denied = ai_access_denied()
    if denied:
        return denied
    f = request.files.get("image")
    if f is None:
        return error("no_image", "We didn't get a photo. Try again?")
    try:
        processed = process_image(f.read())
    except ImageRejected as e:
        return error(e.code, e.message)
    answers = _parse_answers()
    _store_answers(answers)
    m = current_member()
    img = Image(owner_id=m.id if m else None, guest_id=None if m else guest_id(), kind="temp",
                mime=processed["mime"], data=processed["data"], thumb=processed["thumb"],
                width=processed["width"], height=processed["height"])
    db.session.add(img)
    _cleanup_temp_images()
    db.session.commit()  # save before the slow AI call (never hold the database during it)
    try:
        persona, safety, _ = ai().persona_from_image(processed["data"], answers)
    except AIError as e:
        return ai_error_response(e, temp_image_id=img.id, fallback="describe",
                                 fallback_message=settings.copy_text("error.vision_fallback"))
    if safety.get("status") in ("not_a_drawing", "unsafe") or _blocked_persona(persona):
        db.session.delete(img)  # unsafe or not-a-drawing photos are never kept
    db.session.commit()
    return _draft_response(persona, safety, img.id)


@bp.post("/api/delegates/draft-from-text")
@ai_limit
def draft_from_text():
    denied = ai_access_denied()
    if denied:
        return denied
    data_ = body()
    description = clean_text(data_.get("description"), 200, single_line=True)
    if len(description) < 3:
        return error("too_short", "Tell me a little about it — one sentence is perfect.")
    answers = clean_answers(data_.get("answers"))
    _store_answers(answers)
    temp = _own_temp_image(data_.get("temp_image_id"))
    db.session.commit()
    if contains_blocked(description):
        return jsonify({"ok": False, "safety": {"status": "unsafe"}, "message": settings.copy_text(UNSAFE_MSG_KEY)})
    try:
        persona, safety, _ = ai().persona_from_text(description, answers)
    except AIError as e:
        return ai_error_response(e)
    if safety.get("status") == "not_a_drawing":
        safety["status"] = "ok"  # a description can't be "not a drawing"
    return _draft_response(persona, safety, temp.id if temp else None)


@bp.post("/api/delegates/revise-draft")
@ai_limit
def revise_draft():
    denied = ai_access_denied()
    if denied:
        return denied
    data_ = body()
    instruction = clean_text(data_.get("instruction"), 300, single_line=True)
    if len(instruction) < 2:
        return error("too_short", "Tell it what to change, like “interrupt less” or “make it stricter.”")
    try:
        old, _ = P.normalize_persona(data_.get("persona") or {})
    except (ValidationError, ValueError, TypeError):
        return error("bad_persona", "That nightmare card looks scrambled. Refresh and try again?")
    if contains_blocked(instruction):
        return jsonify({"ok": True, "summary": "Let's keep it kind. Try a different change?", "changes": [], "persona": old})
    try:
        out = ai().revise_persona(old, instruction)
    except AIError as e:
        return ai_error_response(e)
    db.session.commit()
    new = out["persona"]
    if _blocked_persona(new):
        return jsonify({"ok": True, "summary": "Let's keep it kind. Try a different change?", "changes": [], "persona": old})
    return jsonify({"ok": True, "summary": out["summary"], "changes": P.persona_diff(old, new, out["changes"]),
                    "persona": new})


# ------------------------------------------------------------------ save

@bp.post("/api/images/temp")
@member_required
@limiter.limit("30 per hour")
def upload_temp_image():
    """The Blank saves its rendered avatar as the 'drawing'."""
    f = request.files.get("image")
    if f is None:
        return error("no_image", "We didn't get the picture. Try again?")
    try:
        processed = process_image(f.read())
    except ImageRejected as e:
        return error(e.code, e.message)
    img = Image(owner_id=current_member().id, kind="temp", mime=processed["mime"], data=processed["data"],
                thumb=processed["thumb"], width=processed["width"], height=processed["height"])
    db.session.add(img)
    _cleanup_temp_images()
    db.session.commit()
    return jsonify({"ok": True, "temp_image_id": img.id, "image_url": image_url(img.id)})


@bp.post("/api/delegates")
@member_required
@limiter.limit("30 per hour")
def save_delegate():
    m = current_member()
    data_ = body()
    try:
        persona, _ = P.normalize_persona(data_.get("persona") or {})
    except (ValidationError, ValueError, TypeError):
        return error("bad_persona", "That nightmare card looks scrambled. Refresh and try again?")
    story = clean_text(data_.get("story"), 280)
    if _blocked_persona(persona, story):
        return error("unsafe", settings.copy_text(UNSAFE_MSG_KEY))
    visibility = "private" if data_.get("visibility") == "private" else "public"
    credit = "anonymous" if data_.get("credit") == "anonymous" else "name"
    source = data_.get("source") if data_.get("source") in SOURCES else "photo"
    img = _own_temp_image(data_.get("temp_image_id"))
    status = "active"
    if visibility == "public" and settings.get("wall_moderation") == "approval" and not m.is_editor:
        status = "pending"
    persona["training"] = {"rules": persona.get("training", {}).get("rules", []), "version": 1, "trained_count": 0}
    d = Delegate(owner_id=m.id, name=persona["name"], source=source, status=status, visibility=visibility,
                 credit=credit, story=story or None, persona=persona, version=1, pack="mun")
    if img is not None:
        img.kind = "drawing"
        img.owner_id = m.id
        img.guest_id = None
        d.drawing_image_id = img.id
    db.session.add(d)
    db.session.flush()
    db.session.add(DelegateVersion(delegate_id=d.id, version=1, persona=persona, summary="Born from the drawing",
                                   changed_by=m.id))
    counters.bump("delegates_created")
    db.session.commit()
    message = "An editor will check it before it goes on the Wall." if status == "pending" else None
    return jsonify({"ok": True, "id": d.id, "status": status, "message": message, "url": f"/d/{d.id}"})


# ------------------------------------------------------------------ the Wall

@bp.get("/api/delegates")
def wall():
    m = current_member()
    args = request.args
    rows = db.session.execute(select(Delegate).where(Delegate.visibility == "public", Delegate.status == "active")
                              ).scalars().all()
    fears = {}
    if m:
        fears = {f.delegate_id: f for f in db.session.execute(
            select(FearMeter).where(FearMeter.member_id == m.id)).scalars()}
    difficulties = {int(x) for x in args.get("difficulty", "").split(",") if x.strip().isdigit()}
    traits = {t for t in args.get("traits", "").split(",") if t.strip()}
    source = args.get("source", "")
    q = clean_text(args.get("q"), 60).lower()
    out = []
    for d in rows:
        p = d.persona or {}
        if difficulties and p.get("base_difficulty") not in difficulties:
            continue
        if traits:
            have = {t["id"] for t in p.get("tactics", [])} | set(p.get("temperament", [])) | set(p.get("quirks", []))
            if not traits <= have:
                continue
        if source == "drawing" and d.source not in ("photo", "canvas", "description"):
            continue
        if source == "built" and d.source != "blank":
            continue
        if source == "example" and d.source != "seed":
            continue
        if m and args.get("not_tried") in ("1", "true") and d.id in fears:
            continue
        if m and args.get("befriended") in ("1", "true") and not (d.id in fears and fears[d.id].befriended_at):
            continue
        if q:
            hay = " ".join([d.name, p.get("nickname", ""), p.get("one_liner", "")] +
                           [data.label(t["id"]) for t in p.get("tactics", [])] +
                           [data.label(t) for t in p.get("temperament", []) + p.get("quirks", [])]).lower()
            if q not in hay:
                continue
        out.append(d)
    # Sorting: Random (default) or Newest. There is no "most popular" on purpose.
    if args.get("sort") == "new":
        out.sort(key=lambda d: d.created_at, reverse=True)
    else:
        seed = args.get("seed") or str(random.random())
        out.sort(key=lambda d: d.id)
        random.Random(seed).shuffle(out)
    per_page = as_int(args.get("limit"), 24, 1, 60)
    page = as_int(args.get("page"), 1, 1)
    total = len(out)
    pages = max(1, (total + per_page - 1) // per_page)
    chunk = out[(page - 1) * per_page: page * per_page]
    return jsonify({"items": [card_json(d, fears.get(d.id)) for d in chunk], "page": page, "pages": pages,
                    "total": total, "empty_message": settings.copy_text("wall.empty")})


@bp.get("/api/traits")
def traits_list():
    """The trait library for editors and The Blank."""
    t = data.traits()
    return jsonify({"by_category": t["by_category"], "look_by_slot": t["look_by_slot"],
                    "voices": data.tts_voices()})


# ------------------------------------------------------------------ one delegate

def _get_visible(delegate_id):
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_view_delegate(d):
        return None
    return d


def delegate_json(d):
    m = current_member()
    fear = db.session.get(FearMeter, (m.id, d.id)) if m else None
    tips = db.session.execute(select(Tip).where(Tip.delegate_id == d.id, Tip.status == "visible")
                              .order_by(Tip.created_at.desc()).limit(30)).scalars().all()
    out = card_json(d, fear)
    out.update({
        "persona": d.persona,
        "story": d.story,
        "version": d.version,
        "trained_count": (d.persona or {}).get("training", {}).get("trained_count", 0),
        "image_url": image_url(d.drawing_image_id),
        "thumb_url": image_url(d.drawing_image_id, thumb=True),
        "visibility": d.visibility,
        "status": d.status,
        "credit_choice": d.credit,
        "is_owner": bool(m and d.owner_id == m.id),
        "can_edit": can_edit_delegate(d, m),
        "can_delete": can_delete_delegate(d, m),
        "times_practiced": d.times_practiced,
        "fear": {"value": fear.value if fear else 100, "befriended": bool(fear and fear.befriended_at)} if m else None,
        "tips": [{"text": t.text, "credit": "Anonymous" if t.credit == "anonymous" or not t.member_id else
                  (db.session.get(Member, t.member_id).display_name if db.session.get(Member, t.member_id) else "Anonymous")}
                 for t in tips],
    })
    if m and (d.owner_id == m.id or m.is_editor):
        sugg = db.session.execute(select(ChangeRequest).where(ChangeRequest.delegate_id == d.id)
                                  .order_by(ChangeRequest.created_at.desc()).limit(20)).scalars().all()
        out["suggestions"] = [{"what": s.what_happened, "should": s.what_should_happen, "from": s.credit_name or "Anonymous",
                               "date": s.created_at.date().isoformat()} for s in sugg]
        out["pending_examples"] = len(db.session.execute(select(TrainingExample.id).where(
            TrainingExample.delegate_id == d.id, TrainingExample.status == "pending")).all())
    return out


@bp.get("/api/delegates/<delegate_id>")
def get_delegate(delegate_id):
    d = _get_visible(delegate_id)
    if d is None:
        return error("not_found", "We couldn't find that nightmare. Maybe it's private, or it was removed.", 404)
    return jsonify(delegate_json(d))


@bp.patch("/api/delegates/<delegate_id>")
@member_required
def edit_delegate(delegate_id):
    m = current_member()
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_edit_delegate(d, m):
        return error("forbidden", "Only the owner or an editor can change this nightmare.", 403)
    data_ = body()
    story = clean_text(data_["story"], 280) if "story" in data_ else d.story
    changed_persona = False
    if "persona" in data_:
        try:
            new, _ = P.normalize_persona(data_["persona"], keep_training=(d.persona or {}).get("training"))
        except (ValidationError, ValueError, TypeError):
            return error("bad_persona", "That nightmare card looks scrambled. Refresh and try again?")
        if d.persona.get("opens_blank"):
            new["opens_blank"] = True
        if _blocked_persona(new, story or ""):
            return error("unsafe", settings.copy_text(UNSAFE_MSG_KEY))
        if new != d.persona:
            changed_persona = True
            d.version += 1
            new["training"]["version"] = d.version
            d.persona = new
            d.name = new["name"]
            summary = clean_text(data_.get("summary"), 120, single_line=True) or "Edited"
            db.session.add(DelegateVersion(delegate_id=d.id, version=d.version, persona=new, summary=summary,
                                           changed_by=m.id))
    elif story and contains_blocked(story):
        return error("unsafe", settings.copy_text(UNSAFE_MSG_KEY))
    d.story = story or None
    if data_.get("visibility") in ("public", "private"):
        d.visibility = data_["visibility"]
        if (d.visibility == "public" and d.status == "active" and settings.get("wall_moderation") == "approval"
                and not m.is_editor and d.owner_id == m.id and changed_persona):
            d.status = "pending"
    if data_.get("credit") in ("name", "anonymous"):
        d.credit = data_["credit"]
    if d.owner_id != m.id:
        audit(m, "edited_delegate", "delegate", d.id, {"version": d.version})
    db.session.commit()
    return jsonify({"ok": True, "delegate": delegate_json(d)})


@bp.delete("/api/delegates/<delegate_id>")
@member_required
def delete_delegate(delegate_id):
    m = current_member()
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_delete_delegate(d, m):
        return error("forbidden", "Only the owner or a maintainer can delete this nightmare.", 403)
    if d.owner_id != m.id:
        audit(m, "deleted_delegate", "delegate", d.id, {"name": d.name})
    image_id = d.drawing_image_id
    db.session.delete(d)
    db.session.flush()
    if image_id:
        db.session.execute(delete(Image).where(Image.id == image_id))
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/api/delegates/<delegate_id>/versions")
@member_required
def versions(delegate_id):
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_edit_delegate(d):
        return error("forbidden", "Only the owner or an editor can see versions.", 403)
    rows = db.session.execute(select(DelegateVersion).where(DelegateVersion.delegate_id == d.id)
                              .order_by(DelegateVersion.version.desc())).scalars().all()
    names = {}
    for r in rows:
        if r.changed_by and r.changed_by not in names:
            who = db.session.get(Member, r.changed_by)
            names[r.changed_by] = who.display_name if who else "someone"
    return jsonify({"versions": [{"version": r.version, "summary": r.summary, "by": names.get(r.changed_by, "the club"),
                                  "date": r.created_at.isoformat()} for r in rows]})


@bp.post("/api/delegates/<delegate_id>/restore")
@member_required
def restore(delegate_id):
    m = current_member()
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_edit_delegate(d, m):
        return error("forbidden", "Only the owner or an editor can restore versions.", 403)
    v = as_int(body().get("version"), 0)
    row = db.session.execute(select(DelegateVersion).where(DelegateVersion.delegate_id == d.id,
                                                           DelegateVersion.version == v)).scalars().first()
    if row is None:
        return error("not_found", "That version doesn't exist.", 404)
    d.version += 1
    persona = json.loads(json.dumps(row.persona))
    persona.setdefault("training", {})["version"] = d.version
    d.persona = persona
    d.name = persona.get("name", d.name)
    db.session.add(DelegateVersion(delegate_id=d.id, version=d.version, persona=persona,
                                   summary=f"Restored v{v}", changed_by=m.id))
    db.session.commit()
    return jsonify({"ok": True, "version": d.version})


@bp.post("/api/delegates/<delegate_id>/report")
@limiter.limit("20 per day", key_func=lambda: "report:" + requester_key())
def report(delegate_id):
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_view_delegate(d):
        return error("not_found", "We couldn't find that nightmare.", 404)
    reason = clean_text(body().get("reason"), 300, single_line=True)
    db.session.add(Report(target_type="delegate", target_id=d.id, reporter_key=requester_key(), reason=reason))
    if d.status == "active" and d.visibility == "public":
        d.status = "flagged"  # hidden from the Wall until an editor looks at it
    db.session.commit()
    return jsonify({"ok": True, "message": "Thanks for telling us. An editor will take a look."})


@bp.post("/api/delegates/<delegate_id>/examples")
@member_required
def add_example(delegate_id):
    m = current_member()
    d = _get_visible(delegate_id)
    if d is None:
        return error("not_found", "We couldn't find that nightmare.", 404)
    data_ = body()
    student_text = clean_text(data_.get("student_text"), 600)
    ideal = clean_text(data_.get("ideal_reply"), 400)
    if not student_text or not ideal:
        return error("missing", "Add what the student said and what the nightmare should say back.")
    if contains_blocked(student_text, ideal):
        return error("unsafe", settings.copy_text(UNSAFE_MSG_KEY))
    direct = can_edit_delegate(d, m)
    ex = TrainingExample(delegate_id=d.id, student_text=student_text, ideal_reply=ideal,
                         source="manual" if direct else "thumbs_down", suggested_by=m.id,
                         status="approved" if direct else "pending", message_id=data_.get("message_id"))
    db.session.add(ex)
    db.session.commit()
    return jsonify({"ok": True, "status": ex.status})


@bp.get("/api/delegates/<delegate_id>/export.jsonl")
@member_required
def export_jsonl(delegate_id):
    d = db.session.get(Delegate, delegate_id)
    if d is None or not can_edit_delegate(d):
        return error("forbidden", "Only the owner or an editor can export training data.", 403)
    rows = db.session.execute(select(TrainingExample).where(TrainingExample.delegate_id == d.id,
                                                            TrainingExample.status == "approved")).scalars().all()
    ctx = {"format": "rebuttal_duel", "committee": "a committee", "topic": "the topic",
           "my_country": "the student's country", "their_country": "your country"}
    system = P.turn_system_prompt(d.persona, ctx, d.persona.get("base_difficulty", 3), [], False)
    lines = [json.dumps({"messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": r.student_text},
                                      {"role": "assistant", "content": r.ideal_reply}]}, ensure_ascii=False)
             for r in rows]
    resp = Response("\n".join(lines) + ("\n" if lines else ""), mimetype="application/jsonl")
    resp.headers["Content-Disposition"] = f'attachment; filename="nightmare-{d.id[:8]}-training.jsonl"'
    return resp


# ------------------------------------------------------------------ images

@bp.get("/api/images/<image_id>")
def get_image(image_id):
    img = db.session.get(Image, image_id)
    if img is None:
        return error("not_found", "Image not found.", 404)
    m = current_member()
    allowed = False
    if img.kind == "seed":
        allowed = True
    elif img.kind == "temp":
        allowed = bool((m and img.owner_id == m.id) or (img.guest_id and img.guest_id == session.get("guest_id")))
    else:
        users = db.session.execute(select(Delegate).where(
            (Delegate.drawing_image_id == img.id) | (Delegate.portrait_image_id == img.id))).scalars().all()
        allowed = any(can_view_delegate(d, m) for d in users) or bool(m and img.owner_id == m.id)
    if not allowed:
        return error("not_found", "Image not found.", 404)
    use_thumb = request.args.get("thumb") in ("1", "true") and img.thumb
    resp = Response(img.thumb if use_thumb else img.data, mimetype=img.mime)
    if img.kind == "temp":
        resp.headers["Cache-Control"] = "no-store"
    else:
        resp.headers["Cache-Control"] = "private, max-age=86400"
    if img.mime == "image/svg+xml":
        resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    return resp
