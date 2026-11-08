"""Build reproducible, privacy-scanned skill and showcase archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "ambient-wallpapers"
SHOWCASE = ROOT / "showcase"
DIST = ROOT / "dist"
PRIVATE_PATTERNS = {
    "absolute home path": re.compile(r"(?:[a-z]:[\\/]+Users[\\/]+|/Users/|/home/)", re.I),
    "display hardware identifier": re.compile(r"\bDISPLAY#[A-Z0-9]+#", re.I),
    "credential": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b"),
}
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".html", ".swift"}
NOTICE_NAMES = ("LICENSE", "ASSETS-LICENSE.md")


def clean_files(folder: Path) -> list[Path]:
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink requires review before packaging: {path}")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}:
            files.append(path)
    return files


def check_public(files: list[Path]) -> None:
    for path in files:
        if path.suffix not in TEXT_SUFFIXES:
            continue
        body = path.read_text(encoding="utf-8-sig")
        for name, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(body):
                raise ValueError(f"Potential private data in {path.relative_to(ROOT)}: {name}")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", body):
                if "://" in target or target.startswith("#"):
                    continue
                if not (path.parent / target.split("#", 1)[0]).exists():
                    raise ValueError(f"Broken local Markdown link in {path}: {target}")


def add_files(archive: zipfile.ZipFile, folder: Path, prefix: str, files: list[Path]) -> None:
    for path in files:
        info = zipfile.ZipInfo(f"{prefix}/{path.relative_to(folder).as_posix()}",
                               date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, path.read_bytes())


def add_notices(archive: zipfile.ZipFile, prefix: str) -> None:
    """Every distributed ZIP carries both legal notices, including its artwork terms."""
    for name in NOTICE_NAMES:
        path = ROOT / name
        info = zipfile.ZipInfo(f"{prefix}/{name}", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, path.read_bytes())


def build(version: str) -> dict:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must be MAJOR.MINOR.PATCH")
    DIST.mkdir(exist_ok=True)
    skill_files = clean_files(SOURCE)
    showcase_files = clean_files(SHOWCASE)
    notices = [ROOT / name for name in NOTICE_NAMES]
    if not all(path.is_file() for path in notices):
        raise ValueError("Both LICENSE and ASSETS-LICENSE.md must be present")
    check_public(skill_files + showcase_files + notices)
    skill_zip = DIST / f"ambient-wallpapers-{version}.zip"
    showcase_zip = DIST / f"ambient-wallpapers-showcase-{version}.zip"
    with zipfile.ZipFile(skill_zip, "w") as archive:
        add_files(archive, SOURCE, "ambient-wallpapers", skill_files)
        add_notices(archive, "ambient-wallpapers")
    with zipfile.ZipFile(showcase_zip, "w") as archive:
        add_files(archive, SHOWCASE, "ambient-wallpapers-showcase", showcase_files)
        add_notices(archive, "ambient-wallpapers-showcase")
    records = [{
        "path": path.relative_to(SOURCE).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
    } for path in skill_files]
    manifest = {
        "name": "ambient-wallpapers",
        "version": version,
        "licenses": {"code": "MIT", "example_artwork": "CC-BY-4.0"},
        "notices": [{"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in notices],
        "files": records,
        "archives": [{
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        } for path in (skill_zip, showcase_zip)]
    }
    (DIST / "ambient-wallpapers-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return {"version": version, "skill_files": len(skill_files),
            "showcase_files": len(showcase_files), "private_marker_check": "passed",
            "relative_links": "passed", "archives": [skill_zip.name, showcase_zip.name]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.1.0", help="Release version (MAJOR.MINOR.PATCH)")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.version), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
