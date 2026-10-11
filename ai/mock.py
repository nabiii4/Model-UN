"""Mock mode: realistic pretend AI answers, with no key and no cost (BUILD_PROMPT.md section 9.5).

Everything here is deterministic enough to test, and varied enough that a demo feels real.
The answers have exactly the same shape as the real AI's answers.
"""
import colorsys
import hashlib
import json
import random
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

from ai import delivery
from logic import data

LINES = json.loads((Path(__file__).resolve().parent / "mock_lines.json").read_text(encoding="utf-8"))

TEMPLATES = {
    "interrupter": {"noun": "Interrupter", "nickname": "Point of Information!", "tactics": [("interrupts", 4), ("rhetorical_questions", 3), ("time_pressure", 3)],
                    "temperament": ["impatient", "theatrical"], "quirks": ["raises_placard_constantly"], "interrupt": 4, "silence": 0,
                    "clue": ("Something like a raised hand or a pointing finger", "Cuts in with Points of Information"),
                    "look": {"mouth": "shouting", "accessory": "placard", "hair": "spiky", "eyebrows": "raised"},
                    "catch": ["Point of information!", "Will the delegate yield?"], "voice": ("ash", "fast", 5),
                    "weakness": ("Runs out of steam if you calmly decline and keep going.", ["Calmly say 'I do not yield'", "Finish your point anyway"])},
    "stare": {"noun": "Stare", "nickname": "The Silent One", "tactics": [("silent_treatment", 4), ("so_what", 3), ("mirror", 2)],
              "temperament": ["deadpan", "mysterious"], "quirks": ["never_blinks", "dramatic_pauses"], "interrupt": 0, "silence": 3,
              "clue": ("Big, wide eyes", "Stares you down without blinking"),
              "look": {"eyes": "wide_unblinking", "mouth": "o_shape", "hair": "bald"},
              "catch": ["...And?", "I'm listening."], "voice": ("sage", "slow", 1),
              "weakness": ("Fill the silence with one clear question. It has to answer.", ["Ask one clear question", "Stay calm in the quiet"])},
    "shark": {"noun": "Shark", "nickname": "Number One", "tactics": [("demands_evidence", 4), ("rapid_stats", 4), ("yes_no_traps", 3)],
              "temperament": ["competitive", "smug"], "quirks": ["shuffles_papers"], "interrupt": 2, "silence": 0,
              "clue": ("Lots of busy lines, like stacks of paper", "Throws numbers at you fast"),
              "look": {"mouth": "toothy_grin", "accessory": "paper_stack", "outfit": "blazer_blouse", "eyes": "narrow"},
              "catch": ["Source?", "Yes or no, delegate?"], "voice": ("echo", "very_fast", 5),
              "weakness": ("Its numbers are vague. Ask where they come from.", ["Ask where the number is from", "Use one solid fact"])},
    "professor": {"noun": "Professor", "nickname": "Big Thinker", "tactics": [("thought_experiments", 5), ("analogies", 3), ("reframes_question", 3)],
                  "temperament": ["enthusiastic", "eccentric"], "quirks": ["says_relatively_speaking", "big_words_then_explains"], "interrupt": 1, "silence": 0,
                  "clue": ("Wild, swirly lines", "Thinks in big thought experiments"),
                  "look": {"hair": "wild", "eyebrows": "bushy", "facial_hair": "mustache", "outfit": "tweed_jacket", "accessory": "chalk"},
                  "catch": ["Imagine this...", "Relatively speaking..."], "voice": ("fable", "fast", 4),
                  "weakness": ("Gets lost when you bring it back to real people.", ["Use one real example", "Ask what it means for ordinary people"])},
    "note_taker": {"noun": "Note-Taker", "nickname": "Interesting...", "tactics": [("quotes_you_back", 5), ("finds_contradictions", 4)],
                   "temperament": ["skeptical", "calm"], "quirks": ["slow_interesting"], "interrupt": 1, "silence": 1,
                   "clue": ("Something that looks like a notepad", "Writes down everything you say"),
                   "look": {"glasses": "round", "eyes": "hidden_by_glasses", "accessory": "clipboard", "hair": "bun"},
                   "catch": ["Interesting...", "Earlier you said..."], "voice": ("coral", "normal", 2),
                   "weakness": ("Stay consistent and it has nothing to quote.", ["Pick one position and keep it", "Repeat your main point"])},
    "stickler": {"noun": "Stickler", "nickname": "Point of Order", "tactics": [("procedural_objections", 5), ("demands_specifics", 3)],
                 "temperament": ["stern", "overly_polite"], "quirks": ["third_person_formal"], "interrupt": 2, "silence": 0,
                 "clue": ("Straight, careful lines", "Knows every rule and uses them"),
                 "look": {"outfit": "bow_tie_vest", "accessory": "gavel", "glasses": "half_moon", "mouth": "frown"},
                 "catch": ["Point of order!", "The delegate will use the third person."], "voice": ("ballad", "normal", 3),
                 "weakness": ("Strong on rules, weak on substance. Push the real topic.", ["Use formal words once", "Then push the real topic"])},
    "suit": {"noun": "Suit", "nickname": "The Polished One", "tactics": [("pins_down_dodges", 4), ("finds_contradictions", 3), ("demands_specifics", 3)],
             "temperament": ["calm", "cold"], "quirks": ["adjusts_tie"], "interrupt": 1, "silence": 1,
             "clue": ("Neat, sharp shapes", "Polished and hard to rattle"),
             "look": {"hair": "slicked_back", "outfit": "power_suit", "eyes": "narrow", "eyebrows": "arched"},
             "catch": ["That wasn't my question.", "Let's be precise."], "voice": ("onyx", "slow", 2),
             "weakness": ("Softens when you're sincere and specific.", ["Be sincere and specific", "Give one clear example"])},
    "charmer": {"noun": "Charmer", "nickname": "Two Faces", "tactics": [("flattery_then_attack", 5), ("side_deals", 4), ("compromise_offers", 2)],
                "temperament": ["cheerful", "cold"], "quirks": ["overly_formal_greetings"], "interrupt": 1, "silence": 0,
                "clue": ("A big smile", "Friendly first, then tough"),
                "look": {"mouth": "smile", "eyes": "sparkly", "hair": "curly"},
                "catch": ["What a lovely point. However...", "Let's make a deal."], "voice": ("nova", "normal", 3),
                "weakness": ("Pin it to a clear yes-or-no commitment.", ["Ask for a yes or no", "Don't trade away your main point"])},
}

NERVOUS_TO_TEMPLATE = {
    "Being interrupted": "interrupter", "Silence": "stare", "Someone staring at me": "stare",
    "Fast talkers": "shark", "Big words": "professor", "Being asked for proof": "shark",
    "Forgetting my point": "note_taker", "Everyone watching": "suit", "Not knowing the rules": "stickler",
}
TEXT_KEYWORDS = [
    (r"interrupt|point of information|cuts? in|loud|yell|mouth", "interrupter"),
    (r"stare|eyes|blink|silent|quiet", "stare"),
    (r"number|stat|paper|fact|proof|evidence|smart|varsity|#1", "shark"),
    (r"einstein|professor|chalk|hair|formula|science|imagine", "professor"),
    (r"note|notepad|writes|glasses|clipboard", "note_taker"),
    (r"rule|gavel|procedure|order|bow tie", "stickler"),
    (r"suit|tie|shoes|polish|slick|blazer", "suit"),
    (r"smile|two face|fake|nice then|flip", "charmer"),
]
COLOR_WORDS = {"red": "Crimson", "blue": "Cobalt", "green": "Emerald", "yellow": "Golden", "orange": "Tangerine",
               "purple": "Violet", "pink": "Rose", "black": "Midnight", "gray": "Graphite", "grey": "Graphite",
               "brown": "Cocoa", "white": "Chalk"}
REAL_PERSON_RE = re.compile(r"\b(mr|mrs|ms|miss|mx|dr|coach|principal|teacher|president|senator|professor [A-Z])\b\.?", re.IGNORECASE)
COMFORT_ANSWERS = {"Typing first", "Short rounds", "Kind feedback", "A slower opponent", "No timer", "Hints", "Practicing alone first"}


def _rng(seed_text):
    return random.Random(int(hashlib.sha256(seed_text.encode("utf-8", "ignore")).hexdigest()[:12], 16))


# ------------------------------------------------------------------ drawings

def image_facts(image_bytes):
    """Color name, and whether the page looks blank (for the 'not a drawing' path).

    "Ink" = pixels clearly darker than the paper itself (or clearly colorful), so a
    light pencil sketch still counts, but a photo of an empty page doesn't.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((512, 512))
    raw = img.tobytes()  # RGB bytes (getdata() is deprecated in newer Pillow)
    pixels = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
    total = len(pixels) or 1
    lums = sorted((r * 299 + g * 587 + b * 114) // 1000 for r, g, b in pixels)
    paper = lums[len(lums) // 2]
    colorful, ink, dark = [], 0, 0
    for r, g, b in pixels:
        h, s_, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        lum = (r * 299 + g * 587 + b * 114) // 1000
        is_color = s_ > 0.35 and v > 0.25
        if is_color:
            colorful.append(h)
        if lum < paper - 35 or is_color:
            ink += 1
        if v < 0.55:
            dark += 1
    ink_share = ink / total
    blank = ink_share < 0.0005
    if len(colorful) > total * 0.01:
        hue = sorted(colorful)[len(colorful) // 2] * 360
        name = ("Crimson" if hue < 15 or hue >= 345 else "Tangerine" if hue < 40 else "Golden" if hue < 65 else
                "Emerald" if hue < 160 else "Teal" if hue < 195 else "Cobalt" if hue < 255 else "Violet" if hue < 290 else "Rose")
    else:
        name = "Graphite" if dark > total * 0.04 else "Pencil"
    return {"color": name, "blank": blank, "ink_share": round(ink_share, 4)}


def _choose_template(answers, rng, text=""):
    for pattern, key in TEXT_KEYWORDS:
        if text and re.search(pattern, text, re.IGNORECASE):
            return key
    for item in (answers or {}).get("nervous") or []:
        if item in NERVOUS_TO_TEMPLATE:
            return NERVOUS_TO_TEMPLATE[item]
    return rng.choice(sorted(TEMPLATES))


def _difficulty(answers, rng):
    comfort = set((answers or {}).get("comfortable") or [])
    if comfort & COMFORT_ANSWERS:
        return rng.choice([1, 2])
    return rng.choice([2, 3])


PALETTE_FOR_COLOR = {"Crimson": "sunset", "Tangerine": "sunset", "Golden": "highlighter", "Emerald": "mint", "Teal": "mint",
                     "Cobalt": "blue", "Violet": "grape", "Rose": "grape", "Graphite": "pencil", "Pencil": "pencil",
                     "Midnight": "ink", "Chalk": "chalkboard", "Cocoa": "pencil"}


def _build_persona(key, color, answers, rng, clue_source):
    t = TEMPLATES[key]
    nervous = [n for n in (answers or {}).get("nervous") or [] if n]
    difficulty = _difficulty(answers, rng)
    tactics = [{"id": tid, "intensity": max(1, min(5, lvl - (1 if difficulty <= 1 else 0)))} for tid, lvl in t["tactics"]]
    if "Being asked for proof" in nervous and all(x["id"] != "demands_evidence" for x in tactics):
        tactics.append({"id": "demands_evidence", "intensity": 2})
    if "Being interrupted" in nervous and all(x["id"] != "interrupts" for x in tactics):
        tactics.append({"id": "interrupts", "intensity": 2})
    look = {"style": "sketch", "hair": "side_part", "eyebrows": "flat", "eyes": "round", "glasses": "none", "mouth": "flat",
            "facial_hair": "none", "headwear": "none", "outfit": "navy_suit", "accessory": "none", "skin_tone": "sketch",
            "palette": PALETTE_FOR_COLOR.get(color, "pencil")}
    look.update(t["look"])
    name = f"The {color} {t['noun']}"
    clues = [
        {"saw": clue_source, "means": "Bold and hard to ignore"},
        {"saw": t["clue"][0], "means": t["clue"][1]},
    ]
    if nervous:
        clues.append({"saw": f"You said '{nervous[0].lower()}' makes you nervous", "means": "It does that, but at a level you can handle"})
    else:
        clues.append({"saw": "The way it's posed", "means": f"Feels {data.label(t['temperament'][0]).lower()}"})
    voice_id, pace, energy = t["voice"]
    return {
        "safety": {"status": "ok", "renamed_from_real_person": False, "note": None},
        "name": name,
        "nickname": t["nickname"],
        "alt_text": f"A drawing of a debate delegate the student calls {name}."[:125],
        "clues": clues[:4],
        "one_liner": {"interrupter": "Has a question before you finish your sentence.",
                      "stare": "Stares in silence until you say too much.",
                      "shark": "Fires numbers faster than you can check them.",
                      "professor": "Turns every point into a thought experiment.",
                      "note_taker": "Writes down everything and reads it back later.",
                      "stickler": "Knows every rule and reminds you of all of them.",
                      "suit": "Never raises its voice. Never lets a dodge slide.",
                      "charmer": "Compliments you, then flips the table."}[key],
        "temperament": list(t["temperament"]),
        "quirks": list(t["quirks"]),
        "catchphrases": list(t["catch"]),
        "tactics": tactics[:5],
        "interrupt_level": t["interrupt"],
        "silence_seconds": t["silence"],
        "base_difficulty": difficulty,
        "voice": {"tts_voice": voice_id, "pace": pace, "energy": energy,
                  "tone": f"Sounds {data.label(t['temperament'][0]).lower()} and {data.label(t['temperament'][-1]).lower()}."},
        "look": dict(look, summary=f"A {color.lower()} sketch of a {t['noun'].lower()}."),
        "weakness": {"description": t["weakness"][0], "how_to_beat": list(t["weakness"][1]) + ["Stay calm and keep going"]},
    }


def persona_from_image(image_bytes, answers):
    facts = image_facts(image_bytes)
    rng = _rng(hashlib.sha256(image_bytes).hexdigest())
    if facts["blank"]:
        draft = _build_persona("suit", "Pencil", answers, rng, "A mostly empty page")
        draft["safety"] = {"status": "not_a_drawing", "renamed_from_real_person": False, "note": "The page looks blank."}
        return draft
    key = _choose_template(answers, rng)
    clue_source = f"Lots of {facts['color'].lower()} lines" if facts["color"] not in ("Pencil", "Graphite") else "Dark pencil lines"
    return _build_persona(key, facts["color"], answers, rng, clue_source)


def persona_from_text(description, answers):
    from logic.security import contains_blocked
    rng = _rng(description)
    if contains_blocked(description):
        draft = _build_persona("suit", "Pencil", answers, rng, "Your description")
        draft["safety"] = {"status": "unsafe", "renamed_from_real_person": False, "note": None}
        return draft
    color = next((name for word, name in COLOR_WORDS.items() if re.search(rf"\b{word}\b", description, re.IGNORECASE)), "Pencil")
    key = _choose_template(answers, rng, text=description)
    draft = _build_persona(key, color, answers, rng, "Your description")
    words = delivery.limit_words(description, 8).rstrip("…")
    draft["clues"][0] = {"saw": f"You wrote: '{words}'", "means": "That's the heart of this character"}
    if REAL_PERSON_RE.search(description):
        draft["safety"] = {"status": "ok", "renamed_from_real_person": True,
                           "note": "This might be a real person, so it's an original character instead."}
    return draft


# ------------------------------------------------------------------ trainer ("Not quite?")

TACTIC_WORDS = {o["label"].lower(): o["id"] for o in data.traits()["by_category"]["tactic"]}


def revise_persona(persona, instruction):
    p = json.loads(json.dumps(persona))
    text = instruction.lower()
    changes, refused = [], []

    def change(field, before, after, why):
        changes.append({"field": field, "before": str(before), "after": str(after), "why": why})

    if re.search(r"\b(insult|rude|curse|swear|mean to me|make fun|bully)\b", text):
        refused.append("I kept it kind to people (tough on arguments only)")
    if REAL_PERSON_RE.search(instruction) or "my teacher" in text or "classmate" in text:
        refused.append("I kept it an original character, not a real person")

    m = re.search(r"(?:rename(?: it)? to|call it|name it|named)\s+[\"']?([A-Za-z][A-Za-z' -]{1,40})", instruction, re.IGNORECASE)
    if m and not refused:
        new = " ".join(m.group(1).strip().split()[:4])
        change("name", p["name"], new, "You asked for a new name.")
        p["name"] = new

    if re.search(r"(interrupt(s)? less|less interrupt|stop interrupt|fewer interrupt|don'?t interrupt)", text):
        before = p.get("interrupt_level", 0)
        p["interrupt_level"] = max(0, before - 2)
        change("interrupt_level", before, p["interrupt_level"], "Interrupts less, like you asked.")
        for t in p.get("tactics", []):
            if t["id"] == "interrupts":
                t["intensity"] = max(0, t["intensity"] - 2)
    elif re.search(r"(interrupt(s)? more|more interrupt)", text):
        before = p.get("interrupt_level", 0)
        p["interrupt_level"] = min(5, before + 2)
        change("interrupt_level", before, p["interrupt_level"], "Interrupts more, like you asked.")

    if re.search(r"\b(harder|tougher|stricter|scarier|more intense|meaner)\b", text) and "insult" not in text:
        before = p.get("base_difficulty", 2)
        p["base_difficulty"] = min(5, before + 1)
        change("base_difficulty", before, p["base_difficulty"], "A bit tougher.")
    if re.search(r"\b(easier|nicer|kinder|gentler|softer|less scary|friendlier)\b", text):
        before = p.get("base_difficulty", 2)
        p["base_difficulty"] = max(1, before - 1)
        change("base_difficulty", before, p["base_difficulty"], "A bit gentler.")
    if re.search(r"\b(faster|quicker)\b", text):
        change("voice.pace", p["voice"]["pace"], "fast", "Talks faster.")
        p["voice"]["pace"] = "fast"
    if re.search(r"\b(slower|slow down)\b", text):
        change("voice.pace", p["voice"]["pace"], "slow", "Talks slower.")
        p["voice"]["pace"] = "slow"

    for label, tid in TACTIC_WORDS.items():
        if label in text and all(t["id"] != tid for t in p.get("tactics", [])) and len(p.get("tactics", [])) < 5:
            p["tactics"].append({"id": tid, "intensity": 3})
            change("tactics", "-", f"{label} (3/5)", "Added the tactic you named.")

    if not changes and not refused:
        rules = p.setdefault("training", {}).setdefault("rules", [])
        rule = "Always: " + instruction.strip().rstrip(".")[:110]
        before = "; ".join(rules) or "(none)"
        rules.append(rule)
        change("training.rules", before, rule, "Saved your request as a rule it always follows.")

    if refused:
        summary = "Done. " + "; ".join(refused) + "."
        if not changes:
            summary = "I couldn't do that part: " + "; ".join(refused) + ". Try another change?"
    else:
        summary = f"Updated {len(changes)} thing{'s' if len(changes) != 1 else ''} to match your request."
    return {"summary": delivery.limit_words(summary, 25).rstrip("…"), "changes": changes, "persona": p}


# ------------------------------------------------------------------ rounds

SUBTOPICS = ["Funding and who pays", "The first year of action", "Helping the countries most affected",
             "Checking that promises are kept", "Working with local communities"]
HUMAN_QUESTIONS = [
    "Should countries solve {topic_l} alone, or only together?",
    "Who should pay the most to fix {topic_l}, and why?",
    "What is the first thing the world should do about {topic_l}?",
    "Is it fair to ask every country to act the same way on {topic_l}?",
]


def _fill(text, ctx, quote=""):
    return (text.replace("{country}", ctx.get("their_country", "my country"))
                .replace("{student_country}", ctx.get("my_country", "your country"))
                .replace("{topic}", ctx.get("topic", "this topic").lower() if text.find("{topic}") > 0 else ctx.get("topic", "This topic"))
                .replace("{quote}", quote or "that"))


def round_opening(persona, ctx):
    rng = _rng(ctx.get("seed", "") + persona.get("name", ""))
    fmt = ctx["format"]
    topic_l = ctx["topic"].lower()
    subtopic = rng.choice(SUBTOPICS) if fmt == "moderated_caucus" else None
    greeting = "Honorable delegate of" if "overly_formal_greetings" in persona.get("quirks", []) else "Delegate of"
    if fmt == "opening_speech":
        opening = None
    elif fmt == "points_of_information":
        opening = f"{greeting} {ctx['my_country']}, first question: what is your country's main goal on {topic_l}?"
    elif fmt == "moderated_caucus":
        opening = (f"On {subtopic.lower()}, {ctx['their_country']} has a simple view: talk is cheap. "
                   f"{greeting} {ctx['my_country']}, what will you actually do?")
    else:
        catch = persona.get("catchphrases", [""])[0]
        opening = (f"{greeting} {ctx['my_country']}, {ctx['their_country']} has serious doubts about how this room "
                   f"handles {topic_l}. {catch} What is your plan, and who pays for it?")
    pois = ["Point of information: who pays for that?", "Point of information: which countries agree?",
            "Point of information: how long will that take?"]
    return {
        "opening": delivery.limit_words(opening, 60).rstrip("…") if opening else None,
        "pois": pois,
        "human_round_question": rng.choice(HUMAN_QUESTIONS).replace("{topic_l}", topic_l),
        "bloc_must_haves": None,
        "caucus_subtopic": subtopic,
    }


def _snippet(student_text):
    ss = delivery.sentences(student_text) or [student_text]
    longest = max(ss, key=lambda s: len(s.split()))
    words = longest.split()[:8]
    return " ".join(words).rstrip(".,!?;:")


def _pick_tactic(persona, rng):
    tactics = [t for t in persona.get("tactics", []) if t["id"] in LINES["tactics"] and t["intensity"] > 0]
    if not tactics:
        return None
    weights = [t["intensity"] ** 2 for t in tactics]
    return rng.choices(tactics, weights=weights, k=1)[0]["id"]


def debate_turn(persona, ctx, student_text, heat, turn_index, switched=False, time_up=False):
    rng = _rng(f"{ctx.get('seed', '')}:{turn_index}:{student_text}")
    fmt = data.format_info(ctx["format"])
    words = delivery.word_count(student_text)
    dodged = words < max(5, int(0.12 * fmt["target_words"]))
    evidence = delivery.looks_like_evidence(student_text)
    quote = _snippet(student_text)
    line_ctx = dict(ctx)
    if switched:
        line_ctx["their_country"], line_ctx["my_country"] = ctx["my_country"], ctx["their_country"]
    tactic = "none"
    if dodged and heat >= 2:
        line = rng.choice(LINES["dodge"])
        if any(t["id"] == "pins_down_dodges" for t in persona.get("tactics", [])):
            tactic = "pins_down_dodges"
    elif heat <= 1 or (heat == 2 and rng.random() < 0.35):
        line = LINES["gentle"][turn_index % len(LINES["gentle"])]
    elif evidence and rng.random() < 0.3:
        line = rng.choice(LINES["evidence_ok"])
    else:
        tactic = _pick_tactic(persona, rng) or "none"
        pool = LINES["tactics"].get(tactic) or LINES["gentle"]
        offset = int(hashlib.sha256((ctx.get("seed", "") + tactic).encode()).hexdigest()[:4], 16)
        line = pool[(offset + turn_index) % len(pool)]
    text = _fill(line["text"], line_ctx, quote)
    quirks = persona.get("quirks", [])
    if heat >= 2 and rng.random() < 0.25 and persona.get("catchphrases"):
        text = f"{rng.choice(persona['catchphrases'])} {text}"
    if "slow_interesting" in quirks and rng.random() < 0.4:
        text = "Interesting... " + text
    if "says_relatively_speaking" in quirks and rng.random() < 0.3:
        text = "Relatively speaking, " + text[0].lower() + text[1:]
    if "ends_with_question" in quirks and not text.rstrip().endswith("?"):
        text += " Your answer, delegate?"
    if heat >= 4:
        parts = delivery.sentences(text)
        text = " ".join(parts[:2])
    if time_up and heat >= 4:
        text = "Time, delegate. " + text
    if fmt["id"] == "points_of_information" and "?" not in text:
        text += " Next question: what would you do first?"
    suggest = 1 if (evidence and words >= 0.5 * fmt["target_words"]) else (-1 if dodged else 0)
    return {
        "reply": delivery.limit_words(text, 70).rstrip("…"),
        "expression": line.get("expression", "neutral"),
        "eyebrows": line.get("eyebrows", 0),
        "tactic_used": tactic,
        "student_dodged": dodged,
        "student_used_evidence": evidence,
        "suggest_heat": suggest,
        "break_character": False,
    }


def hint(ctx, delegate_text):
    t = (delegate_text or "").lower()
    if re.search(r"pay|cost|money|fund|budget|price", t):
        idea = "Say who pays: maybe the companies, or a shared fund for poorer countries."
        ask = "Who would {country} want to pay?"
    elif re.search(r"source|evidence|proof|data|number|prove", t):
        idea = "Give one real example from {student_country} or a country you know."
        ask = "Where do your numbers come from?"
    elif re.search(r"when|time|how long|deadline|year", t):
        idea = "Name a simple timeline: start small this year, grow over five years."
        ask = "What timeline would {country} accept?"
    elif re.search(r"yes or no|yield", t):
        idea = "You can say 'The delegate does not yield' and finish your point calmly."
        ask = "Can I finish my point first?"
    else:
        idea = "Agree with one small part, then explain your main point in one sentence."
        ask = "Which part of my plan worries you most?"
    fill = lambda s: s.replace("{country}", ctx.get("their_country", "your country")).replace(
        "{student_country}", ctx.get("my_country", "your country"))
    return {"idea": delivery.limit_words(fill(idea), 20).rstrip("…"), "ask_back": delivery.limit_words(fill(ask), 15).rstrip("…")}


POLITE = re.compile(r"\b(thank|agree|together|respect|appreciate|delegate|support|work with|fair)\b", re.IGNORECASE)


def feedback(persona, ctx, transcript, final_heat, switched, delivery_stats=None):
    student = [m["text"] for m in transcript if m["role"] == "student" and m["text"].strip()]
    all_sentences = [s for t in student for s in delivery.sentences(t)]
    if not all_sentences:
        all_sentences = ["I showed up and tried."]
    best = max(all_sentences, key=lambda s: (len(s.split()), delivery.looks_like_evidence(s)))
    quote = " ".join(best.split()[:25])
    if delivery.looks_like_evidence(quote):
        why = "You used a real detail, so your point felt solid."
        strength = "examples"
    elif "yield" in quote.lower():
        why = "You stayed calm and kept your point."
        strength = "calm"
    elif quote.endswith("?"):
        why = "You asked a sharp question and took control."
        strength = "questions"
    else:
        why = "You said it clearly, in your own words."
        strength = "clarity"

    turns = len(student) or 1
    avg_words = sum(delivery.word_count(t) for t in student) / turns
    sent_len = sum(len(s.split()) for s in all_sentences) / len(all_sentences)
    evidence_turns = sum(1 for t in student if delivery.looks_like_evidence(t))
    short_turns = sum(1 for t in student if delivery.word_count(t) < 8)
    polite = sum(1 for t in student if POLITE.search(t))

    clarity = 4 if 6 <= sent_len <= 22 else 3
    evidence = min(5, 2 + evidence_turns) if evidence_turns else 2
    answering = max(1, min(5, 5 - short_turns - (1 if avg_words < 15 else 0)))
    diplomacy = min(5, 3 + (1 if polite else 0) + (1 if polite >= 2 else 0))
    scores = {
        "clarity": {"score": clarity, "reason": "Short sentences, easy to follow." if clarity >= 4 else "Some sentences ran long or very short."},
        "evidence": {"score": evidence, "reason": "You backed up your points." if evidence >= 4 else "Add one real example or number."},
        "answering": {"score": answering, "reason": "You answered what was asked." if answering >= 4 else "Answer their question first, then add yours."},
        "diplomacy": {"score": diplomacy, "reason": "Polite and ready to work together." if diplomacy >= 4 else "Try one friendly line, like 'I agree that...'."},
        "listening": None,
        "perspective": {"score": 4, "reason": "You argued the other side. That takes flexibility."} if switched else None,
    }
    weakest = min(("evidence", "answering", "clarity", "diplomacy"), key=lambda k: scores[k]["score"])
    fixes = {
        "evidence": ("Add one example", f"You already {'explain clearly' if strength != 'examples' else 'use examples'}. Use that same skill to add one real example or number to each answer.", "Start one answer with 'For example...'"),
        "answering": ("Answer first", "You speak well. Use that to answer their exact question in your first sentence, then make your point.", "Begin with 'Yes,' 'No,' or 'Here's how.'"),
        "clarity": ("One idea per sentence", "You have good ideas. Give each one its own short sentence so it lands.", "Say your main point in under 15 words."),
        "diplomacy": ("Find common ground", "You make your point well. Add one line that agrees with them before you push back.", "Try 'I agree that... but...'"),
    }
    focus, how, try_next = fixes[weakest]
    if scores[weakest]["score"] >= 4:
        # Everything went well: level up the strength itself (the spec's own example).
        focus, how, try_next = ("Lead with your example",
                                "You already use great examples. Next time, put the example in your first sentence "
                                "so your point lands faster.", "Start your next answer with 'For example…'")
    short_round = turns <= 1
    return {
        "strength_quote": quote,
        "strength_why": why,
        "fix_focus": focus,
        "fix_how": how,
        "try_next_time": try_next,
        "scores": scores,
        "encouragement": ("Short rounds count too. You showed up and spoke. Now go try it on a human."
                          if short_round else "That was a real debate. Now go try it on a human."),
    }
