from course_mcp_server import billing


def test_one_time_course_purchase_provisions_access_without_plan_or_token_leak(monkeypatch):
    queued = []
    recorded = []
    monkeypatch.setattr(billing, "database_url", lambda: "postgresql://configured")
    monkeypatch.setattr(billing, "previous_event", lambda _event_id: None)
    monkeypatch.setattr(
        billing,
        "grant_paid_access",
        lambda token, email: {"share_token": token, "access_token": "secret-access-token"},
    )
    monkeypatch.setattr(billing, "queue_email", lambda **kwargs: queued.append(kwargs))
    monkeypatch.setattr(billing, "record_event", lambda event, result, tenant: recorded.append(result))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://courses.example.com")
    event = {
        "id": "evt_course_purchase",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_course",
                "mode": "payment",
                "customer": "cus_course",
                "customer_details": {"email": "buyer@example.com"},
                "metadata": {
                    "tenant": "tenant-course",
                    "tier": "course",
                    "share_token": "share-token-value-long-enough",
                    "checkout_mode": "payment",
                    "product_name": "Safety Essentials",
                },
            }
        },
    }
    result = billing.process_checkout_event(event)
    assert result["purchase_type"] == "hosted_course"
    assert "access_token" not in result
    assert "secret-access-token" not in str(recorded)
    assert queued[0]["template"] == "enrollment"
    assert "secret-access-token" in queued[0]["data"]["action_url"]
