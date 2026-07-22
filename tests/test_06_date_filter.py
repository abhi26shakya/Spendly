"""Tests for Step 6 — the date filter on the profile page.

Derived from `.claude/specs/06-date-filter.md`, not from reading the filter's
implementation. Two kinds of fixtures are used:

- Fixed, literal 2026 dates for the `database/queries.py` helpers, so those
  tests never depend on the real "today" the suite happens to run on.
- Dates computed from `date.today()` (via the exact arithmetic the spec
  documents) for the HTTP-level preset tests, since presets are themselves
  defined relative to today.

Every test runs against a throwaway database, never the live spendly.db, using
the same monkeypatch-DB_PATH approach as `tests/test_backend_connection.py`.
"""

from datetime import date, timedelta

import pytest

import database.db as db
from app import app, _preset_bounds, _resolve_range
from database.db import create_user, get_db, init_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)


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
def client(isolated_db):
    app.config["TESTING"] = True
    return app.test_client()


def signed_in(client, uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def insert_expense(user_id, amount, category, day, description=None):
    """Insert one expense on an explicit ISO date, via parameterised SQL."""
    if description is None:
        description = f"{category} on {day}"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day, description),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def jan_expenses(user_id):
    """Four expenses on fixed 2026 dates, independent of the real today.

    Food: 50 (Jan 10) + 20 (Jan 20) = 70
    Bills: 30 (Jan 15)
    Transport: 40 (Feb 1) — outside any January range.
    """
    insert_expense(user_id, 50.0, "Food", "2026-01-10", "Groceries")
    insert_expense(user_id, 30.0, "Bills", "2026-01-15", "Electricity")
    insert_expense(user_id, 20.0, "Food", "2026-01-20", "Snacks")
    insert_expense(user_id, 40.0, "Transport", "2026-02-01", "Train ticket")
    return user_id


@pytest.fixture
def boundary_dates():
    """Dates computed from the real today, per the spec's preset formulas."""
    today = date.today()
    return {
        "today": today,
        "month_start": today.replace(day=1),
        "before_month_start": today.replace(day=1) - timedelta(days=1),
        "year_start": today.replace(month=1, day=1),
        "before_year_start": date(today.year - 1, 12, 31),
        "d29_ago": today - timedelta(days=29),
        "d30_ago": today - timedelta(days=30),
    }


# ==================================================================== #
# 1. Preset bounds — "month", "30d", "year", "all"                     #
# ==================================================================== #

class TestPresetBounds:
    """_preset_bounds(preset, today) resolves the documented inclusive bounds.

    A fixed `today` is passed in (the function takes it as a parameter),
    so these are deterministic regardless of the real calendar date.
    """

    def test_month_is_the_1st_of_the_month_through_today(self):
        today = date(2026, 7, 23)
        assert _preset_bounds("month", today) == (date(2026, 7, 1), today)

    def test_30d_is_29_days_back_through_today_inclusive(self):
        today = date(2026, 7, 23)
        assert _preset_bounds("30d", today) == (date(2026, 6, 24), today)

    def test_year_is_jan_1st_through_today(self):
        today = date(2026, 7, 23)
        assert _preset_bounds("year", today) == (date(2026, 1, 1), today)

    def test_all_has_no_bounds(self):
        today = date(2026, 7, 23)
        assert _preset_bounds("all", today) == (None, None)

    def test_month_bounds_at_a_month_boundary(self):
        """1 Jan is still the start of "this month" — no bleed into December."""
        today = date(2026, 1, 1)
        assert _preset_bounds("month", today) == (date(2026, 1, 1), today)

    def test_30d_bounds_crossing_a_year_boundary(self):
        today = date(2026, 1, 5)
        assert _preset_bounds("30d", today) == (date(2025, 12, 7), today)


# ==================================================================== #
# 2. _resolve_range — validation, precedence, open-ended ranges        #
# ==================================================================== #

class TestResolveRange:
    """No query string behaves exactly like all-time; bad input never aborts."""

    def test_no_params_defaults_to_all_time(self):
        result = _resolve_range({})
        assert result["start"] is None
        assert result["end"] is None
        assert result["error"] is None

    def test_unknown_preset_falls_back_to_all_with_a_message(self):
        result = _resolve_range({"range": "banana"})
        assert result["start"] is None
        assert result["end"] is None
        assert result["error"], "an unknown preset must report why it fell back"

    def test_malformed_date_falls_back_to_all_with_a_message(self):
        result = _resolve_range({"start": "2026-13-45"})
        assert result["start"] is None
        assert result["end"] is None
        assert result["error"]

    def test_start_after_end_falls_back_to_all_with_a_message(self):
        result = _resolve_range({"start": "2026-02-01", "end": "2026-01-01"})
        assert result["start"] is None
        assert result["end"] is None
        assert result["error"]

    def test_explicit_dates_win_over_a_simultaneous_preset(self):
        result = _resolve_range(
            {"range": "month", "start": "2026-01-05", "end": "2026-01-10"}
        )
        assert result["start"] == "2026-01-05"
        assert result["end"] == "2026-01-10"
        assert result["error"] is None

    def test_start_only_is_open_ended_at_the_far_end(self):
        result = _resolve_range({"start": "2026-01-05"})
        assert result["start"] == "2026-01-05"
        assert result["end"] is None
        assert result["error"] is None

    def test_end_only_is_open_ended_at_the_near_end(self):
        result = _resolve_range({"end": "2026-01-05"})
        assert result["start"] is None
        assert result["end"] == "2026-01-05"
        assert result["error"] is None


# ==================================================================== #
# 3. get_summary_stats — with and without start/end                    #
# ==================================================================== #

class TestSummaryStatsRange:
    def test_unchanged_from_step_5_when_no_range_given(self, jan_expenses):
        stats = get_summary_stats(jan_expenses)
        assert stats["total_spent"] == pytest.approx(140.0)
        assert stats["transaction_count"] == 4
        assert stats["top_category"] == "Food"

    def test_narrows_to_the_given_range(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, start="2026-01-01", end="2026-01-31")
        assert stats["total_spent"] == pytest.approx(100.0)
        assert stats["transaction_count"] == 3
        assert stats["top_category"] == "Food"

    def test_start_bound_is_inclusive(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, start="2026-01-10", end="2026-01-10")
        assert stats["total_spent"] == pytest.approx(50.0)
        assert stats["transaction_count"] == 1

    def test_end_bound_is_inclusive(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, start="2026-01-20", end="2026-01-20")
        assert stats["total_spent"] == pytest.approx(20.0)
        assert stats["transaction_count"] == 1

    def test_range_matching_nothing_returns_zeros(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, start="2026-03-01", end="2026-03-31")
        assert stats == {
            "total_spent": 0,
            "transaction_count": 0,
            "top_category": "—",
        }

    def test_open_ended_start_only(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, start="2026-01-15")
        assert stats["total_spent"] == pytest.approx(90.0)  # 30 + 20 + 40
        assert stats["transaction_count"] == 3

    def test_open_ended_end_only(self, jan_expenses):
        stats = get_summary_stats(jan_expenses, end="2026-01-15")
        assert stats["total_spent"] == pytest.approx(80.0)  # 50 + 30
        assert stats["transaction_count"] == 2


# ==================================================================== #
# 4. get_recent_transactions — with and without start/end              #
# ==================================================================== #

class TestRecentTransactionsRange:
    def test_unchanged_from_step_5_when_no_range_given(self, jan_expenses):
        rows = get_recent_transactions(jan_expenses)
        assert len(rows) == 4

    def test_narrows_to_the_given_range(self, jan_expenses):
        rows = get_recent_transactions(jan_expenses, start="2026-01-01", end="2026-01-31")
        assert [r["description"] for r in rows] == ["Snacks", "Electricity", "Groceries"]

    def test_range_matching_nothing_returns_empty_list(self, jan_expenses):
        assert get_recent_transactions(jan_expenses, start="2026-03-01", end="2026-03-31") == []

    def test_open_ended_start_only(self, jan_expenses):
        rows = get_recent_transactions(jan_expenses, start="2026-01-15")
        assert [r["description"] for r in rows] == ["Train ticket", "Snacks", "Electricity"]

    def test_open_ended_end_only(self, jan_expenses):
        rows = get_recent_transactions(jan_expenses, end="2026-01-15")
        assert [r["description"] for r in rows] == ["Electricity", "Groceries"]

    def test_limit_still_applies_inside_a_range(self, jan_expenses):
        rows = get_recent_transactions(
            jan_expenses, limit=1, start="2026-01-01", end="2026-01-31"
        )
        assert len(rows) == 1
        assert rows[0]["description"] == "Snacks"


# ==================================================================== #
# 5. get_category_breakdown — with and without start/end               #
# ==================================================================== #

class TestCategoryBreakdownRange:
    def test_unchanged_from_step_5_when_no_range_given(self, jan_expenses):
        rows = get_category_breakdown(jan_expenses)
        names = {r["name"] for r in rows}
        assert names == {"Food", "Bills", "Transport"}
        assert sum(r["pct"] for r in rows) == 100

    def test_narrows_to_the_given_range_and_percentages_still_sum_to_100(
        self, jan_expenses
    ):
        rows = get_category_breakdown(jan_expenses, start="2026-01-01", end="2026-01-31")
        names = {r["name"] for r in rows}
        assert names == {"Food", "Bills"}
        assert "Transport" not in names
        assert sum(r["pct"] for r in rows) == 100

    def test_range_matching_nothing_returns_empty_list(self, jan_expenses):
        assert get_category_breakdown(jan_expenses, start="2026-03-01", end="2026-03-31") == []

    def test_open_ended_start_only(self, jan_expenses):
        rows = get_category_breakdown(jan_expenses, start="2026-01-15")
        names = {r["name"] for r in rows}
        assert names == {"Bills", "Food", "Transport"}
        assert sum(r["pct"] for r in rows) == 100

    def test_open_ended_end_only(self, jan_expenses):
        rows = get_category_breakdown(jan_expenses, end="2026-01-15")
        names = {r["name"] for r in rows}
        assert names == {"Food", "Bills"}
        assert sum(r["pct"] for r in rows) == 100


# ==================================================================== #
# 6. GET /profile — presets through the route                          #
# ==================================================================== #

class TestProfilePresetsHTTP:
    def test_no_query_string_matches_all_time(self, client, user_id, boundary_dates):
        insert_expense(user_id, 5.0, "Food", boundary_dates["before_year_start"].isoformat(), "Ancient")
        insert_expense(user_id, 7.0, "Food", boundary_dates["today"].isoformat(), "Recent")
        signed_in(client, user_id)
        body = client.get("/profile").get_data(as_text=True)
        assert response_ok_and_contains(body, "Ancient", "Recent")
        assert "12.00" in body  # 5 + 7

    def test_range_all_matches_all_time_identically_to_no_query_string(
        self, client, user_id, boundary_dates
    ):
        insert_expense(user_id, 5.0, "Food", boundary_dates["before_year_start"].isoformat(), "Ancient")
        insert_expense(user_id, 7.0, "Food", boundary_dates["today"].isoformat(), "Recent")
        signed_in(client, user_id)
        body_none = client.get("/profile").get_data(as_text=True)
        body_all = client.get("/profile?range=all").get_data(as_text=True)
        assert "Ancient" in body_none and "Ancient" in body_all
        assert "Recent" in body_none and "Recent" in body_all
        assert "12.00" in body_none and "12.00" in body_all

    def test_range_month_includes_month_start_and_today_excludes_day_before(
        self, client, user_id, boundary_dates
    ):
        insert_expense(user_id, 10.0, "Food", boundary_dates["month_start"].isoformat(), "In month start")
        insert_expense(user_id, 5.0, "Food", boundary_dates["today"].isoformat(), "Today expense")
        insert_expense(user_id, 999.0, "Food", boundary_dates["before_month_start"].isoformat(), "Before month")
        signed_in(client, user_id)
        response = client.get("/profile?range=month")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "In month start" in body
        assert "Today expense" in body
        assert "Before month" not in body
        assert "15.00" in body  # 10 + 5, the 999 row excluded

    def test_range_year_includes_year_start_excludes_day_before(
        self, client, user_id, boundary_dates
    ):
        insert_expense(user_id, 10.0, "Bills", boundary_dates["year_start"].isoformat(), "Year start expense")
        insert_expense(user_id, 999.0, "Bills", boundary_dates["before_year_start"].isoformat(), "Before year expense")
        signed_in(client, user_id)
        response = client.get("/profile?range=year")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Year start expense" in body
        assert "Before year expense" not in body

    def test_range_30d_is_inclusive_of_29_days_ago_exclusive_of_30(
        self, client, user_id, boundary_dates
    ):
        insert_expense(user_id, 10.0, "Food", boundary_dates["d29_ago"].isoformat(), "Within 30d window")
        insert_expense(user_id, 999.0, "Food", boundary_dates["d30_ago"].isoformat(), "Outside 30d window")
        signed_in(client, user_id)
        response = client.get("/profile?range=30d")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Within 30d window" in body
        assert "Outside 30d window" not in body

    def test_range_matching_nothing_shows_zeroed_empty_state(self, client, user_id):
        insert_expense(user_id, 42.0, "Food", "2020-01-01", "Way in the past")
        signed_in(client, user_id)
        response = client.get("/profile?start=2099-01-01&end=2099-01-02")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "₹0.00" in body
        assert "—" in body  # top category placeholder
        assert "No expenses in this range." in body
        assert "Way in the past" not in body


# ==================================================================== #
# 7. GET /profile — precedence and validation fallbacks                #
# ==================================================================== #

class TestProfileValidationAndPrecedenceHTTP:
    def test_explicit_start_end_win_over_a_simultaneous_range_preset(
        self, client, user_id, boundary_dates
    ):
        old_day = boundary_dates["before_year_start"].isoformat()
        insert_expense(user_id, 10.0, "Food", boundary_dates["today"].isoformat(), "Recent A")
        insert_expense(user_id, 20.0, "Bills", old_day, "Old B")
        signed_in(client, user_id)

        # "month" alone would include "Recent A" and exclude "Old B"; the
        # explicit start/end pins the window to exactly "Old B"'s day instead.
        response = client.get(f"/profile?range=month&start={old_day}&end={old_day}")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Old B" in body
        assert "Recent A" not in body
        assert "20.00" in body

    def test_unknown_range_falls_back_to_all_time_with_a_message(self, client, user_id):
        insert_expense(user_id, 42.5, "Food", "2020-01-01", "Old expense")
        signed_in(client, user_id)
        response = client.get("/profile?range=banana")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Traceback" not in body
        assert "Old expense" in body  # fell back to all-time, not to nothing
        assert "42.50" in body
        assert has_visible_message(body)

    def test_malformed_date_falls_back_to_all_time_with_a_message(self, client, user_id):
        insert_expense(user_id, 42.5, "Food", "2020-01-01", "Old expense")
        signed_in(client, user_id)
        response = client.get("/profile?start=2026-13-45")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Traceback" not in body
        assert "Old expense" in body
        assert has_visible_message(body)

    def test_start_after_end_falls_back_to_all_time_with_a_message(self, client, user_id):
        insert_expense(user_id, 42.5, "Food", "2020-01-01", "Old expense")
        signed_in(client, user_id)
        response = client.get("/profile?start=2026-02-01&end=2026-01-01")
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Traceback" not in body
        assert "Old expense" in body
        assert has_visible_message(body)


# ==================================================================== #
# 8. Auth guard and member_since                                       #
# ==================================================================== #

class TestProfileAuthAndMemberSince:
    def test_profile_with_range_redirects_when_signed_out(self, client):
        response = client.get("/profile?range=month")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_member_since_is_unaffected_by_the_filter(self, client, user_id):
        from datetime import datetime

        expected_label = datetime.now().strftime("%B %Y")
        insert_expense(user_id, 10.0, "Food", "2020-01-01", "Irrelevant to member_since")
        signed_in(client, user_id)

        body_all_time = client.get("/profile").get_data(as_text=True)
        body_matching_nothing = client.get(
            "/profile?start=2099-01-01&end=2099-01-02"
        ).get_data(as_text=True)

        assert expected_label in body_all_time
        assert expected_label in body_matching_nothing


# ==================================================================== #
# Small local helpers (not implementation lookups)                     #
# ==================================================================== #

def response_ok_and_contains(body, *snippets):
    return all(snippet in body for snippet in snippets)


def has_visible_message(body):
    """A loose check that *some* human-readable message is on the page.

    The spec requires "a visible message" on validation fallback without
    dictating its exact copy, so this checks for common wording rather than
    a literal string.
    """
    lowered = body.lower()
    return any(
        keyword in lowered
        for keyword in ("invalid", "unknown", "must be", "showing all time", "error")
    )
