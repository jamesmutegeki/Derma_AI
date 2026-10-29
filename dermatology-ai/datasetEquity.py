import os
from pathlib import Path

import pandas as pd
from PIL import Image
from torch.utils.data import Dataset


REQUIRED_COLUMNS = ("image_id", "label", "fitzpatrick_type")
CLASSES = {"benign": 0, "melanoma": 1, "kaposi_sarcoma": 2}


def _load_metadata(csv_path, required=REQUIRED_COLUMNS) -> pd.DataFrame:
    """Read a metadata CSV and fail with an actionable message on bad schemas."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Metadata CSV not found: {path}")
    df = pd.read_csv(path)
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"{path} is missing required column(s) {missing}; found {list(df.columns)}. "
            f"Expected at least {list(required)}."
        )
    if df.empty:
        raise ValueError(f"{path} contains no rows")
    return df


class DermDataset(Dataset):
    def __init__(self, csv_path, img_dir, transform=None):
        self.df = _load_metadata(csv_path)
        self.img_dir = str(img_dir)
        self.transform = transform
        self.classes = dict(CLASSES)
        unknown = set(self.df["label"].unique()) - set(self.classes)
        if unknown:
            raise ValueError(f"Unknown labels {sorted(unknown)}; expected {sorted(self.classes)}")

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        img_path = os.path.join(self.img_dir, f"{row['image_id']}.jpg")
        img = Image.open(img_path).convert('RGB')

        if self.transform:
            img = self.transform(img)

        label = self.classes[row['label']]
        fitz = int(row['fitzpatrick_type'])  # ensure Python int, not numpy

        return img, label, fitz


class MultiSourceDermDataset(Dataset):
    """
    Dataset that handles images from multiple source directories.
    CSV must have columns: image_id, label, fitzpatrick_type, source
    where 'source' is one of: 'ham10000', 'passion', 'synthetic', 'isic2019', 'isic2020'
    """

    SOURCE_DIRS = {
        'ham10000': 'ham10000',
        'passion': 'passion/images',
        'synthetic': 'synthetic/images',
        'isic2019': 'isic2019/images',
        'isic2020': 'isic2020/images',
    }

    def __init__(self, csv_path, data_root, transform=None):
        self.df = _load_metadata(csv_path)
        self.data_root = Path(data_root)
        self.transform = transform
        self.classes = {'benign': 0, 'melanoma': 1, 'kaposi_sarcoma': 2}

        # Validate source column
        if 'source' not in self.df.columns:
            # Try to infer from image_id prefix
            self.df['source'] = self.df['image_id'].apply(self._infer_source)

    def _infer_source(self, image_id: str) -> str:
        img_id = str(image_id).lower()
        if img_id.startswith('isic_'):
            return 'ham10000'  # HAM10000 uses ISIC_ ids
        elif img_id.startswith('syn_'):
            return 'synthetic'
        elif img_id.startswith('passion_') or img_id.startswith('pas_'):
            return 'passion'
        else:
            return 'ham10000'  # default

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        source = row.get('source', 'ham10000')
        img_subdir = self.SOURCE_DIRS.get(source, 'ham10000')
        img_dir = self.data_root / img_subdir

        img_path = img_dir / f"{row['image_id']}.jpg"

        # Try other extensions if .jpg not found
        if not img_path.exists():
            for ext in ['.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
                alt_path = img_dir / f"{row['image_id']}{ext}"
                if alt_path.exists():
                    img_path = alt_path
                    break

        if not img_path.exists():
            raise FileNotFoundError(f"Image not found: {img_path}")

        img = Image.open(img_path).convert('RGB')

        if self.transform:
            img = self.transform(img)

        label = self.classes[row['label']]
        fitz = int(row['fitzpatrick_type'])

        return img, label, fitz

