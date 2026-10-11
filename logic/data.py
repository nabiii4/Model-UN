"""Loads the JSON files in data/. They are read once and cached (restart the app after editing them)."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache(maxsize=None)
def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def traits():
    """The trait library, indexed a few handy ways."""
    options = load_json("traits.json")["options"]
    by_id, by_category, look_by_slot, voice_slots = {}, {}, {}, {}
    for opt in options:
        by_category.setdefault(opt["category"], []).append(opt)
        if opt["category"] == "look":
            slot, value = opt["puppet"]["slot"], opt["puppet"]["value"]
            look_by_slot.setdefault(slot, []).append(value)
            by_id[opt["id"]] = opt
        elif opt["category"] == "voice":
            slot = opt["puppet"]["slot"]
            voice_slots.setdefault(slot, []).append(opt["puppet"].get("value", opt["id"]))
            by_id[f"voice:{opt['id']}"] = opt
        else:
            by_id[opt["id"]] = opt
    return {"options": options, "by_id": by_id, "by_category": by_category,
            "look_by_slot": look_by_slot, "voice_slots": voice_slots}


def ids(category):
    return [o["id"] for o in traits()["by_category"].get(category, [])]


def label(trait_id):
    opt = traits()["by_id"].get(trait_id)
    return opt["label"] if opt else trait_id.replace("_", " ")


def describe(trait_id):
    opt = traits()["by_id"].get(trait_id)
    return opt["description"] if opt else ""


def tts_voices():
    return [str(v) for v in traits()["voice_slots"].get("tts_voice", [])]


def look_values(slot):
    return traits()["look_by_slot"].get(slot, [])


@lru_cache(maxsize=None)
def formats():
    items = load_json("formats.json")["formats"]
    return {f["id"]: f for f in items}


def format_info(format_id):
    return formats().get(format_id) or formats()["rebuttal_duel"]


@lru_cache(maxsize=None)
def countries():
    return [c["name"] for c in load_json("countries.json")["countries"]]


def seeds():
    return load_json("seeds/delegates.json")["delegates"]


def demo_round():
    return load_json("demo_round.json")


@lru_cache(maxsize=None)
def copy_defaults():
    return {k: v for k, v in load_json("copy.json").items() if not k.startswith("_")}


@lru_cache(maxsize=None)
def blocklist():
    words = []
    path = DATA_DIR / "blocklist.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                words.append(line)
    return words


def pack(pack_id="mun"):
    try:
        return load_json(f"packs/{pack_id}.json")
    except FileNotFoundError:
        return load_json("packs/mun.json")


def default_committees():
    committees = load_json("committees.json")["committees"]
    topics = load_json("topics.json")["topics"]
    out = []
    for c in committees:
        out.append({"id": c["id"], "name": c["name"],
                    "topics": [t["title"] for t in topics if t["committee"] == c["id"]]})
    return out
