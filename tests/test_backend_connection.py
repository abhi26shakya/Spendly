"""Tests for Step 5 — the profile page reading real data.

Every test runs against a throwaway database seeded by the project's own
seed_db(), never the live spendly.db. get_db() reads DB_PATH from the module
global at call time, so monkeypatching it redirects both the query helpers and
the route.
"""

import pytest

import database.db as db
from app import app
from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

# The 8 rows seed_db() writes for the demo user.
SEED_TOTAL = 316.44
SEED_COUNT = 8
SEED_CATEGORIES = 7


@pytest.fixture
def demo_db(tmp_path, monkeypatch):
    """A fresh database holding only the demo user and their 8 expenses."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    init_db()
    seed_db()
    return 1  # seed_db() inserts the demo user first, so id 1


@pytest.fixture
def empty_user(demo_db):
    """A second user with no expenses at all."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("New Person", "new@spendly.com", "x"),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


@pytest.fixture
def client(demo_db):
    app.config["TESTING"] = True
    return app.test_client()


def signed_in(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# --- get_user_by_id ------------------------------------------------- #

def test_get_user_by_id_returns_the_user(demo_db):
    user = get_user_by_id(demo_db)
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    # created_at defaults to now, so assert the shape rather than a literal.
    assert user["member_since"].split()[0].isalpha()
    assert len(user["member_since"].split()) == 2


def test_get_user_by_id_unknown_id_returns_none(demo_db):
    assert get_user_by_id(9999) is None


# --- get_summary_stats ---------------------------------------------- #

def test_summary_stats_with_expenses(demo_db):
    stats = get_summary_stats(demo_db)
    assert stats["total_spent"] == pytest.approx(SEED_TOTAL)
    assert stats["transaction_count"] == SEED_COUNT
    assert stats["top_category"] == "Bills"


def test_summary_stats_with_no_expenses(empty_user):
    assert get_summary_stats(empty_user) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


# --- get_recent_transactions ---------------------------------------- #

def test_recent_transactions_are_newest_first(demo_db):
    rows = get_recent_transactions(demo_db, limit=SEED_COUNT)
    assert len(rows) == SEED_COUNT
    assert set(rows[0]) == {"date", "description", "category", "amount"}

    # Seed dates are generated relative to today, so compare the underlying
    # ordering rather than any literal date.
    conn = get_db()
    try:
        expected = [
            r["description"]
            for r in conn.execute(
                "SELECT description FROM expenses WHERE user_id = ?"
                " ORDER BY date DESC, id DESC",
                (demo_db,),
            )
        ]
    finally:
        conn.close()
    assert [r["description"] for r in rows] == expected


def test_recent_transactions_respects_limit(demo_db):
    assert len(get_recent_transactions(demo_db, limit=3)) == 3


def test_recent_transactions_formats_the_date(demo_db):
    date = get_recent_transactions(demo_db)[0]["date"]
    day, month = date.split()
    assert day.isdigit() and len(day) == 2  # "16", not "2026-07-16"
    assert month.isalpha() and len(month) == 3


def test_recent_transactions_with_no_expenses(empty_user):
    assert get_recent_transactions(empty_user) == []


# --- get_category_breakdown ----------------------------------------- #

def test_category_breakdown_with_expenses(demo_db):
    rows = get_category_breakdown(demo_db)
    assert len(rows) == SEED_CATEGORIES
    assert rows[0]["name"] == "Bills"
    assert rows[0]["amount"] == pytest.approx(95.20)
    # Food appears twice in the seed and must be aggregated.
    food = next(r for r in rows if r["name"] == "Food")
    assert food["amount"] == pytest.approx(54.25)
    assert [r["amount"] for r in rows] == sorted(
        (r["amount"] for r in rows), reverse=True
    )


def test_category_percentages_are_ints_summing_to_100(demo_db):
    rows = get_category_breakdown(demo_db)
    assert all(isinstance(r["pct"], int) for r in rows)
    assert sum(r["pct"] for r in rows) == 100


def test_category_percentages_sum_to_100_when_rounding_is_awkward(empty_user):
    """Three equal shares round to 33+33+33 = 99; the remainder rule fixes it."""
    conn = get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date)"
            " VALUES (?, ?, ?, '2026-07-01')",
            [(empty_user, 10.0, c) for c in ("Food", "Bills", "Health")],
        )
        conn.commit()
    finally:
        conn.close()

    rows = get_category_breakdown(empty_user)
    assert len(rows) == 3
    assert sum(r["pct"] for r in rows) == 100


def test_category_breakdown_with_no_expenses(empty_user):
    assert get_category_breakdown(empty_user) == []


# --- GET /profile ---------------------------------------------------- #

def test_profile_redirects_when_signed_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_renders_the_signed_in_user(client, demo_db):
    signed_in(client, demo_db)
    body = client.get("/profile").get_data(as_text=True)

    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "316.44" in body
    assert "Bills" in body
    assert ">8<" in body  # the transaction count stat


def test_profile_shows_every_category(client, demo_db):
    signed_in(client, demo_db)
    body = client.get("/profile").get_data(as_text=True)
    for category in (
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ):
        assert category in body


def test_profile_bar_widths_all_have_a_matching_css_rule(client, demo_db):
    """A width class with no rule silently collapses the bar to nothing."""
    signed_in(client, demo_db)
    body = client.get("/profile").get_data(as_text=True)

    import re

    # Anchor on the class attribute — a bare "profile-bar-w55" also matches the
    # CSS rule that defines it, which would make this assertion vacuous.
    used = set(re.findall(r'class="profile-bar [\w-]+ profile-bar-(w\d+)"', body))
    defined = set(re.findall(r"\.profile-bar-(w\d+)\s*\{", body))
    assert len(used) == SEED_CATEGORIES
    assert used <= defined


def test_profile_for_a_user_with_no_expenses(client, empty_user):
    signed_in(client, empty_user)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "New Person" in body
    assert "₹0.00" in body
    assert "No expenses yet." in body


def test_profile_does_not_leak_another_users_expenses(client, empty_user):
    signed_in(client, empty_user)
    body = client.get("/profile").get_data(as_text=True)
    assert "Groceries for the week" not in body
    assert "316.44" not in body


def test_profile_clears_a_session_pointing_at_a_deleted_user(client, demo_db):
    signed_in(client, 9999)
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
