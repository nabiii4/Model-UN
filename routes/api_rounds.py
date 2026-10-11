"""Practice rounds: start, take turns, hints, switch sides, end with feedback, and human rounds."""
import random

from flask import Blueprint, jsonify
from pydantic import ValidationError
from sqlalchemy import func, select

from ai import delivery
from ai import persona as P
from ai.client import AIError, finish_feedback
from ai import mock
from extensions import db
from logic import counters, data, fear, handoff, heat, journey, schedule, settings
from logic.care import CARE_MESSAGE, needs_care
from logic.security import (can_view_delegate, clean_text, contains_blocked, current_member, guest_id,
                            member_required)
from models import (Delegate, FearMeter, HumanRound, Member, Message, Reaction, Round, Strength,
                    TrainingExample)
from routes.api_auth import comfort_for
from routes.helpers import ai, ai_error_response, as_bool, as_int, body, error
from routes.limits import ai_access_denied, ai_limit

bp = Blueprint("rounds", __name__)

PHASE1_FORMATS = ("rebuttal_duel", "opening_speech", "points_of_information", "moderated_caucus")
TIMED_SECONDS = 240


# ------------------------------------------------------------------ helpers

def _owner_ok(r):
    m = current_member()
    if m is not None:
        return r.member_id == m.id
    return r.member_id is None and r.guest_id and r.guest_id == guest_id(create=False)


def _get_round(round_id):
    r = db.session.get(Round, round_id)
    if r is None or not _owner_ok(r):
        return None
    return r


def _messages(r):
    return db.session.execute(select(Message).where(Message.round_id == r.id).order_by(Message.seq)).scalars().all()


def _add_message(r, role, text, meta=None):
    seq = (db.session.execute(select(func.max(Message.seq)).where(Message.round_id == r.id)).scalar() or 0) + 1
    msg = Message(round_id=r.id, seq=seq, role=role, text=text, meta=meta or {})
    db.session.add(msg)
    db.session.flush()
    return msg


def total_exchanges(fmt, length):
    if fmt.get("exchanges"):
        return fmt["exchanges"]
    if length == "timed":
        return 12
    return 3 if length == "quick" else 5


def _committee_names():
    return [c["name"] for c in settings.get("committees")]


def _ctx(r):
    s = r.settings
    return {"format": s["format"], "committee": s["committee"], "topic": s["topic"], "my_country": s["my_country"],
            "their_country": s["their_country"], "caucus_subtopic": (r.opening or {}).get("caucus_subtopic"),
            "seed": r.id}


def _delegate_info(r):
    p = r.persona_snapshot or {}
    d = db.session.get(Delegate, r.delegate_id) if r.delegate_id else None
    return {"id": r.delegate_id, "name": p.get("name"), "nickname": p.get("nickname"),
            "image_url": f"/api/images/{d.drawing_image_id}" if d and d.drawing_image_id else None,
            "alt_text": p.get("alt_text"), "look": p.get("look", {}), "quirks": p.get("quirks", []),
            "silence_seconds": p.get("silence_seconds", 0), "interrupt_level": p.get("interrupt_level", 0),
            "base_difficulty": p.get("base_difficulty", 2), "one_liner": p.get("one_liner", "")}


def round_json(r):
    msgs = _messages(r)
    s = r.settings
    elapsed = int((schedule.utc_now() - r.started_at).total_seconds())
    return {
        "id": r.id,
        "settings": s,
        "opening": {k: v for k, v in (r.opening or {}).items() if k != "bloc_must_haves"},
        "heat": r.heat,
        "heat_trace": r.heat_trace,
        "hints_left": max(0, 2 - r.hints_used),
        "switched_sides": r.switched_sides,
        "switch_pending": r.switch_pending,
        "exchanges": r.exchanges,
        "total_exchanges": s.get("total_exchanges", 3),
        "elapsed_seconds": elapsed,
        "completed": r.completed,
        "abandoned": r.abandoned,
        "ended": r.ended_at is not None,
        "paused": r.paused,
        "messages": [{"id": m.id, "role": m.role, "text": m.text, "meta": m.meta or {}} for m in msgs],
        "feedback": r.feedback,
        "fear_change": r.fear_change,
        "handoff": r.handoff,
        "delegate": _delegate_info(r),
        "comfort": comfort_for(current_member()),
    }


# ------------------------------------------------------------------ start

@bp.post("/api/rounds")
@ai_limit
def start_round():
    denied = ai_access_denied()
    if denied:
        return denied
    m = current_member()
    gid = None if m else guest_id()
    d_ = body()

    # Who are we debating?
    d = None
    if d_.get("delegate_id"):
        d = db.session.get(Delegate, str(d_["delegate_id"]))
        if d is None or not can_view_delegate(d, m):
            return error("not_found", "We couldn't find that nightmare. Pick another from the Wall?", 404)
        persona = d.persona
        if persona.get("opens_blank"):
            return error("use_blank", "The Blank is a builder. Build your nightmare first!", 400, url="/blank")
    elif d_.get("guest_persona") and m is None:
        try:
            persona, _ = P.normalize_persona(d_["guest_persona"])
        except (ValidationError, ValueError, TypeError):
            return error("bad_persona", "That nightmare looks scrambled. Try drawing it again?")
        if contains_blocked(persona["name"], persona.get("one_liner"), *persona.get("catchphrases", [])):
            return error("unsafe", settings.copy_text("error.unsafe"))
    else:
        return error("no_delegate", "Pick a nightmare to practice against first.")

    comfort = comfort_for(m)
    gentle = bool(comfort.get("gentle"))
    fmt_id = d_.get("format") if d_.get("format") in PHASE1_FORMATS else "rebuttal_duel"
    fmt = data.format_info(fmt_id)
    committees = _committee_names()
    committee = clean_text(d_.get("committee"), 80, single_line=True)
    if committee not in committees:
        committee = committees[0] if committees else "General Assembly"
    topic = clean_text(d_.get("topic"), 120, single_line=True) or "Plastic pollution"
    if contains_blocked(topic):
        return error("unsafe", "Let's pick a different topic.")
    countries = data.countries()
    my_country = d_.get("my_country") if d_.get("my_country") in countries else "Canada"
    their_country = d_.get("their_country")
    if their_country not in countries or their_country == my_country:
        their_country = random.choice([c for c in countries if c != my_country])
    mode = "type"  # Speak mode arrives in Phase 2
    difficulty = as_int(d_.get("difficulty"), persona.get("base_difficulty", 2), 1, 5)
    if gentle:
        difficulty = min(difficulty, 2)
    length = d_.get("length") if d_.get("length") in ("quick", "standard", "timed") else comfort.get("default_length", "quick")
    opts = d_.get("options") if isinstance(d_.get("options"), dict) else {}
    options = {"hints": as_bool(opts.get("hints", True)), "timer": as_bool(opts.get("timer", comfort.get("timers", True))),
               "breath": as_bool(opts.get("breath", False))}

    # The handoff lock is enforced here, on the server (section 8.9).
    now = schedule.utc_now()
    state = handoff.state_for(m, gid, now)
    lock_round, lock_until = handoff.active_lock(m.id if m else None, gid, now)
    allowed, is_overtime, lock_error = handoff.check_start(
        now=now, mode=state["mode"], meeting=state["meeting"], active_lock_until=lock_until,
        overtime_used=state["overtime_used"], overtime_requested=as_bool(d_.get("overtime")),
        overtime_status=handoff.overtime_status(m.id if m else None, now),
        overtime_confirmed=as_bool(d_.get("confirm_overtime")), home_cap=settings.get("home_cap"),
        ai_rounds_today=state["ai_rounds_today"])
    if not allowed:
        return jsonify(lock_error), 423

    ctx = {"format": fmt_id, "committee": committee, "topic": topic, "my_country": my_country,
           "their_country": their_country, "seed": f"{now.isoformat()}{persona.get('name')}"}
    try:
        opening = ai().round_opening(persona, ctx)
    except AIError as e:
        return ai_error_response(e)

    s = {"format": fmt_id, "format_name": fmt["name"], "committee": committee, "topic": topic,
         "my_country": my_country, "their_country": their_country, "mode": mode, "difficulty": difficulty,
         "length": length, "options": options, "gentle": gentle,
         "total_exchanges": total_exchanges(fmt, length), "turn_seconds": fmt["turn_seconds"],
         "target_words": fmt["target_words"], "word_limit": fmt.get("word_limit", 120), "timed_seconds": TIMED_SECONDS if length == "timed" else None,
         "who_starts": fmt["who_starts"], "streak": []}
    r = Round(member_id=m.id if m else None, guest_id=gid, delegate_id=d.id if d else None,
              delegate_version=d.version if d else 1, persona_snapshot=persona, settings=s, opening=opening,
              heat=difficulty, heat_trace=[difficulty], labels=[], is_overtime=is_overtime,
              is_home=not state["meeting"], started_at=now)
    db.session.add(r)
    db.session.flush()
    if opening.get("opening"):
        _add_message(r, "delegate", opening["opening"], {"expression": "skeptical", "eyebrows": -1, "opening": True})
    if m is not None:
        m.last_round_settings = {k: s[k] for k in ("format", "committee", "topic", "my_country", "their_country",
                                                    "mode", "difficulty", "length", "options")}
        m.last_round_settings["delegate_id"] = d.id if d else None
        if is_overtime:
            m.bot_slot_count = (m.bot_slot_count or 0) + 1
            m.last_bot_slot_at = now
    db.session.commit()
    return jsonify({"ok": True, "round_id": r.id, "url": f"/practice/{r.id}", "opening": opening.get("opening"),
                    "pois": opening.get("pois", []), "has_poi_audio": False, "is_overtime": is_overtime})


# ------------------------------------------------------------------ turns

@bp.get("/api/rounds/<round_id>")
def get_round(round_id):
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    return jsonify(round_json(r))


@bp.post("/api/rounds/<round_id>/turn")
@ai_limit
def take_turn(round_id):
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    if r.ended_at is not None:
        return error("round_over", "This round is already over.", 409)
    d_ = body()
    expected = d_.get("expected_exchange")
    if expected is not None and as_int(expected, -1) != r.exchanges:
        return error("already_answered", "That answer was already sent.", 409, round=round_json(r))
    text = clean_text(d_.get("text"), 2000)
    if not delivery.words(text):
        return error("empty", "Type your answer first — even one sentence is great.")
    s = r.settings
    if s.get("total_exchanges") and r.exchanges >= s["total_exchanges"]:
        return error("round_over", "That was the last exchange. Let's see your feedback!", 409)
    speaking_seconds = as_int(d_.get("speaking_seconds"), 0, 0, 600)
    poi = d_.get("poi") if isinstance(d_.get("poi"), dict) else None
    time_up = as_bool(d_.get("time_up")) and not s.get("gentle")
    switched = bool(r.switch_pending)

    # Safety net: a student in real distress gets a kind, out-of-character reply. No lock, no AI.
    if needs_care(text):
        _add_message(r, "student", text, {"words": delivery.word_count(text)})
        msg = _add_message(r, "delegate", CARE_MESSAGE, {"expression": "neutral", "eyebrows": 0, "break_character": True})
        r.paused = True
        db.session.commit()
        return jsonify({"ok": True, "message_id": msg.id, "reply": CARE_MESSAGE, "expression": "neutral", "eyebrows": 0,
                        "break_character": True, "heat": r.heat, "heat_change": 0, "exchange": r.exchanges,
                        "total_exchanges": s.get("total_exchanges"), "done": False})

    history = [{"role": m.role, "text": m.text} for m in _messages(r)]
    examples = []
    if r.delegate_id:
        rows = db.session.execute(select(TrainingExample).where(
            TrainingExample.delegate_id == r.delegate_id, TrainingExample.status == "approved")
            .order_by(TrainingExample.updated_at.desc()).limit(6)).scalars().all()
        examples = [{"student_text": e.student_text, "ideal_reply": e.ideal_reply} for e in reversed(rows)]
    turn_index = sum(1 for m in history if m["role"] == "student")
    turn_info = {"used": speaking_seconds or as_int(d_.get("seconds_used"), 0, 0, 3600),
                 "limit": s.get("turn_seconds", 60), "mode": s.get("mode", "type"), "poi": poi,
                 "listening": clean_text(d_.get("listening_label"), 20) or None}
    try:
        reply = ai().debate_turn(r.persona_snapshot, _ctx(r), history, text, heat=r.heat, turn_index=turn_index,
                                 examples=examples, switched=switched, turn_info=turn_info, time_up=time_up)
    except AIError as e:
        return ai_error_response(e, keep_text=True)

    # Heat (section 8.2): label this turn, then maybe move the thermostat.
    words = delivery.word_count(text)
    fillers_pm = delivery.fillers_per_minute(text, speaking_seconds) if s.get("mode") == "speak" and speaking_seconds else None
    label = heat.label_turn(dodged=reply["student_dodged"], used_evidence=reply["student_used_evidence"],
                            words=words, target_words=s.get("target_words", 120), mode=s.get("mode", "type"),
                            fillers_per_min=fillers_pm, hint_used=bool(r.hint_pending))
    streak = list(s.get("streak", [])) + [label]
    old_heat = r.heat
    new_heat, fired = heat.next_heat(old_heat, streak, reply["suggest_heat"], s["difficulty"], gentle=bool(s.get("gentle")))
    if fired:
        streak = []

    student = _add_message(r, "student", text, {"words": words, "label": label, "switched": switched, "poi": poi,
                                                 "speaking_seconds": speaking_seconds or None})
    delegate_msg = _add_message(r, "delegate", reply["reply"], {
        "expression": reply["expression"], "eyebrows": reply["eyebrows"], "tactic_used": reply["tactic_used"],
        "dodged": reply["student_dodged"], "evidence": reply["student_used_evidence"],
        "break_character": reply["break_character"], "heat": new_heat})
    if switched:
        _add_message(r, "system", "Back to your own side.", {"divider": True})
        r.switch_pending = False
    r.heat = new_heat
    r.heat_trace = list(r.heat_trace or []) + [new_heat]
    r.labels = list(r.labels or []) + [label]
    r.hint_pending = False
    r.exchanges += 1
    if reply["break_character"]:
        r.paused = True
    s = dict(s)
    s["streak"] = streak
    r.settings = s
    elapsed = (schedule.utc_now() - r.started_at).total_seconds()
    done = r.exchanges >= s.get("total_exchanges", 3) or (s.get("length") == "timed" and elapsed >= TIMED_SECONDS)
    db.session.commit()
    change = new_heat - old_heat
    silence = 0
    comfort = comfort_for(current_member())
    if comfort.get("dramatic_silence", True) and "never_blinks" in r.persona_snapshot.get("quirks", []):
        silence = r.persona_snapshot.get("silence_seconds", 0)
    elif comfort.get("dramatic_silence", True):
        silence = min(2, r.persona_snapshot.get("silence_seconds", 0))
    return jsonify({
        "ok": True, "message_id": delegate_msg.id, "student_message_id": student.id,
        "reply": reply["reply"], "expression": reply["expression"], "eyebrows": reply["eyebrows"],
        "tactic_used": reply["tactic_used"], "break_character": reply["break_character"],
        "heat": new_heat, "heat_change": change,
        "toast": settings.copy_text("round.heat_up") if change > 0 else settings.copy_text("round.heat_down") if change < 0 else None,
        "label": label, "exchange": r.exchanges, "total_exchanges": s.get("total_exchanges"), "done": done,
        "switched_back": switched, "silence_seconds": silence,
    })


@bp.post("/api/rounds/<round_id>/hint")
@ai_limit
def get_hint(round_id):
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    if r.ended_at is not None:
        return error("round_over", "This round is already over.", 409)
    if r.hints_used >= 2:
        return error("no_hints", "You've used both hints this round. You've got this!", 409, hints_left=0)
    last = next((m.text for m in reversed(_messages(r)) if m.role == "delegate"), "")
    try:
        h = ai().hint(_ctx(r), last)
    except AIError as e:
        return ai_error_response(e)
    r.hints_used += 1
    r.hint_pending = True
    db.session.commit()
    return jsonify({"ok": True, "idea": h["idea"], "ask_back": h["ask_back"], "hints_left": max(0, 2 - r.hints_used)})


@bp.post("/api/rounds/<round_id>/switch-sides")
def switch_sides(round_id):
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    if r.ended_at is not None:
        return error("round_over", "This round is already over.", 409)
    if not r.switch_pending:
        r.switch_pending = True
        r.switched_sides = True
        s = r.settings
        _add_message(r, "system", f"Switched sides: for the next exchange you argue for {s['their_country']}, "
                                  f"and they argue for {s['my_country']}.", {"divider": True})
        db.session.commit()
    return jsonify({"ok": True, "switch_pending": True,
                    "message": f"For the next exchange, you're the delegate of {r.settings['their_country']}."})


@bp.post("/api/rounds/<round_id>/resume")
def resume(round_id):
    """'Keep going' after a break-character pause."""
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    r.paused = False
    db.session.commit()
    return jsonify({"ok": True})


# ------------------------------------------------------------------ end

def _next_nightmares(m, exclude_id):
    """Suggest delegates whose tactics match the member's remaining 'what makes you nervous' answers."""
    nervous = set((m.answers or {}).get("nervous") or [])
    wanted = set()
    for n in nervous:
        key = mock.NERVOUS_TO_TEMPLATE.get(n)
        if key:
            wanted |= {t for t, _ in mock.TEMPLATES[key]["tactics"]}
    befriended = {f.delegate_id for f in db.session.execute(select(FearMeter).where(
        FearMeter.member_id == m.id, FearMeter.befriended_at.is_not(None))).scalars()}
    rows = db.session.execute(select(Delegate).where(Delegate.visibility == "public", Delegate.status == "active")).scalars().all()
    scored = []
    for d in rows:
        if d.id == exclude_id or d.id in befriended or d.persona.get("opens_blank"):
            continue
        overlap = len(wanted & {t["id"] for t in d.persona.get("tactics", [])})
        scored.append((overlap, random.random(), d))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"id": d.id, "name": d.name, "url": f"/practice/new?delegate={d.id}"} for _, _, d in scored[:3]]


@bp.post("/api/rounds/<round_id>/end")
@ai_limit
def end_round(round_id):
    r = _get_round(round_id)
    if r is None:
        return error("not_found", "We couldn't find that round.", 404)
    if r.ended_at is not None:
        return jsonify({"ok": True, "already": True, "abandoned": r.abandoned, "feedback": r.feedback,
                        "fear": r.fear_change, "handoff": r.handoff,
                        "url": f"/practice/{r.id}/feedback" if r.completed else "/"})
    d_ = body()
    # Messages that triggered the care note are private moments, not debate turns:
    # they never appear in feedback, and a care pause never triggers the handoff lock.
    msgs = [m for m in _messages(r) if not (m.role == "student" and needs_care(m.text))
            and not (m.meta or {}).get("break_character")]
    had_care = any((m.meta or {}).get("break_character") for m in _messages(r))
    student_turns = [m for m in msgs if m.role == "student"]
    now = schedule.utc_now()
    if as_bool(d_.get("abandon")) or not student_turns:
        # "Leave this round? It won't count." No lock, no stats.
        r.ended_at = now
        r.abandoned = True
        r.completed = False
        db.session.commit()
        return jsonify({"ok": True, "abandoned": True, "url": "/"})

    m = current_member()
    transcript = [{"role": x.role, "text": x.text} for x in msgs]
    delivery_stats = d_.get("delivery") if isinstance(d_.get("delivery"), dict) else None
    fallback = False
    try:
        fb = ai().feedback(r.persona_snapshot, _ctx(r), transcript, final_heat=r.heat, switched=r.switched_sides,
                           delivery_stats=delivery_stats)
    except AIError:
        # The coach is on break: give quick non-AI feedback so the round still counts.
        fb = finish_feedback(mock.feedback(r.persona_snapshot, _ctx(r), transcript, r.heat, r.switched_sides),
                             transcript, switched=r.switched_sides, listening_used=False)
        fallback = True
    fb["fallback"] = fallback

    d = db.session.get(Delegate, r.delegate_id) if r.delegate_id else None
    fear_change = None
    if d is not None:
        d.times_practiced = (d.times_practiced or 0) + 1
    if m is not None and d is not None:
        meter = db.session.get(FearMeter, (m.id, d.id))
        if meter is None:
            meter = FearMeter(member_id=m.id, delegate_id=d.id, value=100)
            db.session.add(meter)
        before = meter.value if meter.value is not None else 100
        after, _ = fear.fear_after_round(before, final_heat=r.heat,
                                         base_difficulty=r.persona_snapshot.get("base_difficulty", 2),
                                         mode=r.settings.get("mode", "type"))
        meter.value = after
        newly = after == 0 and meter.befriended_at is None
        if newly:
            meter.befriended_at = now
            d.befriended_count = (d.befriended_count or 0) + 1
            counters.bump("befriended")
        fear_change = {"name": d.name, "before": before, "after": after, "befriended": after == 0,
                       "newly_befriended": newly,
                       "message": settings.copy_text("befriended", name=d.name) if newly else None,
                       "next_nightmares": _next_nightmares(m, d.id) if after == 0 else []}
    if m is not None:
        m.stage = journey.advance_stage(m.stage, "spoken_round" if r.settings.get("mode") == "speak" else "typed_round")
        today = schedule.local_today(now, settings.get("timezone"))
        if m.last_active_date != today:
            m.show_up_days = (m.show_up_days or 0) + 1
            m.last_active_date = today
        handoff.count_completed_round(m, now)
        db.session.add(Strength(member_id=m.id, round_id=r.id, text=fb["strength_quote"]))
    counters.bump("rounds")

    state = handoff.state_for(m, None if m else r.guest_id, now)
    _, existing_lock = handoff.active_lock(m.id if m else None, None if m else r.guest_id, now)
    ho = handoff.compute_handoff(now=now, mode=state["mode"], meeting=state["meeting"],
                                 lock_minutes=as_int(settings.get("lock_minutes"), 10, 0, 120),
                                 home_cap=settings.get("home_cap"),
                                 ai_rounds_today=handoff.ai_rounds_today(m, None if m else r.guest_id, now) + (0 if m else 1),
                                 is_overtime=r.is_overtime, existing_lock_until=existing_lock,
                                 overtime_status=handoff.overtime_status(m.id if m else None, now))
    if had_care:
        ho = dict(ho, lock_until=None, overtime_available=False, reason="care")
    r.ended_at = now
    r.completed = True
    r.feedback = fb
    r.delivery = delivery_stats
    r.fear_change = fear_change
    r.handoff = ho
    r.paused = False
    db.session.commit()
    return jsonify({"ok": True, "feedback": fb, "fear": fear_change, "handoff": ho,
                    "url": f"/practice/{r.id}/feedback"})


# ------------------------------------------------------------------ reactions and human rounds

@bp.post("/api/messages/<message_id>/react")
@member_required
def react(message_id):
    m = current_member()
    msg = db.session.get(Message, message_id)
    if msg is None or msg.role != "delegate":
        return error("not_found", "We couldn't find that message.", 404)
    r = db.session.get(Round, msg.round_id)
    if r is None or r.member_id != m.id:
        return error("not_found", "We couldn't find that message.", 404)
    d_ = body()
    kind = d_.get("kind")
    if kind not in ("up", "down", "laugh"):
        return error("bad_kind", "Pick 👍, 👎, or 😂.")
    suggestion = clean_text(d_.get("suggestion"), 400) or None
    if suggestion and contains_blocked(suggestion):
        return error("unsafe", settings.copy_text("error.unsafe"))
    existing = db.session.execute(select(Reaction).where(Reaction.message_id == msg.id, Reaction.member_id == m.id,
                                                         Reaction.kind == kind)).scalars().first()
    if existing is None:
        db.session.add(Reaction(message_id=msg.id, member_id=m.id, kind=kind, suggestion=suggestion))
    elif suggestion:
        existing.suggestion = suggestion
    pending = False
    if kind == "down" and suggestion and r.delegate_id:
        # "What should it have said?" becomes a training suggestion for the owner to approve (section 7.2).
        prev = db.session.execute(select(Message).where(Message.round_id == r.id, Message.seq < msg.seq,
                                                        Message.role == "student").order_by(Message.seq.desc())).scalars().first()
        db.session.add(TrainingExample(delegate_id=r.delegate_id, student_text=prev.text if prev else "(opening)",
                                       ideal_reply=suggestion, source="thumbs_down", suggested_by=m.id,
                                       status="pending", message_id=msg.id))
        pending = True
    db.session.commit()
    return jsonify({"ok": True, "pending_example": pending,
                    "message": "Thanks! The owner can teach it that." if pending else "Thanks!"})


@bp.post("/api/human-rounds")
@member_required
def log_human_round():
    m = current_member()
    d_ = body()
    seconds = as_int(d_.get("seconds"), 0, 0, 3600)
    topic = clean_text(d_.get("topic"), 200, single_line=True)
    partner_name = clean_text(d_.get("partner_name"), 40, single_line=True) or None
    partner_id = d_.get("partner_member_id")
    partner = db.session.get(Member, partner_id) if partner_id else None
    if partner and partner.id == m.id:
        partner = None
    if partner_name and contains_blocked(partner_name):
        partner_name = None
    source = d_.get("source_round_id")
    entries = [(m, partner.id if partner else None, partner.display_name if partner else partner_name)]
    if partner is not None:
        entries.append((partner, m.id, m.display_name))  # "logs a human round for each logged-in participant"
    for who, pid, pname in entries:
        db.session.add(HumanRound(member_id=who.id, partner_member_id=pid, partner_name=pname, topic=topic,
                                  seconds=seconds, source_round_id=source if who is m else None))
        who.stage = journey.advance_stage(who.stage, "human_round")
        counters.bump("human_rounds")
    today = schedule.local_today(schedule.utc_now(), settings.get("timezone"))
    if m.last_active_date != today:
        m.show_up_days = (m.show_up_days or 0) + 1
        m.last_active_date = today
    db.session.commit()
    return jsonify({"ok": True, "message": settings.copy_text("handoff.human_done"), "stage": m.stage})


@bp.get("/api/handoff")
def handoff_state():
    m = current_member()
    gid = None if m else guest_id(create=False)
    state = handoff.state_for(m, gid, schedule.utc_now())
    return jsonify(state)
