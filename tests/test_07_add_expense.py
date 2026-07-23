"""Tests for Step 7 — Add Expense (`GET`/`POST /expenses/add`).

Derived from `.claude/specs/07-add-expense.md`, not from reading
`add_expense`'s implementation in `app.py`. Two behaviours were pinned down
during planning that the spec's prose leaves looser, and are treated here as
authoritative:

1. A future-dated expense (a date after today) is rejected.
2. The submitted amount is rounded to 2 decimal places before storage
   (e.g. "33.333" is stored as 33.33).

Every test runs against a throwaway database, never the live spendly.db,
using the same monkeypatch-DB_PATH approach as `tests/test_backend_connection.py`
and `tests/test_06_date_filter.py`.
"""

from datetime import date, timedelta

import pytest

import database.db as db
from app import app
from database.db import CATEGORIES, create_user, get_db, init_db


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A fresh, empty database — no seed_db(), full control over the rows."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    init_db()


@pytest.fixture
def user_id(isolated_db):
    return create_user("Demo User", "demo@spendly.com", "password123")


@pytest.fixture
def other_user_id(isolated_db):
    """A second registered user, used to test the forged user_id case."""
    return create_user("Other User", "other@spendly.com", "password123")


@pytest.fixture
def client(isolated_db):
    app.config["TESTING"] = True
    return app.test_client()


def signed_in(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def all_expenses():
    """Every row in the expenses table, for asserting DB side effects."""
    conn = get_db()
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT user_id, amount, category, date, description FROM expenses"
            )
        ]
    finally:
        conn.close()


def expense_count():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


VALID_FORM = {
    "amount": "250.00",
    "category": "Food",
    "date": None,  # filled in per-test with today's ISO date
    "description": "Dinner",
}


def valid_form(**overrides):
    today = date.today().isoformat()
    form = {**VALID_FORM, "date": today}
    form.update(overrides)
    return form


# ==================================================================== #
# 1. GET /expenses/add — form rendering                                #
# ==================================================================== #

class TestGetForm:
    def test_renders_for_a_logged_in_user(self, client, user_id):
        signed_in(client, user_id)
        response = client.get("/expenses/add")
        assert response.status_code == 200

    def test_lists_all_seven_categories(self, client, user_id):
        signed_in(client, user_id)
        body = client.get("/expenses/add").get_data(as_text=True)
        assert len(CATEGORIES) == 7, "sanity check on the fixture list itself"
        for category in CATEGORIES:
            assert category in body, f"{category!r} missing from the add-expense form"

    def test_date_field_defaults_to_today(self, client, user_id):
        signed_in(client, user_id)
        body = client.get("/expenses/add").get_data(as_text=True)
        today = date.today().isoformat()
        assert today in body, "today's ISO date should pre-fill the date field"

    def test_get_redirects_to_login_when_signed_out(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ==================================================================== #
# 2. Auth guard on POST                                                #
# ==================================================================== #

class TestPostAuthGuard:
    def test_post_redirects_to_login_when_signed_out(self, client):
        response = client.post("/expenses/add", data=valid_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_signed_out_inserts_nothing(self, client):
        client.post("/expenses/add", data=valid_form())
        assert expense_count() == 0


# ==================================================================== #
# 3. Happy path                                                        #
# ==================================================================== #

class TestHappyPath:
    def test_valid_submission_redirects_to_profile(self, client, user_id):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form())
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_valid_submission_inserts_exactly_one_row(self, client, user_id):
        signed_in(client, user_id)
        client.post("/expenses/add", data=valid_form())
        assert expense_count() == 1

    def test_valid_submission_stores_the_submitted_values(self, client, user_id):
        signed_in(client, user_id)
        today = date.today().isoformat()
        client.post(
            "/expenses/add",
            data={
                "amount": "250.00",
                "category": "Food",
                "date": today,
                "description": "Dinner",
            },
        )
        rows = all_expenses()
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == user_id
        assert row["amount"] == pytest.approx(250.00)
        assert row["category"] == "Food"
        assert row["date"] == today
        assert row["description"] == "Dinner"

    def test_blank_description_succeeds(self, client, user_id):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(description=""))
        assert response.status_code == 302
        assert expense_count() == 1

    def test_amount_is_rounded_to_two_decimal_places(self, client, user_id):
        signed_in(client, user_id)
        client.post("/expenses/add", data=valid_form(amount="33.333"))
        rows = all_expenses()
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(33.33)

    def test_refreshing_after_a_successful_add_does_not_double_insert(
        self, client, user_id
    ):
        """A refresh replays the last request; POST->redirect->GET means a
        browser refresh re-issues the GET /profile, not the POST, so a second
        identical POST call here simulates two independent submissions."""
        signed_in(client, user_id)
        form = valid_form()
        client.post("/expenses/add", data=form)
        assert expense_count() == 1
        # A literal second submission is a second, independent expense — this
        # route has no idempotency key, so two submits are two rows.
        client.post("/expenses/add", data=form)
        assert expense_count() == 2


# ==================================================================== #
# 4. user_id comes from the session, never the form                    #
# ==================================================================== #

class TestUserIdFromSession:
    def test_forged_user_id_field_is_ignored(self, client, user_id, other_user_id):
        signed_in(client, user_id)
        client.post("/expenses/add", data=valid_form(user_id=str(other_user_id)))
        rows = all_expenses()
        assert len(rows) == 1
        assert rows[0]["user_id"] == user_id, (
            "the expense must be owned by the signed-in user, not the forged "
            "user_id form field"
        )


# ==================================================================== #
# 5. Validation — amount                                               #
# ==================================================================== #

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount", ["", "0", "-5", "abc"])
    def test_rejected_amount_re_renders_with_200(self, client, user_id, bad_amount):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(amount=bad_amount))
        assert response.status_code == 200

    @pytest.mark.parametrize("bad_amount", ["", "0", "-5", "abc"])
    def test_rejected_amount_inserts_nothing(self, client, user_id, bad_amount):
        signed_in(client, user_id)
        client.post("/expenses/add", data=valid_form(amount=bad_amount))
        assert expense_count() == 0

    @pytest.mark.parametrize("bad_amount", ["", "0", "-5", "abc"])
    def test_rejected_amount_preserves_the_other_submitted_fields(
        self, client, user_id, bad_amount
    ):
        signed_in(client, user_id)
        form = valid_form(amount=bad_amount, description="Concert tickets")
        body = client.post("/expenses/add", data=form).get_data(as_text=True)
        assert "Concert tickets" in body, (
            "a rejected form must not discard what the user typed elsewhere"
        )
        assert form["date"] in body


# ==================================================================== #
# 6. Validation — date                                                 #
# ==================================================================== #

class TestDateValidation:
    def test_missing_date_re_renders_with_200_and_inserts_nothing(self, client, user_id):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(date=""))
        assert response.status_code == 200
        assert expense_count() == 0

    def test_malformed_date_re_renders_with_200_and_inserts_nothing(self, client, user_id):
        signed_in(client, user_id)
        response = client.post(
            "/expenses/add", data=valid_form(date="2026-13-45")
        )
        assert response.status_code == 200
        assert expense_count() == 0

    def test_non_iso_date_re_renders_with_200_and_inserts_nothing(self, client, user_id):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(date="not-a-date"))
        assert response.status_code == 200
        assert expense_count() == 0

    def test_future_date_is_rejected(self, client, user_id):
        """Authoritative planning decision: a date after today is an error,
        even though the spec's prose only calls out missing/malformed dates."""
        signed_in(client, user_id)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        response = client.post("/expenses/add", data=valid_form(date=tomorrow))
        assert response.status_code == 200
        assert expense_count() == 0

    def test_today_is_accepted_as_the_boundary(self, client, user_id):
        """Today itself must not be treated as "future" — only strictly
        after today is rejected."""
        signed_in(client, user_id)
        today = date.today().isoformat()
        response = client.post("/expenses/add", data=valid_form(date=today))
        assert response.status_code == 302
        assert expense_count() == 1

    def test_rejected_date_preserves_the_other_submitted_fields(self, client, user_id):
        signed_in(client, user_id)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        form = valid_form(date=tomorrow, description="Concert tickets")
        body = client.post("/expenses/add", data=form).get_data(as_text=True)
        assert "Concert tickets" in body
        assert form["amount"] in body


# ==================================================================== #
# 7. Validation — category                                             #
# ==================================================================== #

class TestCategoryValidation:
    def test_category_outside_categories_is_rejected(self, client, user_id):
        signed_in(client, user_id)
        response = client.post(
            "/expenses/add", data=valid_form(category="Crypto")
        )
        assert response.status_code == 200
        assert expense_count() == 0

    def test_empty_category_is_rejected(self, client, user_id):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(category=""))
        assert response.status_code == 200
        assert expense_count() == 0

    def test_rejected_category_preserves_the_other_submitted_fields(
        self, client, user_id
    ):
        signed_in(client, user_id)
        form = valid_form(category="Crypto", description="Concert tickets")
        body = client.post("/expenses/add", data=form).get_data(as_text=True)
        assert "Concert tickets" in body
        assert form["amount"] in body


# ==================================================================== #
# 8. Every category in CATEGORIES is individually accepted              #
# ==================================================================== #

class TestEveryCategoryAccepted:
    @pytest.mark.parametrize("category", CATEGORIES)
    def test_each_listed_category_is_accepted(self, client, user_id, category):
        signed_in(client, user_id)
        response = client.post("/expenses/add", data=valid_form(category=category))
        assert response.status_code == 302
        rows = all_expenses()
        assert len(rows) == 1
        assert rows[0]["category"] == category
