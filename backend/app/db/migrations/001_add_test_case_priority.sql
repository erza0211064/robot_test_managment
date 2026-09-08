-- Migration 001: add priority to test_case
-- Additive-only change: nullable column, existing rows get NULL automatically.
-- Safe to run against a database that already has data.

ALTER TABLE test_case
ADD COLUMN priority INT;
