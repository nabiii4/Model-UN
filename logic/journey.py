"""Journey stages: Pockets -> Keyboard -> Microphone. They never go backward."""

ORDER = {"pockets": 0, "keyboard": 1, "microphone": 2}
EVENT_STAGE = {
    "joined": "pockets",
    "watched_demo": "pockets",
    "typed_round": "keyboard",
    "spoken_round": "microphone",
    "human_round": "microphone",
}


def advance_stage(current, event):
    target = EVENT_STAGE.get(event, "pockets")
    current = current if current in ORDER else "pockets"
    return target if ORDER[target] > ORDER[current] else current
