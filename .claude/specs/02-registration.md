# Spec: Registration

## Overview

Turn `/register` from a GET-only page that renders a dead form into a working
sign-up flow. The route accepts a POST, validates name / email / password,
hashes the password with werkzeug, inserts a row into the `users` table built in
Step 1, logs the new user in via the Flask session, and redirects to `/profile`.
This is the first feature that writes to the database from a request, and the
first to establish a logged-in session — every later step (logout in Step 3,
profile in Step 4, expense CRUD in Steps 7–9) reads `session["user_id"]` to know
who is acting.

## Depends on

- **Step 1 — Database setup** (merged in `a1afe0c`). Supplies `get_db()`, the
  `users` table, and the `UNIQUE` constraint on `email` that duplicate-email
  handling relies on.

## Routes

- `GET /register` — render the empty sign-up form — public *(exists; currently
  the whole route)*
- `POST /register` — validate input, create the user, set the session, redirect
  to `/profile` — public *(new)*

No other routes change. `/login` and `/logout` stay untouched — they are Step 3.

## Database changes

**No database changes.** The `users` table from Step 1 already has every column
this feature writes (`name`, `email`, `password_hash`) and `created_at` defaults
to `datetime('now')`. The `UNIQUE` constraint on `email` is already in place.

**One correction, not a change:** `database/db.py:7` points `DB_PATH` at
`expense_tracker.db`, but the only database on disk is `spendly.db` — which
holds the seeded data and which nothing currently reads. Repoint `DB_PATH` to
`spendly.db` so the app reads the real file, and update `.gitignore` to match.
This must land before registration is tested, or new users will be written into
a freshly-created `expense_tracker.db` instead.

## Templates

- **Create:** none. `templates/register.html` already exists, extends
  `base.html`, and already renders `{% if error %}` into `.auth-error`.
- **Modify:** `templates/register.html`
  - Change `action="/register"` to `action="{{ url_for('register') }}"` —
    CLAUDE.md requires `url_for` for internal routes, never hardcoded paths.
  - Repopulate `name` and `email` inputs with `{{ name }}` / `{{ email }}` on a
    validation failure so a rejected submission does not clear the whole form.
    Never repopulate either password field.
  - Add a `confirm_password` field below `password`, same `.form-group` /
    `.form-input` markup.

No CSS work. `.auth-error`, `.form-group`, `.form-input`, `.btn-submit`, and
`.auth-switch` are all already defined in `static/css/style.css` (lines
471–544).

## Files to change

- `database/db.py`
  - Repoint `DB_PATH` to `spendly.db`.
  - Add `get_user_by_email(email)` — returns the row or `None`.
  - Add `create_user(name, email, password)` — hashes the password, inserts,
    returns the new `id` via `cursor.lastrowid`.
- `app.py`
  - Import `session`, `redirect`, `url_for`, `request` from flask.
  - Import `create_user`, `get_user_by_email` from `database.db`.
  - Set `app.secret_key` — required for `session` to work.
  - Extend `register()` to `methods=["GET", "POST"]` and implement the POST path.
- `templates/register.html` — as described above.
- `.gitignore` — replace `expense_tracker.db` with `spendly.db`.

## Files to create

None.

## New dependencies

**No new dependencies.** `flask`, `werkzeug` (for `generate_password_hash`), and
`sqlite3` from the standard library cover all of it.

## Rules for implementation

- No SQLAlchemy or ORMs.
- Parameterised queries only — never string-format values into SQL.
- Passwords hashed with `werkzeug.security.generate_password_hash`. Never store
  or log a plaintext password.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- **Keep SQL in `database/db.py`.** The route calls `create_user()` and
  `get_user_by_email()`; it must not open a connection or write SQL itself. That
  separation is the point of the exercise.
- Link internal routes with `url_for()`, never hardcoded paths.
- Re-render `register.html` with an `error` string on invalid input — do not
  redirect and do not use `flash`, since the template already handles `error`.
- Rely on the `UNIQUE` constraint as the source of truth for duplicate emails:
  catch `sqlite3.IntegrityError` rather than trusting a prior `SELECT` to stay
  true.

### Validation rules

| Field | Rule | Error message |
| --- | --- | --- |
| name | required, stripped, non-empty | "Please enter your name." |
| email | required, stripped, lowercased, contains `@` | "Please enter a valid email address." |
| email | not already registered | "That email is already registered." |
| password | required, at least 8 characters | "Password must be at least 8 characters." |
| confirm_password | required, must equal `password` | "Those passwords do not match." |

Store email lowercased and stripped so `Nitish@Example.com` and
`nitish@example.com` cannot become two accounts. The 8-character minimum matches
the placeholder text the form already shows.

Check the rules in the order listed. The length rule fires before the match rule
so a short password reports its own problem, rather than making the user fix a
mismatch and only then discover the length limit. The match is enforced
server-side, not just via the HTML `required` attribute — a POST that omits
`confirm_password` entirely must still be rejected.

## Definition of done

- [ ] App starts with no errors: `./venv/bin/python app.py` → http://127.0.0.1:5001
- [ ] `database/db.py` reads `spendly.db`; no `expense_tracker.db` is created on
      startup, and the existing seeded users remain visible to the app
- [ ] `GET /register` renders the form as before, with no visual regression
- [ ] Submitting valid details creates exactly one new row in `users`, verifiable
      with `sqlite3 spendly.db "SELECT id, name, email FROM users"`
- [ ] The stored `password_hash` is a werkzeug hash, not the plaintext password
- [ ] After a successful submit the browser lands on `/profile` (currently the
      string "Profile page — coming in Step 4") — proving the session was set
- [ ] Submitting an email that already exists re-renders the form with "That
      email is already registered." and creates no new row
- [ ] Submitting a blank name, a malformed email, or a 7-character password
      re-renders the form with the matching error and creates no new row
- [ ] Two different passwords re-render with "Those passwords do not match." and
      create no new row; a POST omitting `confirm_password` is rejected too
- [ ] After a failed submit the name and email fields retain what was typed and
      both password fields are empty
- [ ] `demo@spendly.com` / `demo123` still exists and is untouched
