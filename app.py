import os
import sqlite3
from datetime import date, timedelta

from flask import (
    Flask,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    create_expense,
    create_user,
    # Aliased because the route function below owns the plain name — the same
    # split edit_expense/update_expense get from being named differently.
    delete_expense as delete_expense_row,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
    update_expense,
)
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-not-for-production")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name:
        error = "Please enter your name."
    elif "@" not in email:
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    else:
        error = None

    if error is None:
        try:
            session["user_id"] = create_user(name, email, password)
            session["user_name"] = name
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            error = "That email is already registered."

    return render_template("register.html", error=error, name=name, email=email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    # One message for both failure modes — a distinct "no such email" would
    # confirm to an attacker which addresses have accounts.
    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Incorrect email or password.", email=email
        )

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


def _initials(name):
    """First and last initials of a name — "Demo User" becomes "DU"."""
    parts = name.split()
    if not parts:
        return "?"
    return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else parts[0][0].upper()


def _to_view_categories(breakdown):
    """Adapt get_category_breakdown() rows to what profile.html renders.

    `share` is the category's percentage of total spend — the number shown to
    the reader. `width` scales the bar against the largest category instead,
    rounded to the nearest 5 so it can be a CSS class rather than an inline
    style; the template carries a rule for every step from w0 to w100.
    """
    if not breakdown:
        return []

    largest = breakdown[0]["amount"]
    return [
        {
            "name": row["name"],
            "slug": row["name"].lower(),
            "total": row["amount"],
            "share": row["pct"],
            "width": round(row["amount"] / largest * 100 / 5) * 5 if largest else 0,
        }
        for row in breakdown
    ]


_PRESETS = ("month", "30d", "year", "all")


def _preset_bounds(preset, today):
    """Inclusive (start, end) dates for a named preset — (None, None) for all."""
    if preset == "month":
        return today.replace(day=1), today
    if preset == "30d":
        # 29 days back plus today itself is 30 days inclusive.
        return today - timedelta(days=29), today
    if preset == "year":
        return today.replace(month=1, day=1), today
    return None, None


def _format_day(value):
    """Format an ISO date like "2026-07-01" as "1 Jul 2026".

    The day is built by hand because %-d, the strftime flag for an unpadded
    day, is not portable.
    """
    day = date.fromisoformat(value)
    return f"{day.day} {day:%b %Y}"


def _range_label(start, end):
    """Caption for the resolved range, e.g. "1 Jul 2026 – 23 Jul 2026"."""
    if start and end:
        return f"{_format_day(start)} – {_format_day(end)}"
    if start:
        return f"From {_format_day(start)}"
    if end:
        return f"Up to {_format_day(end)}"
    return "All time"


def _resolve_range(args):
    """Turn ?range= / ?start= / ?end= into what the profile page needs.

    Returns {"preset", "start", "end", "label", "error", "active"} where start
    and end are ISO strings or None. Explicit dates win over a preset, and
    either one alone is allowed — a range open at the far end. Bad input never
    aborts: it falls back to all time and reports why, so a mistyped URL still
    renders a page.
    """
    start_raw = args.get("start", "").strip()
    end_raw = args.get("end", "").strip()

    if start_raw or end_raw:
        try:
            start = date.fromisoformat(start_raw) if start_raw else None
            end = date.fromisoformat(end_raw) if end_raw else None
        except ValueError:
            return _build_range("all", None, None, "Please enter valid dates.")

        if start and end and start > end:
            return _build_range(
                "all", None, None, "Start date must be on or before the end date."
            )

        return _build_range("custom", start, end, None)

    preset = args.get("range", "all").strip()
    if preset not in _PRESETS:
        return _build_range("all", None, None, "Unknown date range — showing all time.")

    start, end = _preset_bounds(preset, date.today())
    return _build_range(preset, start, end, None)


def _build_range(preset, start, end, error):
    """Assemble the range dict, converting the date objects to ISO strings."""
    start = start.isoformat() if start else None
    end = end.isoformat() if end else None
    return {
        "preset": preset,
        "start": start,
        "end": end,
        "label": _range_label(start, end),
        "error": error,
        "active": bool(start or end),
    }


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        # The session points at a user who no longer exists — treat it as
        # signed out rather than rendering a half-empty page.
        session.clear()
        return redirect(url_for("login"))

    date_filter = _resolve_range(request.args)
    start, end = date_filter["start"], date_filter["end"]

    stats = get_summary_stats(user_id, start=start, end=end)

    return render_template(
        "profile.html",
        user={**user, "initials": _initials(user["name"])},
        stats={
            "total": stats["total_spent"],
            "count": stats["transaction_count"],
            "top_category": stats["top_category"],
        },
        expenses=get_recent_transactions(user_id, start=start, end=end),
        categories=_to_view_categories(
            get_category_breakdown(user_id, start=start, end=end)
        ),
        date_filter=date_filter,
        # Both the transaction table and the breakdown fall back to this, so
        # the wording is decided once rather than twice in the template.
        empty_message=(
            "No expenses in this range."
            if date_filter["active"]
            else "No expenses yet."
        ),
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("analytics.html")


# Nothing in the schema bounds the description, so the limit is set here — a
# form field should not accept an unbounded string from an anonymous POST body.
DESCRIPTION_MAX = 500


def _validate_expense(form):
    """Check a submitted expense form.

    Returns (values, error). `values` is what the template re-fills the fields
    with, so a rejected form never loses what the user typed — amount and date
    stay as the raw strings they submitted. `error` is None when everything
    passed, and the amount in `values` is then a float rounded to 2 decimals,
    ready to store.

    The HTML input types are a convenience, not a guarantee: anything can POST
    here, so every field is checked again on this side.
    """
    amount_raw = form.get("amount", "").strip()
    category = form.get("category", "").strip()
    date_raw = form.get("date", "").strip()
    description = form.get("description", "").strip()

    values = {
        "amount": amount_raw,
        "category": category,
        "date": date_raw,
        "description": description,
    }

    try:
        amount = float(amount_raw)
    except ValueError:
        return values, "Please enter a valid amount."

    if amount <= 0:
        return values, "Amount must be greater than zero."

    if category not in CATEGORIES:
        return values, "Please choose a valid category."

    try:
        day = date.fromisoformat(date_raw)
    except ValueError:
        return values, "Please enter a valid date."

    if day > date.today():
        return values, "Date cannot be in the future."

    # The description is optional and free text, so the only thing to check is
    # its size. Rejecting rather than silently truncating — a form that quietly
    # eats half of what was typed is worse than one that says why.
    if len(description) > DESCRIPTION_MAX:
        return values, f"Description must be {DESCRIPTION_MAX} characters or fewer."

    # Store the rounded amount so the ₹ display and the stored REAL agree.
    values["amount"] = round(amount, 2)
    return values, None


def _render_expense_form(mode, values, error=None, expense_id=None):
    """Render expense_form.html for whichever of the two routes is calling.

    Add and edit submit the same fields to the same validator, so the only
    differences are the wording and where the form posts — everything else is
    identical and lives here rather than in four near-identical
    render_template() calls.
    """
    if mode == "edit":
        labels = {
            "heading": "Edit expense",
            "subtitle": "Update what you spent and where it went",
            "submit_label": "Save changes",
            "form_action": url_for("edit_expense", id=expense_id),
        }
    else:
        labels = {
            "heading": "Add an expense",
            "subtitle": "Record what you spent and where it went",
            "submit_label": "Add expense",
            "form_action": url_for("add_expense"),
        }

    return render_template(
        "expense_form.html",
        categories=CATEGORIES,
        values=values,
        error=error,
        today=date.today().isoformat(),
        description_max=DESCRIPTION_MAX,
        **labels,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    # Guard before reading the form, so an anonymous POST never reaches the
    # database.
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if request.method == "GET":
        return _render_expense_form("add", {"date": date.today().isoformat()})

    values, error = _validate_expense(request.form)

    if error is None:
        # user_id comes from the session — a user_id field in the form is
        # never read, so nobody can file an expense against another account.
        create_expense(
            user_id,
            values["amount"],
            values["category"],
            values["date"],
            values["description"],
        )
        # Redirect rather than render, so a refresh cannot insert twice.
        return redirect(url_for("profile"))

    return _render_expense_form("add", values, error=error)


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    # Guard before reading the form, so an anonymous POST never reaches the
    # database.
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # Scoped to the session's user, so someone else's expense simply does not
    # exist here. Both cases 404 on purpose: a 403 for "not yours" would
    # confirm the id is real and turn this URL into a way to count another
    # account's expenses.
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return _render_expense_form(
            "edit",
            {
                # Formatted so the field reads 42.50 rather than 42.5.
                "amount": f"{expense['amount']:.2f}",
                "category": expense["category"],
                "date": expense["date"],
                "description": expense["description"],
            },
            expense_id=id,
        )

    values, error = _validate_expense(request.form)

    if error is None:
        # user_id is passed again so the UPDATE re-checks ownership itself —
        # the GET-time fetch says nothing about who is submitting this POST.
        update_expense(
            id,
            user_id,
            values["amount"],
            values["category"],
            values["date"],
            values["description"],
        )
        # Redirect rather than render, so a refresh cannot re-apply the edit.
        return redirect(url_for("profile"))

    return _render_expense_form("edit", values, error=error, expense_id=id)


# POST only, and deliberately so: a delete reachable by following a link can be
# fired by a browser prefetch, a crawler or an <img src> on another site, none
# of which involve the user deciding anything. A GET here is a 405.
@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    # Guard before touching the database, so an anonymous POST never deletes.
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    # Ownership lives in the DELETE's WHERE clause, so a row belonging to
    # someone else simply matches nothing. Missing and not-yours give the same
    # 404 on purpose — a 403 for "not yours" would confirm the id is real.
    if delete_expense_row(id, user_id) == 0:
        abort(404)

    # Redirect rather than render, so a refresh re-requests the profile page
    # instead of re-posting the delete.
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
