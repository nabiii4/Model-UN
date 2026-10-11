"""Reads settings from environment variables (.env locally) and decides mock mode.

Why this file exists: every secret lives in the environment, never in code.
This is the only file that reads those values, and it never prints them.
If something is missing we log a clear warning and fall back to mock mode
instead of crashing, so the site always starts.
"""
import logging
import os
import secrets
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("nightmare.config")

# Used only when nothing is set, so a brand-new copy works with zero setup.
# Both are printed in the README and shown on the Join page in demo mode.
DEFAULT_CLUB_CODE = "blanksheet"
DEMO_ADMIN_PASSCODE = "demo-admin"
DEFAULT_TIMEZONE = "America/New_York"

# Values copied from .env.example. If a value still looks like this, it was never filled in.
PLACEHOLDER_HINTS = ("paste-", "your-resource", "your-backup-resource", "make-a-long-random",
                     "choose-a-strong", "pick-a-club")


def _is_placeholder(value):
    v = (value or "").strip().lower()
    return (not v) or any(h in v for h in PLACEHOLDER_HINTS)


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class Config:
    """All settings in one object. Pass `overrides` (a dict) in tests."""

    def __init__(self, overrides=None, load_env_file=True):
        if load_env_file and not (overrides or {}).get("SKIP_DOTENV"):
            # Does nothing if there is no .env file - that's fine, we run in mock mode.
            load_dotenv(BASE_DIR / ".env")
        o = dict(overrides or {})

        def get(name, default=""):
            if name in o:
                return "" if o[name] is None else str(o[name]).strip()
            return os.environ.get(name, default).strip()

        self.testing = _truthy(get("TESTING", "0"))
        self.warnings = []

        # ----- AI provider -----
        self.ai_provider = (get("AI_PROVIDER", "azure") or "azure").lower()
        if self.ai_provider not in ("azure", "openai_compatible"):
            self._warn(f"AI_PROVIDER '{self.ai_provider}' is unknown; using 'azure'.")
            self.ai_provider = "azure"

        self.azure_endpoint = get("AZURE_OPENAI_ENDPOINT")
        self.azure_key = get("AZURE_OPENAI_API_KEY")
        self.api_version = get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview") or "2025-01-01-preview"
        self.media_api_version = get("AZURE_OPENAI_MEDIA_API_VERSION", "2025-04-01-preview") or "2025-04-01-preview"
        self.deployment = get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-nano") or "gpt-5-nano"
        self.vision_deployment = get("AZURE_OPENAI_VISION_DEPLOYMENT") or self.deployment
        self.transcribe_model = get("AZURE_OPENAI_TRANSCRIBE_MODEL")
        self.tts_model = get("AZURE_OPENAI_TTS_MODEL")
        self.image_model = get("AZURE_OPENAI_IMAGE_MODEL")
        self.embedding_model = get("AZURE_OPENAI_EMBEDDING_MODEL")
        self.backup_endpoint = get("AZURE_OPENAI_BACKUP_ENDPOINT")
        self.backup_key = get("AZURE_OPENAI_BACKUP_API_KEY")
        if _is_placeholder(self.backup_endpoint) or _is_placeholder(self.backup_key):
            self.backup_endpoint, self.backup_key = "", ""

        self.openai_base_url = get("OPENAI_BASE_URL")
        self.openai_api_key = get("OPENAI_API_KEY")
        self.openai_chat_model = get("OPENAI_CHAT_MODEL")
        self.openai_vision_model = get("OPENAI_VISION_MODEL") or self.openai_chat_model

        effort = (get("AI_REASONING_EFFORT", "low") or "low").lower()
        self.reasoning_effort = effort if effort in ("minimal", "low", "medium", "high", "none") else "low"
        self.daily_call_cap = self._int(get("AI_DAILY_CALL_CAP", "1500"), 1500, "AI_DAILY_CALL_CAP")

        # ----- Mock mode -----
        self.mock_requested = _truthy(get("MOCK_AI", "0"))
        self.mock, self.mock_reason = self._decide_mock()
        # Pretend "thinking" time in mock mode so loading screens are visible. 0 in tests.
        default_delay = "0" if self.testing else "1"
        try:
            self.mock_delay = max(0.0, min(5.0, float(get("MOCK_AI_DELAY", default_delay))))
        except ValueError:
            self.mock_delay = 0.0 if self.testing else 1.0

        # ----- App -----
        secret = get("FLASK_SECRET_KEY")
        self.secret_key_generated = _is_placeholder(secret)
        if self.secret_key_generated:
            # A random key works fine; people just get logged out when the server restarts.
            secret = secrets.token_urlsafe(48)
            if not self.testing:
                self._warn("FLASK_SECRET_KEY is not set. Using a random one "
                           "(everyone is logged out when the server restarts).")
        self.secret_key = secret

        passcode = get("ADMIN_PASSCODE")
        self.admin_passcode_is_demo = False
        if _is_placeholder(passcode):
            if self.mock:
                passcode = DEMO_ADMIN_PASSCODE
                self.admin_passcode_is_demo = True
                if not self.testing:
                    self._warn(f"ADMIN_PASSCODE is not set. Demo mode uses '{DEMO_ADMIN_PASSCODE}'. "
                               "Set a real one in .env before sharing the site.")
            else:
                passcode = ""
                self._warn("ADMIN_PASSCODE is not set, so nobody can become a maintainer yet.")
        self.admin_passcode = passcode

        club_code = get("CLUB_CODE")
        self.club_code_is_default = _is_placeholder(club_code)
        self.club_code = DEFAULT_CLUB_CODE if self.club_code_is_default else club_code

        self.database_url = self._database_url(get("DATABASE_URL"))

        tz = get("TIMEZONE", DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE
        try:
            ZoneInfo(tz)
        except Exception:
            self._warn(f"TIMEZONE '{tz}' is not a real time zone; using {DEFAULT_TIMEZONE}.")
            tz = DEFAULT_TIMEZONE
        self.timezone = tz

        self.port = self._int(get("PORT", "5000"), 5000, "PORT")
        self.https_only = _truthy(get("HTTPS_ONLY", "0"))
        self.trust_proxy = _truthy(get("TRUST_PROXY", "0"))
        self.debug = _truthy(get("FLASK_DEBUG", "0"))

    # ------------------------------------------------------------------
    def _warn(self, message):
        self.warnings.append(message)
        log.warning(message)

    def _int(self, raw, default, name):
        try:
            return int(raw)
        except (TypeError, ValueError):
            self._warn(f"{name} should be a number; using {default}.")
            return default

    def _decide_mock(self):
        if self.mock_requested:
            return True, "MOCK_AI=1"
        if self.ai_provider == "azure":
            if _is_placeholder(self.azure_key) or _is_placeholder(self.azure_endpoint):
                self._warn("No Azure OpenAI key/endpoint found. Starting in mock mode (the AI is pretend).")
                return True, "no key"
        else:
            if _is_placeholder(self.openai_api_key) or not self.openai_base_url or not self.openai_chat_model:
                self._warn("AI_PROVIDER=openai_compatible but OPENAI_BASE_URL / OPENAI_API_KEY / "
                           "OPENAI_CHAT_MODEL are missing. Starting in mock mode.")
                return True, "no key"
        return False, ""

    def _database_url(self, url):
        if not url:
            url = "sqlite:///instance/nightmare.db"
        # Hosted Postgres URLs often start with postgres:// - SQLAlchemy needs the driver name.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////") and url != "sqlite:///:memory:":
            # Make relative SQLite paths relative to this project, not to wherever you ran python from.
            rel = url[len("sqlite:///"):]
            path = Path(rel)
            if not path.is_absolute():
                path = BASE_DIR / path
            path.parent.mkdir(parents=True, exist_ok=True)
            url = "sqlite:///" + path.as_posix()
        return url

    def secret_values(self):
        """Every value that must never appear in a log line, page, or API response."""
        values = [self.azure_key, self.backup_key, self.openai_api_key, self.secret_key]
        if not self.admin_passcode_is_demo:
            values.append(self.admin_passcode)
        return [v for v in values if v and len(v) >= 6 and not _is_placeholder(v)]

    def flask_settings(self):
        from datetime import timedelta
        return {
            "SECRET_KEY": self.secret_key,
            "SQLALCHEMY_DATABASE_URI": self.database_url,
            "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
            "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,  # 15 MB images + a little form overhead
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": self.https_only,
            "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
            "WTF_CSRF_TIME_LIMIT": None,  # token lives as long as the session (pages stay open in class)
            "WTF_CSRF_HEADERS": ["X-CSRFToken", "X-CSRF-Token"],
            "RATELIMIT_STORAGE_URI": "memory://",
            "RATELIMIT_HEADERS_ENABLED": False,
            "TESTING": self.testing,
            "JSON_SORT_KEYS": False,
        }


class SecretFilter(logging.Filter):
    """Removes secret values from every log line, just in case something tries to print one."""

    def __init__(self, secrets_list):
        super().__init__()
        self.secrets = [s for s in secrets_list if s]

    def filter(self, record):
        if not self.secrets:
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        changed = False
        for s in self.secrets:
            if s in message:
                message = message.replace(s, "[hidden]")
                changed = True
        if changed:
            record.msg = message
            record.args = ()
        return True


def setup_logging(cfg):
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    secret_filter = SecretFilter(cfg.secret_values())
    for handler in root.handlers:
        # Replace any older filter (tests create several apps).
        handler.filters = [f for f in handler.filters if not isinstance(f, SecretFilter)]
        handler.addFilter(secret_filter)
    # The HTTP libraries can log request details at DEBUG level. Keep them quiet.
    for noisy in ("openai", "httpx", "httpx2", "httpcore", "httpcore2", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
