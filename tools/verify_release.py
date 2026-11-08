"""Verify versioned release ZIPs match current source and their SHA-256 manifest."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SKILL = ROOT / "skills" / "ambient-wallpapers"
SHOWCASE = ROOT / "showcase"
NOTICE_NAMES = ("LICENSE", "ASSETS-LICENSE.md")


def entries(root: Path) -> dict[str, Path]:
    found = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink in public archive: {path}")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            found[path.relative_to(root).as_posix()] = path
    return found


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_zip(path: Path, source: dict[str, Path], prefix: str) -> None:
    with zipfile.ZipFile(path) as archive:
        expected = {f"{prefix}/{key}" for key in source}
        expected.update(f"{prefix}/{name}" for name in NOTICE_NAMES)
        actual = archive.namelist()
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError(f"Archive content list does not match source: {path.name}")
        corrupted = archive.testzip()
        if corrupted:
            raise ValueError(f"Corrupt ZIP entry: {corrupted}")
        for relative, file_path in source.items():
            if archive.read(f"{prefix}/{relative}") != file_path.read_bytes():
                raise ValueError(f"Archive entry differs from source: {path.name}:{relative}")
        for name in NOTICE_NAMES:
            if archive.read(f"{prefix}/{name}") != (ROOT / name).read_bytes():
                raise ValueError(f"Archive licence notice differs from source: {path.name}:{name}")


def verify() -> dict:
    manifest = json.loads((DIST / "ambient-wallpapers-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "ambient-wallpapers":
        raise ValueError("Wrong archive name")
    version = manifest["version"]
    if manifest.get("licenses") != {"code": "MIT", "example_artwork": "CC-BY-4.0"}:
        raise ValueError("Unsupported or missing licence metadata")
    notices = manifest.get("notices")
    if not isinstance(notices, list) or {item.get("path") for item in notices} != set(NOTICE_NAMES) or len(notices) != len(NOTICE_NAMES):
        raise ValueError("Licence notice inventory is incomplete")
    for notice in notices:
        path = ROOT / notice["path"]
        if not path.is_file() or sha256(path.read_bytes()) != notice["sha256"]:
            raise ValueError(f"Licence notice differs from manifest: {notice['path']}")
    skill = entries(SKILL)
    showcase = entries(SHOWCASE)
    files = manifest["files"]
    paths = [item["path"] for item in files]
    if len(paths) != len(set(paths)) or set(paths) != set(skill):
        raise ValueError("Manifest file inventory differs from the skill source")
    for item in files:
        data = skill[item["path"]].read_bytes()
        if item["bytes"] != len(data) or item["sha256"] != sha256(data):
            raise ValueError(f"Manifest checksum differs from source: {item['path']}")

    expected = {
        f"ambient-wallpapers-{version}.zip": (skill, "ambient-wallpapers"),
        f"ambient-wallpapers-showcase-{version}.zip": (showcase, "ambient-wallpapers-showcase"),
    }
    manifest_archives = manifest["archives"]
    names = [entry["path"] for entry in manifest_archives]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise ValueError("Unexpected archive inventory")
    for item in manifest_archives:
        archive = DIST / item["path"]
        if sha256(archive.read_bytes()) != item["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {archive.name}")
        verify_zip(archive, *expected[item["path"]])

    image_dimensions = {}
    for name, file_path in showcase.items():
        if not name.endswith(".png"):
            continue
        png = file_path.read_bytes()[:24]
        if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            raise ValueError(f"Invalid PNG signature or header: {name}")
        image_dimensions[name] = list(struct.unpack(">II", png[16:24]))
    page = (SHOWCASE / "index.html").read_text(encoding="utf-8")
    for needle in ("og:image", 'rel="canonical"', "github.com/MaxLaurieHutchinson/ambient-wallpapers#install-in-codex"):
        if needle not in page:
            raise ValueError(f"Showcase is missing external navigation/metadata: {needle}")
    return {"status": "verified", "version": version, "skill_files": len(skill),
            "showcase_files": len(showcase), "image_dimensions": image_dimensions}


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), indent=2))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"Release verification failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
