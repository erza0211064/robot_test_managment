"""
Test Execution Worker — standalone service.

Receives a request to run a (mocked) test, does it in the background,
then calls back to the main backend's internal completion endpoint.
"""
import os
import random
import threading
import time

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Test Execution Worker")

# The main backend's internal callback URL, e.g. http://backend:8000
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

MIN_DURATION_SEC = 3
MAX_DURATION_SEC = 15
FAILURE_RATE = 0.2


class ExecuteRequest(BaseModel):
    execute_id: str
    hw_ids: list[str]


@app.post("/execute-test")
def execute_test(body: ExecuteRequest):
    # Return immediately, do the "work" in a background thread —
    # same non-blocking shape as before, just now it's a separate process.
    thread = threading.Thread(
        target=_run_and_report, args=(body.execute_id, body.hw_ids), daemon=True
    )
    thread.start()
    return {"accepted": True, "execute_id": body.execute_id}


def _run_and_report(execute_id: str, hw_ids: list[str]) -> None:
    duration = random.uniform(MIN_DURATION_SEC, MAX_DURATION_SEC)
    time.sleep(duration)

    if random.random() < FAILURE_RATE:
        status, result, msg = "ERROR", None, "Mock hardware reported a fault."
    else:
        status, result, msg = "COMPLETE", "PASS", "Test completed successfully."

    # Call back to the main backend instead of touching the DB directly —
    # the worker shouldn't need direct DB access at all now.
    httpx.post(
        f"{BACKEND_URL}/internal/test-run-complete",
        json={
            "execute_id": execute_id,
            "hw_ids": hw_ids,
            "status": status,
            "result": result,
            "msg": msg,
        },
        timeout=10,
    )