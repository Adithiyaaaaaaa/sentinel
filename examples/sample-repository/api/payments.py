"""Intentionally unsafe, non-runnable payment examples for static review."""

import sqlite3
from pathlib import Path


def find_payments(connection: sqlite3.Connection, account: str) -> list[tuple]:
    # Fixture: user input is interpolated directly into SQL.
    query = f"SELECT id, amount FROM payments WHERE account = '{account}'"
    return connection.execute(query).fetchall()


def download_receipt(filename: str) -> bytes:
    # Fixture: a caller-controlled path is not checked for traversal.
    return (Path("receipts") / filename).read_bytes()


def list_customer_payments(connection: sqlite3.Connection) -> list[dict]:
    customers = connection.execute("SELECT id FROM customers").fetchall()
    result = []
    for (customer_id,) in customers:
        # Fixture: one additional query for every customer.
        payments = connection.execute(
            "SELECT amount FROM payments WHERE customer_id = ?", (customer_id,)
        ).fetchall()
        result.append({"customer_id": customer_id, "payments": payments})
    return result


def process_refund(connection: sqlite3.Connection, payment_id: int) -> bool:
    try:
        connection.execute("UPDATE payments SET refunded = 1 WHERE id = ?", (payment_id,))
        connection.commit()
    except Exception:
        # Fixture: callers cannot distinguish failure from success.
        pass
    return True
