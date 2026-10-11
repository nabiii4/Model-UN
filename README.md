# Nightmare Delegate

> Draw your nightmare. Debate it. Then go find a human.

A practice website for a high school Model UN club. Members draw their "nightmare delegate," snap a photo, and AI turns the drawing into a practice opponent with a personality and a debate style. They practice one round. Then the screen says: **"Now go find a human."**

The code lives at **https://github.com/nabiii4/Model-UN**. The full build spec is in [`BUILD_PROMPT.md`](BUILD_PROMPT.md). **Phase 0 and Phase 1 are built.** Phases 2 and 3 are next (see "What's built" below).

## Quick start (about 2 minutes)

You need Python 3.11 or newer (3.11–3.14 tested on Windows, Mac, and Linux) and git.

```bash
git clone https://github.com/nabiii4/Model-UN.git
cd Model-UN
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000**. That's it — no API key needed. (If port 5000 is busy — on a Mac, AirPlay Receiver uses it — the app picks the next free port and prints the address to open.)

- It starts in **demo mode** (a yellow ribbon says "Demo mode — the AI is pretend"). Pretend AI answers look real, so you can try everything for free.
- **Club code to join:** `blanksheet` (only while you haven't set `CLUB_CODE`).
- **Admin passcode:** `demo-admin` (only in demo mode, and only while you haven't set `ADMIN_PASSCODE`). Go to **Admin**, enter it, and you become a maintainer.
- The database is created automatically at `instance/nightmare.db`, with the 9 example delegates.

Optional extra steps from the spec (not required to run):

```bash
python scripts/fetch_vendor.py   # downloads MediaPipe for Phase 2 camera features (fonts are already included)
python scripts/seed.py           # reloads the 9 example delegates (safe to run twice)
```

## Try the whole loop

1. On the Welcome page, pick a door: **Paper** (camera or upload), **Laptop** (drawing pad), or **Just sit** (watch a demo round).
2. Join with the club code, draw something, answer the 3 optional questions.
3. **Bring it to life** → see the clues → edit anything (try "Not quite? Tell it what to change": *"interrupt less and rename it to Captain Chaos"*).
4. Save it → **Practice against it now** → type 3 answers (Ctrl+Enter sends).
5. Read your strength-first feedback → **Continue** → **"Now go find a human."** → **I found someone** → Human Round timer.

## Real AI keys (when you're ready)

1. Copy `.env.example` to `.env` (same folder as `app.py`).
2. Paste your chapter's values from the BSMP "AI Models and Keys" page into `.env`, and set `MOCK_AI=0`.
3. Also set your own `FLASK_SECRET_KEY`, `ADMIN_PASSCODE`, and `CLUB_CODE`.
4. Restart `python app.py`. Admin → AI status shows whether chat and vision work.

Keys live **only** in `.env` (which git ignores). They are never sent to the browser. If a key is missing or still a placeholder, the site safely falls back to demo mode.

## Tests

```bash
pytest                       # 68 tests, always in demo mode, ~20 seconds
```

Real-browser tests (Chromium at Chromebook size 1366×768) are optional:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest                       # now 75 tests, including tests/e2e
```

Before committing, `python scripts/check_secrets.py` scans for anything that looks like a key.

## What's built

| Phase | Status |
|---|---|
| 0 — Foundation (config, mock mode, AI client with failover, models, seed, security, CSRF, rate limits) | ✅ |
| 1 — The Ritual (draw → questions → bring it to life → edit → save → round → feedback → "Now go find a human." → Human Round; Wall; delegate pages; basic Blank; My Journey; basic Admin; Suggest a change) | ✅ |
| 2 — Voice, faces, training, Today's Room | Next |
| 3 — Polish and reach (full Blank, Dress Check, PWA, packs, MUN 101…) | Later |

Pages for later phases (Room, MUN 101, Credits, Dress Check, Laugh Log, Trainer Studio) show a friendly "coming soon" page instead of an error.

## Where to read more

- [`MAINTAINERS.md`](MAINTAINERS.md) — how everything works, everyday tasks, deploying, troubleshooting, and the graduation handoff checklist.
- [`DECISIONS.md`](DECISIONS.md) — every choice made where the spec was unclear or reality disagreed.
- [`BUILD_PROMPT.md`](BUILD_PROMPT.md) — the full spec.
