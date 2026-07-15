import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

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


# Step 4 builds the profile UI against hardcoded data; Step 5 swaps these three
# constants for real queries. They mirror the demo user seeded by seed_db(), so
# the page should look near-identical once it is reading from the database.
_PROFILE_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "initials": "DU",
    "member_since": "July 2026",
}

_PROFILE_STATS = {
    "total": 316.44,
    "count": 8,
    "top_category": "Bills",
}

_PROFILE_EXPENSES = [
    {"date": "16 Jul", "description": "Lunch at the cafe", "category": "Food", "amount": 11.75},
    {"date": "13 Jul", "description": "Gift for a friend", "category": "Other", "amount": 25.00},
    {"date": "11 Jul", "description": "Running shoes", "category": "Shopping", "amount": 79.00},
    {"date": "09 Jul", "description": "Movie ticket", "category": "Entertainment", "amount": 14.99},
    {"date": "06 Jul", "description": "Pharmacy — cold medicine", "category": "Health", "amount": 30.00},
    {"date": "04 Jul", "description": "Electricity bill", "category": "Bills", "amount": 95.20},
    {"date": "02 Jul", "description": "Metro card top-up", "category": "Transport", "amount": 18.00},
    {"date": "01 Jul", "description": "Groceries for the week", "category": "Food", "amount": 42.50},
]

# `share` is the category's percentage of total spend — the number shown to the
# reader. `width` scales the bar against the largest category instead, rounded
# to the nearest 5 so it can be a CSS class rather than an inline style.
_PROFILE_CATEGORIES = [
    {"name": "Bills", "slug": "bills", "total": 95.20, "share": 30, "width": 100},
    {"name": "Shopping", "slug": "shopping", "total": 79.00, "share": 25, "width": 85},
    {"name": "Food", "slug": "food", "total": 54.25, "share": 17, "width": 55},
    {"name": "Health", "slug": "health", "total": 30.00, "share": 9, "width": 30},
    {"name": "Other", "slug": "other", "total": 25.00, "share": 8, "width": 25},
    {"name": "Transport", "slug": "transport", "total": 18.00, "share": 6, "width": 20},
    {"name": "Entertainment", "slug": "entertainment", "total": 14.99, "share": 5, "width": 15},
]


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=_PROFILE_USER,
        stats=_PROFILE_STATS,
        expenses=_PROFILE_EXPENSES,
        categories=_PROFILE_CATEGORIES,
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
