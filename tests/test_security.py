"""Security and privacy: keys never leak, images are cleaned, roles are checked, rate limits are friendly."""
import io
import json

import pytest

from conftest import FAKE_ENDPOINT, FAKE_KEY, Api, drawing_bytes, make_app, make_delegate, start_round

PAGES = ["/", "/draw", "/draw?path=paper", "/draw?path=canvas", "/wall", "/d/seed-interrupter", "/human", "/join",
         "/login", "/how-it-works", "/ritual", "/privacy", "/room", "/learn", "/credits", "/dress-check", "/laugh-log",
         "/d/seed-interrupter/train", "/u/abcdef"]
MEMBER_PAGES = ["/blank", "/practice/new", "/me", "/admin"]


# ---------------------------------------------------------------- the key never appears anywhere

def test_key_never_leaks(tmp_path):
    from app import create_app  # noqa: F401 - make sure the app module imports cleanly
    app = make_app(tmp_path, AZURE_OPENAI_API_KEY=FAKE_KEY, AZURE_OPENAI_ENDPOINT=FAKE_ENDPOINT,
                   AZURE_OPENAI_BACKUP_API_KEY=FAKE_KEY + "B", AZURE_OPENAI_BACKUP_ENDPOINT=FAKE_ENDPOINT,
                   AZURE_OPENAI_DEPLOYMENT="secret-deployment-name", MOCK_AI="1")
    api = Api(app.test_client())
    seen = []

    def grab(resp):
        seen.append(resp.get_data(as_text=True))
        seen.append(json.dumps(dict(resp.headers)))

    for p in PAGES:
        grab(api.get(p))
    api.join("Leaky")
    api.become_maintainer()
    did = make_delegate(api)
    rid = start_round(api, did).get_json()["round_id"]
    grab(api.post(f"/api/rounds/{rid}/turn", {"text": "Canada has a plan with 3 steps."}))
    grab(api.post(f"/api/rounds/{rid}/end"))
    for p in PAGES + MEMBER_PAGES + [f"/practice/{rid}/feedback", "/api/health", "/api/me", "/api/delegates",
                                     f"/api/delegates/{did}", f"/api/rounds/{rid}", "/api/admin/ai-status",
                                     "/api/admin/settings", "/api/admin/usage", "/api/admin/audit", "/api/me/export",
                                     "/api/copy", "/api/traits", "/api/setup-data", "/api/stats/club"]:
        grab(api.get(p))
    static_root = app.static_folder
    import os
    for folder, _, files in os.walk(static_root):
        if "vendor" in folder:
            continue
        for f in files:
            if f.endswith((".js", ".css", ".svg", ".json", ".webmanifest", ".html")):
                rel = os.path.relpath(os.path.join(folder, f), static_root).replace(os.sep, "/")
                grab(api.get(f"/static/{rel}"))
    blob = "\n".join(seen)
    assert len(seen) > 60
    for secret in (FAKE_KEY, "fake-test-resource", "secret-deployment-name"):
        assert secret not in blob, f"{secret} leaked"


def test_secrets_are_redacted_from_logs(caplog):
    import logging
    from config import SecretFilter
    f = SecretFilter([FAKE_KEY])
    rec = logging.LogRecord("x", logging.WARNING, __file__, 1, "calling with %s", (FAKE_KEY,), None)
    f.filter(rec)
    assert FAKE_KEY not in rec.getMessage() and "[hidden]" in rec.getMessage()


# ---------------------------------------------------------------- pages, headers, CSRF

def test_every_page_renders(api):
    for p in PAGES:
        r = api.get(p)
        assert r.status_code == 200, p
        assert "default-src 'self'" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["Referrer-Policy"] == "same-origin"
    for p in MEMBER_PAGES:
        assert api.get(p).status_code == 302, p  # sends guests to log in
    api.join("Pager")
    for p in MEMBER_PAGES:
        assert api.get(p).status_code == 200, p
    assert api.get("/no-such-page").status_code == 404
    assert api.get("/api/no-such-thing").get_json()["error"] == "not_found"


def test_mock_ribbon_shown(api):
    assert "Demo mode — the AI is pretend." in api.get("/").get_data(as_text=True)


def test_csrf_required_on_writes(api):
    r = api.client.post("/api/auth/join", json={"club_code": "testclub", "name": "NoToken", "pin": "1234"})
    assert r.status_code == 400 and r.get_json()["error"] == "csrf"


# ---------------------------------------------------------------- image pipeline

def test_exif_and_gps_are_removed(api, app):
    from PIL import Image
    exif = Image.Exif()
    exif[0x010F] = "SpyPhone"
    exif[0x8825] = {1: "N", 2: (40.0, 44.0, 30.0), 3: "W", 4: (73.0, 59.0, 0.0)}
    raw = drawing_bytes(exif=exif.tobytes())
    assert Image.open(io.BytesIO(raw)).getexif()  # the test photo really has EXIF
    api.join("Exify")
    r = api.post_form("/api/delegates/draft-from-image", {"image": (io.BytesIO(raw), "gps.jpg"), "answers": "{}"}).get_json()
    stored = api.get(r["image_url"]).get_data()
    img = Image.open(io.BytesIO(stored))
    assert not img.getexif() and "exif" not in img.info
    assert max(img.size) <= 1280 and len(stored) <= 1.5 * 1024 * 1024


def test_image_rules():
    from logic.security import ImageRejected, process_image
    with pytest.raises(ImageRejected) as e:
        process_image(drawing_bytes(fmt="WEBP"))
    assert e.value.code == "bad_type"
    with pytest.raises(ImageRejected) as e:
        process_image(b"x" * (15 * 1024 * 1024 + 1))
    assert e.value.code == "too_big"
    with pytest.raises(ImageRejected):
        process_image(b"definitely not an image")
    out = process_image(drawing_bytes(fmt="PNG", size=(4000, 3000)))
    assert max(out["width"], out["height"]) == 1280 and out["mime"] == "image/jpeg"


def test_temp_images_are_private(api, new_api):
    api.join("Owner")
    r = api.post_form("/api/delegates/draft-from-image", {"image": (io.BytesIO(drawing_bytes()), "d.jpg"), "answers": "{}"}).get_json()
    other = new_api()
    other.join("Snoop")
    assert other.get(r["image_url"]).status_code == 404


# ---------------------------------------------------------------- permissions matrix

def test_permissions_matrix(api, new_api):
    guest = new_api()
    member = new_api()
    editor = new_api()
    maint = api
    maint.join("Boss")
    maint.become_maintainer()
    member.join("Mem")
    e = editor.join("Eddie")
    assert maint.patch(f"/api/admin/members/{e['id']}", {"role": "editor"}).status_code == 200
    did = make_delegate(member)

    def code(client, method, path, body=None):
        fn = {"get": client.get, "post": client.post, "patch": client.patch, "delete": client.delete}[method]
        resp = fn(path) if method == "get" else fn(path, body or {})
        return resp.status_code

    # (method, path, body, {who: expected status})
    matrix = [
        ("get", "/api/me", None, {"guest": 401, "member": 200}),
        ("get", "/api/admin/moderation", None, {"guest": 401, "member": 403, "editor": 200, "maint": 200}),
        ("get", "/api/requests", None, {"guest": 401, "member": 403, "editor": 200}),
        ("get", "/api/admin/settings", None, {"member": 403, "editor": 403, "maint": 200}),
        ("patch", "/api/admin/settings", {"lock_minutes": 12}, {"editor": 403, "maint": 200}),
        ("get", "/api/admin/audit", None, {"editor": 403, "maint": 200}),
        ("get", "/api/admin/export", None, {"editor": 403, "maint": 200}),
        ("patch", "/api/admin/copy", {"overrides": {}}, {"member": 403, "editor": 200}),
        ("patch", f"/api/delegates/{did}", {"story": "edited"}, {"guest": 401, "editor": 200, "member": 200}),
        ("get", f"/api/delegates/{did}/versions", None, {"guest": 401, "editor": 200}),
        ("post", "/api/delegates", {"persona": {}}, {"guest": 401}),
        ("post", "/api/admin/ai-test/chat", None, {"editor": 403, "maint": 200}),
        ("post", "/api/human-rounds", {"seconds": 60}, {"guest": 401, "member": 200}),
    ]
    clients = {"guest": guest, "member": member, "editor": editor, "maint": maint}
    for method, path, body, expect in matrix:
        for who, status in expect.items():
            assert code(clients[who], method, path, body) == status, (who, method, path)
    # Only the owner (or a maintainer) can delete; editors can't.
    other = new_api()
    other.join("Other")
    assert other.delete(f"/api/delegates/{did}").status_code == 403
    assert editor.delete(f"/api/delegates/{did}").status_code == 403
    assert maint.delete(f"/api/delegates/{did}").status_code == 200
    # Roles: editors can't promote anyone.
    assert editor.patch(f"/api/admin/members/{e['id']}", {"role": "maintainer"}).status_code == 403
    # Someone else's round is invisible.
    rid = start_round(member).get_json()["round_id"]
    assert other.get(f"/api/rounds/{rid}").status_code == 404
    assert other.get(f"/practice/{rid}").status_code == 404


def test_private_delegates_are_hidden(api, new_api):
    api.join("Shy")
    did = make_delegate(api)
    api.patch(f"/api/delegates/{did}", {"visibility": "private"})
    other = new_api()
    assert other.get(f"/api/delegates/{did}").status_code == 404
    assert all(i["id"] != did for i in other.get("/api/delegates").get_json()["items"])
    assert api.get(f"/api/delegates/{did}").status_code == 200


def test_report_hides_until_editor_approves(api, new_api):
    api.join("Mod")
    api.become_maintainer()
    reporter = new_api()
    r = reporter.post("/api/delegates/seed-varsity-shark/report", {"reason": "test"})
    assert r.status_code == 200
    assert all(i["id"] != "seed-varsity-shark" for i in reporter.get("/api/delegates").get_json()["items"])
    items = api.get("/api/admin/moderation").get_json()["items"]
    assert any(i["id"] == "seed-varsity-shark" and i["reports"] == ["test"] for i in items)
    api.patch("/api/admin/moderation/delegate/seed-varsity-shark", {"action": "approve"})
    assert any(i["id"] == "seed-varsity-shark" for i in reporter.get("/api/delegates?limit=60").get_json()["items"])


def test_wall_moderation_approval_mode(api, new_api):
    api.join("Admin")
    api.become_maintainer()
    api.patch("/api/admin/settings", {"wall_moderation": "approval"})
    kid = new_api()
    kid.join("Kid")
    did = make_delegate(kid)
    assert kid.get(f"/api/delegates/{did}").get_json()["status"] == "pending"
    assert all(i["id"] != did for i in new_api().get("/api/delegates").get_json()["items"])


def test_join_rules(api, new_api):
    assert api.post("/api/auth/join", {"club_code": "wrong", "name": "Al", "pin": "1234"}).status_code == 400
    assert api.post("/api/auth/join", {"club_code": "testclub", "name": "Al", "pin": "12a4"}).status_code == 400
    api.join("Al")
    dup = new_api().post("/api/auth/join", {"club_code": "testclub", "name": "al", "pin": "1234"})
    assert dup.status_code == 409  # names are unique, ignoring case
    fresh = new_api()
    assert fresh.post("/api/auth/login", {"name": "AL", "pin": "9999"}).status_code == 401
    assert fresh.post("/api/auth/login", {"name": "AL", "pin": "1234"}).status_code == 200


# ---------------------------------------------------------------- rate limits

def test_rate_limit_is_friendly(api):
    for _ in range(5):
        assert api.post("/api/auth/login", {"name": "nobody", "pin": "0000"}).status_code == 401
    r = api.post("/api/auth/login", {"name": "nobody", "pin": "0000"})
    assert r.status_code == 429
    body = r.get_json()
    assert body["error"] == "slow_down" and body["retry_after"] > 0
    assert body["message"].startswith("Whoa, speedy.")


def test_ai_calls_are_rate_limited_per_member(api, app):
    api.join("Speedy")
    rid = start_round(api).get_json()["round_id"]
    codes = [api.post(f"/api/rounds/{rid}/hint").status_code for _ in range(45)]
    assert 429 in codes  # 40 AI calls / 10 minutes
