# MAINTAINERS.md

Welcome! You're one of the people who keeps Nightmare Delegate running. You don't need to know everything — this page tells you where things are and what to do when something goes wrong. Read it once start to finish, then keep it handy.

*(First draft, written at the end of Phase 1. Update it whenever you change how things work.)*

---

## 1. What this is

Nightmare Delegate is our Model UN club's practice website. New members draw the debate opponent that scares them most ("nightmare delegate"), take a photo, and the AI turns the drawing into a practice opponent. They practice one round against it, get strength-first feedback, and then the screen says **"Now go find a human."** The site is a warm-up, never a replacement for practicing with people.

### The 11 design principles (don't break these)

1. **The laptop is where you start, not where you stay.** Every AI round ends on "Now go find a human."
2. **Nobody sits out.** Odd number? The odd person gets one round with a nightmare, then a human partner first next time.
3. **Inclusion is designed on purpose.** Ask on every screen: who might feel left out here?
4. **Choose your path.** Paper, laptop, or just sit. Voice, camera, and timers are always optional.
5. **Tough on arguments, kind to people.** Delegates never insult anyone or mention looks or identity.
6. **Strength first.** Feedback starts with something the person did well.
7. **No leaderboards.** Personal growth and club totals only.
8. **Mistakes are funny, not fatal.** Friendly errors; every dead end has a door.
9. **Practice over polish.** A returning member starts a round in under 60 seconds (Quick Start).
10. **Built to outlive its builder.** Editors change content without code. That's why this file exists.
11. **Private by default.** First names only, no emails, photo location data stripped, audio never stored.

---

## 2. Map of the code

The code lives at **https://github.com/nabiii4/Model-UN** (public). Get your own copy with
`git clone https://github.com/nabiii4/Model-UN.git`. The How it works page links there; change that link in
Admin → Site text (`site.code_repo_url`), or type `none` there to hide the link (only `https://` links are shown; capital letters are fine).

| Folder / file | What's in it |
|---|---|
| `app.py` | Starts the app (`python app.py`). Security headers, error pages. |
| `config.py` | Reads `.env`, decides demo (mock) mode, never prints keys. |
| `extensions.py` | Database, CSRF protection, rate limiter. |
| `ai/client.py` | **Every** AI call: failover to the backup resource, retries, daily cap, demo mode switch. |
| `ai/prompts/*.md` | The exact words sent to the AI. Edit wording here — no code needed. |
| `ai/schemas.py` | The shape of each AI answer (checked with Pydantic). |
| `ai/persona.py` | Builds prompts from a nightmare's persona; cleans up personas (unknown traits, too-long names). |
| `ai/mock.py`, `ai/mock_lines.json` | Demo-mode answers (540 pretend debate lines, 15 per tactic). |
| `ai/delivery.py` | Word counts, words per minute, filler words, "is this quote real?" checks. |
| `models/` | Database tables (members, delegates, rounds, messages, …). |
| `routes/pages.py` | The HTML pages. |
| `routes/api_*.py` | The JSON API (auth, delegates, rounds, admin, misc). |
| `logic/` | Game rules with no web code: heat, fear meter, journey stages, handoff lock, security checks, settings, seeding, backups. |
| `data/` | Editable content: traits (244 options), committees, topics, countries, formats, example delegates, demo round, site text, blocklist. |
| `static/css`, `static/js` | The look and the page behavior (plain JavaScript, no build step). |
| `static/img/seeds/` | The 9 example doodles (our own SVG art — never the UN emblem). |
| `static/fonts/` | Patrick Hand + Atkinson Hyperlegible (open-licensed, self-hosted). |
| `templates/` | One HTML template per page, all built on `base.html`. |
| `scripts/` | `seed.py`, `backup.py`, `fetch_vendor.py`, `check_secrets.py`. |
| `tests/` | `pytest` tests (always demo mode). `tests/e2e` = real-browser tests. |

---

## 3. Run it locally (or in a Codespace)

```bash
git clone https://github.com/nabiii4/Model-UN.git
cd Model-UN
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                      # http://localhost:5000
pytest                             # run the tests
```

- No `.env`? It runs in **demo mode**: club code `blanksheet`, admin passcode `demo-admin`.
- **Codespaces:** run the same commands, then open the forwarded port 5000. To let classmates try it during a meeting, set the port's visibility to **Public** (the link stops when the Codespace sleeps).
- Changed a template or a file in `data/`? **Restart** `python app.py` (they're cached).

---

## 4. Deploy it (always on)

Any Python host with HTTPS and environment-variable settings works (Render, Railway, Fly.io, PythonAnywhere). Check free-tier limits and that outbound calls to `*.openai.azure.com` are allowed.

- **Build command:** `pip install -r requirements.txt && python scripts/fetch_vendor.py && python scripts/seed.py`
- **Start command:** `gunicorn app:app --workers 1 --threads 8 --timeout 120`
  (one worker keeps rate limits and caches consistent; vision calls can take ~45 s)
- **Database:** free hosts often wipe local files, so use a hosted Postgres (Neon or Supabase free tier) and put its URL in `DATABASE_URL`. `postgres://…` URLs are fixed automatically.
- **Environment variables:** put every variable from `.env.example` in the host's dashboard. Also set `HTTPS_ONLY=1` and `TRUST_PROXY=1` (most hosts sit behind a proxy).
- **HTTPS is required** for the camera and microphone.
- Free tiers sleep when idle — open the site a minute before the meeting.
- **Before going public:** confirm with the BSMP instructor that the class key may power a public club site.

---

## 5. Keys

Keys live **only** in `.env` locally, and in the host's settings in production. Never in code, chat, screenshots, or this file. `.env` is in `.gitignore`. Run `python scripts/check_secrets.py` before committing.

**Replace or rotate a key:** paste the new value into `.env` (or the host dashboard) and restart. That's all.

**What the errors mean** (Admin → AI status):

| You see | Meaning | Fix |
|---|---|---|
| Key rejected (401/403) | The key is wrong or expired. | Paste the current key; restart. |
| Not found (404) | The deployment name or API version is wrong. | Check `AZURE_OPENAI_DEPLOYMENT` / `AZURE_OPENAI_API_VERSION`. The app also tries Azure's newer v1 API automatically once. |
| 429 / "factory is packed" | Too many requests right now. | Wait a minute; the backup resource takes over automatically. |
| "on break" for everyone | Both resources are down, or the daily cap is used up. | Check Admin → AI status and the daily cap in Settings. |

**Switch AI providers** (if the class key stops working): in `.env` set
`AI_PROVIDER=openai_compatible`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` (and optionally `OPENAI_VISION_MODEL`), then restart. Every AI call goes through `ai/client.py`, so nothing else changes.

---

## 6. Everyday tasks (no code)

All of these are in **Admin** (log in, then Admin in the menu).

| Task | Where |
|---|---|
| Become the first maintainer | Admin → enter the admin passcode. |
| Promote an editor or maintainer | Admin → Members → change the role (maintainers only). |
| Reset someone's PIN ("Forgot PIN?") | Admin → Members → Reset PIN. Tell them the new PIN in person. |
| Moderate the Wall | Admin → Moderation: Approve / Hide / Delete. Reported nightmares are hidden until an editor looks. |
| Require approval before things go on the Wall | Admin → Settings → Wall moderation → "An editor approves first". |
| Add committees and topics | Admin → Committees & topics. |
| Edit site text (any headline, error message, the handoff line) | Admin → Site text. |
| Change the meeting schedule | Admin → Settings → meeting days, start, end, time zone. |
| Change the handoff text or credit line | Admin → Settings → Handoff text / credit line. |
| Change how strict the AI "rest" is | Admin → Settings → Handoff mode (strict / gentle / off), lock minutes, home rounds per day. |
| Let guests use AI | Admin → Settings → Guests can use AI (off by default) + daily quota. |
| Rotate the club code each year | Admin → Settings → Club code. |
| Read suggestions and bug reports | Admin → Requests (set Planned / Done / Won't do and reply — members see it on My Journey). |
| See who changed roles or settings | Admin → Audit log. |

Settings you change in Admin win over `.env`. (`.env` only provides the starting values.)

---

## 7. Small code tasks

**Add a trait** (tactic, quirk, look option, …): add an entry to `data/traits.json`:
```json
{"id": "asks_for_a_map", "label": "Asks for a map", "category": "tactic", "description": "Asks you to point to the country on a map."}
```
The `description` is what the AI reads. For demo mode, also add 15 lines for a new tactic in `ai/mock_lines.json` (`{country}`, `{student_country}`, `{topic}`, and `{quote}` are filled in). Restart.

**Add a round format:** add it to `data/formats.json` (`rules` is sent to the AI), add its id to `data/packs/mun.json`, and add it to `PHASE1_FORMATS` in `routes/api_rounds.py` when it's ready.

**Add a club pack** (Phase 3): copy `data/packs/mun.json` to a new file and change `role_noun`, `venue`, and `formats`.

**Change prompt wording:** edit `ai/prompts/<name>.md`. Keep the `{curly_words}` exactly as they are and keep the HARD RULES.

**Run the tests after every change:** `pytest`. They take ~20 seconds and never call real AI.

---

## 8. Backups

- **Weekly:** Admin → Backups & handoff → **Export everything (.zip)**. Or on the server: `python scripts/backup.py export backups/`.
- The zip has every table (members, nightmares, versions, rounds, settings) plus all drawings.
- **Restore:** `python scripts/backup.py import nightmare-backup-YYYY-MM-DD-HHMM.zip` (it asks you to type YES — it **replaces everything**).
- Keep a copy with the club advisor.

---

## 9. Troubleshooting

| Problem | Try this |
|---|---|
| "Your camera is shy" | Click the camera icon in Chrome's address bar → Allow. Or use **Upload a photo**. Camera needs HTTPS (or localhost). School policy may block it — upload always works. |
| Mic blocked | Speak mode arrives in Phase 2. Type mode always works. |
| "Both nightmare factories are on break" | AI is down or the daily cap is used. Admin → AI status. Human Rounds still work. |
| Slow first load | Free hosts sleep. Open the site a minute before the meeting. |
| "Key rejected" | Paste the current key into `.env` / host settings; restart. |
| "This page got a little stale" | The page sat open a long time or the server restarted. Refresh. |
| Everyone got logged out | The server restarted without `FLASK_SECRET_KEY` set. Set it in `.env`. |
| "Address already in use" / wrong port | Port 5000 is taken (on Macs, AirPlay Receiver uses it). The app now picks the next free port and prints it; or choose one with `PORT=5050 python app.py`. Avoid 5060/5061 (Chrome blocks them). |
| "Database is locked" (SQLite) | Use one worker (`--workers 1`). In production use Postgres. |
| Edited `data/*.json` but nothing changed | Restart the app. |
| Demo ribbon won't go away | `MOCK_AI` is still 1, or the key/endpoint is missing or a placeholder. Check the startup messages. |

---

## 10. Graduation handoff checklist

- [ ] At least 2 maintainers added in Admin, and both can log in.
- [ ] GitHub repo transferred, or maintainers added as admins.
- [ ] Hosting and database access shared with the maintainers and the club advisor.
- [ ] `ADMIN_PASSCODE` changed and shared only with new maintainers and the advisor.
- [ ] Confirmed whose AI key the site uses and what happens when it expires.
- [ ] A fresh backup exported and stored with the advisor.
- [ ] Walked through this doc together, start to finish.
