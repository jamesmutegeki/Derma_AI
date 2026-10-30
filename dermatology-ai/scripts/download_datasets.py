#!/usr/bin/env python3
"""
Dataset Downloader for Dermatology AI Project
============================================
Downloads the public datasets used in the Dermatology AI project.

Datasets included:
  1. HAM10000 (ISIC 2018) — 10,015 dermatoscopic images (7 classes)
  2. ISIC 2019 — 25,331 images (8 classes)  [metadata CSV — images via Kaggle/ISIC]
  3. ISIC 2020 — Melanoma detection dataset
  4. Fitzpatrick17k — 17,000 images with Fitzpatrick skin type labels
  5. DDI (Diverse Dermatology Images) — ~656 images across diverse skin tones
  6. PH2 Dataset — 200 dermatoscopic images

Usage:
    python download_datasets.py
    python download_datasets.py --dataset ham10000
    python download_datasets.py --dataset fitzpatrick17k

Notes:
- ISIC requires Kaggle credentials for full image downloads (kaggle.json).
- DDI requires a free registration on https://ddi-dataset.s3.amazonaws.com/index.html
- Ugandan Mulago images require IRB approval and local access — not downloadable.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# Target directory inside the repository (override with --data-dir).
# Previously hard-coded to D:\Dermatology_AI\datasets, which created a bogus
# directory on Linux/macOS and made the script unusable off Windows.
PROJECT_DATA_DIR = Path(os.environ.get("DERMA_DATA_DIR",
                                       Path(__file__).resolve().parents[1] / "datasets"))
PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path, desc: str = ""):
    """Download a single file with progress reporting."""
    if dest.exists():
        print(f"  ✓ Already exists: {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ Downloading {desc or dest.name} ...")
    try:
        # Harvard Dataverse (HAM10000) returns 403 to default urllib agents.
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✓ Saved: {dest.name} ({size_mb:.1f} MB)")
    except Exception as e:
        print(f"  ✗ Failed: {e}", file=sys.stderr)


def extract_zip(zip_path: Path, extract_to: Path):
    """Extract a zip file."""
    print(f"  📦 Extracting {zip_path.name} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)
    print(f"  ✓ Extracted to {extract_to}")


# ---------------------------------------------------------------------------
# Dataset: HAM10000 (Human Against Machine with 10,000 training images)
# Source: Harvard Dataverse (public, no auth required for metadata)
# ---------------------------------------------------------------------------

def download_ham10000():
    """Download HAM10000 (ISIC 2018) from Harvard Dataverse (public, no auth)."""
    print("\n=== HAM10000 (ISIC 2018) ===")
    target_dir = PROJECT_DATA_DIR / "ham10000"
    target_dir.mkdir(exist_ok=True)

    # Ground truth metadata CSV. Dataverse serves tabular datafiles as .tab (TSV);
    # append ?format=original to get the originally uploaded CSV.
    metadata_url = "https://dataverse.harvard.edu/api/access/datafile/4338392?format=original"
    metadata_path = target_dir / "HAM10000_metadata.csv"
    download_file(metadata_url, metadata_path, "HAM10000 metadata CSV")

    # Lesion segmentations: binary masks for all 10,015 images (XAI / CBM inputs)
    seg_url = "https://dataverse.harvard.edu/api/access/datafile/3838943"
    seg_path = target_dir / "HAM10000_segmentations_lesion_tschandl.zip"
    download_file(seg_url, seg_path, "HAM10000 segmentations (~11 MB)")

    # Official ISIC 2018 Task 3 test set = held-out HAM10000 test images
    test_img_url = "https://dataverse.harvard.edu/api/access/datafile/3855824"
    test_img_path = target_dir / "ISIC2018_Task3_Test_Images.zip"
    download_file(test_img_url, test_img_path, "ISIC2018 Task3 test images (~421 MB)")

    test_gt_url = "https://dataverse.harvard.edu/api/access/datafile/6924466"
    test_gt_path = target_dir / "ISIC2018_Task3_Test_GroundTruth.tab"
    download_file(test_gt_url, test_gt_path, "ISIC2018 Task3 test ground truth")

    # Nature Medicine human-AI interaction benefit ratings (HITL evaluation)
    ai_url = "https://dataverse.harvard.edu/api/access/datafile/3864681"
    ai_path = target_dir / "ISIC2018_Task3_Test_NatureMedicine_AI_Interaction_Benefit.tab"
    download_file(ai_url, ai_path, "Nature Medicine AI-interaction ratings")

    # HAM10000 training images split into two archives
    img1_url = "https://dataverse.harvard.edu/api/access/datafile/3172585"
    img1_path = target_dir / "HAM10000_images_part1.zip"
    download_file(img1_url, img1_path, "HAM10000 images part 1 (~1.37 GB)")

    img2_url = "https://dataverse.harvard.edu/api/access/datafile/3172584"
    img2_path = target_dir / "HAM10000_images_part2.zip"
    download_file(img2_url, img2_path, "HAM10000 images part 2 (~1.4 GB)")

    # Extract zips if present
    if seg_path.exists() and not (target_dir / "HAM10000_segmentations_lesion_tschandl").exists():
        extract_zip(seg_path, target_dir)
    if test_img_path.exists() and not (target_dir / "ISIC2018_Task3_Test_Images").exists():
        extract_zip(test_img_path, target_dir)
    if img1_path.exists() and not (target_dir / "HAM10000_images_part_1").exists():
        extract_zip(img1_path, target_dir)
    if img2_path.exists() and not (target_dir / "HAM10000_images_part_2").exists():
        extract_zip(img2_path, target_dir)


# ---------------------------------------------------------------------------
# Dataset: ISIC 2020 (Melanoma detection)
# Source: Kaggle (requires API key) or ISIC Archive
# ---------------------------------------------------------------------------

def download_isic2020():
    """Download ISIC 2020 melanoma dataset (metadata + sample images)."""
    print("\n=== ISIC 2020 (Melanoma) ===")
    target_dir = PROJECT_DATA_DIR / "isic2020"
    target_dir.mkdir(exist_ok=True)

    # ISIC 2020 metadata is publicly available on the ISIC Archive
    metadata_url = "https://isic-challenge-data.s3.amazonaws.com/2020/ISIC_2020_Training_GroundTruth.csv"
    metadata_path = target_dir / "ISIC_2020_Training_GroundTruth.csv"
    download_file(metadata_url, metadata_path, "ISIC 2020 ground truth CSV")

    print("  ℹ️  Full image archive (~15 GB): ISIC Archive")
    print("     https://www.isic-archive.com/ (free account)")


# ---------------------------------------------------------------------------
# Dataset: Fitzpatrick17k (Skin type labels for 17,000 images)
# Source: GitHub (public)
# ---------------------------------------------------------------------------

def download_fitzpatrick17k():
    """Download Fitzpatrick17k dataset (skin type labels)."""
    print("\n=== Fitzpatrick17k ===")
    target_dir = PROJECT_DATA_DIR / "fitzpatrick17k"
    target_dir.mkdir(exist_ok=True)

    # CSV with Fitzpatrick labels (public GitHub)
    csv_url = "https://raw.githubusercontent.com/mattgroh/fitzpatrick17k/main/fitzpatrick17k.csv"
    csv_path = target_dir / "fitzpatrick17k.csv"
    download_file(csv_url, csv_path, "Fitzpatrick17k CSV labels")

    print("  ℹ️  For the 17,000 image files, request access via:")
    print("     https://forms.gle/4fS35Kg8x9pkG2Bn9")
    print("     (The CSV alone is enough for label-based experiments.)")


# ---------------------------------------------------------------------------
# Dataset: DDI (Diverse Dermatology Images)
# Source: Stanford / S3 (free registration required for images)
# ---------------------------------------------------------------------------

def download_ddi_metadata():
    """Download DDI metadata CSV (Stanford S3)."""
    print("\n=== DDI (Diverse Dermatology Images) ===")
    target_dir = PROJECT_DATA_DIR / "ddi"
    target_dir.mkdir(exist_ok=True)

    # Metadata is publicly available; images require free registration
    print("  ℹ️  DDI requires free academic registration:")
    print("     https://ddi-dataset.s3.amazonaws.com/index.html")
    print("  ℹ️  Once registered, place CSV at:")
    print(f"     {target_dir / 'ddi_metadata.csv'}")


# ---------------------------------------------------------------------------
# Dataset: PH2 (200 dermatoscopic images with ground truth)
# Source: Public (no auth)
# ---------------------------------------------------------------------------

def download_ph2():
    """Download PH2 dermoscopy dataset (200 images + ground truth)."""
    print("\n=== PH2 Dataset ===")
    target_dir = PROJECT_DATA_DIR / "ph2"
    target_dir.mkdir(exist_ok=True)

    ph2_url = "https://www.dropbox.com/s/k88qukc20l8bu20/PH2%20Dataset%20images.zip?dl=1"
    ph2_path = target_dir / "PH2_Dataset_images.zip"
    download_file(ph2_url, ph2_path, "PH2 image archive (~150 MB)")

    gt_url = "https://www.dropbox.com/s/ugdwiy7jhr5j4jh/PH2%20Dataset%20ground%20truth%20labels.zip?dl=1"
    gt_path = target_dir / "PH2_Dataset_labels.zip"
    download_file(gt_url, gt_path, "PH2 ground truth labels (~50 KB)")

    if ph2_path.exists():
        extract_zip(ph2_path, target_dir)


# ---------------------------------------------------------------------------
# Dataset: ISIC 2019 (8-class challenge)
# Source: Kaggle (requires API key) or direct ISIC Archive
# ---------------------------------------------------------------------------

def download_isic2019():
    """Download ISIC 2019 metadata (8 classes)."""
    print("\n=== ISIC 2019 (8-class) ===")
    target_dir = PROJECT_DATA_DIR / "isic2019"
    target_dir.mkdir(exist_ok=True)

    # Ground truth metadata CSV (public mirror)
    csv_url = "https://isic-challenge-data.s3.amazonaws.com/2019/ISIC_2019_Training_GroundTruth.csv"
    csv_path = target_dir / "ISIC_2019_Training_GroundTruth.csv"
    download_file(csv_url, csv_path, "ISIC 2019 ground truth CSV")

    print("  ℹ️  For images (~15 GB), use the ISIC Archive: https://www.isic-archive.com/")


# ---------------------------------------------------------------------------
# Synthetic dataset generator (for testing without waiting for downloads)
# ---------------------------------------------------------------------------

def generate_synthetic_dataset(num_cases: int = 1000):
    """Generate a synthetic CSV + placeholder images for testing the pipeline.

    Useful when real datasets aren't available (no Kaggle creds, no IRB).
    Creates a CSV that matches your `datasetEquity.py` schema:
        image_id, label, fitzpatrick_type
    """
    import csv
    import numpy as np
    from PIL import Image

    print(f"\n=== Generating synthetic dataset ({num_cases} cases) ===")
    target_dir = PROJECT_DATA_DIR / "synthetic"
    target_dir.mkdir(exist_ok=True)
    img_dir = target_dir / "images"
    img_dir.mkdir(exist_ok=True)

    labels = ["benign", "melanoma", "kaposi_sarcoma"]
    csv_path = target_dir / "synthetic_metadata.csv"

    np.random.seed(42)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image_id", "label", "fitzpatrick_type"])
        for i in range(num_cases):
            img_id = f"syn_{i:05d}"
            label = np.random.choice(labels, p=[0.7, 0.2, 0.1])
            # Over-represent dark skin to test equity
            fitz = np.random.choice([1, 2, 3, 4, 5, 6],
                                    p=[0.10, 0.10, 0.10, 0.20, 0.25, 0.25])
            writer.writerow([img_id, label, fitz])

            # Generate a noisy RGB image (placeholder)
            skin_tone = np.clip(
                np.random.normal(180 - fitz * 25, 30, (224, 224, 3)),
                0, 255
            ).astype(np.uint8)
            Image.fromarray(skin_tone).save(img_dir / f"{img_id}.jpg")

    print(f"  ✓ Synthetic dataset saved to {target_dir}")
    print(f"  ✓ CSV: {csv_path}")
    print(f"  ✓ Images: {img_dir} ({num_cases} placeholder JPEGs)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DATASETS = {
    "ham10000": download_ham10000,
    "isic2020": download_isic2020,
    "isic2019": download_isic2019,
    "fitzpatrick17k": download_fitzpatrick17k,
    "ddi": download_ddi_metadata,
    "ph2": download_ph2,
    "synthetic": lambda: generate_synthetic_dataset(),
}


def main():
    parser = argparse.ArgumentParser(
        description="Download datasets for the Dermatology AI project."
    )
    parser.add_argument(
        "--dataset",
        choices=list(DATASETS.keys()) + ["all"],
        default="all",
        help="Which dataset to download (default: all)",
    )
    args = parser.parse_args()

    print(f"Datasets will be saved to: {PROJECT_DATA_DIR}")
    print("=" * 60)

    if args.dataset == "all":
        for name, fn in DATASETS.items():
            try:
                fn()
            except Exception as e:
                print(f"  ✗ {name} failed: {e}", file=sys.stderr)
    else:
        DATASETS[args.dataset]()

    print("\n" + "=" * 60)
    print(f"✅ Done. Datasets at: {PROJECT_DATA_DIR}")
    print("\nNext steps:")
    print(f"  1. Check which folders have data: ls {PROJECT_DATA_DIR}")
    print("  2. For image-only ISIC/Fitzpatrick/DDI data, use the ISIC Archive or request forms")
    print("     (Kaggle is excluded per project preference)")
    print("  3. Update datasetEquity.py csv_path to point to your data")


if __name__ == "__main__":
    main()
