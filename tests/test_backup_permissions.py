import sqlite3
import stat
from pathlib import Path

from sabiai.ops import BackupService


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_backup_and_restore_artifacts_are_private(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample(value) VALUES('kept')")

    service = BackupService()
    manifest = service.create({"v1": source}, destination_root=tmp_path / "backups")
    manifest_file = Path(manifest.manifest_path)
    backup_file = Path(manifest.files[0].backup)

    assert _mode(manifest_file.parent.parent) == 0o700
    assert _mode(manifest_file.parent) == 0o700
    assert _mode(manifest_file) == 0o600
    assert _mode(backup_file) == 0o600

    restored = tmp_path / "restored.db"
    result = service.restore(manifest_file, label="v1", destination=restored)
    assert result["ok"] is True
    assert _mode(restored) == 0o600
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "kept"
