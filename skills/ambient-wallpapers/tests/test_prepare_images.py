"""CLI tests for honest, source-preserving wallpaper image preparation."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_images.py"


def ppm_bytes(width: int, height: int) -> bytes:
    """Return a tiny valid binary PPM source without a test image dependency."""
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + bytes((x % 256 for x in range(width * height * 3)))


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise AssertionError(f"{path} is not a PNG")
    return struct.unpack(">II", header[16:24])


class PrepareImagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.ppm"
        self.source.write_bytes(ppm_bytes(8, 6))
        self.output = self.root / "prepared.png"
        self.manifest = self.root / "prepared.png.manifest.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *extra: str, source: Path | None = None,
                output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--source", str(source or self.source),
             "--output", str(output or self.output), "--width", "4", "--height", "4",
             *extra],
            capture_output=True, text=True, check=False,
        )

    def test_fit_exports_exact_png_size_and_honest_metadata(self) -> None:
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(png_dimensions(self.output), (4, 4))
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(record["source_pixels"], [8, 6])
        self.assertEqual(record["final_pixels"], [4, 4])
        self.assertFalse(record["upscaled"])
        self.assertTrue(record["fit_crop"])
        self.assertIn("crop", record["method"].lower())

    def test_source_is_preserved_byte_for_byte(self) -> None:
        before = self.source.read_bytes()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.source.read_bytes(), before)

    def test_upscale_is_rejected_without_authorization(self) -> None:
        result = self.run_cli("--width", "16", "--height", "12")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upscal", result.stderr.lower())
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_upscale_with_explicit_flag_is_reported(self) -> None:
        result = self.run_cli("--width", "16", "--height", "12", "--allow-upscale")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(png_dimensions(self.output), (16, 12))
        record = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(record["source_pixels"], [8, 6])
        self.assertEqual(record["final_pixels"], [16, 12])
        self.assertTrue(record["upscaled"])

    def test_missing_and_corrupt_sources_are_rejected(self) -> None:
        missing = self.run_cli(source=self.root / "missing.ppm")
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse(self.output.exists())

        corrupt = self.root / "corrupt.img"
        corrupt.write_bytes(b"not an image")
        bad_image = self.run_cli(source=corrupt)
        self.assertNotEqual(bad_image.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_existing_destination_is_preserved_unless_replace_is_explicit(self) -> None:
        self.output.write_bytes(b"keep existing output")
        refused = self.run_cli()
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"keep existing output")

        replaced = self.run_cli("--replace")
        self.assertEqual(replaced.returncode, 0, replaced.stderr)
        self.assertEqual(png_dimensions(self.output), (4, 4))

    def test_existing_manifest_also_requires_replace(self) -> None:
        self.manifest.write_text("keep existing metadata", encoding="utf-8")
        refused = self.run_cli()
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(self.manifest.read_text(encoding="utf-8"), "keep existing metadata")


if __name__ == "__main__":
    unittest.main()
