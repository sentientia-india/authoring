import pytest
from pydantic import ValidationError

from course_mcp_server.schemas import ExportPackageRequest


def test_public_export_contract_allows_only_supported_production_formats():
    assert ExportPackageRequest(project_id="course_12345678", export_format="scorm").export_format == "scorm"
    assert ExportPackageRequest(project_id="course_12345678", export_format="h5p").export_format == "h5p"
    with pytest.raises(ValidationError):
        ExportPackageRequest(project_id="course_12345678", export_format="adapt")
