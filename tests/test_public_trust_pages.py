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


def test_public_demo_gallery_contains_three_keyboard_accessible_samples():
    landing = (LANDING / "index.html").read_text(encoding="utf-8")
    gallery = (LANDING / "demos.html").read_text(encoding="utf-8")
    script = (LANDING / "demos.js").read_text(encoding="utf-8")
    assert landing.count('href="/demos.html#') == 3
    assert gallery.count('class="demo-card"') == 3
    assert gallery.count('class="button demo-check"') == 3
    assert gallery.count('role="status" aria-live="polite"') == 3
    assert "input:checked" in script and "card.dataset.answer" in script


def test_public_five_minute_quickstart_is_linked_and_copy_paste_ready():
    landing = (LANDING / "index.html").read_text(encoding="utf-8")
    quickstart = (LANDING / "quickstart.html").read_text(encoding="utf-8")
    documentation = (ROOT / "docs" / "five-minute-mcp-quickstart.md").read_text(encoding="utf-8")
    assert 'href="/quickstart.html"' in landing
    assert "Five-minute MCP quickstart" in quickstart
    assert "claude mcp add --transport http" in quickstart
    assert "Authorization: Bearer YOUR_LICENSE_KEY" in quickstart
    assert "less than five minutes" in documentation
