"""Real-execution DOM-level tests for renderFillBlankActivity() inside the
exported SCORM player.js (see src/course_mcp_server/exporters/scorm.py ->
_player_js()).

These exercise two confirmed correctness bugs in the embedded fill-blank
renderer:

1. An activity whose `text` has zero `{{blank}}` tokens (e.g. an author's edit
   accidentally stripped the token while `blanks` metadata still has entries)
   used to render zero <input> elements, leaving `allCorrect` permanently
   false and the activity permanently uncompletable with no visible way to
   fix it.
2. A blank with no configured `answers` used to fall back to accepting ANY
   non-empty input as "correct" (`value.length > 0`).

Rather than only grepping the JS source string, this actually evaluates the
extracted player.js in a small hand-rolled DOM simulation (see
tests/js_harness/fill_blank_harness.js) and drives the real renderer function:
inputs get created, the click handler runs, and completion state is read back
from the (fake) classList/textContent the renderer itself set. A full
jsdom/browser harness was judged disproportionate for this fix since jsdom is
not already a dependency anywhere in this repo and the renderer only touches a
small, well-known slice of DOM API surface.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from course_mcp_server.exporters.scorm import _player_js

HARNESS_PATH = Path(__file__).parent / "js_harness" / "fill_blank_harness.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not available in this environment")
def test_fill_blank_activity_dom_behavior(tmp_path):
    player_js_path = tmp_path / "player.js"
    player_js_path.write_text(_player_js(), encoding="utf-8")

    result = subprocess.run(
        ["node", str(HARNESS_PATH), str(player_js_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"fill-blank DOM harness failed (exit {result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "OK" in result.stdout
