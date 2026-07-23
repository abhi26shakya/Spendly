import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

DB_PATH = Path(__file__).resolve().parent.parent / "spendly.db"

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Per-connection setting — SQLite defaults it off on every new connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL NOT NULL,
            category    TEXT NOT NULL,
            date        TEXT NOT NULL,
            description TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def _seed_dates(count):
    """Spread `count` dates over the current month, from the 1st up to today."""
    today = date.today()
    span = today.day - 1
    return [
        today.replace(day=1 + round(i * span / (count - 1))).isoformat()
        for i in range(count)
    ]


def seed_db():
    conn = get_db()

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )
    user_id = cursor.lastrowid

    samples = [
        (42.50, "Food", "Groceries for the week"),
        (18.00, "Transport", "Metro card top-up"),
        (95.20, "Bills", "Electricity bill"),
        (30.00, "Health", "Pharmacy — cold medicine"),
        (14.99, "Entertainment", "Movie ticket"),
        (79.00, "Shopping", "Running shoes"),
        (25.00, "Other", "Gift for a friend"),
        (11.75, "Food", "Lunch at the cafe"),
    ]
    dates = _seed_dates(len(samples))

    conn.executemany(
        """
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (user_id, amount, category, day, description)
            for (amount, category, description), day in zip(samples, dates)
        ],
    )

    conn.commit()
    conn.close()


def get_user_by_email(email):
    """Return the user row for an email, or None if nobody has it."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a user and return the new id.

    Raises sqlite3.IntegrityError if the email is already registered — the
    UNIQUE constraint on users.email is the source of truth.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def create_expense(user_id, amount, category, expense_date, description):
    """Insert an expense and return the new id.

    `expense_date` is ISO YYYY-MM-DD text — the format the range filters
    compare against. It is not named `date` because that would shadow the
    datetime class this module imports. `description` may be empty; the column
    is nullable. `created_at` is left to the column default.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_expense(expense_id, user_id, amount, category, expense_date, description):
    """Overwrite one expense and return how many rows changed.

    `user_id` narrows the UPDATE rather than being written by it — an expense
    never changes owner, so it belongs in the WHERE clause. A row that does not
    exist and a row belonging to someone else are the same case here: nothing
    matches, nothing is written and the return value is 0. `created_at` records
    when the expense was filed, not when it was last touched, so it is left
    alone.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, date = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (amount, category, expense_date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def delete_expense(expense_id, user_id):
    """Remove one expense and return how many rows were deleted.

    `user_id` narrows the DELETE rather than being checked in Python first — a
    row that does not exist and a row belonging to someone else are the same
    case here: nothing matches, nothing is removed and the return value is 0.
    The row is really gone; there is no archived copy to restore from.
    """
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
