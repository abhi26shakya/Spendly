"""Read-only queries backing the profile page.

`db.py` owns the schema, the seed and writes; this module owns the reads. No
Flask imports here — every function takes a user_id, opens its own connection
through get_db() and closes it before returning.
"""

from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return {"name", "email", "member_since"} for a user, or None if unknown.

    `member_since` is users.created_at rendered as "July 2026".
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": datetime.fromisoformat(row["created_at"]).strftime("%B %Y"),
    }


def get_summary_stats(user_id):
    """Return total spent, transaction count and top category for one user.

    Falls back to {"total_spent": 0, "transaction_count": 0,
    "top_category": "—"} when the user has no expenses yet.
    """
    conn = get_db()
    try:
        totals = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total_spent,
                   COUNT(*)                 AS transaction_count
            FROM expenses
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        # A GROUP BY aggregate cannot produce the account-wide totals in the
        # same row set, so the top category needs its own query.
        top = conn.execute(
            """
            SELECT category
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY SUM(amount) DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if top is None:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    return {
        "total_spent": float(totals["total_spent"]),
        "transaction_count": int(totals["transaction_count"]),
        "top_category": top["category"],
    }


def get_recent_transactions(user_id, limit=10):
    """Return a user's most recent expenses, newest first.

    Each item is a plain dict with "date" (formatted "16 Jul"), "description",
    "category" and "amount". Returns [] when the user has no expenses.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT date, description, category, amount
            FROM expenses
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b"),
            "description": row["description"],
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


def get_category_breakdown(user_id):
    """Return one dict per category the user has spent in.

    Each dict is {"name": <category>, "amount": <float>, "pct": <int>}, sorted
    by amount descending. The pct values always sum to exactly 100 for a
    non-empty result. Returns [] when the user has no expenses.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    overall = sum(row["total"] for row in rows)

    breakdown = [
        {
            "name": row["category"],
            "amount": float(row["total"]),
            # Guard the division: a total of 0 (e.g. only zero-amount rows)
            # would otherwise raise ZeroDivisionError.
            "pct": round(row["total"] / overall * 100) if overall else 0,
        }
        for row in rows
    ]

    # Rounding each category independently rarely lands on 100 (three equal
    # shares round to 33+33+33 = 99). Push the whole leftover — positive or
    # negative — onto the largest category, which is first after the ORDER BY,
    # since it can absorb a point or two with the least relative distortion.
    breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)

    return breakdown
