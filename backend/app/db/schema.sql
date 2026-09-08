-- =========================================================
-- Test Case Management System - Database Schema
-- Run automatically by docker-compose on first Postgres init.
-- =========================================================

-- 1. test_case: definitions of test cases
CREATE TABLE test_case (
    test_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    hw_config_ids JSONB NOT NULL,      -- e.g. ["motor_01", "camera_01"]
    execute_steps TEXT NOT NULL,
    expected_result TEXT,
    priority INT DEFAULT 0,             -- lower number = higher priority
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. hw_config: static configuration for each piece of hardware
CREATE TABLE hw_config (
    hw_id VARCHAR(50) PRIMARY KEY,     -- e.g. "motor_01"
    hw_type VARCHAR(50) NOT NULL,      -- "motor", "camera", "plc", ...
    ip VARCHAR(50),
    port INT,
    extra_params JSONB                 -- flexible extra fields, e.g. {"speed": 100}
);

-- 3. hw_status: live availability state for each hardware unit
--    This is the table the HW-lock transaction reads/writes.
CREATE TABLE hw_status (
    hw_id VARCHAR(50) PRIMARY KEY REFERENCES hw_config(hw_id),
    connection_status BOOLEAN NOT NULL DEFAULT true,
    in_use BOOLEAN NOT NULL DEFAULT false,
    current_execute_id VARCHAR(50),
    last_updated TIMESTAMP DEFAULT NOW()
);

-- 4. test_run: one row per execution ("unique-executeID")
CREATE TABLE test_run (
    execute_id VARCHAR(50) PRIMARY KEY,   -- generated UUID
    test_id INT NOT NULL REFERENCES test_case(test_id),
    status VARCHAR(20) NOT NULL,          -- RUNNING | COMPLETE | ERROR
    result TEXT,
    msg TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP
);

CREATE INDEX idx_test_run_test_id ON test_run(test_id);
CREATE INDEX idx_test_run_started_at ON test_run(started_at DESC);

-- =========================================================
-- Seed data: mock hardware so you can test end-to-end
-- without any real devices.
-- =========================================================
INSERT INTO hw_config (hw_id, hw_type, ip, port, extra_params) VALUES
    ('motor_01',  'motor',  '127.0.0.1', 6001, '{"speed": 100}'),
    ('motor_02',  'motor',  '127.0.0.1', 6002, '{"speed": 100}'),
    ('camera_01', 'camera', '127.0.0.1', 6101, '{"filter": "IR"}'),
    ('camera_02', 'camera', '127.0.0.1', 6102, '{"filter": "RGB"}');

INSERT INTO hw_status (hw_id, connection_status, in_use) VALUES
    ('motor_01',  true, false),
    ('motor_02',  true, false),
    ('camera_01', true, false),
    ('camera_02', false, false);  -- one HW is deliberately "disconnected" to test that path
