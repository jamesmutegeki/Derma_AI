#!/usr/bin/env python3
"""
PASSION for Dermatology Dataset Download Script

Prerequisites:
1. Register at https://passionderm.github.io/ with academic email
2. After approval, you'll receive download credentials (typically a direct download link or API token)
3. Update the DOWNLOAD_URL and AUTH_TOKEN below with your credentials

The dataset should contain:
- metadata.csv with columns: image_id, label, fitzpatrick_type (1-6), and optionally disease_type
- images/ directory with JPEG files named <image_id>.jpg

After download, this script will:
1. Extract the archive
2. Validate the structure
3. Create a standardized metadata CSV compatible with DermDataset
4. Map PASSION's 12 disease classes to our 3-class schema (benign, melanoma, kaposi_sarcoma)
"""

import zipfile
import tarfile
import shutil
from pathlib import Path
import pandas as pd
import requests
from tqdm import tqdm

# ============================================================
# CONFIGURATION - UPDATE THESE AFTER REGISTRATION
# ============================================================
# Option 1: Direct download URL (if provided after registration)
DOWNLOAD_URL = "https://passionderm.github.io/download/passion_dataset.zip"  # PLACEHOLDER - UPDATE THIS

# Option 2: If using an API token
AUTH_TOKEN = ""  # PLACEHOLDER - UPDATE IF NEEDED

# Target directory
DATA_ROOT = Path(__file__).parent.parent / "datasets" / "passion"
METADATA_CSV = DATA_ROOT / "metadata.csv"
IMAGES_DIR = DATA_ROOT / "images"

# PASSION class mapping to our 3-class schema
# PASSION has 12 disease categories. Map them as follows:
# ML FIX: Exclude BCC/SCC (malignant) from benign class - they are filtered out
CLASS_MAPPING = {
    # Benign conditions
    "nevus": "benign",
    "seborrheic_keratosis": "benign",
    "lentigo": "benign",
    "dermatofibroma": "benign",
    "vascular_lesion": "benign",
    # Malignant melanoma
    "melanoma": "melanoma",
    # Kaposi sarcoma (if present in PASSION)
    "kaposi_sarcoma": "kaposi_sarcoma",
    # ML FIX: BCC and SCC are MALIGNANT - exclude from benign class
    # These will be filtered out and logged (see standardize_metadata)
    # "basal_cell_carcinoma": "benign",  # EXCLUDED - malignant
    # "squamous_cell_carcinoma": "benign",  # EXCLUDED - malignant
    "actinic_keratosis": "benign",
    "eczema": "benign",
    "psoriasis": "benign",
}

# Classes to exclude (malignant but not melanoma/KS)
EXCLUDED_CLASSES = {"basal_cell_carcinoma", "squamous_cell_carcinoma"}

# ============================================================


def download_with_progress(url: str, dest: Path, token: str = ""):
    """Download file with progress bar."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))

    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as f, tqdm(
        total=total_size, unit="B", unit_scale=True, desc=dest.name
    ) as pbar:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))


def extract_archive(archive_path: Path, extract_to: Path):
    """Extract zip or tar.gz archive."""
    print(f"Extracting {archive_path} to {extract_to}...")
    extract_to.mkdir(parents=True, exist_ok=True)

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_to)
    elif archive_path.suffix in [".gz", ".tgz", ".tar.gz"]:
        with tarfile.open(archive_path, "r:gz") as tf:
            tf.extractall(extract_to)
    elif archive_path.suffix == ".tar":
        with tarfile.open(archive_path, "r:") as tf:
            tf.extractall(extract_to)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path.suffix}")


def find_metadata_and_images(root: Path):
    """Find metadata CSV and images directory in extracted archive."""
    # Common patterns
    metadata_candidates = list(root.rglob("*metadata*.csv")) + list(root.rglob("*labels*.csv"))
    images_dirs = [d for d in root.rglob("images") if d.is_dir()] + [d for d in root.rglob("img") if d.is_dir()]

    if not metadata_candidates:
        raise FileNotFoundError(f"No metadata CSV found in {root}")
    if not images_dirs:
        raise FileNotFoundError(f"No images directory found in {root}")

    # Use the first match (usually there's only one)
    metadata_path = metadata_candidates[0]
    images_dir = images_dirs[0]

    print(f"Found metadata: {metadata_path}")
    print(f"Found images dir: {images_dir}")

    return metadata_path, images_dir


def standardize_metadata(metadata_path: Path, output_path: Path):
    """Convert PASSION metadata to our standard format."""
    df = pd.read_csv(metadata_path)
    print(f"Original columns: {df.columns.tolist()}")
    print(f"Original shape: {df.shape}")
    print(f"Unique labels: {df['label'].unique() if 'label' in df.columns else 'N/A'}")

    # Try to find the right columns
    # PASSION might have: image_id, diagnosis, fitzpatrick, disease_type, etc.
    id_col = None
    label_col = None
    fitz_col = None

    for col in df.columns:
        col_lower = col.lower()
        if "id" in col_lower or "image" in col_lower:
            id_col = col
        if "label" in col_lower or "diagnosis" in col_lower or "disease" in col_lower or "class" in col_lower:
            label_col = col
        if "fitz" in col_lower or "skin" in col_lower or "type" in col_lower:
            fitz_col = col

    if not id_col or not label_col:
        raise ValueError(f"Could not identify ID and label columns. Columns: {df.columns.tolist()}")

    # Create standardized dataframe
    std_df = pd.DataFrame()
    std_df["image_id"] = df[id_col].astype(str)
    # Map labels, keeping original for exclusion logic
    std_df["_original_label"] = df[label_col].astype(str)
    std_df["label"] = std_df["_original_label"].map(CLASS_MAPPING)

    # Handle Fitzpatrick
    if fitz_col and fitz_col in df.columns:
        std_df["fitzpatrick_type"] = df[fitz_col].astype(int).clip(1, 6)
    else:
        # Try to infer from other columns or use default
        print("WARNING: No Fitzpatrick column found. Using default type 3.")
        std_df["fitzpatrick_type"] = 3

    # Check for unmapped labels (excluding explicitly excluded classes)
    unmapped = std_df[std_df["label"].isna()]["_original_label"].unique()
    if len(unmapped) > 0:
        print(f"WARNING: Unmapped labels (will be dropped): {unmapped}")
        print("Update CLASS_MAPPING in this script to include them.")
        std_df = std_df.dropna(subset=["label"])

    # ML FIX: Exclude BCC/SCC (malignant) from benign class
    excluded_mask = std_df["_original_label"].isin(EXCLUDED_CLASSES)
    excluded_count = excluded_mask.sum()
    if excluded_count > 0:
        print(f"ML FIX: Excluding {excluded_count} samples with malignant labels {EXCLUDED_CLASSES} from benign class")
        std_df = std_df[~excluded_mask].copy()

    # Ensure image files exist
    print("Verifying image files...")
    missing = []
    for img_id in std_df["image_id"]:
        img_path = IMAGES_DIR / f"{img_id}.jpg"
        if not img_path.exists():
            # Try other extensions
            found = False
            for ext in [".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
                if (IMAGES_DIR / f"{img_id}{ext}").exists():
                    found = True
                    break
            if not found:
                missing.append(img_id)

    if missing:
        print(f"WARNING: {len(missing)} images not found. First 10: {missing[:10]}")
        std_df = std_df[~std_df["image_id"].isin(missing)]

    # Save standardized metadata
    std_df.to_csv(output_path, index=False)
    print(f"Standardized metadata saved to {output_path}")
    print(f"Shape: {std_df.shape}")
    print(f"Label distribution:\n{std_df['label'].value_counts()}")
    print(f"Fitzpatrick distribution:\n{std_df['fitzpatrick_type'].value_counts().sort_index()}")

    return std_df


def create_train_val_split(metadata_path: Path, train_frac: float = 0.8, seed: int = 42):
    """Create stratified train/val split."""
    df = pd.read_csv(metadata_path)

    from sklearn.model_selection import train_test_split

    train_df, val_df = train_test_split(
        df,
        train_size=train_frac,
        random_state=seed,
        stratify=df[["label", "fitzpatrick_type"]]
    )

    train_path = metadata_path.parent / "train_meta.csv"
    val_path = metadata_path.parent / "val_meta.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)

    print(f"Train: {len(train_df)} samples -> {train_path}")
    print(f"Val: {len(val_df)} samples -> {val_path}")
    print(f"Train label dist:\n{train_df['label'].value_counts()}")
    print(f"Val label dist:\n{val_df['label'].value_counts()}")


def main():
    print("=" * 60)
    print("PASSION for Dermatology Dataset Setup")
    print("=" * 60)

    # Check if already downloaded
    if METADATA_CSV.exists() and IMAGES_DIR.exists():
        print(f"Dataset already exists at {DATA_ROOT}")
        response = input("Re-download and overwrite? (y/N): ").strip().lower()
        if response != "y":
            print("Skipping download.")
            return

    # Check configuration
    if "PLACEHOLDER" in DOWNLOAD_URL:
        print("\n⚠️  CONFIGURATION REQUIRED")
        print("Please register at: https://passionderm.github.io/")
        print("After approval, update DOWNLOAD_URL and AUTH_TOKEN in this script.")
        print("\nThen re-run this script.")
        return

    # Download
    archive_path = DATA_ROOT / "passion_dataset.zip"
    print(f"\nDownloading from {DOWNLOAD_URL}...")
    try:
        download_with_progress(DOWNLOAD_URL, archive_path, AUTH_TOKEN)
    except Exception as e:
        print(f"Download failed: {e}")
        print("Please check your DOWNLOAD_URL and AUTH_TOKEN.")
        return

    # Extract
    try:
        extract_dir = DATA_ROOT / "extracted"
        extract_archive(archive_path, extract_dir)
    except Exception as e:
        print(f"Extraction failed: {e}")
        return

    # Find metadata and images
    try:
        meta_path, img_dir = find_metadata_and_images(extract_dir)
    except Exception as e:
        print(f"Could not locate dataset files: {e}")
        return

    # Move images to standard location
    if img_dir != IMAGES_DIR:
        print(f"Moving images to {IMAGES_DIR}...")
        if IMAGES_DIR.exists():
            shutil.rmtree(IMAGES_DIR)
        shutil.move(str(img_dir), str(IMAGES_DIR))

    # Standardize metadata
    try:
        standardize_metadata(meta_path, METADATA_CSV)
    except Exception as e:
        print(f"Metadata standardization failed: {e}")
        return

    # Create train/val split
    try:
        create_train_val_split(METADATA_CSV)
    except Exception as e:
        print(f"Split creation failed: {e}")
        return

    # Cleanup
    shutil.rmtree(extract_dir, ignore_errors=True)
    archive_path.unlink(missing_ok=True)

    print("\n✅ PASSION dataset ready!")
    print(f"  Metadata: {METADATA_CSV}")
    print(f"  Images: {IMAGES_DIR}")
    print(f"  Train split: {DATA_ROOT / 'train_meta.csv'}")
    print(f"  Val split: {DATA_ROOT / 'val_meta.csv'}")


if __name__ == "__main__":
    main()