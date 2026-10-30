#!/usr/bin/env python3
"""Locate a downloaded PASSION for Dermatology archive and convert it.

What this script does **not** do, deliberately:

* it does not carry a label map -- PASSION's four published conditions (atopic
  dermatitis, dermatophytosis, scabies, impetigo) do not correspond to this
  project's ``benign`` / ``melanoma`` / ``kaposi_sarcoma`` classes, so any
  mapping is a research decision that must be made by a person and written to a
  JSON file, not guessed here;
* it does not impute a Fitzpatrick value -- a source that omits skin type
  produces ``fitzpatrick_type = 0`` ("unknown") and is counted in the report;
* it does not download anything unless you give it a URL, because access to
  PASSION is granted individually and the project currently has none.

Previous versions of this file assumed twelve classes (naevus, seborrhoeic
keratosis, melanoma, Kaposi sarcoma, BCC, SCC, ...) and defaulted a missing
Fitzpatrick value to 3. Neither was true of PASSION; both were removed on
2026-10-30 (see ``docs/DATASET_CARD_PASSION.md``). For the same reason there is
no ``scripts/label_maps/passion.json``: shipping one would imply the mapping is
known.

Usage
-----
    # After the PASSION team grants access and sends an archive:
    python scripts/download_passion.py --archive ~/Downloads/passion.zip \\
        --label-map my_passion_map.json \\
        --output datasets/passion

    # Or from a URL, with the token in the environment (never in source):
    PASSION_TOKEN=... python scripts/download_passion.py \\
        --url https://.../passion.zip --label-map my_passion_map.json \\
        --output datasets/passion

    # Show the documented facts and exit:
    python scripts/download_passion.py --info

Access state (2026-10-30): requests to https://passionderm.github.io/ are
unanswered, so nothing in this repository depends on PASSION. The replacement
analysis is in ``docs/DATASET_ALTERNATIVES.md``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prepare_dataset  # noqa: E402  (sibling script, imported by path)

ACCESS_URL = "https://passionderm.github.io/"
FACTS = {
    "full_name": "PASSION for Dermatology",
    "access": f"Access-controlled release, request via {ACCESS_URL}",
    "access_state": "unanswered as of 2026-10-30",
    "size": "4,901 images from 1,653 patients (MICCAI 2024, arXiv:2411.04584)",
    "labels": ["atopic dermatitis", "dermatophytosis", "scabies", "impetigo"],
    "skin_types": "IV-VI",
    "sites": ["Cote d'Ivoire", "Malawi", "Tanzania", "Madagascar"],
    "classes_in_this_project": "none -- the four conditions are not benign/melanoma/kaposi_sarcoma",
    "licence": "PASSION access agreement; ethics approval per project; not redistributable",
}


def _safe_extract(archive: Path, destination: Path) -> None:
    """Extract without allowing members to escape `destination`."""
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()

    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                target = (destination / member).resolve()
                if not str(target).startswith(str(destination_resolved)):
                    raise SystemExit(f"refusing to extract {member!r}: escapes the target directory")
            bundle.extractall(destination)
        return

    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as bundle:
            members = []
            for member in bundle.getmembers():
                target = (destination / member.name).resolve()
                if not str(target).startswith(str(destination_resolved)):
                    raise SystemExit(f"refusing to extract {member.name!r}: escapes the target directory")
                if member.issym() or member.islnk():
                    raise SystemExit(f"refusing to extract link {member.name!r}")
                members.append(member)
            bundle.extractall(destination, members=members)
        return

    raise SystemExit(f"unsupported archive format: {archive.name} (expected .zip or .tar*)")


def _find_layout(root: Path) -> tuple[Path, Path]:
    csv_files = sorted(root.rglob("*.csv"))
    if not csv_files:
        raise SystemExit(f"no CSV found inside the archive ({root})")
    metadata = next(
        (path for path in csv_files if "metadata" in path.name.lower()),
        csv_files[0],
    )
    image_dirs = [path for path in root.rglob("*") if path.is_dir()
                  and path.name.lower() in {"images", "img", "image"}]
    if not image_dirs:
        # Images may sit next to the CSV without a dedicated directory.
        image_dirs = [metadata.parent]
    return metadata, image_dirs[0]


def _download(url: str, destination: Path) -> Path:
    import urllib.request

    token = os.environ.get("PASSION_TOKEN", "").strip()
    request = urllib.request.Request(url)  # noqa: S310 -- operator-supplied URL
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as handle:  # noqa: S310
        shutil.copyfileobj(response, handle)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a downloaded PASSION archive into this project's training layout",
    )
    parser.add_argument("--archive", help="local .zip/.tar archive provided by the PASSION team")
    parser.add_argument("--url", help="direct download URL; token read from $PASSION_TOKEN")
    parser.add_argument("--label-map", help="JSON label map (required; no default is shipped)")
    parser.add_argument("--output", required=False, help="destination directory")
    parser.add_argument("--image-column", default="image_id")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--fitz-column", default="fitzpatrick_type")
    parser.add_argument("--source", default="passion")
    parser.add_argument("--info", action="store_true", help="print the documented facts and exit")
    args = parser.parse_args(argv)

    import json

    if args.info:
        print(json.dumps(FACTS, indent=2))
        return 0

    if not args.archive and not args.url:
        print("PASSION is access-controlled and has not been provided to this project.")
        print(f"  request access at: {ACCESS_URL} (state: {FACTS['access_state']})")
        print(f"  documented cohort: {FACTS['size']}")
        print(f"  labels: {', '.join(FACTS['labels'])}")
        print(f"  three-class head: {FACTS['classes_in_this_project']}")
        print("Re-run with --archive <file> once access is granted, or --info for details.")
        return 2

    if not args.label_map:
        print("refusing to convert: --label-map is required.")
        print("PASSION's four conditions do not map onto benign/melanoma/kaposi_sarcoma,")
        print("so the mapping must be written deliberately, not assumed.")
        return 2

    if not args.output:
        print("refusing to convert: --output is required.")
        return 2

    with tempfile.TemporaryDirectory(prefix="passion-") as workspace:
        if args.archive:
            archive = Path(args.archive).expanduser()
            if not archive.is_file():
                raise SystemExit(f"archive not found: {archive}")
        else:
            print(f"downloading from {args.url} ...")
            archive = _download(args.url, Path(workspace) / "passion-archive")

        extract_dir = Path(workspace) / "extracted"
        _safe_extract(archive, extract_dir)
        metadata_csv, images_dir = _find_layout(extract_dir)
        print(f"metadata: {metadata_csv}")
        print(f"images:   {images_dir}")

        report = prepare_dataset.convert(argparse.Namespace(
            input=str(metadata_csv),
            images_root=str(images_dir),
            output=args.output,
            label_map=args.label_map,
            source=args.source,
            image_column=args.image_column,
            label_column=args.label_column,
            fitz_column=args.fitz_column,
        ))

    print(f"converted {report['rows_out']}/{report['rows_in']} rows -> {args.output}")
    print(f"  classes: {report['class_counts']}")
    print(f"  fitzpatrick: {report['fitzpatrick_counts']}  (0 = not provided by the source)")
    if report["unmapped_labels"]:
        print(f"  unmapped: {report['unmapped_labels'][:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
