"""Game rules: heat, fear meter, journey stages, handoff lock, delivery stats, quotes."""
from datetime import datetime, timedelta

from ai import delivery
from logic import fear, heat, journey
from logic.handoff import check_start, compute_handoff
from logic.schedule import in_meeting

# ---------------------------------------------------------------- heat (section 8.2)


def test_label_turn():
    assert heat.label_turn(dodged=False, used_evidence=True, words=20, target_words=60) == "strong"
    assert heat.label_turn(dodged=False, used_evidence=False, words=40, target_words=60) == "strong"
    assert heat.label_turn(dodged=False, used_evidence=False, words=20, target_words=60) == "ok"
    assert heat.label_turn(dodged=True, used_evidence=True, words=80, target_words=60) == "struggling"
    assert heat.label_turn(dodged=False, used_evidence=False, words=10, target_words=60) == "struggling"
    assert heat.label_turn(dodged=False, used_evidence=True, words=50, target_words=60, hint_used=True) == "struggling"
    assert heat.label_turn(dodged=False, used_evidence=True, words=50, target_words=60, mode="speak", fillers_per_min=13) == "struggling"
    assert heat.label_turn(dodged=False, used_evidence=True, words=50, target_words=60, mode="speak", fillers_per_min=8) == "ok"


def test_heat_two_in_a_row_and_range():
    assert heat.next_heat(3, ["strong", "strong"], 0, 3) == (4, True)
    assert heat.next_heat(3, ["struggling", "struggling"], 0, 3) == (2, True)
    assert heat.next_heat(3, ["strong"], 1, 3) == (3, False)          # needs two turns
    assert heat.next_heat(4, ["strong", "strong"], 0, 3) == (4, True)  # capped at start + 1
    assert heat.next_heat(1, ["struggling", "struggling"], 0, 1) == (1, True)


def test_suggest_heat_only_breaks_ties():
    assert heat.next_heat(3, ["strong", "ok"], 1, 3) == (4, True)
    assert heat.next_heat(3, ["strong", "ok"], -1, 3) == (3, False)
    assert heat.next_heat(3, ["ok", "struggling"], -1, 3) == (2, True)
    assert heat.next_heat(3, ["strong", "struggling"], 1, 3) == (3, False)
    assert heat.next_heat(3, ["ok", "ok"], 1, 3) == (3, False)


def test_gentle_mode_never_above_two():
    assert heat.heat_range(2, gentle=True) == (1, 2)
    assert heat.next_heat(2, ["strong", "strong"], 1, 2, gentle=True) == (2, True)


# ---------------------------------------------------------------- fear meter (section 8.4)

def test_fear_meter_math():
    assert fear.fear_after_round(100, final_heat=2, base_difficulty=3) == (90, 10)
    assert fear.fear_after_round(100, final_heat=3, base_difficulty=3) == (85, 15)
    assert fear.fear_after_round(100, final_heat=3, base_difficulty=3, mode="speak") == (80, 20)
    assert fear.fear_after_round(100, final_heat=4, base_difficulty=3, mode="speak", avg_listening=2) == (75, 25)
    assert fear.fear_after_round(10, final_heat=5, base_difficulty=1) == (0, 15)  # floor 0


# ---------------------------------------------------------------- journey stages

def test_stages_never_go_backward():
    s = journey.advance_stage("pockets", "typed_round")
    assert s == "keyboard"
    s = journey.advance_stage(s, "human_round")
    assert s == "microphone"
    assert journey.advance_stage(s, "typed_round") == "microphone"
    assert journey.advance_stage(s, "joined") == "microphone"


# ---------------------------------------------------------------- handoff lock (section 8.9)

NOW = datetime(2026, 10, 13, 19, 30)  # a Tuesday, 3:30 PM in New York (UTC-4)
SCHEDULE = {"days": ["tue", "thu"], "start": "15:00", "end": "16:30"}


def test_meeting_hours_use_the_club_time_zone():
    assert in_meeting(NOW, SCHEDULE, "America/New_York")
    assert not in_meeting(NOW + timedelta(hours=2), SCHEDULE, "America/New_York")
    assert not in_meeting(NOW + timedelta(days=1), SCHEDULE, "America/New_York")  # Wednesday


def test_compute_handoff_modes():
    strict = compute_handoff(now=NOW, mode="strict", meeting=True, lock_minutes=10, home_cap=5, ai_rounds_today=1, is_overtime=False)
    assert strict["lock_until"].startswith("2026-10-13T19:40") and strict["overtime_available"]
    home = compute_handoff(now=NOW, mode="strict", meeting=False, lock_minutes=10, home_cap=5, ai_rounds_today=2, is_overtime=False)
    assert home["lock_until"] is None and home["home_rounds_left"] == 3 and home["reason"] == "home"
    gentle = compute_handoff(now=NOW, mode="gentle", meeting=True, lock_minutes=10, home_cap=5, ai_rounds_today=1, is_overtime=False)
    assert gentle["lock_until"] is None and gentle["home_rounds_left"] == 4
    off = compute_handoff(now=NOW, mode="off", meeting=True, lock_minutes=10, home_cap=5, ai_rounds_today=9, is_overtime=False)
    assert off["lock_until"] is None and off["reason"] == "off"
    lock = NOW + timedelta(minutes=8)
    over = compute_handoff(now=NOW, mode="strict", meeting=True, lock_minutes=10, home_cap=5, ai_rounds_today=2,
                           is_overtime=True, existing_lock_until=lock)
    assert over["lock_until"].startswith("2026-10-13T19:38") and not over["overtime_available"]


def test_check_start_rules():
    lock = NOW + timedelta(minutes=5)
    base = dict(now=NOW, mode="strict", meeting=True, active_lock_until=lock, overtime_used=False,
                overtime_requested=False, overtime_status="confirm", overtime_confirmed=False, home_cap=5, ai_rounds_today=1)
    ok, _, err = check_start(**base)
    assert not ok and err["error"] == "locked" and err["overtime_available"]
    ok, overtime, _ = check_start(**{**base, "overtime_requested": True, "overtime_confirmed": True})
    assert ok and overtime
    ok, _, err = check_start(**{**base, "overtime_requested": True, "overtime_confirmed": True, "overtime_used": True})
    assert not ok  # one overtime per lock
    ok, _, _ = check_start(**{**base, "overtime_requested": True, "overtime_status": "no", "overtime_confirmed": True})
    assert not ok  # you have a human partner in today's Room
    ok, _, _ = check_start(**{**base, "active_lock_until": NOW - timedelta(seconds=1)})
    assert ok  # lock over
    ok, _, err = check_start(**{**base, "meeting": False, "ai_rounds_today": 5})
    assert not ok and err["error"] == "home_cap_reached"
    ok, _, _ = check_start(**{**base, "mode": "off", "ai_rounds_today": 50})
    assert ok


# ---------------------------------------------------------------- delivery stats + quotes (section 8.8)

def test_words_per_minute_and_fillers():
    text = "Um so I think, uh, we should like start. You know, basically the plan is hmm simple."
    assert delivery.words_per_minute("one two three four five six", 3) == 120
    c = delivery.filler_counts(text)
    assert c["strong"] == 3 and c["soft"] == 3
    assert delivery.fillers_per_minute(text, 30) == 12.0
    assert delivery.filler_counts("Ummm and uhhh") == {"strong": 2, "soft": 0}
    assert delivery.filler_counts("I liked the umbrella")["strong"] == 0


def test_strength_quote_must_be_real():
    student = ["We would phase it in over five years.", "The fee is paid by the companies, not shoppers."]
    assert delivery.verify_quote("the FEE is paid by the companies,  not shoppers", student) == "the FEE is paid by the companies,  not shoppers"
    fixed = delivery.verify_quote("Companies pay the fee instead of shoppers, I said.", student)
    assert fixed == "The fee is paid by the companies, not shoppers."
