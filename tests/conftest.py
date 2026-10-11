"""Shared test setup. Tests ALWAYS run in mock mode with a throwaway database."""
import io
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAKE_KEY = "zzFAKEkey0123456789abcdefTESTONLY"
FAKE_ENDPOINT = "https://fake-test-resource.openai.azure.com/"


def make_app(tmp_path, **extra):
    from app import create_app
    from extensions import limiter
    overrides = {
        "TESTING": "1", "SKIP_DOTENV": "1", "MOCK_AI": "1", "MOCK_AI_DELAY": "0",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "FLASK_SECRET_KEY": "test-secret-key-not-real-123456",
        "ADMIN_PASSCODE": "letmein-test", "CLUB_CODE": "testclub", "TIMEZONE": "America/New_York",
        "AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_BACKUP_API_KEY": "",
        "AZURE_OPENAI_BACKUP_ENDPOINT": "", "OPENAI_API_KEY": "",
    }
    overrides.update({k: str(v) for k, v in extra.items()})
    app = create_app(overrides)
    limiter.reset()
    return app


class Api:
    """A test client that sends the CSRF token on every non-GET request, like api.js does."""

    def __init__(self, client):
        self.client = client
        self.token = None

    def refresh_token(self):
        html = self.client.get("/").get_data(as_text=True)
        m = re.search(r'name="csrf-token" content="([^"]+)"', html)
        self.token = m.group(1) if m else ""

    def _headers(self):
        if self.token is None:
            self.refresh_token()
        return {"X-CSRFToken": self.token}

    def get(self, path, **kw):
        return self.client.get(path, **kw)

    def post(self, path, json_body=None, **kw):
        return self.client.post(path, json=json_body if json_body is not None else {}, headers=self._headers(), **kw)

    def post_form(self, path, data):
        return self.client.post(path, data=data, headers=self._headers(), content_type="multipart/form-data")

    def patch(self, path, json_body=None):
        return self.client.patch(path, json=json_body or {}, headers=self._headers())

    def delete(self, path, json_body=None):
        return self.client.delete(path, json=json_body or {}, headers=self._headers())

    def join(self, name, pin="1234", code="testclub", shared=True):
        r = self.post("/api/auth/join", {"club_code": code, "name": name, "pin": pin, "shared_device": shared})
        assert r.status_code == 200, r.get_json()
        self.refresh_token()
        return r.get_json()["member"]

    def become_maintainer(self):
        r = self.post("/api/admin/login", {"passcode": "letmein-test"})
        assert r.status_code == 200, r.get_json()


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def api(app):
    return Api(app.test_client())


@pytest.fixture
def new_api(app):
    """Make extra independent browsers (each with its own cookies)."""
    return lambda: Api(app.test_client())


def drawing_bytes(fmt="JPEG", blank=False, size=(900, 700), exif=None):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, "white")
    if not blank:
        d = ImageDraw.Draw(img)
        d.ellipse((250, 120, 650, 520), outline="black", width=8)
        d.line((300, 300, 600, 300), fill="red", width=6)
    buf = io.BytesIO()
    kw = {}
    if exif is not None:
        kw["exif"] = exif
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def make_delegate(api, answers=None):
    """Run the real draw flow through the API and save the result. Returns the delegate id."""
    r = api.post_form("/api/delegates/draft-from-image", {
        "image": (io.BytesIO(drawing_bytes()), "drawing.jpg"),
        "answers": json.dumps(answers or {"nervous": ["Being interrupted"]})})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["ok"], d
    r = api.post("/api/delegates", {"persona": d["draft"], "temp_image_id": d["temp_image_id"], "visibility": "public",
                                    "credit": "name", "story": "It scares me.", "source": "photo"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def start_round(api, delegate_id="seed-interrupter", **extra):
    body = {"delegate_id": delegate_id, "format": "rebuttal_duel", "committee": "UNEP", "topic": "Plastic pollution",
            "my_country": "Canada", "their_country": "Brazil", "difficulty": 3, "length": "quick"}
    body.update(extra)
    return api.post("/api/rounds", body)
