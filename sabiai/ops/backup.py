from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


@dataclass(frozen=True, slots=True)
class BackupFile:
    label: str
    source: str
    backup: str
    sha256: str
    size: int
    integrity: str


@dataclass(frozen=True, slots=True)
class BackupManifest:
    created_at: str
    directory: str
    files: tuple[BackupFile, ...]
    manifest_path: str

    def as_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "directory": self.directory,
            "files": [asdict(item) for item in self.files],
            "manifest_path": self.manifest_path,
        }


class BackupService:
    """Consistent SQLite snapshots with integrity checks and checksums."""

    def create(
        self,
        files: dict[str, str | Path],
        *,
        destination_root: str | Path,
    ) -> BackupManifest:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        root = Path(destination_root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root.chmod(0o700)
        directory = root / stamp
        directory.mkdir(exist_ok=False)
        directory.chmod(0o700)

        entries: list[BackupFile] = []
        for label, source_value in files.items():
            source = Path(source_value).expanduser()
            if not source.is_file():
                continue
            backup = directory / f"{self._safe(label)}-{source.name}"
            integrity = self._sqlite_integrity(source)
            if integrity != "ok":
                raise RuntimeError(f"Refusing backup of {label}: SQLite integrity check returned {integrity}")
            self._sqlite_backup(source, backup)
            copied_integrity = self._sqlite_integrity(backup)
            if copied_integrity != "ok":
                raise RuntimeError(f"Backup verification failed for {label}: {copied_integrity}")
            entries.append(
                BackupFile(
                    label=label,
                    source=str(source),
                    backup=str(backup),
                    sha256=self._sha256(backup),
                    size=backup.stat().st_size,
                    integrity=copied_integrity,
                )
            )

        if not entries:
            shutil.rmtree(directory, ignore_errors=True)
            raise FileNotFoundError("No requested SQLite database files existed to back up.")

        manifest_path = directory / "manifest.json"
        manifest = BackupManifest(
            created_at=datetime.now(timezone.utc).isoformat(),
            directory=str(directory),
            files=tuple(entries),
            manifest_path=str(manifest_path),
        )
        manifest_path.touch(mode=0o600, exist_ok=False)
        manifest_path.write_text(
            json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest

    def verify(self, manifest_path: str | Path) -> dict:
        manifest = self._load(manifest_path)
        results = []
        ok = True
        for item in manifest["files"]:
            path = Path(item["backup"])
            exists = path.is_file()
            checksum = self._sha256(path) if exists else None
            integrity = self._sqlite_integrity(path) if exists else "missing"
            matches = exists and checksum == item["sha256"] and integrity == "ok"
            ok = ok and matches
            results.append(
                {
                    "label": item["label"],
                    "path": str(path),
                    "exists": exists,
                    "checksum_matches": checksum == item["sha256"] if exists else False,
                    "integrity": integrity,
                    "ok": matches,
                }
            )
        return {"ok": ok, "manifest": str(manifest_path), "files": results}

    def restore(
        self,
        manifest_path: str | Path,
        *,
        label: str,
        destination: str | Path | None = None,
        overwrite: bool = False,
    ) -> dict:
        manifest = self._load(manifest_path)
        item = next((row for row in manifest["files"] if row["label"] == label), None)
        if item is None:
            raise KeyError(f"Backup manifest has no label: {label}")
        backup = Path(item["backup"])
        if self._sha256(backup) != item["sha256"] or self._sqlite_integrity(backup) != "ok":
            raise RuntimeError("Backup failed checksum/integrity verification; refusing restore.")
        target = Path(destination).expanduser() if destination else Path(item["source"]).expanduser()
        if target.exists() and not overwrite:
            raise FileExistsError(f"Restore target already exists: {target}. Use overwrite explicitly.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".restore-tmp")
        if temp.exists():
            temp.unlink()
        self._sqlite_backup(backup, temp)
        if self._sqlite_integrity(temp) != "ok":
            temp.unlink(missing_ok=True)
            raise RuntimeError("Restored temporary database failed SQLite integrity check.")
        if target.exists():
            target.unlink()
        temp.replace(target)
        return {
            "ok": True,
            "label": label,
            "destination": str(target),
            "sha256": self._sha256(target),
            "integrity": self._sqlite_integrity(target),
        }

    @staticmethod
    def _sqlite_backup(source: Path, destination: Path) -> None:
        src_uri = f"file:{source.resolve()}?mode=ro"
        src = sqlite3.connect(src_uri, uri=True)
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
            src.close()

    @staticmethod
    def _sqlite_integrity(path: Path) -> str:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return str(row[0]) if row else "no result"
        finally:
            conn.close()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value).strip("-") or "db"

    @staticmethod
    def _load(manifest_path: str | Path) -> dict:
        path = Path(manifest_path).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("files"), list):
            raise ValueError("Invalid Sabi Boy backup manifest.")
        return data
