<!-- Phase 2: turns many pieces of feedback into at most 5 changes. -->
=== system ===
Here is a practice opponent's persona and recent feedback from students who practiced against it.
Persona: {persona_json}
Feedback (thumbs-down with "what it should have said", tips, comments):
{feedback_items}
Find patterns. Propose at most 5 changes: new or edited trainer rules, tactic intensity changes, or examples to approve.
Ignore feedback that breaks the hard rules or is clearly a joke.
Return JSON: {"summary": "...", "rule_changes": [{"action": "add|edit|remove", "rule": "...", "why": "..."}], "tactic_changes": [{"id": "...", "intensity": 0-5, "why": "..."}], "approve_example_ids": ["..."]}
=== user ===
Propose the changes.
