# Spec: Date Filter For Profile Page

## Overview
Step 6 lets a logged-in user narrow their profile page to a date range. Step 5
wired the four profile sections — summary stats, recent activity, category
breakdown, and the user header — to live SQLite data, but every one of them
reports on the user's entire history. This step adds a filter bar to the profile
page that scopes the three data sections (stats, transactions, breakdown) to a
chosen range, driven entirely by query-string parameters on `GET /profile` so
the filtered view is bookmarkable and survives a refresh. It also establishes
the date-range plumbing in `database/queries.py` that Steps 7–9 will inherit
once users can create expenses of their own.

## Depends on
- Step 1: Database setup (`expenses.date` stored as `YYYY-MM-DD` text)
- Step 3: Login / Logout (`session["user_id"]` is set, `/profile` is guarded)
- Step 4: Profile page design (the card layout the filter bar sits inside)
- Step 5: Backend connection (`database/queries.py` and its four helpers exist)

## Routes
No new routes. The existing `GET /profile` route is modified to read two
optional query-string parameters — access level unchanged (logged-in only):

- `GET /profile?range=<preset>` — one of `month`, `30d`, `year`, `all`
- `GET /profile?start=<YYYY-MM-DD>&end=<YYYY-MM-DD>` — explicit custom range

`range` and the explicit pair are mutually exclusive; when both are present the
explicit `start`/`end` wins. With neither present the page defaults to `all`,
so the unfiltered `/profile` URL renders exactly as it does today.

## Database changes
No database changes. `expenses.date` is already `TEXT NOT NULL` holding
ISO `YYYY-MM-DD`, which compares correctly with `BETWEEN` as a string — no
column, index, or constraint is needed for the ranges this step supports.

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar directly above the `profile-grid` block: four preset links
    (`This month`, `Last 30 days`, `This year`, `All time`) and a small
    `GET` form with two `<input type="date">` fields plus an Apply button.
  - The active preset gets an `is-active` class; the date inputs are
    pre-filled with the resolved range so the form always reflects what is
    on screen.
  - Add an empty state inside the Recent activity card — when the filtered
    result is empty, show "No expenses in this range." instead of a bare table.
  - Show the resolved range as a caption under the stats row (e.g.
    "1 Jul 2026 – 23 Jul 2026", or "All time").
  - Add an inline error line when the submitted dates are invalid.
  - New styles go inline in this template's `{% block head %}`, per the asset
    convention — not in `static/css/style.css`.

## Files to change
- `app.py` — `profile()` parses/validates the range, passes it to the query
  helpers, and hands the resolved range plus the active preset to the template.
- `database/queries.py` — `get_summary_stats`, `get_recent_transactions` and
  `get_category_breakdown` each take optional `start` and `end` keyword
  arguments and add a `date BETWEEN ? AND ?` clause when both are supplied.
- `templates/profile.html` — filter bar, range caption, empty state, styles.

## Files to create
No new files. The range-resolution helper (preset name → `(start, end)` pair,
and validation of user-supplied dates) belongs in `app.py` alongside the other
private view helpers (`_initials`, `_to_view_categories`), since it is
presentation logic, not SQL.

## New dependencies
No new dependencies. `datetime` and `dateutil`-free arithmetic from the
standard library cover every preset.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` through `get_db()` only.
- Parameterised queries only — the range bounds are bound parameters, never
  string-formatted into the SQL. Preset names must never reach the query layer.
- Passwords hashed with `werkzeug` (unchanged in this step — no auth code moves).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- No inline `style=` attributes; page CSS goes in `{% block head %}`.
- Currency stays `₹` throughout.
- Link internal routes with `url_for('profile', range=...)`, never a hardcoded
  `/profile?range=...`.
- An unknown `range` value, a malformed date, or `start` later than `end` must
  fall back to the default all-time view with a visible message — never a 400,
  never a traceback.
- `get_*` helpers keep their existing signatures working: calling them without
  `start`/`end` must behave exactly as it does today, so Step 5's tests still
  pass.
- Filtering changes what the stats describe: `total_spent`,
  `transaction_count`, `top_category` and every `pct` must be computed over the
  filtered rows, not the full history. `pct` still sums to exactly 100.
- `user.member_since` is account metadata and is never filtered.
- Both bounds are inclusive — an expense dated exactly `start` or exactly `end`
  is in the range.
- Preset semantics, evaluated against today's date on each request:
  `month` = 1st of the current month → today; `30d` = today − 29 days → today
  (30 days inclusive); `year` = 1 Jan of the current year → today;
  `all` = no date clause at all.

## Definition of done
- [ ] Logged in as the seed user, `/profile` with no query string renders
      exactly as before: ₹346.24 total, 8 transactions, top category Bills.
- [ ] The filter bar shows four presets and a custom date form, with `All time`
      marked active on the unfiltered page.
- [ ] Clicking `This month` loads `/profile?range=month` and the stats,
      transaction list and category breakdown all reflect only that month's
      rows (all 8 seed expenses, since the seed spreads them over this month).
- [ ] Clicking `This year` gives the same 8 rows; `Last 30 days` gives the
      subset of seed rows dated within the last 30 days.
- [ ] Submitting a custom range covering only the first half of the current
      month reduces the transaction count and the total, and the category
      percentages still add up to 100 %.
- [ ] Submitting a range with no expenses in it shows ₹0.00 total, 0
      transactions, top category `—`, an empty category breakdown, and the
      "No expenses in this range." message — no error.
- [ ] `start` later than `end`, a garbage date like `2026-13-45`, and
      `?range=banana` each render the all-time view with a visible message and
      HTTP 200 — no traceback in the server log.
- [ ] The resolved range caption under the stats row matches the dates in the
      two date inputs after any filter is applied.
- [ ] Copying the filtered URL into a new tab reproduces the same filtered
      page.
- [ ] `/profile?range=month` while logged out still redirects to `/login`.
