"""
Hardware locking logic.

Implements the design decision from the system design doc:
  1. SELECT the relevant hw_status rows FOR UPDATE, in sorted hw_id order
     (sorting avoids deadlocks if two requests lock overlapping HW sets
     in different orders).
  2. Check in Python that every requested HW is connected AND not in use.
  3. If any HW fails the check -> roll back (raise), naming which HW failed.
  4. If all pass -> UPDATE those rows to in_use=true, commit.

Because both the SELECT ... FOR UPDATE and the UPDATE happen inside the same
transaction (see app/db/connection.py -> get_db_transaction), no other
request can slip in between the check and the update for the same HW ids.
"""
from app.db.connection import get_db_transaction


class HardwareUnavailableError(Exception):
    def __init__(self, hw_id: str, reason: str):
        self.hw_id = hw_id
        self.reason = reason
        super().__init__(f"{hw_id} is {reason}")


def acquire_hardware(hw_ids: list[str], execute_id: str) -> None:
    """
    Atomically checks and locks all given hw_ids for this execute_id.
    Raises HardwareUnavailableError if any of them is unavailable.
    """
    sorted_ids = sorted(hw_ids)  # consistent lock ordering -> avoids deadlock

    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            SELECT hw_id, connection_status, in_use
            FROM hw_status
            WHERE hw_id = ANY(%s)
            ORDER BY hw_id
            FOR UPDATE
            """,
            (sorted_ids,),
        )
        rows = {row["hw_id"]: row for row in cur.fetchall()}

        # Make sure every requested hw_id actually exists
        for hw_id in sorted_ids:
            if hw_id not in rows:
                raise HardwareUnavailableError(hw_id, "not found")

        # Check availability for every requested hw_id
        for hw_id in sorted_ids:
            row = rows[hw_id]
            if not row["connection_status"]:
                raise HardwareUnavailableError(hw_id, "disconnected")
            if row["in_use"]:
                raise HardwareUnavailableError(hw_id, "in use")

        # All good -> lock them all for this execute_id
        cur.execute(
            """
            UPDATE hw_status
            SET in_use = true, current_execute_id = %s, last_updated = NOW()
            WHERE hw_id = ANY(%s)
            """,
            (execute_id, sorted_ids),
        )
    # `with get_db_transaction()` commits here automatically.
    # If HardwareUnavailableError was raised above, it rolls back instead
    # (the UPDATE never runs), so no partial locking happens.


def release_hardware(hw_ids: list[str]) -> None:
    """Called when a test run finishes (complete or error) to free the HW."""
    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            UPDATE hw_status
            SET in_use = false, current_execute_id = NULL, last_updated = NOW()
            WHERE hw_id = ANY(%s)
            """,
            (hw_ids,),
        )
