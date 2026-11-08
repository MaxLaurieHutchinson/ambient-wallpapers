"""Prepare one wallpaper image at an exact size while preserving its source."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Fit an image to an exact PNG size using a centred crop and "
                     "Lanczos resampling. The source file is never modified.")
    )
    parser.add_argument("--source", required=True, type=Path, help="source image path")
    parser.add_argument("--output", required=True, type=Path, help="destination .png path")
    parser.add_argument("--width", required=True, type=_positive_int, help="final width in pixels")
    parser.add_argument("--height", required=True, type=_positive_int, help="final height in pixels")
    parser.add_argument("--allow-upscale", action="store_true",
                        help="authorize enlarging the source image")
    parser.add_argument("--replace", action="store_true",
                        help="replace an existing output image or dimension manifest")
    return parser


def _manifest_path(output: Path) -> Path:
    return output.with_name(output.name + ".manifest.json")


def prepare(source_path: Path, output_path: Path, width: int, height: int,
            allow_upscale: bool = False, replace: bool = False) -> dict[str, object]:
    source_path = source_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    manifest_path = _manifest_path(output_path)

    if not source_path.is_file():
        raise ValueError(f"Source image does not exist or is not a file: {source_path}")
    if output_path.suffix.lower() != ".png":
        raise ValueError("Output path must use the .png extension")
    if source_path == output_path or source_path == manifest_path:
        raise ValueError("Output and manifest paths must not overwrite the source image")
    if not replace:
        existing = [str(path) for path in (output_path, manifest_path) if path.exists()]
        if existing:
            raise FileExistsError("Refusing to overwrite existing file(s): " + ", ".join(existing))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image.load()
        source_width, source_height = image.size
        if source_width <= 0 or source_height <= 0:
            raise ValueError("Source image has invalid dimensions")
        scale = max(width / source_width, height / source_height)
        upscaled = scale > 1.0
        if upscaled and not allow_upscale:
            raise ValueError(
                f"Requested fit would upscale source from {source_width}x{source_height}; "
                "pass --allow-upscale to authorize it"
            )

        crop_needed = not math.isclose(
            source_width / source_height, width / height, rel_tol=1e-12, abs_tol=0.0
        )
        fitted = ImageOps.fit(
            image, (width, height), method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        record: dict[str, object] = {
            "source": str(source_path),
            "output": str(output_path),
            "source_pixels": [source_width, source_height],
            "final_pixels": [width, height],
            "upscaled": upscaled,
            "fit_crop": crop_needed,
            "crop": "center" if crop_needed else None,
            "method": ("Pillow ImageOps.fit with Lanczos resampling; centered crop when "
                       "aspect ratios differ"),
        }

        temporary_output: Path | None = None
        temporary_manifest: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=output_path.stem + ".", suffix=".tmp.png",
                dir=output_path.parent, delete=False,
            ) as stream:
                temporary_output = Path(stream.name)
            fitted.save(temporary_output, format="PNG", optimize=True)
            with Image.open(temporary_output) as check:
                check.verify()
            with Image.open(temporary_output) as check:
                if check.size != (width, height):
                    raise ValueError(f"Prepared image has unexpected dimensions: {check.size}")

            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n",
                prefix=manifest_path.name + ".", suffix=".tmp",
                dir=manifest_path.parent, delete=False,
            ) as stream:
                temporary_manifest = Path(stream.name)
                json.dump(record, stream, indent=2)
                stream.write("\n")

            os.replace(temporary_output, output_path)
            temporary_output = None
            os.replace(temporary_manifest, manifest_path)
            temporary_manifest = None
        finally:
            if temporary_output is not None:
                temporary_output.unlink(missing_ok=True)
            if temporary_manifest is not None:
                temporary_manifest.unlink(missing_ok=True)
        return record


def main() -> int:
    args = _parser().parse_args()
    try:
        record = prepare(args.source, args.output, args.width, args.height,
                         allow_upscale=args.allow_upscale, replace=args.replace)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
