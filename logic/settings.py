"""Club settings stored in the database (editable in Admin), with safe defaults.

Why a database table and not a file: free hosts wipe files on redeploy, and editors
should be able to change these without touching code.
"""
import copy

from flask import current_app, g

from extensions import db
from logic import data
from models import Setting


def defaults():
    cfg = current_app.config["APP_CONFIG"]
    return {
        "club_name": "Nightmare Delegate",
        "club_code": cfg.club_code,
        "timezone": cfg.timezone,
        "meeting_schedule": {"days": ["tue", "thu"], "start": "15:00", "end": "16:30"},
        "handoff_mode": "strict",          # strict / gentle / off
        "lock_minutes": 10,
        "home_cap": 5,
        "handoff_text": "Now go find a human.",
        "handoff_credit": "— written by our co-designer",
        "guest_ai": {"enabled": False, "daily_quota": 15},
        "ai_daily_cap": cfg.daily_call_cap,
        "wall_moderation": "auto",         # auto (blocklist + AI safety check) / approval (editor approves first)
        "features": {"ai_voice": True, "speech_to_text": True, "camera_coach": False, "head_follow": False,
                     "reimagine": False, "dress_check": False, "club_packs": False},
        "copy_overrides": {},
        "committees": data.default_committees(),
        "credits": [],
    }


EDITABLE_BY_MAINTAINER = {"club_name", "club_code", "timezone", "meeting_schedule", "handoff_mode", "lock_minutes",
                          "home_cap", "handoff_text", "handoff_credit", "guest_ai", "ai_daily_cap",
                          "wall_moderation", "features", "credits"}
EDITABLE_BY_EDITOR = {"copy_overrides", "committees"}


def _cache():
    if "settings_cache" not in g:
        g.settings_cache = {}
    return g.settings_cache


def get(key):
    cache = _cache()
    if key in cache:
        return copy.deepcopy(cache[key])
    row = db.session.get(Setting, key)
    value = row.value if row is not None and row.value is not None else defaults().get(key)
    # Settings that are dicts get any newly added default keys filled in.
    default = defaults().get(key)
    if isinstance(default, dict) and isinstance(value, dict) and key not in ("copy_overrides",):
        merged = copy.deepcopy(default)
        merged.update(value)
        value = merged
    cache[key] = value
    return copy.deepcopy(value)


def set(key, value):  # noqa: A001 - "set" reads naturally here: settings.set(...)
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.session.add(row)
    else:
        row.value = value
    _cache().pop(key, None)


def all_settings():
    return {k: get(k) for k in defaults()}


def copy_text(key, **values):
    text = get("copy_overrides").get(key) or data.copy_defaults().get(key, "")
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def all_copy():
    merged = dict(data.copy_defaults())
    merged.update({k: v for k, v in get("copy_overrides").items() if k in merged and v})
    return merged
