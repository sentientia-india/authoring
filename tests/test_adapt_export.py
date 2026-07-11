import json
from pathlib import Path
from zipfile import ZipFile

from course_mcp_server.exporters.adapt_source import ADAPT_FRAMEWORK_VERSION, build_adapt_source_package


def _fixture_course() -> dict:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "agile_course_content.json").read_text(encoding="utf-8")
    )
    fixture["course_title"] = "Agile Sprint Playbook"
    fixture["course_slug"] = "agile-sprint-playbook"
    fixture["audience"] = "project managers"
    return fixture


def test_adapt_source_package_has_import_contract_layout(tmp_path):
    result = build_adapt_source_package(_fixture_course(), str(tmp_path))

    with ZipFile(result["package_path"]) as package:
        names = set(package.namelist())
        # The exact layout importsourcecheck.js validates.
        for required in (
            "package.json",
            "src/course/config.json",
            "src/course/en/course.json",
            "src/course/en/contentObjects.json",
            "src/course/en/articles.json",
            "src/course/en/blocks.json",
            "src/course/en/components.json",
            "src/theme/adapt-contrib-vanilla/bower.json",
            "src/menu/adapt-contrib-boxMenu/bower.json",
        ):
            assert required in names, f"missing {required}"
        assert json.loads(package.read("package.json"))["version"] == ADAPT_FRAMEWORK_VERSION


def test_adapt_source_maps_course_structure_and_components(tmp_path):
    result = build_adapt_source_package(_fixture_course(), str(tmp_path))

    with ZipFile(result["package_path"]) as package:
        pages = json.loads(package.read("src/course/en/contentObjects.json"))
        articles = json.loads(package.read("src/course/en/articles.json"))
        blocks = json.loads(package.read("src/course/en/blocks.json"))
        components = json.loads(package.read("src/course/en/components.json"))

    # 3 modules + final assessment page
    assert [p["title"] for p in pages][:3] == [
        "The Sprint Engine",
        "Ceremonies That Earn Their Time",
        "Evidence and Judgement",
    ]
    assert pages[3]["title"] == "Sprint Playbook Final Check"
    # 6 lessons + 1 final-assessment article
    assert len(articles) == 7
    # One component per block, every parent id resolves
    assert len(blocks) == len(components)
    block_ids = {b["_id"] for b in blocks}
    article_ids = {a["_id"] for a in articles}
    page_ids = {p["_id"] for p in pages}
    assert all(c["_parentId"] in block_ids for c in components)
    assert all(b["_parentId"] in article_ids for b in blocks)
    assert all(a["_parentId"] in page_ids for a in articles)
    # Core-only component set (no plugin installs needed at import)
    used = {c["_component"] for c in components}
    assert used <= {"text", "graphic", "media", "mcq", "matching", "accordion"}
    # Quiz questions arrive as mcq with the correct answer flagged
    mcq = next(c for c in components if c["_component"] == "mcq")
    assert any(item["_shouldBeSelected"] for item in mcq["_items"])
    # Authored prose is present and editable
    all_text = json.dumps(components)
    assert "optimism can compound" in all_text


def test_adapt_source_packages_uploaded_media_assets(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "backlog-labels.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    result = build_adapt_source_package(_fixture_course(), str(tmp_path), upload_dir=str(uploads))

    with ZipFile(result["package_path"]) as package:
        names = package.namelist()
        components = json.loads(package.read("src/course/en/components.json"))
    assert "src/course/en/assets/backlog-labels.svg" in names
    graphic = next(c for c in components if c["_component"] == "graphic")
    assert graphic["_graphic"]["large"] == "course/en/assets/backlog-labels.svg"
