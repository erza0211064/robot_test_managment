import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://tcms_user:tcms_pass@localhost:5432/tcms_db",
)


@contextmanager
def get_connection():
    """
    Yields a psycopg2 connection. Caller is responsible for commit/rollback
    (see get_db_transaction below for the common case).
    """
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_transaction():
    """
    Yields (conn, cursor) inside a transaction.
    - On success: commits automatically when the `with` block exits.
    - On exception: rolls back automatically, then re-raises.

    This is the building block for the HW-lock logic: run the SELECT ... FOR
    UPDATE and the UPDATE inside the same `with get_db_transaction()` block,
    and either both succeed together or neither does.
    """
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn:  # psycopg2: commits on success, rolls back on exception
            with conn.cursor() as cur:
                yield conn, cur
    finally:
        conn.close()
