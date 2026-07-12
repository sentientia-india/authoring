import sys
from types import SimpleNamespace

import pytest

from course_mcp_server.generation_queue import QueueUnavailableError, enqueue_generation_job


class FakeRedis:
    def __init__(self):
        self.markers = set()
        self.items = []

    def set(self, key, value, *, nx, ex):
        assert nx is True and ex > 0 and value == "queued"
        if key in self.markers:
            return False
        self.markers.add(key)
        return True

    def rpush(self, queue, value):
        self.items.append((queue, value))


def test_redis_queue_deduplicates_identical_jobs(monkeypatch):
    fake = FakeRedis()
    redis_module = SimpleNamespace(Redis=SimpleNamespace(from_url=lambda _url: fake))
    monkeypatch.setitem(sys.modules, "redis", redis_module)
    monkeypatch.setenv("REDIS_URL", "redis://queue")

    first = enqueue_generation_job(queue_name="generation", payload={"project_id": "course_1"})
    second = enqueue_generation_job(queue_name="generation", payload={"project_id": "course_1"})

    assert first["backend"] == "redis" and first["deduplicated"] is False
    assert second["backend"] == "redis" and second["deduplicated"] is True
    assert len(fake.items) == 1


def test_production_never_silently_falls_back_when_redis_is_down(monkeypatch):
    class BrokenRedis:
        @staticmethod
        def from_url(_url):
            raise ConnectionError("down")

    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(Redis=BrokenRedis))
    monkeypatch.setenv("REDIS_URL", "redis://queue")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(QueueUnavailableError, match="Durable generation queue"):
        enqueue_generation_job(queue_name="generation", payload={"project_id": "course_1"})
