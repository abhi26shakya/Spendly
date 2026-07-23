# Spec: Add Expense

## Overview
Step 7 is the first write path a real user gets: until now every expense in the
app came from `seed_db()`, so a freshly registered account sees an empty profile
with no way to fill it. This step replaces the `/expenses/add` placeholder with a
real form — amount, category, date and an optional description — that inserts a
row into `expenses` owned by the logged-in user and returns them to the profile
page, where the stats, recent activity and category breakdown built in Steps 5
and 6 immediately reflect the new spend. It also introduces the first write
helper in the data layer beyond `create_user()`, establishing the shape that
Steps 8 (edit) and 9 (delete) will follow.

## Depends on
- Step 1: Database setup (`expenses` table, `CATEGORIES` list in `database/db.py`)
- Step 3: Login / Logout (`session["user_id"]` is what stamps ownership on a row)
- Step 4: Profile page design (where the new expense lands and is verified)
- Step 5: Backend connection (`database/queries.py`, the read helpers that must
  pick the new row up with no change)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the expense, then redirect to
  `/profile` — logged-in only

Both replace the current placeholder `@app.route("/expenses/add")` that returns
`"Add expense — coming in Step 7"`. Logged out, both redirect to `/login`
exactly as `/profile` does — the `POST` must never insert for an anonymous
caller. The endpoint name stays `add_expense`, so the existing
`url_for('add_expense')` link in `templates/analytics.html` keeps working.

## Database changes
No database changes. `expenses` already has every column this step writes:
`user_id`, `amount`, `category`, `date`, `description` (nullable) and a
defaulted `created_at`. `user_id` already carries
`REFERENCES users(id)` and `get_db()` turns on `PRAGMA foreign_keys`, so an
orphan row is rejected by the database.

## Templates
- **Create:** `templates/expense_form.html`
  - Extends `base.html`, follows the `auth-card` shape used by
    `register.html` — a titled card holding one `POST` form.
  - Fields: `amount` (`<input type="number" step="0.01" min="0.01">`),
    `category` (`<select>` populated from `CATEGORIES`, no hardcoded option
    list in the template), `date` (`<input type="date">`, defaulting to today)
    and `description` (`<input type="text">`, optional).
  - Renders a single inline error message in the same style as the auth pages,
    and re-fills every field with what the user submitted so a rejected form
    never loses their input.
  - Page-specific CSS goes inline in `{% block head %}` per the asset
    convention; only reuse of existing global classes goes uncommented.
  - Named `expense_form.html` rather than `expense_add.html` because Step 8's
    edit screen is the same form with different values and a different action.
- **Modify:** `templates/profile.html`
  - Add an "Add expense" button linking to `url_for('add_expense')`, placed in
    the Recent activity card header so it is reachable from the page the user
    lands on.
  - Extend the existing empty state so the "No expenses yet." case invites the
    user into the form (the "No expenses in this range." wording is unchanged).

## Files to change
- `app.py` — replace the `add_expense` placeholder with a `GET`/`POST` route:
  guard on `session["user_id"]`, validate the submitted fields, call the new
  insert helper, redirect to `profile` on success and re-render the form with an
  error on failure.
- `database/db.py` — add `create_expense(user_id, amount, category, date,
  description)`, mirroring `create_user()`: opens its own connection, one
  parameterised `INSERT`, commits, returns `cursor.lastrowid`, closes in a
  `finally`.
- `templates/profile.html` — the "Add expense" entry point and empty-state copy.

## Files to create
- `templates/expense_form.html` — the form template described above.

Validation helpers (parsing the amount, checking the category against
`CATEGORIES`, checking the date parses as ISO) live in `app.py` beside
`_resolve_range` and the other private view helpers — they are request
handling, not SQL.

## New dependencies
No new dependencies. `datetime.date.fromisoformat` and `float()` cover every
check this step needs.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` through `get_db()` only.
- Parameterised queries only — every submitted value is a bound parameter.
- Passwords hashed with `werkzeug` (unchanged in this step — no auth code moves).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Keep SQL out of the route: the `INSERT` belongs in `database/db.py`, which
  owns writes, not in `app.py` and not in `queries.py`, which is read-only.
- `user_id` comes from `session`, never from the form — a submitted `user_id`
  field must be ignored entirely.
- The category is validated against `database.db.CATEGORIES` server-side; a
  value outside that list is rejected even though the `<select>` makes it
  awkward to send one.
- Validate on the server regardless of the HTML input types — `type="number"`
  and `required` are conveniences, not a guarantee.
- Rejections re-render the form with HTTP 200, the error message and the
  submitted values. No 400s, no tracebacks, no silent redirect that discards
  what the user typed.
- A successful `POST` ends in `redirect(url_for("profile"))`, so a refresh
  cannot double-insert.
- Link internal routes with `url_for('add_expense')`, never `/expenses/add`.
- Currency stays `₹` throughout; the amount is stored as a bare `REAL`, with no
  symbol or thousands separator in the database.
- `date` is stored as ISO `YYYY-MM-DD` text — the same format `_range_clause`
  compares against. Anything else silently breaks Step 6's filter.
- Do not touch `seed_db()` or the seed data to test this; add expenses through
  the form.

## Definition of done
- [ ] Logged out, `GET /expenses/add` redirects to `/login`, and a `POST` to it
      redirects to `/login` without inserting a row.
- [ ] Logged in as the seed user, `/expenses/add` renders a form with an amount
      field, a category dropdown listing all seven `CATEGORIES`, a date field
      pre-filled with today, and an optional description.
- [ ] Submitting ₹250.00 / Food / today / "Dinner" redirects to `/profile`,
      where the new row is the top entry in Recent activity, the total rises by
      250.00 and the transaction count rises by 1.
- [ ] The new expense appears under `?range=month` and `?range=30d` and moves
      the Food share of the category breakdown, which still sums to 100 %.
- [ ] Submitting an empty amount, `0`, a negative amount, or `abc` re-renders
      the form with a visible error, keeps the other fields filled in, and
      inserts nothing.
- [ ] Submitting a missing or malformed date re-renders the form with an error
      and inserts nothing.
- [ ] Submitting a category not in `CATEGORIES` (e.g. via `curl`) is rejected
      with an error, not stored.
- [ ] Submitting with the description left blank succeeds, and the row shows on
      the profile page without a traceback from the empty description.
- [ ] Refreshing the profile page after a successful add does not create a
      second copy of the expense.
- [ ] A second registered user's profile does not show the first user's new
      expense.
- [ ] `git status` shows no `spendly.db` — the database is still ignored.
