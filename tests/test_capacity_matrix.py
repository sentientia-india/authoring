from scripts import capacity_matrix


def test_capacity_matrix_runs_all_projected_levels(monkeypatch):
    calls = []

    def fake_run_load(*, url, requests, concurrency, timeout):
        calls.append((url, requests, concurrency, timeout))
        return {"error_rate": 0, "p95_seconds": 0.1}

    monkeypatch.setattr(capacity_matrix, "run_load", fake_run_load)
    result = capacity_matrix.run_matrix(
        url="http://service/health", timeout=2, max_error_rate=0, max_p95=0.4
    )
    assert result["passed"] is True
    assert [level[0] for level in capacity_matrix.LOAD_LEVELS] == ["1x", "3x", "10x"]
    assert [call[2] for call in calls] == [5, 15, 50]


def test_capacity_matrix_fails_when_any_level_misses_slo(monkeypatch):
    monkeypatch.setattr(
        capacity_matrix,
        "run_load",
        lambda **kwargs: {"error_rate": 0, "p95_seconds": 0.6 if kwargs["concurrency"] == 50 else 0.1},
    )
    result = capacity_matrix.run_matrix(
        url="http://service/health", timeout=2, max_error_rate=0, max_p95=0.4
    )
    assert result["passed"] is False
    assert result["levels"][-1]["passed"] is False
