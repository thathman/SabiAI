#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


KEYS = {
    "SABIAI_VAPID_PRIVATE_KEY_FILE",
    "SABIAI_VAPID_PUBLIC_KEY",
    "SABIAI_VAPID_SUBJECT",
}


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return lines, values


def write_private(path: Path, private_key) -> None:
    data = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".vapid-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def public_key_text(private_key) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def update_env(path: Path, original: list[str], values: dict[str, str]) -> None:
    output: list[str] = []
    written: set[str] = set()
    for raw in original:
        stripped = raw.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in KEYS:
            output.append(f"{key}={values[key]}")
            written.add(key)
        else:
            output.append(raw)
    if written != KEYS:
        output.extend(f"{key}={values[key]}" for key in sorted(KEYS - written))
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure private Sabi Boy Web Push keys")
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    env_file = args.env_file.expanduser().resolve()
    lines, values = read_env(env_file)
    key_file = Path(
        values.get("SABIAI_VAPID_PRIVATE_KEY_FILE")
        or env_file.parent / "vapid-private.pem"
    ).expanduser().resolve()

    if key_file.is_file():
        private_key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("Existing VAPID private key is not an EC private key.")
    else:
        private_key = ec.generate_private_key(ec.SECP256R1())
        write_private(key_file, private_key)
    os.chmod(key_file, 0o600)

    values.update(
        {
            "SABIAI_VAPID_PRIVATE_KEY_FILE": str(key_file),
            "SABIAI_VAPID_PUBLIC_KEY": public_key_text(private_key),
            "SABIAI_VAPID_SUBJECT": values.get("SABIAI_VAPID_SUBJECT")
            or "https://picks.hendrix.com.ng",
        }
    )
    update_env(env_file, lines, values)
    print(json.dumps({"configured": True, "private_key_file": str(key_file)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
