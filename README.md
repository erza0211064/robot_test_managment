# Test Case Management System (MVP)

A test case management system for hardware-in-the-loop testing (robot arms,
motors, sensors, PLCs), designed to handle concurrent hardware access
safely. Hardware is mocked so the whole thing runs free, locally, with no
real devices.

## Why this exists
Built as a portfolio project to demonstrate system design → implementation:
handling concurrent access to a limited pool of shared hardware resources,
with correctness guaranteed via database transactions rather than
application-level locking.

## Architecture
```
Client -> FastAPI backend -> PostgreSQL (test cases, test runs, HW status)
                           -> Redis (cache, WIP)
                           -> Mock HW worker (background thread, simulates
                              running a test on real hardware)
```

Full design doc: see `docs/DESIGN.md` (TODO: copy in the design notes).

## Key design decision: hardware locking
Each hardware unit (`motor_01`, `camera_01`, ...) is a row in `hw_status`.
Starting a test run:
1. Looks up which HW the test case needs.
2. Runs `SELECT ... FOR UPDATE` on those rows inside a transaction (locked
   in sorted order to avoid deadlocks).
3. Checks all requested HW is connected and not in use.
4. If any HW fails the check, rolls back and reports exactly which HW
   is unavailable (`HW in use` / `HW disconnected`).
5. If all pass, marks them `in_use` and commits — atomically, so two
   simultaneous requests can never both grab the same hardware.

See `backend/app/services/hw_lock.py`.

## Running locally

Requires [Docker](https://www.docker.com/) (free) and Docker Compose.

```bash
docker-compose up --build
```

This starts:
- Postgres on `localhost:5432` (schema + mock HW seeded automatically on first run)
- Redis on `localhost:6379`
- API on `localhost:8000`

Interactive API docs (Swagger UI): http://localhost:8000/docs

### Resetting the database
The schema/seed data only runs on the *first* container start (empty
volume). To reset:
```bash
docker-compose down -v   # -v also removes the postgres data volume
docker-compose up --build
```

## Try it out
1. Open http://localhost:8000/docs
2. `POST /new-test-case` with:
   ```json
   {
     "name": "Motor spin test",
     "description": "Spin motor_01 and verify with camera_01",
     "hw_config_ids": ["motor_01", "camera_01"],
     "execute_steps": "1. Start motor. 2. Capture image. 3. Compare.",
     "expected_result": "Motor spins at target speed, image shows motion."
   }
   ```
3. `POST /start-test/{test_id}` — starts the (mocked) test run and locks the HW.
4. `GET /hardware-status` — see `motor_01`/`camera_01` now `in_use: true`.
5. Try starting the same test case again immediately — you should get
   `"status": "HW in use"`.
6. Wait a few seconds, then `GET /view-test-result/{executeID}` — status
   moves from `RUNNING` to `COMPLETE` or `ERROR`, and the HW is released.

## Current scope (MVP)
- ✅ Test case CRUD
- ✅ Hardware-aware test run start (transactional lock)
- ✅ Mock hardware execution (background thread, random pass/fail)
- ✅ Test run status polling
- ⏳ Redis caching layer (recent runs / result cache with status-based TTL) — not yet wired in
- ⏳ Real hardware adapters — out of scope for now, mocked by design
- ⏳ Access control, notifications, flaky-test analytics — deferred (see project notes)

## Tech stack
- FastAPI (Python) — backend API
- PostgreSQL — primary datastore (raw SQL via psycopg2, not an ORM — written
  by hand as a learning exercise in relational DB / transactions)
- Redis — caching layer (planned)
- Docker Compose — one-command local environment
