"""The whole loop through the API in mock mode: join -> draw -> save -> round -> feedback -> handoff."""
import io
import json

from conftest import drawing_bytes, make_delegate, start_round


def test_full_loop(api):
    api.join("Sam")
    did = make_delegate(api)

    wall = api.get("/api/delegates?sort=new").get_json()
    assert any(i["id"] == did for i in wall["items"])
    assert "popular" not in json.dumps(wall)  # no ranking anywhere

    r = start_round(api, did)
    assert r.status_code == 200, r.get_json()
    rid = r.get_json()["round_id"]
    assert r.get_json()["opening"]

    answers = ["Canada would phase out single-use plastic over five years, for example with a fee on producers.",
               "That is fair. The fee is paid by the companies that make the packaging, not shoppers.",
               "Canada agrees jobs matter, so we would fund job training with part of the fee."]
    hint = api.post(f"/api/rounds/{rid}/hint").get_json()
    assert hint["idea"] and hint["ask_back"] and hint["hints_left"] == 1
    assert api.post(f"/api/rounds/{rid}/switch-sides").get_json()["switch_pending"]
    last = None
    for i, text in enumerate(answers):
        last = api.post(f"/api/rounds/{rid}/turn", {"text": text, "expected_exchange": i})
        assert last.status_code == 200, last.get_json()
        body = last.get_json()
        assert body["reply"] and body["expression"] and 1 <= body["heat"] <= 5
    assert last.get_json()["done"] is True
    # A 4th turn is refused: the round is over.
    assert api.post(f"/api/rounds/{rid}/turn", {"text": "One more?"}).status_code == 409

    end = api.post(f"/api/rounds/{rid}/end").get_json()
    fb = end["feedback"]
    norm = lambda t: " ".join(t.lower().replace(",", "").replace(".", "").split())  # noqa: E731
    assert any(norm(fb["strength_quote"]) in norm(a) for a in answers), fb["strength_quote"]
    assert fb["scores"]["perspective"] is not None  # switched sides
    assert fb["scores"]["listening"] is None
    assert end["fear"]["before"] == 100 and end["fear"]["after"] < 100
    assert end["handoff"]["reason"] in ("home", "meeting", "gentle", "off")
    # Ending twice is safe.
    assert api.post(f"/api/rounds/{rid}/end").get_json()["already"] is True

    # Human Round
    r = api.post("/api/human-rounds", {"partner_name": "Priya", "topic": "Plastic pollution", "seconds": 180,
                                       "source_round_id": rid})
    assert r.status_code == 200
    me = api.get("/api/me").get_json()
    assert me["member"]["stage"] == "microphone"
    assert me["strengths"] and me["strengths"][0]["text"] == fb["strength_quote"]
    assert me["human_rounds"] == 1
    assert me["rounds"][0]["id"] == rid

    stats = api.get("/api/stats/club").get_json()["week"]
    assert stats["rounds"] == 1 and stats["human_rounds"] == 1


def test_abandoned_round_does_not_count(api):
    api.join("Ana")
    rid = start_round(api).get_json()["round_id"]
    r = api.post(f"/api/rounds/{rid}/end", {"abandon": True}).get_json()
    assert r["abandoned"] is True
    me = api.get("/api/me").get_json()
    assert me["rounds"] == [] and me["strengths"] == []
    assert api.get("/api/stats/club").get_json()["week"]["rounds"] == 0


def test_not_a_drawing_is_never_saved(api, app):
    api.join("Blanky")
    r = api.post_form("/api/delegates/draft-from-image", {"image": (io.BytesIO(drawing_bytes(blank=True)), "blank.jpg"),
                                                          "answers": "{}"})
    body = r.get_json()
    assert body["ok"] is False and body["safety"]["status"] == "not_a_drawing"
    with app.app_context():
        from extensions import db
        from models import Image
        assert db.session.query(Image).filter(Image.kind == "temp").count() == 0  # photo thrown away


def test_unsafe_description_and_real_person(api):
    api.join("Desc")
    r = api.post("/api/delegates/draft-from-text", {"description": "a nazi with a shit attitude", "answers": {}}).get_json()
    assert r["ok"] is False and r["safety"]["status"] == "unsafe"
    r = api.post("/api/delegates/draft-from-text", {"description": "My teacher Mr. Smith who stares", "answers": {}}).get_json()
    assert r["ok"] is True and r["safety"]["renamed_from_real_person"] is True and r["note"]


def test_revise_draft_shows_diff_and_refuses_unkind_requests(api):
    api.join("Rev")
    draft = api.post("/api/delegates/draft-from-text", {"description": "a loud interrupter", "answers": {}}).get_json()["draft"]
    r = api.post("/api/delegates/revise-draft", {"persona": draft, "instruction": "make it stricter and rename it to Major Pause"}).get_json()
    fields = {c["field"] for c in r["changes"]}
    assert {"name", "base_difficulty"} <= fields
    assert r["persona"]["name"] == "Major Pause"
    r2 = api.post("/api/delegates/revise-draft", {"persona": draft, "instruction": "make it insult me"}).get_json()
    assert r2["changes"] == [] and "kind" in r2["summary"].lower()


def test_blocklisted_name_cannot_be_saved(api):
    api.join("Blocky")
    draft = api.post("/api/delegates/draft-from-text", {"description": "a calm suit", "answers": {}}).get_json()["draft"]
    draft["name"] = "The Shit Lord"
    r = api.post("/api/delegates", {"persona": draft, "visibility": "public"})
    assert r.status_code == 400 and r.get_json()["error"] == "unsafe"


def test_edit_makes_versions_and_restore(api):
    api.join("Ed")
    did = make_delegate(api)
    d = api.get(f"/api/delegates/{did}").get_json()
    p = d["persona"]
    p["name"] = "Renamed One"
    r = api.patch(f"/api/delegates/{did}", {"persona": p}).get_json()
    assert r["delegate"]["version"] == 2
    versions = api.get(f"/api/delegates/{did}/versions").get_json()["versions"]
    assert [v["version"] for v in versions] == [2, 1]
    api.post(f"/api/delegates/{did}/restore", {"version": 1})
    d = api.get(f"/api/delegates/{did}").get_json()
    assert d["version"] == 3 and d["name"] != "Renamed One"


def test_thumbs_down_becomes_pending_example_and_export(api):
    api.join("Thumb")
    did = make_delegate(api)
    rid = start_round(api, did).get_json()["round_id"]
    t = api.post(f"/api/rounds/{rid}/turn", {"text": "Plastic is bad for the ocean."}).get_json()
    r = api.post(f"/api/messages/{t['message_id']}/react", {"kind": "down", "suggestion": "Bad how? Name one country."}).get_json()
    assert r["pending_example"] is True
    d = api.get(f"/api/delegates/{did}").get_json()
    assert d["pending_examples"] == 1
    api.post(f"/api/delegates/{did}/examples", {"student_text": "We should ban it.", "ideal_reply": "Which country goes first?"})
    lines = api.get(f"/api/delegates/{did}/export.jsonl").get_data(as_text=True).strip().splitlines()
    assert len(lines) == 1
    msg = json.loads(lines[0])["messages"]
    assert [m["role"] for m in msg] == ["system", "user", "assistant"]


def test_break_character_safety_net(api):
    api.join("Care")
    rid = start_round(api).get_json()["round_id"]
    r = api.post(f"/api/rounds/{rid}/turn", {"text": "honestly i want to hurt myself"}).get_json()
    assert r["break_character"] is True and "988" in r["reply"]
    rnd = api.get(f"/api/rounds/{rid}").get_json()
    assert rnd["paused"] is True and rnd["exchanges"] == 0
    # The round can end without a lock: no completed turns -> it's just closed.
    assert api.post(f"/api/rounds/{rid}/end").get_json()["abandoned"] is True


def test_delete_my_data(api, app):
    m = api.join("Gone")
    did = make_delegate(api)
    api.post(f"/api/rounds/{start_round(api, did).get_json()['round_id']}/end", {"abandon": True})
    export = api.get("/api/me/export")
    assert export.status_code == 200 and "Gone" in export.get_data(as_text=True)
    assert api.delete("/api/me", {"public_delegates": "anonymize"}).get_json()["ok"]
    d = api.get(f"/api/delegates/{did}").get_json()
    assert d["credit"] == "Anonymous"
    with app.app_context():
        from extensions import db
        from models import Member, Round
        assert db.session.get(Member, m["id"]) is None
        assert db.session.query(Round).count() == 0


def test_guests_see_join_message_when_guest_ai_is_off(api):
    r = api.post_form("/api/delegates/draft-from-image", {"image": (io.BytesIO(drawing_bytes()), "d.jpg"), "answers": "{}"})
    assert r.status_code == 403 and r.get_json()["error"] == "guest_ai_off"
    assert start_round(api).status_code == 403
