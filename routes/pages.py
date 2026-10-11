"""HTML pages. Each page gets a small `page_data` JSON blob; the page's JavaScript does the rest."""
from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from sqlalchemy import select

from extensions import db
from logic import handoff, schedule, settings
from logic.security import current_member, guest_id, member_required
from models import Delegate, FearMeter, Round
from routes.api_auth import comfort_for

bp = Blueprint("pages", __name__)


def page(template, title, active=None, **page_data):
    m = current_member()
    page_data.setdefault("logged_in", m is not None)
    page_data.setdefault("comfort", comfort_for(m))
    return render_template(template, title=title, active=active, page_data=page_data)


def _safe_next(url):
    """Only allow going back to a page on this site (never "//evil.com" or "/\\evil.com")."""
    if not url or not url.startswith("/") or url.startswith("//") or "\\" in url or any(c in url for c in "\r\n\t"):
        return "/"
    return url


@bp.get("/")
def welcome():
    m = current_member()
    returning = None
    if m is not None:
        fear = db.session.execute(select(FearMeter).where(FearMeter.member_id == m.id)
                                  .order_by(FearMeter.updated_at.desc())).scalars().first()
        nightmare = None
        if fear is not None:
            d = db.session.get(Delegate, fear.delegate_id)
            if d is not None:
                nightmare = {"id": d.id, "name": d.name, "fear": fear.value}
        if nightmare is None:
            d = db.session.execute(select(Delegate).where(Delegate.owner_id == m.id)
                                   .order_by(Delegate.created_at.desc())).scalars().first()
            if d is not None:
                nightmare = {"id": d.id, "name": d.name, "fear": 100}
        returning = {"name": m.display_name, "nightmare": nightmare,
                     "has_last_settings": bool(m.last_round_settings)}
    return page("welcome.html", "Welcome", "home", returning=returning)


@bp.get("/draw")
def draw():
    path = request.args.get("path", "")
    if path not in ("paper", "canvas"):
        path = ""
    m = current_member()
    return page("draw.html", "Draw your nightmare", "draw", path=path,
                guest=m is None, guest_ai=bool(settings.get("guest_ai").get("enabled")))


@bp.get("/wall")
def wall():
    return page("wall.html", "Nightmare Wall", "wall")


@bp.get("/d/<delegate_id>")
def delegate_page(delegate_id):
    return page("delegate.html", "Nightmare", "wall", delegate_id=delegate_id)


@bp.get("/blank")
@member_required
def blank():
    return page("blank.html", "The Blank", "draw")


@bp.get("/practice/new")
def practice_new():
    m = current_member()
    if m is None and not settings.get("guest_ai").get("enabled"):
        return redirect(url_for("pages.join", next=request.full_path.rstrip("?")))
    now = schedule.utc_now()
    state = handoff.state_for(m, None if m else guest_id(), now)
    return page("practice_new.html", "Set up a round", "practice",
                delegate_id=request.args.get("delegate", ""), quick=request.args.get("quick") == "1",
                last_settings=(m.last_round_settings if m else None), handoff=state,
                overtime=request.args.get("overtime") == "1", home=request.args.get("home") == "1")


@bp.get("/practice")
def practice_index():
    return redirect(url_for("pages.wall"))


def _own_round(round_id):
    r = db.session.get(Round, round_id)
    if r is None:
        return None
    m = current_member()
    if m is not None and r.member_id == m.id:
        return r
    if m is None and r.guest_id and r.guest_id == guest_id(create=False):
        return r
    return None


@bp.get("/practice/<round_id>")
def practice_room(round_id):
    r = _own_round(round_id)
    if r is None:
        abort(404)
    if r.completed:
        return redirect(url_for("pages.feedback", round_id=r.id))
    return page("practice.html", "Practice Room", "practice", round_id=r.id)


@bp.get("/practice/<round_id>/feedback")
def feedback(round_id):
    r = _own_round(round_id)
    if r is None:
        abort(404)
    if not r.completed:
        return redirect(url_for("pages.practice_room", round_id=r.id))
    return page("feedback.html", "Feedback", "practice", round_id=r.id)


@bp.get("/human")
def human():
    m = current_member()
    gid = None if m else guest_id()
    r = None
    rid = request.args.get("round")
    if rid:
        r = _own_round(rid)
    if r is None:
        q = select(Round).where(Round.completed.is_(True))
        q = q.where(Round.member_id == m.id) if m else q.where(Round.guest_id == gid)
        r = db.session.execute(q.order_by(Round.ended_at.desc())).scalars().first()
    card = None
    if r is not None:
        card = {"round_id": r.id, "topic": r.settings.get("topic"), "my_country": r.settings.get("my_country"),
                "their_country": r.settings.get("their_country"),
                "question": (r.opening or {}).get("human_round_question") or f"What should the world do about {r.settings.get('topic', 'this').lower()}?"}
    state = handoff.state_for(m, gid, schedule.utc_now())
    last = None
    if m is not None and m.last_round_settings:
        last = m.last_round_settings
    elif r is not None:
        last = {k: r.settings.get(k) for k in ("format", "committee", "topic", "my_country", "their_country",
                                                "difficulty", "length", "options")}
        last["delegate_id"] = r.delegate_id
    return page("human.html", "Now go find a human", "practice", card=card, handoff=state, last_settings=last,
                handoff_text=settings.get("handoff_text"), handoff_credit=settings.get("handoff_credit"),
                demo=request.args.get("demo") == "1")


@bp.get("/me")
@member_required
def me():
    return page("me.html", "My Journey", "me")


@bp.get("/admin")
@member_required
def admin():
    m = current_member()
    cfg = current_app.config["APP_CONFIG"]
    return page("admin.html", "Admin", "admin", role=m.role, passcode_set=bool(cfg.admin_passcode))


@bp.get("/join")
def join():
    if current_member() is not None:
        return redirect(_safe_next(request.args.get("next")))
    cfg = current_app.config["APP_CONFIG"]
    demo_code = cfg.club_code if (cfg.mock and cfg.club_code_is_default and
                                  settings.get("club_code") == cfg.club_code) else None
    return page("join.html", "Join the club", "join", next=_safe_next(request.args.get("next")), demo_code=demo_code)


@bp.get("/login")
def login():
    if current_member() is not None:
        return redirect(_safe_next(request.args.get("next")))
    from flask import session
    timed_out = session.pop("timed_out", False)
    return page("login.html", "Log in", "join", next=_safe_next(request.args.get("next")), timed_out=timed_out)


@bp.get("/how-it-works")
def how_it_works():
    return page("how_it_works.html", "How it works", "how")


@bp.get("/ritual")
def ritual():
    return page("ritual.html", "The Ritual")


@bp.get("/privacy")
def privacy():
    return page("privacy.html", "Privacy")


COMING_SOON = {
    "room": ("Today's Room", "Check-in, fair pairing, and timers for meetings arrive in Phase 2."),
    "learn": ("MUN 101", "A friendly glossary of MUN words arrives in Phase 3."),
    "credits": ("Credits", "The credits page arrives in Phase 3. Thank you to everyone who helped!"),
    "dress-check": ("Dress Code Check", "Intimidation doesn't have a dress code. Conferences do. This arrives in Phase 3."),
    "laugh-log": ("Laugh Log", "Funny moments, saved with 😂, arrive in Phase 3."),
}


@bp.get("/<slug>")
def coming_soon(slug):
    if slug not in COMING_SOON:
        abort(404)
    title, text = COMING_SOON[slug]
    return page("coming_soon.html", title, slug, heading=title, text=text)


@bp.get("/d/<delegate_id>/train")
def train(delegate_id):
    return page("coming_soon.html", "Trainer Studio", "wall", heading="Trainer Studio",
                text="Your nightmare learns from you. The full Trainer Studio arrives in Phase 2. "
                     "For now, use Edit on the nightmare's page.", back=f"/d/{delegate_id}")


@bp.get("/u/<code>")
def phone_upload(code):
    return page("coming_soon.html", "Phone upload", None, heading="Phone upload",
                text="Uploading from your phone with a QR code arrives in Phase 3. For now, use Upload a photo.")
