"""Who is logged in, what they may do, and checks on everything people send us.

Every route checks roles here on the server. Never trust the UI to hide a button.
"""
import io
import re
import secrets
import time
import unicodedata
import warnings
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for
from PIL import Image as PILImage
from PIL import ImageOps

from extensions import db
from logic import data
from models import Member

SHARED_IDLE_SECONDS = 30 * 60  # shared Chromebooks log out after 30 minutes idle

# ------------------------------------------------------------------ sessions


def current_member():
    if "member" not in g:
        member_id = session.get("member_id")
        g.member = db.session.get(Member, member_id) if member_id else None
        if member_id and g.member is None:
            session.pop("member_id", None)  # member was deleted
    return g.member


def guest_id(create=True):
    gid = session.get("guest_id")
    if not gid and create:
        gid = secrets.token_hex(12)
        session["guest_id"] = gid
    return gid


def check_idle_timeout():
    """Called before every request. Shared devices log out after 30 idle minutes."""
    if not session.get("member_id"):
        return
    now = int(time.time())
    last = session.get("last_seen", now)
    if session.get("shared", True) and now - int(last) > SHARED_IDLE_SECONDS:
        log_out()
        session["timed_out"] = True
        return
    session["last_seen"] = now


def log_in(member, shared_device=True):
    keep_guest = session.get("guest_id")
    session.clear()
    session["member_id"] = member.id
    session["shared"] = bool(shared_device)
    session["last_seen"] = int(time.time())
    if keep_guest:
        session["guest_id"] = keep_guest
    # Shared Chromebook: session ends when the browser closes. Otherwise remember for 30 days.
    session.permanent = not shared_device
    g.pop("member", None)


def log_out():
    keep_guest = session.get("guest_id")
    session.clear()
    if keep_guest:
        session["guest_id"] = keep_guest
    g.pop("member", None)


def requester_key():
    member = current_member()
    return f"member:{member.id}" if member else f"guest:{guest_id()}"


# ------------------------------------------------------------------ role decorators

def _wants_json():
    return request.path.startswith("/api/")


def _deny(status, code, message):
    if _wants_json():
        return jsonify({"error": code, "message": message}), status
    if status == 401:
        return redirect(url_for("pages.login", next=request.full_path.rstrip("?")))
    return redirect(url_for("pages.welcome"))


def member_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if current_member() is None:
            return _deny(401, "login_required", "Join the club (or log in) to do that. It takes 20 seconds.")
        return fn(*args, **kwargs)
    return wrapper


def editor_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        m = current_member()
        if m is None:
            return _deny(401, "login_required", "Please log in first.")
        if not m.is_editor:
            return _deny(403, "forbidden", "That's for editors. Ask an officer if you need it.")
        return fn(*args, **kwargs)
    return wrapper


def maintainer_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        m = current_member()
        if m is None:
            return _deny(401, "login_required", "Please log in first.")
        if not m.is_maintainer:
            return _deny(403, "forbidden", "That's for maintainers only.")
        return fn(*args, **kwargs)
    return wrapper


# ------------------------------------------------------------------ delegate permissions

def can_view_delegate(delegate, member=None):
    member = member if member is not None else current_member()
    if delegate.visibility == "public" and delegate.status == "active":
        return True
    if member is None:
        return False
    return delegate.owner_id == member.id or member.is_editor


def can_edit_delegate(delegate, member=None):
    member = member if member is not None else current_member()
    if member is None:
        return False
    return delegate.owner_id == member.id or member.is_editor


def can_delete_delegate(delegate, member=None):
    member = member if member is not None else current_member()
    if member is None:
        return False
    return delegate.owner_id == member.id or member.is_maintainer


# ------------------------------------------------------------------ text checks

_CONTROL = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F​-‏‪-‮⁦-⁩]")


def clean_text(value, max_chars=None, single_line=False):
    """Strip control characters and trim. Never raises."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL.sub("", text)
    if single_line:
        text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def contains_blocked(*texts):
    """True if any text contains a word from data/blocklist.txt (whole words, any case)."""
    words = data.blocklist()
    for text in texts:
        if not text:
            continue
        low = " " + re.sub(r"[^a-z0-9' ]+", " ", str(text).lower()) + " "
        low = re.sub(r"\s+", " ", low)
        for w in words:
            if f" {w} " in low:
                return True
    return False


# Starts with a letter; then letters, numbers, spaces, apostrophes, dots, or dashes (e.g. "Sam K", "Jo-Ann", "Max2").
NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9' .-]{0,29}$")


def valid_display_name(name):
    return bool(NAME_RE.match(name or "")) and not contains_blocked(name)


# ------------------------------------------------------------------ images

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_STORED_BYTES = int(1.5 * 1024 * 1024)
MAX_SIDE = 1280
THUMB_SIDE = 400
ALLOWED_FORMATS = {"JPEG", "PNG"}
PILImage.MAX_IMAGE_PIXELS = 40_000_000  # refuse "decompression bomb" images


class ImageRejected(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _flatten(img):
    """Transparent PNGs get a white paper background."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = PILImage.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def _encode_jpeg(img, max_bytes):
    quality = 85
    work = img
    while True:
        buf = io.BytesIO()
        # Saving without exif= means no EXIF/GPS data is written.
        work.save(buf, format="JPEG", quality=quality, optimize=True)
        out = buf.getvalue()
        if len(out) <= max_bytes:
            return out, work.size
        if quality > 50:
            quality -= 10
        else:
            work = work.resize((max(1, int(work.width * 0.85)), max(1, int(work.height * 0.85))))


def process_image(raw):
    """Re-open and re-encode an uploaded image with Pillow.

    JPEG/PNG only (no WEBP), rotation fixed, all metadata (including GPS location) removed,
    long side <= 1280 px, stored file <= 1.5 MB. Returns dict(data, thumb, width, height, mime).
    """
    if not raw:
        raise ImageRejected("bad_image", data.copy_defaults()["error.bad_image"])
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ImageRejected("too_big", data.copy_defaults()["error.big_file"])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PILImage.DecompressionBombWarning)
            probe = PILImage.open(io.BytesIO(raw))
            fmt = probe.format
            probe.verify()
            if fmt not in ALLOWED_FORMATS:
                raise ImageRejected("bad_type", "Please use a JPG or PNG photo.")
            img = PILImage.open(io.BytesIO(raw))
            img.load()
    except ImageRejected:
        raise
    except Exception:
        raise ImageRejected("bad_image", data.copy_defaults()["error.bad_image"])
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    img = _flatten(img)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    full, (w, h) = _encode_jpeg(img, MAX_STORED_BYTES)
    thumb_img = img.copy()
    thumb_img.thumbnail((THUMB_SIDE, THUMB_SIDE))
    thumb, _ = _encode_jpeg(thumb_img, 200 * 1024)
    return {"data": full, "thumb": thumb, "width": w, "height": h, "mime": "image/jpeg"}


# ------------------------------------------------------------------ audio (Phase 2)

AUDIO_MIME_ALLOWLIST = {"audio/webm", "audio/ogg", "audio/mp4", "audio/m4a", "audio/x-m4a", "audio/wav",
                        "audio/x-wav", "audio/mpeg", "audio/mp3", "video/webm"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def audio_ok(mime, size):
    base = (mime or "").split(";")[0].strip().lower()
    return base in AUDIO_MIME_ALLOWLIST and 0 < size <= MAX_AUDIO_BYTES
