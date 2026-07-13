from course_mcp_server import outbox_worker


def test_outbox_worker_delivers_retries_and_dead_letters(monkeypatch):
    events = [
        {"tenant_id": "tenant-a", "event_id": "ok", "event_type": "known"},
        {"tenant_id": "tenant-a", "event_id": "retry", "event_type": "known"},
        {"tenant_id": "tenant-a", "event_id": "unknown", "event_type": "unknown"},
    ]
    delivered = []
    released = []
    monkeypatch.setattr(outbox_worker, "claim_events", lambda **_kwargs: events)
    monkeypatch.setattr(outbox_worker, "mark_delivered", lambda **kwargs: delivered.append(kwargs))

    def release(**kwargs):
        released.append(kwargs)
        return {"status": "dead_lettered" if kwargs["event_id"] == "unknown" else "retry_scheduled"}

    monkeypatch.setattr(outbox_worker, "release_failed", release)

    def handler(event):
        if event["event_id"] == "retry":
            raise ConnectionError("provider unavailable")

    summary = outbox_worker.process_outbox_batch({"known": handler}, max_attempts=4)
    assert summary == {"claimed": 3, "delivered": 1, "retry_scheduled": 1, "dead_lettered": 1}
    assert delivered == [{"tenant_id": "tenant-a", "event_id": "ok"}]
    assert {item["error_code"] for item in released} == {"connectionerror", "lookuperror"}
    assert all(item["max_attempts"] == 4 for item in released)


def test_production_outbox_allowlist_delivers_only_queued_email(monkeypatch):
    delivered = []
    monkeypatch.setattr(outbox_worker, "deliver_email", lambda **kwargs: delivered.append(kwargs))
    handlers = outbox_worker.production_handlers()
    assert set(handlers) == {"email.queued"}
    handlers["email.queued"](
        {"tenant_id": "tenant-a", "payload": {"delivery_id": "mail-1"}}
    )
    assert delivered == [{"tenant_id": "tenant-a", "delivery_id": "mail-1"}]
