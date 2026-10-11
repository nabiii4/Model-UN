"""Seed content, persona validation, config, and backups."""
import pytest
from pydantic import ValidationError

from ai.persona import normalize_persona
from conftest import make_delegate, start_round
from logic import data


def test_seed_content_counts():
    assert len(data.load_json("traits.json")["options"]) >= 200
    assert len(data.countries()) == 195
    assert "Holy See" in data.countries() and "State of Palestine" in data.countries()
    assert len(data.seeds()) == 9
    assert len(data.ids("tactic")) == 36
    for seed in data.seeds():
        persona, dropped = normalize_persona({k: v for k, v in seed.items() if k not in ("id", "image", "story", "opens_blank")})
        assert dropped == [], (seed["id"], dropped)


def test_seed_is_safe_to_run_twice(app):
    with app.app_context():
        from extensions import db
        from logic.seeding import count_seeds, seed_all
        from models import Delegate, DelegateVersion
        seed_all()
        seed_all()
        assert count_seeds() == 9
        assert db.session.query(DelegateVersion).filter(DelegateVersion.delegate_id.like("seed-%")).count() == 9
        assert db.session.get(Delegate, "seed-interrupter").drawing_image_id


def base_persona():
    return {k: v for k, v in data.seeds()[0].items() if k not in ("id", "image", "story", "opens_blank")}


def test_persona_unknown_ids_dropped_and_limits_clamped():
    p = base_persona()
    p.update(name="One Two Three Four Five Six", temperament=["calm", "made_up", "cold", "smug", "stern"],
             quirks=["never_blinks", "fake_quirk"], interrupt_level=12, silence_seconds=-3, base_difficulty="9",
             tactics=[{"id": "interrupts", "intensity": 9}, {"id": "laser_eyes", "intensity": 3}],
             catchphrases=["one two three four five six seven eight nine ten eleven twelve"],
             clues=[{"saw": "x", "means": "y"}] * 6)
    p["voice"]["tts_voice"] = "darth"
    p["look"]["hair"] = "rainbow"
    out, dropped = normalize_persona(p)
    assert out["name"] == "One Two Three Four"
    assert out["temperament"] == ["calm", "cold", "smug"]
    assert out["quirks"] == ["never_blinks"]
    assert out["interrupt_level"] == 5 and out["silence_seconds"] == 0 and out["base_difficulty"] == 5
    assert out["tactics"][0] == {"id": "interrupts", "intensity": 5} and len(out["tactics"]) == 2  # padded to 2
    assert len(out["catchphrases"]) == 2 and len(out["catchphrases"][0].split()) == 10
    assert len(out["clues"]) == 4
    assert out["voice"]["tts_voice"] == "alloy" and out["look"]["hair"] == "side_part"
    assert {"temperament:made_up", "tactic:laser_eyes", "voice:darth", "look.hair:rainbow"} <= set(dropped)


def test_persona_with_wrong_shape_raises():
    with pytest.raises(ValidationError):
        normalize_persona({"name": "x", "tactics": "not a list"})


def test_config_postgres_url_and_placeholders():
    from config import Config
    c = Config({"SKIP_DOTENV": "1", "TESTING": "1", "DATABASE_URL": "postgres://u:p@host/db"})
    assert c.database_url == "postgresql+psycopg://u:p@host/db"
    c = Config({"SKIP_DOTENV": "1", "TESTING": "1", "DATABASE_URL": "postgresql://u:p@host/db", "CLUB_CODE": "pick-a-club-code"})
    assert c.database_url.startswith("postgresql+psycopg://")
    assert c.club_code == "blanksheet" and c.club_code_is_default
    c = Config({"SKIP_DOTENV": "1", "TESTING": "1", "TIMEZONE": "Mars/Olympus", "PORT": "abc"})
    assert c.timezone == "America/New_York" and c.port == 5000


def test_backup_export_wipe_import(api, app):
    api.join("Backer")
    api.become_maintainer()
    did = make_delegate(api)
    rid = start_round(api, did).get_json()["round_id"]
    api.post(f"/api/rounds/{rid}/turn", {"text": "A plan with 2 steps."})
    api.post(f"/api/rounds/{rid}/end")
    blob = api.get("/api/admin/export").get_data()
    with app.app_context():
        from extensions import db
        from logic.backup import import_zip
        from models import Delegate, DelegateVersion, Image, Member, Round
        before = {m.__name__: db.session.query(m).count() for m in (Member, Delegate, DelegateVersion, Image, Round)}
        for m in (Round, DelegateVersion, Delegate, Image, Member):
            db.session.query(m).delete()
        db.session.commit()
        assert db.session.query(Member).count() == 0
        import_zip(blob)
        after = {m.__name__: db.session.query(m).count() for m in (Member, Delegate, DelegateVersion, Image, Round)}
        assert before == after
        assert db.session.get(Delegate, did).drawing_image_id
