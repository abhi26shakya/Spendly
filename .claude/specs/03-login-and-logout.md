# Spec: Login and Logout

## Overview

Close the auth loop. Step 2 established a session at sign-up, but nothing reads
it and nothing clears it — a returning user has no way back in, and a signed-in
user has no way out. This step makes `/login` accept a POST that verifies an
email and password against the `users` table, sets `session["user_id"]`, and
redirects to `/profile`; makes `/logout` clear the session and return to the
landing page; and makes the navbar reflect which of the two states the visitor is
in. It is the first feature that *reads* the session rather than only writing it,
and it is what makes the demo user (`demo@spendly.com` / `demo123`) reachable
through the UI for the first time. Everything after it — profile in Step 4,
expense CRUD in Steps 7–9 — assumes a user can sign in and out at will.

## Depends on

- **Step 1 — Database setup.** Supplies `get_db()`, the `users` table, and the
  seeded demo user this step's login is verified against.
- **Step 2 — Registration** (merged in `b68fd08`). Supplies `app.secret_key`, the
  session convention (`session["user_id"]`), and the `password_hash` column
  populated by `generate_password_hash` — `check_password_hash` in this step is
  the other half of that pair.

## Routes

- `GET /login` — render the sign-in form — public *(exists; currently the whole
  route)*
- `POST /login` — verify credentials, set the session, redirect to `/profile` —
  public *(new)*
- `GET /logout` — clear the session, redirect to `/` — public *(exists as the
  placeholder string `"Logout — coming in Step 3"`; becomes real)*

No new route paths. `/logout` stays `GET` so the navbar can link to it with a
plain `<a href>`; it is a teaching scaffold, and a POST-and-CSRF-token logout is
out of scope for this step.

## Database changes

**No database changes.** The `users` table from Step 1 already holds every column
login reads (`id`, `email`, `password_hash`), and logout touches no table at all.

**One gap to close, not a schema change:** spec 02 listed
`get_user_by_email(email)` under "Files to change", but it was never written —
`database/db.py` today has `get_db`, `init_db`, `_seed_dates`, `seed_db`, and
`create_user`, and nothing else. This step adds it. Verify with
`grep -n "^def " database/db.py` before assuming it exists.

## Templates

- **Create:** none. `templates/login.html` already exists, extends `base.html`,
  and already renders `{% if error %}` into `.auth-error`.
- **Modify:** `templates/login.html`
  - Change `action="/login"` to `action="{{ url_for('login') }}"`. The hardcoded
    path breaks the CLAUDE.md `url_for` convention, and the form is currently
    dead regardless: it POSTs to a GET-only route and gets a 405.
  - Repopulate the `email` input with `{{ email }}` after a failed attempt.
    Never repopulate the password field.
- **Modify:** `templates/base.html`
  - Make `.nav-links` session-aware: when `session["user_id"]` is set, show
    "Profile" and "Sign out"; otherwise keep today's "Sign in" and "Get started".
  - `session` is available in Jinja with no `context_processor` — Flask injects
    it into every template by default. Do not pass it from each route.

No CSS work. `.nav-links a` (style.css:110) styles any bare navbar link, so
"Sign out" and "Profile" inherit it. `.auth-error`, `.form-group`,
`.form-input`, `.btn-submit`, and `.auth-switch` are all already defined.

## Files to change

- `database/db.py`
  - Add `get_user_by_email(email)` — parameterised `SELECT`, returns the
    `sqlite3.Row` or `None`. Close the connection in a `finally`, matching
    `create_user`.
- `app.py`
  - Import `check_password_hash` from `werkzeug.security`, and
    `get_user_by_email` from `database.db`.
  - Extend `login()` to `methods=["GET", "POST"]` and implement the POST path.
  - Replace the `logout()` placeholder body with `session.clear()` and a redirect
    to `landing`.
- `templates/login.html` — as described above.
- `templates/base.html` — as described above.
- `CLAUDE.md` — Step 3 is described as stubbed in two places (the "Architecture"
  paragraph and the "Auth is session-based" paragraph, which says "Nothing reads
  the session yet — login and logout are Step 3"). Update both once this lands.

## Files to create

None.

## New dependencies

**No new dependencies.** `flask` and `werkzeug` (already required by
`generate_password_hash`) cover it — `check_password_hash` ships in the same
module.

## Rules for implementation

- No SQLAlchemy or ORMs.
- Parameterised queries only — never string-format values into SQL.
- Passwords hashed with werkzeug. Verify with
  `werkzeug.security.check_password_hash` — never compare hashes with `==`, and
  never re-hash the submitted password to compare digests (the salt makes that
  fail every time).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- **Keep SQL in `database/db.py`.** The route calls `get_user_by_email()`; it
  must not open a connection or write SQL itself.
- Link internal routes with `url_for()`, never hardcoded paths.
- Re-render `login.html` with an `error` string on a failed attempt — do not
  redirect and do not use `flash`, matching how `register` handles errors.
- Lowercase and strip the submitted email before the lookup. Registration stores
  it lowercased, so a raw `Demo@Spendly.com` would otherwise miss.
- Use `session.clear()` in logout, not `session.pop("user_id")` — it drops
  everything, so no stale key outlives the sign-out.
- Logout must not error when nobody is signed in. `session.clear()` on an empty
  session is a no-op; just redirect.

### The one security rule that shapes the code

**Give one error message for both failure modes.** A missing email and a wrong
password must both produce `"Incorrect email or password."` Distinct messages
turn the form into an oracle that confirms which emails have accounts.

That has a consequence worth stating outright: do not early-return when the email
lookup comes back `None`. Structure it so both paths converge on the same
message:

```python
user = get_user_by_email(email)
if user is None or not check_password_hash(user["password_hash"], password):
    error = "Incorrect email or password."
```

### Validation rules

| Field | Rule | Error message |
| --- | --- | --- |
| email | required, stripped, lowercased | "Incorrect email or password." |
| password | required | "Incorrect email or password." |
| both | email exists **and** password matches | "Incorrect email or password." |

No length or format checks on login. An 8-character minimum belongs at sign-up;
enforcing it here would reject a valid pre-existing password and leak the rule.
Note that the seeded `demo123` is 6 characters — a length check would lock the
demo user out of their own account.

## Definition of done

- [ ] App starts with no errors: `./venv/bin/python app.py` → http://127.0.0.1:5001
- [ ] `GET /login` renders the form as before, with no visual regression
- [ ] Signing in as `demo@spendly.com` / `demo123` lands on `/profile` (currently
      the string "Profile page — coming in Step 4") — proving the session was set
- [ ] `DEMO@Spendly.com` / `demo123` signs in too — the email is case-insensitive
- [ ] A wrong password re-renders the form with "Incorrect email or password."
- [ ] An unregistered email re-renders the form with the *same* message, byte for
      byte — compare the two responses, do not eyeball them
- [ ] After a failed attempt the email field retains what was typed and the
      password field is empty
- [ ] While signed in, the navbar shows "Profile" and "Sign out"; while signed
      out it shows "Sign in" and "Get started" — verify both with a headless
      Chrome screenshot, since `curl` cannot show the rendered navbar
- [ ] Clicking "Sign out" returns to `/` and the navbar reverts to the signed-out
      links; revisiting `/profile` no longer shows a signed-in session
- [ ] `GET /logout` while already signed out redirects to `/` without erroring
- [ ] A fresh account created via `/register` can sign out, then sign back in
      with the same credentials — the full round trip
- [ ] No plaintext password is written to the database or the server log
