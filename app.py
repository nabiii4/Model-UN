"""Nightmare Delegate - entry point. Run it with:  python app.py

Draw your nightmare. Debate it. Then go find a human.
"""
import logging
import time

from flask import Flask, g, jsonify, render_template, request, session
from flask_wtf.csrf import CSRFError, generate_csrf
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, setup_logging
from extensions import csrf, db, limiter

log = logging.getLogger("nightmare.app")

# Content Security Policy from BUILD_PROMPT.md section 14: everything is self-hosted.
CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
       "script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
       "connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    """SQLite only: WAL mode lets people read while someone else saves (fewer 'database is locked' errors)."""
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA foreign_keys=ON")
        finally:
            cur.close()


def create_app(overrides=None):
    cfg = Config(overrides)
    setup_logging(cfg)

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(cfg.flask_settings())
    app.config["APP_CONFIG"] = cfg
    if cfg.trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from ai.client import AIClient
    from logic import counters, settings as club_settings

    def ai_counter(key):
        from flask import has_request_context
        counters.bump(key)
        if not has_request_context():
            db.session.commit()

    def ai_cap():
        return club_settings.get("ai_daily_cap")

    app.extensions["ai"] = AIClient(cfg, counter=ai_counter, cap_provider=ai_cap)

    from routes import register_blueprints
    register_blueprints(app)
    _register_hooks(app)
    _register_errors(app)

    with app.app_context():
        import models  # noqa: F401 - registers every table
        db.create_all()
        from logic.seeding import seed_if_empty
        seed_if_empty()

    if cfg.mock:
        log.info("Running in MOCK mode (%s). The AI is pretend.", cfg.mock_reason)
    else:
        app.extensions["ai"].probe_async(app)
    return app


def _register_hooks(app):
    from logic import counters
    from logic import settings as club_settings
    from logic.security import check_idle_timeout, current_member

    @app.before_request
    def before():
        g.request_started = time.time()
        if request.endpoint == "static":
            return
        check_idle_timeout()

    @app.after_request
    def security_headers(resp):
        if "Content-Security-Policy" not in resp.headers:  # images set a stricter one
            resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(self), microphone=(self)"
        resp.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/") and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "no-store"
        # Count anonymous visits to pages (not files or API calls) for Club Pulse.
        if (request.method == "GET" and resp.status_code == 200 and request.endpoint
                and request.endpoint.startswith("pages.")):
            try:
                from logic.security import guest_id
                counters.record_visit(session.get("member_id") or guest_id())
            except Exception:
                db.session.rollback()
        return resp

    @app.context_processor
    def template_globals():
        cfg = app.config["APP_CONFIG"]
        member = current_member()
        return {
            "member": member,
            "mock_mode": cfg.mock,
            "copy": club_settings.copy_text,
            "all_copy": club_settings.all_copy,
            "club_name": club_settings.get("club_name"),
            "csrf_token_value": generate_csrf,
            "comfort": (member.comfort or {}) if member else {},
        }


def _wants_json():
    return request.path.startswith("/api/")


def _register_errors(app):
    from logic import settings as club_settings

    def page_error(status, title, message):
        try:
            from logic.security import current_member
            return render_template("error.html", status=status, title=title, message=message,
                                   page_data={"logged_in": current_member() is not None}), status
        except Exception:
            log.exception("Error page failed to render")
            return f"<h1>{title}</h1><p>{message}</p>", status

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        msg = "This page got a little stale. Refresh the page and try again."
        if _wants_json():
            return jsonify({"error": "csrf", "message": msg}), 400
        return page_error(400, "Refresh needed", msg)

    @app.errorhandler(429)
    def too_many(e):
        retry_after = 120
        try:
            current = limiter.current_limit
            if current is not None:
                retry_after = max(1, int(current.reset_at - time.time()))
        except Exception:
            pass
        minutes = max(1, round(retry_after / 60))
        message = club_settings.copy_text("error.rate_limited", n=minutes)
        if _wants_json():
            resp = jsonify({"error": "slow_down", "retry_after": retry_after, "message": message})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp
        return page_error(429, "Whoa, speedy", message)

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify({"error": "not_found", "message": "We couldn't find that."}), 404
        return page_error(404, "Lost in committee", club_settings.copy_text("error.not_found"))

    @app.errorhandler(413)
    def too_large(e):
        msg = club_settings.copy_text("error.big_file")
        if _wants_json():
            return jsonify({"error": "too_big", "message": msg}), 413
        return page_error(413, "Too big", msg)

    @app.errorhandler(HTTPException)
    def http_error(e):
        if _wants_json():
            return jsonify({"error": e.name.lower().replace(" ", "_"), "message": "That didn't work. Try again?"}), e.code
        return page_error(e.code, e.name, "That didn't work. Let's get you back on track.")

    @app.errorhandler(Exception)
    def crash(e):
        log.exception("Unexpected error on %s %s", request.method, request.path)
        db.session.rollback()
        msg = club_settings.copy_text("error.generic")
        if _wants_json():
            return jsonify({"error": "server_error", "message": msg}), 500
        return page_error(500, "Oops", msg)


def pick_port(preferred, host="0.0.0.0", tries=10):
    """Use the preferred port, or the next free one instead of crashing.

    Why: on Macs, AirPlay Receiver already uses port 5000, so `python app.py`
    would fail with "Address already in use".
    """
    import socket
    for port in range(preferred, preferred + tries + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return preferred  # nothing free nearby: let Flask show the real error


# For gunicorn: `gunicorn app:app`
app = None


def _get_app():
    global app
    if app is None:
        app = create_app()
    return app


if __name__ == "__main__":
    import os
    application = _get_app()
    cfg = application.config["APP_CONFIG"]
    port = cfg.port
    # With FLASK_DEBUG=1 the reloader runs this file twice; only the first run picks the port.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        port = pick_port(cfg.port)
        if port != cfg.port:
            print(f"\n  Port {cfg.port} is busy (on a Mac, AirPlay Receiver uses 5000), so using {port} instead.")
            os.environ["PORT"] = str(port)  # the reloader's second run reads PORT again
    print("\n  Nightmare Delegate is running.")
    print(f"  Open http://localhost:{port} in your browser.")
    if cfg.mock:
        print("  Demo mode: the AI is pretend (no key needed).")
        if cfg.club_code_is_default:
            print(f"  Club code to join: {cfg.club_code}")
        if cfg.admin_passcode_is_demo:
            print("  Admin passcode (demo only): see README.md")
    print()
    application.run(host="0.0.0.0", port=port, debug=cfg.debug, use_reloader=cfg.debug, threaded=True)
else:
    # Imported by gunicorn or a test: build the app lazily only for gunicorn ("app:app").
    import sys
    if "gunicorn" in sys.modules:
        app = create_app()
