# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
./venv/bin/python app.py       # run the app → http://127.0.0.1:5001
./venv/bin/pip install -r requirements.txt
```

Invoke the venv binaries by path as shown — that works regardless of shell state.
A bare `python app.py` also works at present, because the venv is activated
(`VIRTUAL_ENV` is set and survives into each Bash tool call), but do not rely on
it: Flask lives only in the venv, so the same command fails the moment the venv
is deactivated. Neither `/usr/bin/python3` nor the 3.14 framework Python has it.

Note that `venv/bin/python` symlinks to the 3.14 framework binary, so the process
shows up in `ps` as capital-`P` `Python app.py`. A `pkill -f "python app.py"` is
case-sensitive and silently matches nothing — use `pkill -f "[Pp]ython app.py"`
and verify with `lsof -nP -iTCP:5001 -sTCP:LISTEN`.

The app hardcodes `port=5001` with `debug=True` (reloader active — edits reload
automatically). Port 5000 is wrong; it is macOS AirPlay's.

### Tests

There are none yet — no `tests/`, no pytest config, no test files. `pytest` and
`pytest-flask` are pinned in `requirements.txt` but unused, so the harness is
ready when the first test is written. Do not claim a test suite passes.

### Seeing the UI

The app is server-rendered with no build step, so `curl` verifies status codes
and markup but never shows the rendered page. For visual checks, headless Chrome
against the running server is the established path (pre-approved in
`.claude/settings.local.json`):

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new \
  --disable-gpu --screenshot=<path>.png --window-size=1200,1180 \
  --hide-scrollbars --virtual-time-budget=6000 http://127.0.0.1:5001/
```

## Architecture

Flask + Jinja2 + SQLite, server-rendered, no ORM and no frontend framework.

`app.py` is the entire backend: a single flat module holding every route, no
blueprints. Routes split in two — those rendering real templates (`/`,
`/register`, `/login`, `/terms`, `/privacy`) and placeholders returning a bare
string like `"Profile page — coming in Step 4"`.

**This is a teaching scaffold.** The placeholder strings are a guided build, and
the "Step N" numbers are the curriculum's ordering. Steps 1 (database layer) and
2 (registration) are implemented; still stubbed are Step 3 logout, Step 4
profile, and Steps 7–9 expense create/edit/delete. Keep SQL in `database/`
instead of inlining it into route handlers, and use no ORM — that separation is
the point of the exercise.

`database/db.py` owns the data layer: `get_db()` (connection with
`row_factory = sqlite3.Row` and `PRAGMA foreign_keys = ON`), `init_db()`
(`CREATE TABLE IF NOT EXISTS` for `users` and `expenses`), `seed_db()` (one demo
user and 8 expenses, early-returns if `users` is non-empty), and `create_user()`.
`app.py` calls `init_db()` and `seed_db()` at import inside `app.app_context()`.

Auth is session-based, no extension: `/register` sets `session["user_id"]`, and
`app.secret_key` comes from `os.environ.get("SECRET_KEY", <dev fallback>)` — so
it runs with no setup, but a real deployment must set the variable. Nothing reads
the session yet — login and logout are Step 3. Duplicate emails are caught
as `sqlite3.IntegrityError` off the `UNIQUE` constraint rather than a prior
`SELECT`, keeping the database the source of truth; emails are stored stripped
and lowercased. Hash with `werkzeug.security`, and use parameterised SQL only.

### The database file

`spendly.db` at the repo root, gitignored. **Do not commit it.** It was tracked
once, and the result was that `git checkout` between a branch tracking it and a
branch ignoring it silently overwrote live data with the committed blob — git
treats an ignored file as expendable. If `git status` ever shows it, that is a
bug, not something to `git add`.

`DB_PATH` in `database/db.py` is the single source of that filename; an
`expense_tracker.db` appearing at the root means something is reading a stale
path.

### Templates and the asset convention

Every page extends `base.html`, which owns the navbar, footer, Google Fonts, the
global stylesheet, and the `title`/`head`/`content`/`scripts` blocks.

Page-specific CSS and JS live **inline in the template's `{% block head %}` and
`{% block scripts %}`**, not in the shared static files. `landing.html` is the
worked example: its video-modal styles and open/close script are both inline
there. `static/css/style.css` carries only global/shared styling, and
`static/js/main.js` is still an empty placeholder. Follow this when adding page
behavior — reaching for `main.js` would break the pattern.

Link internal routes with `url_for('<endpoint>')`, never hardcoded paths.

## Repo notes

- Each curriculum step gets a spec in `.claude/specs/<NN>-<slug>.md`, written by
  the `/create-spec` slash command and committed alongside the step's code.
  Read the matching spec before implementing a step.
- `file.md` is a dumped transcript of an earlier Claude Code session, not
  documentation. Nothing reads it; treat it as cruft.
- `hero_image.png` sits at the repo root, unreferenced by any template or
  stylesheet. It is not wired into the hero and is not served — `static/` is the
  only directory Flask serves assets from.
- Commits follow a `<area>: <imperative summary>` subject, e.g.
  `landing: add youtube modal on see how it works click`.
