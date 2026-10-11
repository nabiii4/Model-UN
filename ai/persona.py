"""Builds prompts from a persona, and cleans up personas (from the AI or from the edit form).

Why cleaning matters: the AI (or a student editing a card) can send an unknown trait id,
a 9-word name, or intensity 12. We fix those quietly instead of crashing.
"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from ai.schemas import PersonaCore
from logic import data

log = logging.getLogger("nightmare.persona")
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

LOOK_SLOTS = ["style", "hair", "eyebrows", "eyes", "glasses", "mouth", "facial_hair", "headwear",
              "outfit", "accessory", "skin_tone", "palette"]
LOOK_DEFAULTS = {"style": "sketch", "hair": "side_part", "eyebrows": "flat", "eyes": "round", "glasses": "none",
                 "mouth": "flat", "facial_hair": "none", "headwear": "none", "outfit": "navy_suit",
                 "accessory": "none", "skin_tone": "sketch", "palette": "pencil"}
PACES = ["slow", "normal", "fast", "very_fast"]
FALLBACK_TACTICS = [{"id": "demands_specifics", "intensity": 2}, {"id": "so_what", "intensity": 2}]

# ------------------------------------------------------------------ prompt files


@lru_cache(maxsize=None)
def load_prompt(name):
    """Returns {section_name: text} from ai/prompts/<name>.md."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    sections, current, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^=== (\w+) ===\s*$", line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            current, buf = m.group(1), []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


def fill(template, **values):
    """Replace {name} only for names we were given, so JSON examples with braces stay intact."""
    def sub(m):
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)
    return re.sub(r"\{([a-z_]+)\}", sub, template)


# ------------------------------------------------------------------ small text helpers

_CTRL = re.compile(r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]")


def _clean(s):
    return _CTRL.sub("", str(s or "")).strip()


def limit_words(s, n):
    words = _clean(s).split()
    return " ".join(words[:n])


def limit_chars(s, n):
    s = re.sub(r"\s+", " ", _clean(s))
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut or s[:n]


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ normalizing

def normalize_persona(raw, *, keep_training=None):
    """Validate types with Pydantic, then clamp every limit from section 10.1.

    Returns (persona_dict, dropped_ids). Raises pydantic.ValidationError only if the
    overall shape is wrong (that triggers one repair call for AI output).
    """
    if isinstance(raw, PersonaCore):
        core = raw
    else:
        raw = dict(raw or {})
        filled = _fill_missing(raw)
        core = PersonaCore.model_validate(filled)
    dropped = []
    tactic_ids = set(data.ids("tactic"))
    temperament_ids = set(data.ids("temperament"))
    quirk_ids = set(data.ids("quirk"))
    voices = data.tts_voices()

    name = limit_chars(limit_words(core.name, 4), 40) or "The Mystery Delegate"
    nickname = limit_chars(limit_words(core.nickname, 4), 40)

    clues = []
    for c in core.clues[:4]:
        saw, means = limit_words(c.saw, 12), limit_words(c.means, 12)
        if saw and means:
            clues.append({"saw": saw, "means": means})
    while len(clues) < 2:
        clues.append([{"saw": "Your drawing", "means": "A one-of-a-kind opponent"},
                      {"saw": "Your answers", "means": "Tuned to what makes you nervous"}][len(clues)])

    def keep(ids, allowed, lo, hi, label):
        out = []
        for i in ids:
            i = _clean(i)
            if i in allowed and i not in out:
                out.append(i)
            elif i not in allowed:
                dropped.append(f"{label}:{i}")
        return out[:hi]

    temperament = keep(core.temperament, temperament_ids, 1, 3, "temperament") or ["calm"]
    quirks = keep(core.quirks, quirk_ids, 0, 3, "quirk")

    catchphrases = [limit_words(c, 10) for c in core.catchphrases if _clean(c)][:3]
    for filler in ["Interesting point, delegate.", "Let's see you prove it."]:
        if len(catchphrases) >= 2:
            break
        if filler not in catchphrases:
            catchphrases.append(filler)

    tactics, seen = [], set()
    for t in core.tactics:
        tid = _clean(t.id)
        if tid in tactic_ids and tid not in seen:
            tactics.append({"id": tid, "intensity": _clamp(t.intensity, 0, 5, 3)})
            seen.add(tid)
        elif tid not in tactic_ids:
            dropped.append(f"tactic:{tid}")
    tactics = tactics[:5]
    for fb in FALLBACK_TACTICS:
        if len(tactics) >= 2:
            break
        if fb["id"] not in seen:
            tactics.append(dict(fb))
            seen.add(fb["id"])

    tts_voice = _clean(core.voice.tts_voice).lower()
    if tts_voice not in voices:
        dropped.append(f"voice:{tts_voice}")
        tts_voice = "alloy"
    pace = _clean(core.voice.pace).lower()
    voice = {"tts_voice": tts_voice, "pace": pace if pace in PACES else "normal",
             "energy": _clamp(core.voice.energy, 1, 5, 3), "tone": limit_words(core.voice.tone, 40)}

    look_in = core.look.model_dump()
    look = {}
    for slot in LOOK_SLOTS:
        value = _clean(look_in.get(slot)).lower()
        if value.startswith(slot + ":"):
            value = value.split(":", 1)[1]
        if value in data.look_values(slot):
            look[slot] = value
        else:
            if value:
                dropped.append(f"look.{slot}:{value}")
            look[slot] = LOOK_DEFAULTS[slot]
    look["summary"] = limit_chars(look_in.get("summary", ""), 160)

    how = [limit_words(h, 12) for h in core.weakness.how_to_beat if _clean(h)][:3]
    for filler in ["Stay calm and keep going", "Use one clear example"]:
        if len(how) >= 2:
            break
        if filler not in how:
            how.append(filler)

    persona = {
        "name": name,
        "nickname": nickname,
        "alt_text": limit_chars(core.alt_text, 125) or f"Drawing of {name}.",
        "clues": clues,
        "one_liner": limit_words(core.one_liner, 20),
        "temperament": temperament,
        "quirks": quirks,
        "catchphrases": catchphrases,
        "tactics": tactics,
        "interrupt_level": _clamp(core.interrupt_level, 0, 5, 1),
        "silence_seconds": _clamp(core.silence_seconds, 0, 6, 0),
        "base_difficulty": _clamp(core.base_difficulty, 1, 5, 2),
        "voice": voice,
        "look": look,
        "weakness": {"description": limit_words(core.weakness.description, 25), "how_to_beat": how},
    }
    training = keep_training if keep_training is not None else (raw.get("training") if isinstance(raw, dict) else None)
    persona["training"] = _normalize_training(training)
    if dropped:
        log.info("Dropped unknown ids from a persona: %s", ", ".join(dropped[:20]))
    return persona, dropped


def _normalize_training(training):
    training = training if isinstance(training, dict) else {}
    rules = [limit_chars(r, 120) for r in (training.get("rules") or []) if _clean(r)][:12]
    return {"rules": rules,
            "version": _clamp(training.get("version", 1), 1, 100000, 1),
            "trained_count": _clamp(training.get("trained_count", 0), 0, 100000, 0)}


def _fill_missing(raw):
    """Let a mostly-complete persona through validation (e.g. an older saved one missing a field)."""
    out = dict(raw)
    out.setdefault("name", "The Mystery Delegate")
    out.setdefault("nickname", "")
    out.setdefault("alt_text", "")
    out.setdefault("clues", [])
    out.setdefault("one_liner", "")
    out.setdefault("temperament", [])
    out.setdefault("quirks", [])
    out.setdefault("catchphrases", [])
    out.setdefault("tactics", [])
    out.setdefault("interrupt_level", 1)
    out.setdefault("silence_seconds", 0)
    out.setdefault("base_difficulty", 2)
    voice = dict(out.get("voice") or {})
    voice.setdefault("tts_voice", "alloy")
    voice.setdefault("pace", "normal")
    voice.setdefault("energy", 3)
    voice.setdefault("tone", "")
    out["voice"] = voice
    look = dict(out.get("look") or {})
    for slot, default in LOOK_DEFAULTS.items():
        look.setdefault(slot, default)
    look.setdefault("summary", "")
    out["look"] = look
    weakness = dict(out.get("weakness") or {})
    weakness.setdefault("description", "")
    weakness.setdefault("how_to_beat", [])
    out["weakness"] = weakness
    return out


def public_core(persona):
    """The persona without the training layer (what the AI edits)."""
    return {k: v for k, v in persona.items() if k != "training"}


# ------------------------------------------------------------------ text for prompts

def answers_text(answers):
    answers = answers or {}

    def join(key):
        items = [str(x) for x in (answers.get(key) or []) if str(x).strip()]
        other = str(answers.get(f"{key}_other") or "").strip()
        if other:
            items.append(other)
        return ", ".join(items) if items else "(skipped)"
    return {"nervous": join("nervous"), "comfortable": join("comfortable"), "try_again": join("try_again")}


def id_lists():
    look = {slot: data.look_values(slot) for slot in LOOK_SLOTS}
    return {
        "temperament_ids": ", ".join(data.ids("temperament")),
        "quirk_ids": ", ".join(data.ids("quirk")),
        "tactic_ids": ", ".join(data.ids("tactic")),
        "look_part_ids_by_slot": "; ".join(f"{k}: {', '.join(v)}" for k, v in look.items()),
        "voice_ids": ", ".join(data.tts_voices()),
    }


def persona_summary(persona):
    temps = ", ".join(data.label(t) for t in persona.get("temperament", []))
    tactics = ", ".join(data.label(t["id"]) for t in persona.get("tactics", [])[:3])
    return f"{persona.get('one_liner', '')} Temperament: {temps}. Favorite tactics: {tactics}."


def _labels(ids):
    return ", ".join(data.label(i) for i in ids) or "none"


def turn_system_prompt(persona, ctx, heat, examples, switched):
    """Build the debate-turn system message (section 10.4) from the persona and its training."""
    sections = load_prompt("debate_turn")
    fmt = data.format_info(ctx["format"])
    from logic.heat import max_words_for_heat
    tactics = "; ".join(f"{data.label(t['id'])} {t['intensity']}/5 ({data.describe(t['id'])})"
                        for t in persona.get("tactics", []))
    rules = persona.get("training", {}).get("rules") or []
    examples_text = "\n".join(f"Student: {e['student_text']}\nYou: {e['ideal_reply']}" for e in examples) or "(none yet)"
    switched_note = ""
    delegate_country, student_country = ctx["their_country"], ctx["my_country"]
    if switched:
        switched_note = (f"\nSWITCHED SIDES for this exchange: the student now argues {ctx['their_country']}'s "
                         f"position and you argue {ctx['my_country']}'s position.")
        delegate_country, student_country = ctx["my_country"], ctx["their_country"]
    weakness = persona.get("weakness", {})
    format_rules = fmt["rules"]
    if ctx.get("caucus_subtopic"):
        format_rules += f" Subtopic: {ctx['caucus_subtopic']}."
    return fill(
        sections["system"],
        name=persona.get("name", ""), nickname=persona.get("nickname", ""),
        delegate_country=delegate_country, committee=ctx["committee"], topic=ctx["topic"],
        format_name=fmt["name"], format_rules=format_rules, student_country=student_country,
        switched_sides_note=switched_note, one_liner=persona.get("one_liner", ""),
        temperament_labels=_labels(persona.get("temperament", [])),
        quirk_labels=_labels(persona.get("quirks", [])),
        catchphrases=" | ".join(persona.get("catchphrases", [])),
        tactics_with_intensity_and_descriptions=tactics,
        interrupt_level=persona.get("interrupt_level", 0),
        weakness=f"{weakness.get('description', '')} (How to beat it: {'; '.join(weakness.get('how_to_beat', []))})",
        trainer_rules_or_none="\n".join(f"- {r}" for r in rules) or "(none)",
        few_shot_examples_or_none=examples_text,
        heat=heat, heat_ladder_line=sections[f"heat_{max(1, min(5, heat))}"],
        max_words=max_words_for_heat(heat, ctx["format"]),
    )


def turn_user_message(*, student_text, used, limit, mode, poi, listening):
    sections = load_prompt("debate_turn")
    if poi and poi.get("text"):
        poi_text = f"offered: '{poi['text']}' — {'accepted' if poi.get('accepted') else 'declined'}"
    else:
        poi_text = "none"
    return fill(sections["turn"], used=used, limit=limit, mode=mode, poi=poi_text,
                listening=listening or "none", student_text=student_text)


def export_persona_json(persona):
    return json.dumps(public_core(persona), ensure_ascii=False)


DIFF_FIELDS = [("name", "Name"), ("nickname", "Nickname"), ("one_liner", "One-liner"), ("temperament", "Temperament"),
               ("quirks", "Quirks"), ("catchphrases", "Catchphrases"), ("tactics", "Tactics"),
               ("interrupt_level", "Interrupt level"), ("silence_seconds", "Dramatic silence"),
               ("base_difficulty", "Difficulty"), ("voice", "Voice"), ("look", "Look"), ("weakness", "Weakness"),
               ("training", "Trainer rules")]


def _show(field, value):
    if field in ("temperament", "quirks"):
        return ", ".join(data.label(v) for v in value) or "none"
    if field == "catchphrases":
        return " | ".join(value)
    if field == "tactics":
        return ", ".join(f"{data.label(t['id'])} {t['intensity']}" for t in value)
    if field == "voice":
        return f"{value.get('tts_voice')} · {value.get('pace')} · energy {value.get('energy')}"
    if field == "look":
        return value.get("summary") or ", ".join(f"{k}: {v}" for k, v in value.items() if k != "summary")
    if field == "weakness":
        return value.get("description", "")
    if field == "training":
        return "; ".join(value.get("rules", [])) or "(none)"
    return str(value)


def persona_diff(old, new, reasons=None):
    """Our own before -> after list for the 'what changed' view (we don't trust the AI's list)."""
    reasons = reasons or []
    out = []
    for field, label in DIFF_FIELDS:
        a, b = old.get(field), new.get(field)
        if field == "training":
            a, b = {"rules": (a or {}).get("rules", [])}, {"rules": (b or {}).get("rules", [])}
        if a != b:
            why = next((r.get("why", "") for r in reasons if str(r.get("field", "")).split(".")[0] == field), "")
            out.append({"field": field, "label": label, "before": _show(field, a or ([] if field in ("temperament", "quirks", "catchphrases", "tactics") else {} if field in ("voice", "look", "weakness", "training") else "")),
                        "after": _show(field, b or ([] if field in ("temperament", "quirks", "catchphrases", "tactics") else {} if field in ("voice", "look", "weakness", "training") else "")), "why": why})
    return out
