# DECISIONS.md

A running log of choices made where `BUILD_PROMPT.md` didn't say, was unclear, or where reality disagreed. Newest phase at the top. Each entry: what we chose and why.

---

## Moving to nabiii4/Model-UN

52. **The site now lives in https://github.com/nabiii4/Model-UN** on its `main` branch (the repo was empty except a one-line README, which the project README replaced). The first build was made on the `claude/zen-shannon-kk4zfd` branch of `nabiii4/Map`; Model-UN is the home from now on.
53. **How it works links to the code** because the repo is public (§6.15 says to link it only if public). The link is the site-text key `site.code_repo_url`, so editors can change it in Admin → Site text, or type `none` to hide it (for example if the repo is ever made private). Only `https://` links are shown (any capitalization), so a `javascript:` link can never be added there.

54. **Tilted Wall cards are clipped left/right with 12px of room** (`.wall-grid` in `components.css`). Random tilts up to 2° made a card poke about 1px past a 390px phone screen, causing sideways scrolling. 12px covers the biggest tilt on the tallest card plus the Example ribbon, and fits inside the page's side padding.

55. **`python app.py` picks the next free port if 5000 is taken** (it prints the address to open). On Macs, AirPlay Receiver holds port 5000, so the spec's default would otherwise crash with "Address already in use". Production (gunicorn) is unaffected.

## Phase 0 + Phase 1 (first build)

### Scope and process
1. **Built Phase 0 and Phase 1 together, then stopped.** The spec's "How to use this file" step 2 says to build both, run them, run the tests, and stop. Phase 2 and 3 pages show friendly "coming soon" pages (not 404s) so no link is a dead end.
2. **Started in mock mode.** Per the request, `.env.example` sets `MOCK_AI=1` (the spec's example had `0`), so copying it to `.env` keeps demo mode until real keys are pasted and `MOCK_AI` is set to `0`.

### Environment and setup
3. **`.env.example` uses placeholder endpoints**, not the real class resource hostnames shown in the spec, because the request was "placeholders only." Placeholder values (like `paste-your-key-here`) are detected and treated as "no key" → demo mode.
4. **Works with zero setup.** With no `.env`: club code defaults to `blanksheet`; the admin passcode defaults to `demo-admin` **only in demo mode** (with real AI and no `ADMIN_PASSCODE`, admin sign-in is disabled with a clear message); a random `FLASK_SECRET_KEY` is generated (people are logged out on restart, with a startup warning).
5. **The database seeds itself on the very first start**, so `python app.py` alone works. `scripts/seed.py` still exists and upserts by stable ids. Auto-seeding only happens once, so deleted examples stay deleted.
6. **Settings defaults live in code, not the database.** Only values changed in Admin are stored, and they win over `.env`. Otherwise a later change to `CLUB_CODE` or `TIMEZONE` in `.env` would be ignored.
7. **Added env vars:** `HTTPS_ONLY` (marks cookies `Secure` in production), `TRUST_PROXY` (correct client IPs behind hosts like Render), `MOCK_AI_DELAY` (pretend thinking time in demo mode; 0 in tests), `FLASK_DEBUG`.
8. **Pinned versions** (all checked for wheels on Python 3.11–3.14, Windows/Mac/Linux): Flask 3.1.3, Flask-SQLAlchemy 3.1.1 with **SQLAlchemy 2.0.54** (not 2.1, for compatibility), **Flask-Limiter 3.12** (stable API), Flask-WTF 1.3.0, **openai 3.28.0** (latest; it uses `httpx2` internally), Pillow 12.3.0, Pydantic 2.14.0. Added **`tzdata`** so time zones work on Windows. `gunicorn` and `psycopg[binary]` stay in `requirements.txt` (they install everywhere). Playwright is only in `requirements-dev.txt`.
9. **Fonts are committed** to `static/fonts/` (OFL licenses included) instead of downloaded, so the site looks right even if `fetch_vendor.py` is never run or the network blocks it. `fetch_vendor.py` downloads from the npm registry (CDNs like jsDelivr may be blocked on school networks) and never fails the build.
10. **MediaPipe Tasks Vision is pinned to 1.1.0** in `fetch_vendor.py` (latest at build time). Only Phase 2 uses it.
11. **Added `pytest.ini`** so `pytest` works from the project folder with no extra flags.

### Data model (§11)
12. Tables are plain SQLAlchemy 2 classes (`models/base.py`) registered with `SQLAlchemy(metadata=Base.metadata)` instead of `db.Model`, so models import without Flask and work in scripts.
13. **Extra columns:** `members.name_key` (lower-case unique name), `members.last_round_settings` (Quick Start); `images.guest_id` (a guest's temp photo); `rounds.persona_snapshot` (so edits mid-round can't confuse it), `heat`, `labels`, `hint_pending`, `switch_pending`, `exchanges`, `abandoned`, `paused`, `fear_change`, `handoff`; `requests.delegate_id`, `requests.credit_name`.
14. **New `reports` table** for Report clicks (target, reporter key — never an IP —, reason, resolved).
15. **No migration tool yet**: `db.create_all()` creates tables. All Phase 2/3 tables already exist, so later phases should rarely need migrations. If they do, add Alembic then (logged here).
16. SQLite runs in WAL mode with a busy timeout, and AI calls happen **after** committing, so one slow AI call never locks the database for others.

### AI client (§9–10)
17. **Strict JSON schemas are generated from the Pydantic models** with length/range keywords removed (strict mode may reject them). All limits from §10.1 are enforced in Python after validation (`ai/persona.py`), fixing small mistakes instead of failing.
18. **On a 404, the client tries Azure's newer v1 API once** (`{endpoint}openai/v1/`) and keeps using it if it works, as §9.3 suggests.
19. **Admin pages show the env var name, not the deployment name** ("check `AZURE_OPENAI_DEPLOYMENT`") because §1.2 says the browser never receives deployment names. Error text shown to admins is scrubbed of keys, endpoints, deployment names, and URLs.
20. **Health probes run in a background thread** at startup and at most every 15 minutes (when `/api/health` is read), so startup is never slow.
21. Content-filter rejections from Azure are treated as "let's keep it friendly" messages, not crashes.
22. Phase 2/3 features (transcribe, TTS, image, embeddings) report `"off"` in `/api/health` until they're built.

### Game rules
23. **Word target vs. word limit.** §8.1 lists "120 words" as a turn *limit*. Using it as the heat *target* made a solid 24-word typed answer count as "struggling." `data/formats.json` now has both: Rebuttal Duel limit 120 / target 60, Opening Speech 200/120, POI 60/30, Moderated Caucus 90/50.
24. **"suggest_heat only breaks ties"** is read as: if the last two turns lean one way (e.g. strong + ok) and the model agrees, move that way. Two strong / two struggling always win. The streak resets after any rule fires.
25. **Length option:** Quick/Standard apply to Rebuttal Duel. Formats with a fixed count (Opening Speech 3, POI 5, Moderated Caucus 3) keep it. Timed = 4 minutes for any format (max 12 exchanges as a safety cap).
26. **Time's up:** at 0 a soft chime plays. Outside Gentle mode and at heat ≥ 4, the answer is sent with "Time, delegate." Otherwise the student keeps typing and the timer shows "+Ns". Gentle mode never cuts anyone off.
27. **Switch sides lasts one exchange**, then a "Back to your own side" divider appears.
28. **A hint makes that turn "struggling" for the heat** (spec §8.2) but never lowers feedback scores (spec §6.6).
29. **The home cap counts finished rounds only.** Abandoned rounds "won't count" (the exit message promises that).
30. **The handoff lock is stored on the round that caused it.** An overtime round never starts a fresh lock (otherwise overtime could repeat forever). With no Room session open (always true until Phase 2), overtime needs a confirm. Using overtime adds to `bot_slot_count`, so Phase 2 pairing gives that person a human partner first.
31. **Break-character safety net:** the server also checks student text for signs of real distress (not just the AI), shows a calm card with the 988 line, pauses the round, keeps that message out of feedback, and never triggers the lock.
32. **The strength quote is always real:** if the AI's quote isn't word-for-word in the student's turns, the closest student sentence is used, trimmed to 25 words.
33. **If the feedback AI call fails, quick non-AI feedback is used** (same shape) so the round still counts, with a note saying so.

### Safety and moderation
34. **Report hides a nightmare from the Wall immediately** (status `flagged`) until an editor approves it. Safer for a site used by minors; reports are rate-limited per device.
35. **"Auto" Wall moderation** = the word blocklist + the AI's safety check. "Approval" = public nightmares wait for an editor.
36. **Names:** first name or nickname, must start with a letter; letters, numbers, spaces, apostrophes, dots, dashes; ≤ 30 characters; blocklist checked.
37. Login and join limits only count **failed** attempts (5 per 10 minutes per name + IP).
38. Redirects after login only go to pages on this site.

### Guests
39. **Guest AI is off by default** (spec). Guests can still draw; at "Bring it to life" they see a friendly join message. Their drawing is kept on the device and the flow **resumes automatically after joining**. If an admin turns guest AI on, guests save nightmares on the device only and can practice with them.

### Screens
40. **The Blank (basic)** includes name, temperament, 5 tactic sliders, difficulty, voice, weakness, the look options, and Randomize. It uploads the rendered face as its "drawing" through a new `POST /api/images/temp`.
41. **"Suggest a change to this nightmare"** goes to the Requests board with the nightmare attached; the owner also sees it on the nightmare's page.
42. **Train** button on a nightmare page goes to a "coming in Phase 2" page; owners can already **Edit** (every save is a new version; `versions` and `restore` APIs exist).
43. **Speak mode** shows as "arrives in Phase 2" on the setup screen; Type mode is first-class.
44. **Site text:** the copy bank (§17.7) plus the main headlines, errors, and buttons are in `data/copy.json` and editable in Admin → Site text. Not every tiny label is in it yet.
45. **Extra API endpoints:** `/api/images/temp`, `/api/traits`, `/api/setup-data`, `/api/copy`, `/api/demo-round`, `/api/handoff`, `/api/me/answers`, `/api/rounds/<id>/resume`, `/api/admin/copy`, `/api/admin/committees`, `DELETE /api/admin/members/<id>`.
46. **Backups came early:** Admin export (zip) and `scripts/backup.py export|import` work now; the import button in Admin is Phase 3.
47. **Extra color tokens** (`--nightmare-text`, `--friend-text`, `--card`, …) so red and green text meet 4.5:1 contrast in both themes. Lighthouse accessibility scored 100 on every page tested (Welcome, Draw, Wall, Practice Room, Feedback, Round setup, My Journey, Join, Human).
48. **Night mode choice and the in-progress drawing** are the only things kept in the browser's storage (both wrapped so blocked storage never breaks a page).
49. **Example drawings are our own SVG doodles** stored in the images table (served with a locked-down CSP).
50. **Countries** use UN short names with a few simplified (e.g. "Bolivia", "Iran", "Micronesia"); 193 members + Holy See + State of Palestine.

### Demo (mock) mode
51. "Not a drawing" is detected by comparing dark pixels to the paper's own brightness (a blank-page photo has none; a light pencil sketch still counts). A description mentioning "Mr./Ms./teacher/coach…" is treated as a real person and renamed, so those safety paths can be tried without a key.
