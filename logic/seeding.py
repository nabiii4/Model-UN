"""Loads example delegates and default settings. Safe to run twice (upserts by stable seed ids)."""
import logging
from pathlib import Path

from sqlalchemy import select

from ai.persona import normalize_persona
from extensions import db
from logic import data, settings
from models import Delegate, DelegateVersion, Image, Setting
from models.base import utcnow

log = logging.getLogger("nightmare.seed")
SEED_IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "seeds"


def _seed_image(seed):
    """Seed drawings are our own SVG doodles, stored like any other image."""
    path = SEED_IMG_DIR / seed["image"]
    if not path.exists():
        log.warning("Seed image missing: %s", path.name)
        return None
    image_id = f"img-{seed['id']}"
    raw = path.read_bytes()
    img = db.session.get(Image, image_id)
    if img is None:
        img = Image(id=image_id, owner_id=None, kind="seed", mime="image/svg+xml", data=raw, thumb=None,
                    width=400, height=500)
        db.session.add(img)
    else:
        img.data, img.kind, img.mime = raw, "seed", "image/svg+xml"
    return image_id


def seed_delegates():
    count = 0
    for seed in data.seeds():
        raw = {k: v for k, v in seed.items() if k not in ("id", "image", "story", "opens_blank")}
        persona, dropped = normalize_persona(raw)
        if dropped:
            log.warning("Seed %s had unknown ids: %s", seed["id"], dropped)
        if seed.get("opens_blank"):
            persona["opens_blank"] = True
        image_id = _seed_image(seed)
        d = db.session.get(Delegate, seed["id"])
        if d is None:
            d = Delegate(id=seed["id"], owner_id=None, source="seed", status="active", visibility="public",
                         credit="anonymous", version=1)
            db.session.add(d)
            db.session.add(DelegateVersion(delegate_id=seed["id"], version=1, persona=persona,
                                           summary="Example delegate", changed_by=None))
        d.name = persona["name"]
        d.persona = persona
        d.story = seed.get("story")
        d.drawing_image_id = image_id
        d.source = "seed"
        count += 1
    return count


def seed_settings():
    """Default settings live in logic/settings.py and are NOT copied into the database.

    Why: values like CLUB_CODE and TIMEZONE come from .env. If we stored the defaults, a later
    change to .env would be ignored. A setting is only stored once someone changes it in Admin
    (and then the Admin value wins). This function just checks the defaults load.
    """
    return settings.defaults()


def seed_all():
    seed_settings()
    n = seed_delegates()
    row = db.session.get(Setting, "seeded_at")
    if row is None:
        db.session.add(Setting(key="seeded_at", value={"at": utcnow().isoformat()}))
    db.session.commit()
    return n


def seed_if_empty():
    """Called at startup: seed only the very first time, so deleted examples stay deleted."""
    if db.session.get(Setting, "seeded_at") is None:
        n = seed_all()
        log.info("First run: loaded %d example delegates and default settings.", n)


def count_seeds():
    return len(db.session.execute(select(Delegate.id).where(Delegate.source == "seed")).all())
