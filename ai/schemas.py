"""Pydantic models for every JSON answer the AI gives (BUILD_PROMPT.md section 10).

Types are checked here. Lengths and ranges are clamped afterwards in ai/persona.py
(we fix small mistakes instead of failing the whole request).
"""
import copy
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

EXPRESSIONS = ["neutral", "skeptical", "stern", "impressed", "amused", "annoyed", "thinking", "smug"]
SAFETY_STATUSES = ["ok", "not_a_drawing", "unsafe"]


def _to_int(v):
    """Accept 3, 3.0, '3', or 3.6 (rounded). Ranges are clamped later."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(round(v))
    if isinstance(v, str):
        try:
            return int(round(float(v.strip())))
        except ValueError:
            pass
    return v


class Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ---------------------------------------------------------------- persona

class Safety(Lenient):
    status: str = Field(json_schema_extra={"enum": SAFETY_STATUSES})
    renamed_from_real_person: bool
    note: Optional[str]

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v):
        v = str(v or "ok").strip().lower()
        return v if v in SAFETY_STATUSES else "ok"


class Clue(Lenient):
    saw: str
    means: str


class TacticLevel(Lenient):
    id: str
    intensity: int

    _int = field_validator("intensity", mode="before")(lambda cls, v: _to_int(v))


class Voice(Lenient):
    tts_voice: str
    pace: str = Field(json_schema_extra={"enum": ["slow", "normal", "fast", "very_fast"]})
    energy: int
    tone: str

    _int = field_validator("energy", mode="before")(lambda cls, v: _to_int(v))


class Look(Lenient):
    style: str
    hair: str
    eyebrows: str
    eyes: str
    glasses: str
    mouth: str
    facial_hair: str
    headwear: str
    outfit: str
    accessory: str
    skin_tone: str
    palette: str
    summary: str


class Weakness(Lenient):
    description: str
    how_to_beat: List[str]


class PersonaCore(Lenient):
    name: str
    nickname: str
    alt_text: str
    clues: List[Clue]
    one_liner: str
    temperament: List[str]
    quirks: List[str]
    catchphrases: List[str]
    tactics: List[TacticLevel]
    interrupt_level: int
    silence_seconds: int
    base_difficulty: int
    voice: Voice
    look: Look
    weakness: Weakness

    _ints = field_validator("interrupt_level", "silence_seconds", "base_difficulty", mode="before")(
        lambda cls, v: _to_int(v))


class PersonaDraft(PersonaCore):
    safety: Safety


# ---------------------------------------------------------------- rounds

class RoundOpening(Lenient):
    opening: Optional[str]
    pois: List[str]
    human_round_question: str
    bloc_must_haves: Optional[List[str]]
    caucus_subtopic: Optional[str]


class TurnReply(Lenient):
    reply: str
    expression: str = Field(json_schema_extra={"enum": EXPRESSIONS})
    eyebrows: int
    tactic_used: str
    student_dodged: bool
    student_used_evidence: bool
    suggest_heat: int
    break_character: bool

    _ints = field_validator("eyebrows", "suggest_heat", mode="before")(lambda cls, v: _to_int(v))

    @field_validator("expression", mode="before")
    @classmethod
    def _expr(cls, v):
        v = str(v or "neutral").strip().lower()
        return v if v in EXPRESSIONS else "neutral"


class ListeningResult(Lenient):
    score: int
    missing_piece: Optional[str]
    note: str

    _int = field_validator("score", mode="before")(lambda cls, v: _to_int(v))


class Hint(Lenient):
    idea: str
    ask_back: str


class Score(Lenient):
    score: int
    reason: str

    _int = field_validator("score", mode="before")(lambda cls, v: _to_int(v))


class Scores(Lenient):
    clarity: Score
    evidence: Score
    answering: Score
    diplomacy: Score
    listening: Optional[Score]
    perspective: Optional[Score]


class Feedback(Lenient):
    strength_quote: str
    strength_why: str
    fix_focus: str
    fix_how: str
    try_next_time: str
    scores: Scores
    encouragement: str


# ---------------------------------------------------------------- training

class TrainerChange(Lenient):
    field: str
    before: str
    after: str
    why: str

    @field_validator("before", "after", mode="before")
    @classmethod
    def _stringify(cls, v):
        if v is None:
            return ""
        if isinstance(v, (list, dict)):
            import json
            return json.dumps(v, ensure_ascii=False)[:300]
        return str(v)


class TrainerOutput(Lenient):
    summary: str
    changes: List[TrainerChange]
    persona: PersonaCore


class RuleChange(Lenient):
    action: str = Field(json_schema_extra={"enum": ["add", "edit", "remove"]})
    rule: str
    why: str


class TacticChange(Lenient):
    id: str
    intensity: int
    why: str

    _int = field_validator("intensity", mode="before")(lambda cls, v: _to_int(v))


class TrainingSession(Lenient):
    summary: str
    rule_changes: List[RuleChange]
    tactic_changes: List[TacticChange]
    approve_example_ids: List[str]


class DressItem(Lenient):
    item: str
    status: str = Field(json_schema_extra={"enum": ["ok", "missing", "unsure", "optional"]})
    note: str


class DressSafety(Lenient):
    status: str = Field(json_schema_extra={"enum": ["ok", "no_outfit", "unsafe"]})


class DressCheck(Lenient):
    safety: DressSafety
    score: int
    items: List[DressItem]
    tips: List[str]
    reassurance: str

    _int = field_validator("score", mode="before")(lambda cls, v: _to_int(v))


# ---------------------------------------------------------------- strict JSON schema

# Keywords that strict structured outputs may reject. We enforce these limits in Python instead.
_DROP = {"title", "default", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems",
         "pattern", "format", "examples", "exclusiveMinimum", "exclusiveMaximum"}


def strict_schema(model):
    """Turn a Pydantic model into a schema that strict mode accepts:
    every property required, additionalProperties false, no $refs, no unsupported keywords."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            out = {k: walk(v) for k, v in node.items() if k not in _DROP}
            if out.get("type") == "object":
                out.setdefault("properties", {})
                out["required"] = list(out["properties"].keys())
                out["additionalProperties"] = False
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
