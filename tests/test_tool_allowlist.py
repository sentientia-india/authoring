import pytest

from course_mcp_server.security import ALLOWED_TOOLS, SecurityError, assert_tool_allowed
from course_mcp_server.tools import TOOL_REGISTRY


def test_tool_registry_matches_allowlist():
    assert set(TOOL_REGISTRY) == ALLOWED_TOOLS


@pytest.mark.parametrize("tool_name", ["shell_exec", "read_file", "get_env", "query_database"])
def test_denied_tools_are_not_allowed(tool_name):
    with pytest.raises(SecurityError):
        assert_tool_allowed(tool_name)
