import json
from pathlib import Path

import pytest

from scripts.database_backup import create_backup


def test_backup_writes_integrity_manifest(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        assert kwargs["check"] is True and kwargs["capture_output"] is True
        output = Path(command[command.index("--file") + 1])
        output.write_bytes(b"database-backup")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = create_backup(database_url="postgresql://example", output_dir=tmp_path)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["size_bytes"] == len(b"database-backup")
    assert len(manifest["sha256"]) == 64


def test_restore_rejects_tampered_backup(tmp_path):
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"tampered")
    manifest = tmp_path / "backup.manifest.json"
    manifest.write_text(json.dumps({"file": backup.name, "sha256": "0" * 64}), encoding="utf-8")

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from database_restore import restore_backup

    with pytest.raises(ValueError, match="integrity"):
        restore_backup(database_url="postgresql://example", backup=backup, manifest=manifest)
