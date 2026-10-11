"""The handoff lock through the real API, with the clock frozen (BUILD_PROMPT.md sections 8.9 and 18)."""
from freezegun import freeze_time

from conftest import start_round

TUESDAY_MEETING = "2026-10-13 19:30:00"   # Tue 3:30 PM New York = inside 15:00-16:30
TUESDAY_EVENING = "2026-10-13 23:30:00"   # Tue 7:30 PM New York = home practice


def finish_round(api, **extra):
    r = start_round(api, **extra)
    assert r.status_code == 200, r.get_json()
    rid = r.get_json()["round_id"]
    assert api.post(f"/api/rounds/{rid}/turn", {"text": "Canada has a plan: a small fee and 5 years to switch."}).status_code == 200
    return api.post(f"/api/rounds/{rid}/end").get_json()


def setup_club(api, **settings):
    api.join("Officer", shared=False)  # shared devices log out after 30 idle minutes (the clock jumps here)
    api.become_maintainer()
    body = {"meeting_schedule": {"days": ["tue", "thu"], "start": "15:00", "end": "16:30"}, "timezone": "America/New_York"}
    body.update(settings)
    assert api.patch("/api/admin/settings", body).status_code == 200


def test_strict_meeting_lock_then_one_overtime(api):
    setup_club(api, handoff_mode="strict", lock_minutes=10)
    with freeze_time(TUESDAY_MEETING) as clock:
        end = finish_round(api)
        assert end["handoff"]["reason"] == "meeting" and end["handoff"]["lock_until"]
        locked = start_round(api)
        assert locked.status_code == 423
        body = locked.get_json()
        assert body["error"] == "locked" and body["overtime_available"] and "resting" in body["message"]
        # Overtime needs a confirm when no Room session is open.
        assert start_round(api, overtime=True).status_code == 423
        ok = start_round(api, overtime=True, confirm_overtime=True)
        assert ok.status_code == 200 and ok.get_json()["is_overtime"]
        rid = ok.get_json()["round_id"]
        api.post(f"/api/rounds/{rid}/turn", {"text": "Overtime: Canada would share data."})
        end2 = api.post(f"/api/rounds/{rid}/end").get_json()
        assert end2["handoff"]["overtime_available"] is False  # overtime never starts a fresh lock
        # A second overtime in the same lock is refused.
        again = start_round(api, overtime=True, confirm_overtime=True)
        assert again.status_code == 423 and again.get_json()["overtime_available"] is False
        clock.tick(11 * 60)
        assert start_round(api).status_code == 200  # the lock has ended


def test_abandoned_rounds_never_lock(api):
    setup_club(api, handoff_mode="strict")
    with freeze_time(TUESDAY_MEETING):
        rid = start_round(api).get_json()["round_id"]
        api.post(f"/api/rounds/{rid}/end", {"abandon": True})
        assert start_round(api).status_code == 200


def test_home_cap_outside_meeting_hours(api):
    setup_club(api, handoff_mode="strict", home_cap=2)
    with freeze_time(TUESDAY_EVENING):
        first = finish_round(api)
        assert first["handoff"]["reason"] == "home" and first["handoff"]["home_rounds_left"] == 1
        second = finish_round(api)
        assert second["handoff"]["home_rounds_left"] == 0
        capped = start_round(api)
        assert capped.status_code == 423 and capped.get_json()["error"] == "home_cap_reached"


def test_gentle_and_off_modes(api):
    setup_club(api, handoff_mode="gentle", home_cap=5)
    with freeze_time(TUESDAY_MEETING):
        end = finish_round(api)
        assert end["handoff"]["lock_until"] is None and end["handoff"]["reason"] == "gentle"
        assert start_round(api).status_code == 200
        # (Stay inside the frozen clock: a cookie signed "in the future" looks invalid back in real time.)
        r = api.patch("/api/admin/settings", {"handoff_mode": "off"})
        assert r.status_code == 200, r.get_json()
        assert finish_round(api)["handoff"]["reason"] == "off"


def test_handoff_screen_always_has_a_card(api):
    setup_club(api)
    with freeze_time(TUESDAY_EVENING):
        end = finish_round(api)
        html = api.get(end["url"].replace("/feedback", "").replace("/practice/", "/human?round=")).get_data(as_text=True)
        assert "Now go find a human." in html
        state = api.get("/api/handoff").get_json()
        assert state["meeting"] is False and state["home_rounds_left"] == 4
