"""
Redis connection helper + small wrapper functions for the cache-aside
pattern used on test_run reads.
"""
import os
import json
import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# decode_responses=True -> get back str instead of bytes, easier to json.loads
_client = redis.from_url(REDIS_URL, decode_responses=True)

TTL_RUNNING = 10          # seconds - still changing, keep cache fresh
TTL_FINISHED = 60 * 60    # 1 hour - COMPLETE/ERROR results are immutable


def get_cached(key: str):
    """Returns the parsed dict, or None on cache miss."""
    raw = _client.get(key)
    return json.loads(raw) if raw else None


def set_cached(key: str, value: dict, status: str):
    ttl = TTL_RUNNING if status == "RUNNING" else TTL_FINISHED
    _client.setex(key, ttl, json.dumps(value, default=str))
    # default=str handles datetime fields (started_at/finished_at) that
    # aren't natively JSON-serializable.

def set_list_cached(key: str, value: list[dict]):
    ttl = TTL_RUNNING
    _client.setex(key, ttl, json.dumps(value, default=str))


def invalidate(key: str):
    _client.delete(key)