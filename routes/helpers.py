"""Small helpers shared by the API routes."""
from flask import current_app, jsonify, request

from extensions import db
from models import AuditLog


def ai():
    return current_app.extensions["ai"]


def body():
    """The JSON body as a dict (never None)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def error(code, message, status=400, **extra):
    payload = {"error": code, "message": message}
    payload.update(extra)
    return jsonify(payload), status


def ai_error_response(exc, **extra):
    """Every AI failure gets a friendly message plus a non-AI way forward."""
    status = 503
    if getattr(exc, "code", "") == "ai_filtered":
        status = 422
    payload = {"error": getattr(exc, "code", "ai_error"), "message": exc.user_message,
               "human_round_url": "/human"}
    payload.update(extra)
    # Keep the AI-call counter even though the request failed.
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify(payload), status


def audit(actor, action, target_type=None, target_id=None, detail=None):
    db.session.add(AuditLog(actor_id=actor.id if actor else None, action=action, target_type=target_type,
                            target_id=str(target_id) if target_id else None, detail=detail or {}))


def as_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def as_int(v, default, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n
