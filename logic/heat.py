"""The thermostat (BUILD_PROMPT.md section 8.2). Pure functions, so they're easy to test."""

FILLER_STRONG_MAX = 6     # fillers per minute for a "strong" spoken turn
FILLER_STRUGGLE_MIN = 12  # more than this per minute = "struggling"


def label_turn(*, dodged, used_evidence, words, target_words, mode="type",
               fillers_per_min=None, hint_used=False):
    """Label one student turn as strong, ok, or struggling."""
    target = max(1, target_words or 1)
    speak = mode == "speak" and fillers_per_min is not None
    if dodged or words < 0.25 * target or hint_used or (speak and fillers_per_min > FILLER_STRUGGLE_MIN):
        return "struggling"
    if (not dodged) and (used_evidence or words >= 0.6 * target) and (not speak or fillers_per_min <= FILLER_STRONG_MAX):
        return "strong"
    return "ok"


def heat_range(start, gentle=False):
    """Heat can move one step either way from where the round started (never above 2 in Gentle mode)."""
    lo, hi = max(1, start - 1), min(5, start + 1)
    if gentle:
        hi = min(hi, 2)
        lo = min(lo, hi)
    return lo, hi


def next_heat(heat, streak, suggest, start, gentle=False):
    """Decide the new heat.

    streak = labels since the last time a rule fired (newest last).
    Two strong in a row -> +1. Two struggling in a row -> -1.
    The model's suggest_heat only breaks ties: when the last two turns lean one way
    (e.g. strong + ok) and the model agrees, we move that way.
    Returns (new_heat, rule_fired). When a rule fires, the caller resets the streak.
    """
    lo, hi = heat_range(start, gentle)
    step = 0
    if len(streak) >= 2:
        a, b = streak[-2], streak[-1]
        if a == b == "strong":
            step = 1
        elif a == b == "struggling":
            step = -1
        elif suggest in (1, -1):
            pair = {a, b}
            if suggest == 1 and "strong" in pair and "struggling" not in pair:
                step = 1
            elif suggest == -1 and "struggling" in pair and "strong" not in pair:
                step = -1
    new = max(lo, min(hi, heat + step))
    return new, step != 0


def max_words_for_heat(heat, format_id):
    if format_id == "points_of_information":
        return 25
    if heat <= 2:
        return 55
    if heat == 3:
        return 70
    return 60
