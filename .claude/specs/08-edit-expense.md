# Spec: Edit Expense

## Overview
Step 7 gave users a way to put an expense into the database; Step 8 gives them a
way to fix one. A mistyped amount, the wrong category or a date off by a day are
currently permanent — the only recorded correction is a second, compensating
row. This step replaces the `/expenses/<id>/edit` placeholder with a real
`GET`/`POST` pair that loads one of the logged-in user's expenses into the same
form Step 7 built, and writes the changed values back with an `UPDATE`. It is
also the first route in the app keyed on a resource id rather than on the
session alone, so it introduces the ownership check — *this row exists **and**
belongs to you* — that Step 9's delete will reuse verbatim.

## Depends on
- Step 1: Database setup (`expenses` table, `CATEGORIES` in `database/db.py`)
- Step 3: Login / Logout (`session["user_id"]` is the owner the row is checked
  against)
- Step 5: Backend connection (`database/queries.py`, the read layer this step
  adds a single-row lookup to)
- Step 6: Date filter (the edited row must still land correctly in a range)
- Step 7: Add expense (`templates/expense_form.html`, `_validate_expense()` and
  `create_expense()` — this step reuses all three rather than duplicating them)

## Routes
- `GET /expenses/<int:id>/edit` — render the form pre-filled with that expense —
  logged-in only, owner only
- `POST /expenses/<int:id>/edit` — validate and update the expense, then
  redirect to `/profile` — logged-in only, owner only

Both replace the current placeholder `@app.route("/expenses/<int:id>/edit")`
that returns `"Edit expense — coming in Step 8"`. The endpoint name stays
`edit_expense` and it keeps its `id` parameter, so `url_for('edit_expense',
id=...)` is the only way any template links to it.

Logged out, both redirect to `/login` exactly as `/profile` and `/expenses/add`
do — the `POST` must never reach the database for an anonymous caller. Logged in
but requesting an id that does not exist **or** belongs to someone else, both
return `404`. The two cases are deliberately indistinguishable: a `403` for
"someone else's row" would confirm that the id exists, turning the URL into a
way to count another account's expenses.

## Database changes
No database changes. Every column this step writes — `amount`, `category`,
`date`, `description` — already exists on `expenses` and is already written by
`create_expense()`. `user_id` and `created_at` are deliberately **not** updated:
an expense does not change owner, and `created_at` records when the row was
filed, not when it was last touched.

## Templates
- **Create:** none.
- **Modify:** `templates/expense_form.html`
  - Generalise the one form Step 7 named for this moment. The hardcoded
    `action="{{ url_for('add_expense') }}"`, the `Add an expense` heading, its
    subtitle, the `Add expense` submit label and the `Add expense — Spendly`
    title all become variables passed by the route (e.g. `form_action`,
    `heading`, `subtitle`, `submit_label`). Nothing about the fields, the
    validation error block, the re-fill behaviour or the inline
    `{% block head %}` CSS changes.
  - The `Cancel` link keeps pointing at `url_for('profile')` for both modes.
- **Modify:** `templates/profile.html`
  - Add an `Edit` action to each row of the Recent activity table, linking to
    `url_for('edit_expense', id=expense.id)`. It needs a fifth `<th>`, and the
    empty-state `<td colspan="4">` must become `colspan="5"` or the empty row
    will render narrower than the header.
  - Style the action inline in the page's existing `{% block head %}` block,
    using CSS variables — no new rules in `static/css/style.css`.

## Files to change
- `app.py`
  - Replace the `edit_expense` placeholder with a `GET`/`POST` route: guard on
    `session["user_id"]`, fetch the expense scoped to that user, `abort(404)`
    when there is no such row, and on `GET` render the form pre-filled from it.
    On `POST`, run the existing `_validate_expense(request.form)`, call the new
    update helper on success and redirect to `profile`, or re-render the form
    with the error and the submitted values on failure.
  - Add `abort` to the existing `flask` import.
  - Both `add_expense` and `edit_expense` now build the same
    `render_template("expense_form.html", ...)` call with different labels;
    factor the shared arguments into one small private helper beside
    `_validate_expense` rather than repeating the argument list four times.
- `database/db.py` — add `update_expense(expense_id, user_id, amount, category,
  expense_date, description)` next to `create_expense()`: same shape (own
  connection, one parameterised statement, `commit`, `close` in a `finally`),
  one `UPDATE ... WHERE id = ? AND user_id = ?`, returning `cursor.rowcount` so
  the caller can tell a real update from a no-such-row.
- `database/queries.py`
  - Add `get_expense_by_id(expense_id, user_id)` returning a plain dict of
    `id`, `amount`, `category`, `date` and `description`, or `None`. `user_id`
    is a required argument and belongs in the `WHERE` clause, not in an `if`
    after the fetch.
  - Extend `get_recent_transactions()` to select `id` and include it in each
    returned dict — the profile table cannot link to a row it does not know the
    id of. The formatted `"date"` stays as it is; nothing else about the
    function changes.
- `templates/expense_form.html` — parameterised as described above.
- `templates/profile.html` — the per-row `Edit` link, the extra header cell and
  the widened `colspan`.

## Files to create
No new files. The point of naming Step 7's template `expense_form.html` rather
than `expense_add.html` was that this step reuses it; a second near-identical
template would be the wrong outcome.

## New dependencies
No new dependencies. `flask.abort` is already available from the installed
Flask.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` through `get_db()` only.
- Parameterised queries only — every submitted value and the id from the URL are
  bound parameters.
- Passwords hashed with `werkzeug` (unchanged in this step — no auth code moves).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Keep SQL out of the route: the `UPDATE` belongs in `database/db.py`, which
  owns writes; the single-row `SELECT` belongs in `database/queries.py`, which
  owns reads. Neither statement may be inlined into `app.py`.
- **Ownership is enforced in SQL, on every request, in both methods.** Both the
  `SELECT` and the `UPDATE` carry `AND user_id = ?` with the id from `session`.
  Fetching the row on `GET` and trusting the browser not to `POST` a different
  id is not sufficient — the `POST` handler must re-check.
- `user_id` comes from `session`, never from the form or the URL. A `user_id`
  field in the submitted body is ignored entirely, and no route ever reassigns
  an expense's owner.
- A missing row and another user's row both produce the same `404`. Do not add a
  distinct message, status or redirect for the "not yours" case.
- Reuse `_validate_expense()` as it stands. Edit and add must accept and reject
  exactly the same values — if a rule needs changing, change it in that one
  function so both routes move together.
- Rejections re-render the form with HTTP 200, the error message and the
  submitted values, still on the edit URL. No 400s, no tracebacks, no redirect
  that discards what the user typed.
- A successful `POST` ends in `redirect(url_for("profile"))`, so a refresh
  cannot re-apply the update.
- Link internal routes with `url_for('edit_expense', id=...)`, never a
  hand-built `/expenses/{{ expense.id }}/edit`.
- Currency stays `₹`; the amount is stored as a bare rounded `REAL`, with no
  symbol or thousands separator in the database.
- `date` is stored as ISO `YYYY-MM-DD` text — the same format `_range_clause`
  compares against. An edited date in any other format silently breaks Step 6's
  filter.
- Do not touch `seed_db()`, the seed data or `spendly.db` to test this; edit
  through the form.

## Definition of done
- [ ] Logged out, `GET /expenses/1/edit` redirects to `/login`, and a `POST` to
      it redirects to `/login` without changing the row.
- [ ] Logged in as the seed user, the Recent activity table shows an `Edit`
      action on every row, and the empty state still spans the full table width.
- [ ] Clicking `Edit` opens the form with that expense's amount, category, date
      and description already filled in, headed for editing rather than adding.
- [ ] Changing the amount from ₹42.50 to ₹52.50 and submitting redirects to
      `/profile`, where that row now reads ₹52.50, the total has risen by
      exactly 10.00, and the transaction count is unchanged.
- [ ] Changing an expense's category moves it between segments of the category
      breakdown, which still sums to 100 %.
- [ ] Changing an expense's date to one outside `?range=month` removes it from
      that view and it reappears under `?range=all`.
- [ ] Clearing the description and submitting succeeds, and the profile page
      renders that row without a traceback.
- [ ] Submitting an empty amount, `0`, a negative amount, or `abc` re-renders
      the edit form with a visible error, keeps the other fields as typed, and
      leaves the stored row untouched.
- [ ] Submitting a malformed date, a future date, or a category not in
      `CATEGORIES` (e.g. via `curl`) is rejected with an error and stores
      nothing.
- [ ] `GET /expenses/99999/edit` returns 404, not a traceback and not an empty
      form.
- [ ] Logged in as a second registered user, both `GET` and `POST` on the seed
      user's expense id return 404, and the seed user's row is unchanged
      afterwards.
- [ ] Refreshing `/profile` after a successful edit does not apply the change a
      second time and does not create an extra row.
- [ ] `/expenses/add` still works end to end — the shared template did not
      regress.
- [ ] `git status` shows no `spendly.db` — the database is still ignored.
