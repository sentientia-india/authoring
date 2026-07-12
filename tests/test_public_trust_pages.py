from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANDING = ROOT / "apps" / "landing"


def test_public_trust_center_covers_launch_policies():
    page = (LANDING / "trust.html").read_text(encoding="utf-8")
    for required in (
        "Privacy",
        "Service terms",
        "Retention, export, and deletion",
        "Support and incidents",
        "Service limits",
        "Subprocessors",
        "security@samratcourse.com",
    ):
        assert required in page
    assert "requires legal review before general availability" in page


def test_public_status_page_has_live_and_failure_states():
    page = (LANDING / "status.html").read_text(encoding="utf-8")
    script = (LANDING / "status.js").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in page
    assert "Live status is temporarily unavailable" in page
    assert 'fetch("/status"' in script
    assert "All monitored systems operational" in script


def test_landing_links_to_public_trust_surfaces():
    page = (LANDING / "index.html").read_text(encoding="utf-8")
    assert 'href="/trust.html"' in page
    assert 'href="/status.html"' in page
