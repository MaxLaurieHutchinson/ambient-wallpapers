"""Build clean, hash-addressed skill and showcase archives from this workspace."""

import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "ambient-wallpapers"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
PRIVATE_PATTERNS = {
    "absolute user home path": re.compile(r"(?:[a-z]:[\\/]+Users[\\/]+|/Users/|/home/)", re.I),
    "display hardware identifier": re.compile(r"\bDISPLAY#[A-Z0-9]+#", re.I),
    "credential": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b"),
}
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".ps1", ".html"}


def clean_files(folder):
    return sorted(path for path in folder.rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"})


def check_public(files):
    for path in files:
        if path.suffix in TEXT_SUFFIXES:
            body = path.read_text(encoding="utf-8-sig")
            for label, pattern in PRIVATE_PATTERNS.items():
                if pattern.search(body):
                    raise ValueError(f"Private data in shareable bundle: {path.relative_to(ROOT)}: {label}")
            if path.suffix == ".md":
                for target in re.findall(r"\]\(([^)]+)\)", body):
                    if "://" in target or target.startswith("#"):
                        continue
                    if not (path.parent / target.split("#", 1)[0]).exists():
                        raise ValueError(f"Broken bundle reference: {path}: {target}")


files = clean_files(SOURCE)
showcase_files = clean_files(ROOT / "showcase")
check_public(files + showcase_files)
records = [{"path": str(p.relative_to(SOURCE)).replace("\\", "/"),
            "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in files]
skill_zip = DIST / "ambient-wallpapers-0.1.0.zip"
with zipfile.ZipFile(skill_zip, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, Path("ambient-wallpapers") / path.relative_to(SOURCE))
showcase_zip = DIST / "ambient-wallpapers-showcase-0.1.0.zip"
with zipfile.ZipFile(showcase_zip, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in showcase_files:
        archive.write(path, Path("ambient-wallpapers-showcase") / path.relative_to(ROOT / "showcase"))
manifest = {"name": "ambient-wallpapers", "version": "0.1.0", "files": records,
            "archives": [{"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in (skill_zip, showcase_zip)]}
(DIST / "ambient-wallpapers-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"skill_files": len(files), "skill_zip": str(skill_zip),
                  "showcase_zip": str(showcase_zip), "private_marker_check": "passed",
                  "relative_links": "passed"}, indent=2))
