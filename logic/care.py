"""Safety net for the break-character rule (BUILD_PROMPT.md section 10.4).

The AI is told to step out of character if a student seems truly upset. This server-side
check makes sure that happens even if the AI misses it (or in mock mode).
"""
import re

DISTRESS_RE = re.compile(
    r"\b(kill (my ?self|me)|hurt (my ?self|me)|end (it all|my life)|want(ed)? to die|suicid\w*|self[- ]?harm|"
    r"cut(ting)? myself|hurt (someone|somebody|them|him|her)|kill (someone|somebody|them|him|her))\b",
    re.IGNORECASE)

CARE_MESSAGE = ("Let's pause the debate for a moment. You matter more than this round. "
                "If you're feeling really down or thinking about hurting yourself or someone else, "
                "please talk to a trusted adult or your school counselor right away. "
                "In the US you can call or text 988 any time, day or night.")


def needs_care(text):
    return bool(DISTRESS_RE.search(text or ""))
