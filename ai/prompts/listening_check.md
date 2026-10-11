<!-- Phase 2: grades the student's one-sentence summary of what the delegate said. -->
=== system ===
The delegate said: "{delegate_text}"
The student summarized it as: "{paraphrase}"
Grade how well the student captured the MAIN point (not every detail).
3 = the main point and the reason behind it · 2 = the main point · 1 = part of it · 0 = missed it.
Return JSON: {"score": 0-3, "missing_piece": "max 15 words, or null", "note": "max 15 kind words"}
=== user ===
Grade the summary.
