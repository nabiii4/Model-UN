"""All URL routes. Pages live in pages.py; JSON APIs live in api_*.py."""


def register_blueprints(app):
    from routes.api_admin import bp as admin_bp
    from routes.api_auth import bp as auth_bp
    from routes.api_delegates import bp as delegates_bp
    from routes.api_misc import bp as misc_bp
    from routes.api_room import bp as room_bp
    from routes.api_rounds import bp as rounds_bp
    from routes.pages import bp as pages_bp

    for bp in (pages_bp, auth_bp, delegates_bp, rounds_bp, room_bp, admin_bp, misc_bp):
        app.register_blueprint(bp)
