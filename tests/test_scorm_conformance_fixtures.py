from scripts.build_scorm_conformance_fixtures import build


def test_conformance_fixture_builder_generates_valid_hashed_packages(tmp_path):
    evidence = build(tmp_path)

    assert evidence["moodle_target"] == "4.5 LTS"
    assert [item["scorm_version"] for item in evidence["packages"]] == ["1.2", "2004"]
    for item in evidence["packages"]:
        assert (tmp_path / item["file"]).is_file()
        assert len(item["sha256"]) == 64
        assert item["validation"]["valid"] is True

    verified = build(tmp_path, verify_only=True)
    assert [item["sha256"] for item in verified["packages"]] == [
        item["sha256"] for item in evidence["packages"]
    ]
