# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
./venv/bin/python app.py       # run the app → http://127.0.0.1:5001
./venv/bin/pip install -r requirements.txt
```

Invoke the venv binaries by path as shown. Each Bash tool call runs in a fresh
shell, so `source venv/bin/activate` does not persist between calls; a bare
`python app.py` will use system Python and fail on the Flask import.

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

**This is a teaching scaffold.** The placeholder strings and the comments in
`database/db.py` describe a guided build, and the "Step N" numbers are the
curriculum's ordering: Step 1 the database layer, Step 3 logout, Step 4 profile,
Steps 7–9 expense create/edit/delete. `database/db.py` is comments only — it
specifies `get_db()` (SQLite connection with `row_factory` and foreign keys on),
`init_db()` (`CREATE TABLE IF NOT EXISTS`), and `seed_db()`. Nothing imports it
yet; there is no schema, no models, and no auth. When implementing a step, honor
the stub's stated design rather than reaching for an ORM, and keep SQL in
`database/` instead of inlining it into route handlers — that separation is the
point of the exercise.

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

- `file.md` is a dumped transcript of an earlier Claude Code session, not
  documentation. Nothing reads it; treat it as cruft.
- `hero_image.png` sits at the repo root, unreferenced by any template or
  stylesheet. It is not wired into the hero and is not served — `static/` is the
  only directory Flask serves assets from.
- Commits follow a `<area>: <imperative summary>` subject, e.g.
  `landing: add youtube modal on see how it works click`.
