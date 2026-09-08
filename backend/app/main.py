import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.db.connection import get_connection, get_db_transaction
from app.services.hw_lock import acquire_hardware, HardwareUnavailableError
from app.mock_hw.simulator import run_test_in_background
from psycopg2.extras import Json

app = FastAPI(title="Test Case Management System (MVP)")


# ---------- Pydantic request/response models ----------

class TestCaseIn(BaseModel):
    name: str
    description: Optional[str] = None
    hw_config_ids: list[str]
    execute_steps: str
    expected_result: Optional[str] = None
    priority: Optional[int] = None


# ---------- Test case CRUD ----------

@app.post("/new-test-case")
def create_test_case(body: TestCaseIn):
    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            INSERT INTO test_case (name, description, hw_config_ids, execute_steps, expected_result, priority)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING test_id, name, description, hw_config_ids, execute_steps, expected_result
            """,
            (body.name, body.description, Json(body.hw_config_ids), body.execute_steps, body.expected_result, body.priority),
        )
        return cur.fetchone()


@app.put("/update-test-case/{test_id}")
def update_test_case(test_id: int, body: TestCaseIn):
    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            UPDATE test_case
            SET name=%s, description=%s, hw_config_ids=%s, execute_steps=%s,
                expected_result=%s, priority=%s, updated_at=NOW()
            WHERE test_id=%s
            RETURNING test_id, name, description, hw_config_ids, execute_steps, expected_result
            """,
            (body.name, body.description, Json(body.hw_config_ids), body.execute_steps,
             body.expected_result, body.priority, test_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="test_id not found")
        return row


@app.get("/list-test-case")
def list_test_cases():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM test_case ORDER BY test_id")
            return cur.fetchall()


@app.get("/list-test-case/{test_id}")
def get_test_case(test_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM test_case WHERE test_id=%s", (test_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="test_id not found")
            return row


@app.delete("/delete-test-case/{test_id}")
def delete_test_case(test_id: int):
    with get_db_transaction() as (conn, cur):
        cur.execute("DELETE FROM test_case WHERE test_id=%s RETURNING test_id", (test_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="test_id not found")
        return {"deleted": test_id}


# ---------- Hardware status ----------

@app.get("/hardware-status")
def hardware_status():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.hw_id, c.hw_type, s.connection_status, s.in_use
                FROM hw_status s JOIN hw_config c ON s.hw_id = c.hw_id
                ORDER BY s.hw_id
                """
            )
            return {row["hw_id"]: row for row in cur.fetchall()}


# ---------- Test run: start / result / list ----------

@app.post("/start-test/{test_id}")
def start_test(test_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM test_case WHERE test_id=%s", (test_id,))
            test_case = cur.fetchone()
    if not test_case:
        raise HTTPException(status_code=404, detail="test_id not found")

    hw_ids = list(test_case["hw_config_ids"])
    execute_id = str(uuid.uuid4())

    try:
        acquire_hardware(hw_ids, execute_id)
    except HardwareUnavailableError as e:
        return {
            "testID": test_id,
            "uniqueExecuteID": None,
            "name": test_case["name"],
            "status": "HW in use" if e.reason == "in use" else "HW disconnected",
            "msg": str(e),
        }

    with get_db_transaction() as (conn, cur):
        cur.execute(
            """
            INSERT INTO test_run (execute_id, test_id, status)
            VALUES (%s, %s, 'RUNNING')
            """,
            (execute_id, test_id),
        )

    run_test_in_background(execute_id, hw_ids)

    return {
        "testID": test_id,
        "uniqueExecuteID": execute_id,
        "name": test_case["name"],
        "status": "RUNNING",
        "msg": "Test started.",
    }


@app.get("/view-test-result/{execute_id}")
def view_test_result(execute_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.execute_id, r.test_id, c.name, r.status, r.result, r.msg,
                       r.started_at, r.finished_at
                FROM test_run r JOIN test_case c ON r.test_id = c.test_id
                WHERE r.execute_id = %s
                """,
                (execute_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="execute_id not found")
            return row


@app.get("/list-test-run")
def list_test_runs():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT execute_id, test_id, status, started_at, finished_at "
                "FROM test_run ORDER BY started_at DESC"
            )
            return cur.fetchall()
