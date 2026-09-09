"""
Mock "Test execution worker".

Since there's no real hardware, this simulates running a test case:
- sleeps for a random duration (standing in for actual HW execution time)
- randomly succeeds or fails
- on finish, updates the test_run row and releases the HW lock

In the real design this would be a separate service reached via
POST /test-run-start, with a POST /test-run-complete callback. Here we
simulate that same shape with a background thread, so the API layer's
behavior (return immediately, poll for result later) is realistic even
without a second service.
"""
import random
import threading
import time

from app.db.connection import get_db_transaction
from app.db.redis_client import invalidate
from app.services.hw_lock import release_hardware

MIN_DURATION_SEC = 3
MAX_DURATION_SEC = 15  # kept short for local testing; real limit is 10 min
FAILURE_RATE = 0.2  # 20% of mock runs randomly "fail" to exercise the ERROR path


def run_test_in_background(execute_id: str, hw_ids: list[str]) -> None:
    thread = threading.Thread(
        target=_execute, args=(execute_id, hw_ids), daemon=True
    )
    thread.start()


def _execute(execute_id: str, hw_ids: list[str]) -> None:
    duration = random.uniform(MIN_DURATION_SEC, MAX_DURATION_SEC)
    time.sleep(duration)

    if random.random() < FAILURE_RATE:
        status, result, msg = "ERROR", None, "Mock hardware reported a fault."
    else:
        status, result, msg = "COMPLETE", "PASS", "Test completed successfully."

    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            UPDATE test_run
            SET status = %s, result = %s, msg = %s, finished_at = NOW()
            WHERE execute_id = %s
            """,
            (status, result, msg, execute_id),
        )

    invalidate(f"test_run:{execute_id}")
    invalidate("test_run:recent_list")
    release_hardware(hw_ids)
    
