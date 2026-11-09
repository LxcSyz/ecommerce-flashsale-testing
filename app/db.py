import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def connect(path):
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def transaction(path):
    conn = connect(path)
    try:
        # Serialize writers BEFORE reading stock, limits, or order status.
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            expires_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL CHECK(price_cents > 0),
            stock INTEGER NOT NULL CHECK(stock >= 0), initial_stock INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('regular', 'flash')),
            starts_at REAL, ends_at REAL
        );
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER REFERENCES users(id), product_id INTEGER REFERENCES products(id),
            quantity INTEGER NOT NULL CHECK(quantity > 0), PRIMARY KEY(user_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL CHECK(status IN ('pending', 'paid', 'cancelled')),
            total_cents INTEGER NOT NULL CHECK(total_cents > 0), kind TEXT NOT NULL,
            idempotency_key TEXT NOT NULL, fingerprint TEXT NOT NULL, created_at REAL NOT NULL,
            UNIQUE(user_id, idempotency_key)
        );
        CREATE TABLE IF NOT EXISTS order_items (
            order_id INTEGER REFERENCES orders(id), product_id INTEGER REFERENCES products(id),
            quantity INTEGER NOT NULL CHECK(quantity > 0), price_cents INTEGER NOT NULL,
            PRIMARY KEY(order_id, product_id)
        );
        """)
        now = time.time()
        conn.executemany(
            "INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(1, "机械键盘", 19900, 100, 100, "regular", None, None),
             (2, "限量降噪耳机", 9900, 10, 10, "flash", now - 3600, now + 86400),
             (3, "无线鼠标", 8900, 50, 50, "regular", None, None)],
        )
    finally:
        conn.close()
