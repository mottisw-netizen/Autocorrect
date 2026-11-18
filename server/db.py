"""SQLite storage for customer access codes and daily usage."""

import os
import secrets
import sqlite3
from datetime import date
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data"))
DB_PATH = DATA_DIR / "autocorrect.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS customers (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            daily_limit INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS usage (
            code TEXT NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (code, day))""")


def new_code() -> str:
    # Short, easy to type, no confusing characters (0/O, 1/I/L).
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def add_customer(name: str, daily_limit: int) -> str:
    code = new_code()
    with connect() as c:
        c.execute("INSERT INTO customers (code, name, daily_limit) VALUES (?, ?, ?)", (code, name, daily_limit))
    return code


def get_customer(code: str):
    with connect() as c:
        row = c.execute("SELECT * FROM customers WHERE code = ?", (code.upper(),)).fetchone()
    return dict(row) if row else None


def set_active(code: str, active: bool) -> bool:
    with connect() as c:
        return c.execute("UPDATE customers SET active = ? WHERE code = ?", (int(active), code.upper())).rowcount > 0


def set_limit(code: str, daily_limit: int) -> bool:
    with connect() as c:
        return c.execute("UPDATE customers SET daily_limit = ? WHERE code = ?", (daily_limit, code.upper())).rowcount > 0


def list_customers():
    today = date.today().isoformat()
    with connect() as c:
        return [dict(r) for r in c.execute(
            """SELECT cu.*, COALESCE(u.count, 0) AS used_today FROM customers cu
               LEFT JOIN usage u ON u.code = cu.code AND u.day = ? ORDER BY cu.created""", (today,))]


def used_today(code: str) -> int:
    with connect() as c:
        row = c.execute("SELECT count FROM usage WHERE code = ? AND day = ?",
                        (code.upper(), date.today().isoformat())).fetchone()
    return row["count"] if row else 0


def try_consume(code: str, daily_limit: int) -> bool:
    """Atomically count one request; False if the daily limit is already reached."""
    today = date.today().isoformat()
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO usage (code, day, count) VALUES (?, ?, 0)", (code.upper(), today))
        return c.execute("UPDATE usage SET count = count + 1 WHERE code = ? AND day = ? AND count < ?",
                         (code.upper(), today, daily_limit)).rowcount > 0


def refund(code: str):
    with connect() as c:
        c.execute("UPDATE usage SET count = MAX(count - 1, 0) WHERE code = ? AND day = ?",
                  (code.upper(), date.today().isoformat()))
