# Spec: Delete Expense

## Overview
Step 7 let a user file an expense and Step 8 let them correct one; Step 9 lets
them remove one outright — a duplicate submission, a row filed against the wrong
account, or an expense that never happened. It replaces the
`/expenses/<id>/delete` placeholder with a real route and finishes the CRUD set
that the profile page reads from. The interesting part of this step is not the
`DELETE` statement, which is three lines, but the method: the placeholder is
currently a `GET` route, and a destructive action must not stay on `GET`. A link
that deletes a row can be fired by a browser prefetch, a crawler, or an
`<img src>` on another site, none of which involve the user deciding anything.
So this step turns the action into a `POST`-only route submitted from a small
form in each transaction row, reusing verbatim the ownership rule Step 8
introduced — *this row exists **and** belongs to you, otherwise 404*.

## Depends on
- Step 1: Database setup (the `expenses` table the row is removed from)
- Step 3: Login / Logout (`session["user_id"]` is the owner the row is checked
  against)
- Step 5: Backend connection (`database/queries.py`, `get_recent_transactions()`
  already returns each row's `id`)
- Step 6: Date filter (the profile page the user is redirected back to)
- Step 8: Edit expense (`get_expense_by_id()`, the `AND user_id = ?` ownership
  pattern, and the per-row actions cell in the transactions table that this
  step adds a second control to)

## Routes
- `POST /expenses/<int:id>/delete` — delete that expense, then redirect to
  `/profile` — logged-in only, owner only

This replaces the current placeholder `@app.route("/expenses/<int:id>/delete")`
that returns `"Delete expense — coming in Step 9"`. The endpoint name stays
`delete_expense` and it keeps its `id` parameter, so `url_for('delete_expense',
id=...)` remains the only way a template addresses it.

`methods=["POST"]` is the whole point of the route, so a `GET` on the same URL
must return `405`, not the row's deletion and not a confirmation page. There is
no `GET /expenses/<id>/delete` in this step: the confirmation happens in the
browser before the form submits, not on a server-rendered intermediate page.

Logged out, the `POST` redirects to `/login` exactly as `/profile`,
`/expenses/add` and `/expenses/<id>/edit` do, and must never reach the database.
Logged in but naming an id that does not exist **or** belongs to someone else,
it returns `404` — the same deliberately indistinguishable pair as Step 8, so
the URL cannot be used to probe which ids another account owns.

## Database changes
No database changes. The `expenses` table already exists with the
`user_id INTEGER NOT NULL REFERENCES users(id)` foreign key, and nothing
references `expenses` in turn, so removing a row breaks no constraint. The
deletion is a real `DELETE` — no `deleted_at` column, no soft-delete flag. Every
existing query (`get_summary_stats`, `get_recent_transactions`,
`get_category_breakdown`) would need a new `WHERE` clause the moment rows could
be present-but-hidden, and that is not a change this step is making.

## Templates
- **Create:** none.
- **Modify:** `templates/profile.html`
  - Add a `Delete` control beside the existing `Edit` link in the
    `.profile-table-actions` cell of each transaction row. Because the route is
    `POST`-only, it is a `<form method="post">` posting to
    `url_for('delete_expense', id=expense.id)` with a single icon `<button>` —
    not an `<a href>`.
  - The two controls now share the cell, so it needs to lay them out (e.g. an
    inline flex wrapper) and the form must not introduce vertical space of its
    own. Style the button to match `.profile-edit` — same size, same
    hover-reveal behaviour — with a distinct hover colour drawn from an existing
    CSS variable.
  - Give the button an `aria-label` naming what it deletes, matching how the
    `Edit` link already labels itself.
  - The empty-state row's `colspan="5"` is already correct and does not change:
    this step adds a control inside the existing actions column, not a new
    column.
  - Add a confirmation step in the page's `{% block scripts %}`: intercept the
    delete forms' `submit` and require a `confirm()` before letting it through.
    This is a guard against a misclick, not a security control — the server
    never depends on it.
  - Both the CSS and the JS go inline in this template's `{% block head %}` and
    `{% block scripts %}`, following `landing.html`. Nothing is added to
    `static/css/style.css` or `static/js/main.js`.

## Files to change
- `app.py`
  - Replace the `delete_expense` placeholder with a `POST`-only route: guard on
    `session["user_id"]` before touching the database, call the new delete
    helper scoped to that user, `abort(404)` when it reports that nothing was
    deleted, and otherwise `redirect(url_for("profile"))`.
  - Move the route up out of the "Placeholder routes — students will implement
    these" section to sit beside `edit_expense`, and delete that section's
    header comment if `delete_expense` was the last route under it.
- `database/db.py` — add `delete_expense(expense_id, user_id)` next to
  `update_expense()`: same shape (own connection, one parameterised statement,
  `commit`, `close` in a `finally`), one
  `DELETE FROM expenses WHERE id = ? AND user_id = ?`, returning
  `cursor.rowcount` so the caller can tell a real deletion from a no-such-row
  without a second query.
- `templates/profile.html` — the per-row delete form, its inline styles, and the
  inline confirmation script, as described above.

## Files to create
No new files. There is no confirmation template — the confirmation is a browser
`confirm()` on the existing page.

## New dependencies
No new dependencies. `flask.abort` is already imported in `app.py` from Step 8.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` through `get_db()` only.
- Parameterised queries only — the id from the URL and the user id from the
  session are both bound parameters.
- Passwords hashed with `werkzeug` (unchanged in this step — no auth code moves).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Keep SQL out of the route: the `DELETE` belongs in `database/db.py`, which
  owns writes. It may not be inlined into `app.py`.
- **The route accepts `POST` only.** Do not leave `GET` on it "for convenience"
  and do not add a separate `GET` confirmation route. A destructive action
  reachable by following a link is the specific mistake this step exists to
  avoid.
- **Ownership is enforced in SQL, in the `DELETE` itself.** The statement carries
  `AND user_id = ?` with the id from `session`. Do not `SELECT` the row, compare
  `user_id` in Python, and then `DELETE` by id alone.
- `user_id` comes from `session`, never from the form or the URL. A `user_id`
  field in the submitted body is ignored entirely.
- A missing row and another user's row both produce the same `404`. Do not add a
  distinct message, status or redirect for the "not yours" case.
- Decide the outcome from `rowcount`: `0` means 404, `1` means redirect. Do not
  redirect to `/profile` on a failed delete as if it had worked.
- The delete is unconditional and immediate once the `POST` arrives — no
  archived copy, no `deleted_at`, no restore path. If it later needs one, that
  is a schema change and a different step.
- A successful `POST` ends in `redirect(url_for("profile"))`, so a refresh
  re-requests the profile page rather than re-posting the delete.
- Link internal routes with `url_for('delete_expense', id=...)`, never a
  hand-built `/expenses/{{ expense.id }}/delete`.
- The JS confirmation is progressive enhancement. With JavaScript disabled the
  form must still submit and the route must still work — no `onclick` handler
  that is the only thing wiring the button to the form.
- Do not touch `seed_db()`, the seed data or `spendly.db` to test this; delete
  through the UI. Deleting seeded rows is fine — `seed_db()` early-returns when
  `users` is non-empty, so they will not silently come back.

## Definition of done
- [ ] Logged out, `POST /expenses/1/delete` redirects to `/login` and the row is
      still present afterwards.
- [ ] `GET /expenses/1/delete` returns `405`, both logged in and logged out, and
      deletes nothing.
- [ ] Logged in as the seed user, every row of the Recent activity table shows a
      delete control next to `Edit`, aligned on one line with it, and both reveal
      themselves on row hover.
- [ ] Clicking delete raises a confirmation; cancelling it leaves the row in the
      table and the totals unchanged.
- [ ] Confirming it redirects to `/profile`, the row is gone from the table, the
      transaction count has dropped by exactly one, and the total has fallen by
      exactly that expense's amount.
- [ ] Deleting the only expense in a category removes that category from the
      breakdown entirely, and the remaining shares still sum to 100 %.
- [ ] Deleting the last remaining expense renders the empty state spanning the
      full table width, with the "Add your first expense" link.
- [ ] `POST /expenses/99999/delete` returns 404, not a traceback and not a
      redirect to `/profile`.
- [ ] Logged in as a second registered user, posting to the seed user's expense
      id returns 404 and that expense is still present on the seed user's
      profile afterwards.
- [ ] Re-posting the same delete (e.g. a second `curl` with the same id) returns
      404 rather than a silent success, and nothing else is removed.
- [ ] After a delete, `?range=month` and `?range=all` both render without a
      traceback, with the deleted row absent from each.
- [ ] `/expenses/add` and `/expenses/<id>/edit` still work end to end — the
      shared profile table and its actions cell did not regress.
- [ ] `git status` shows no `spendly.db` — the database is still ignored.
