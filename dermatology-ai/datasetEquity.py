import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from torch.utils.data import Dataset


class DermDataset(Dataset):
    def __init__(self, csv_path, img_dir, transform=None, label_map=None):
        self.df = pd.read_csv(csv_path)
        # CSV columns: image_id, label, fitzpatrick_type (1-6)
        self.img_dir = img_dir
        self.transform = transform
        self.classes = {'benign': 0, 'melanoma': 1, 'kaposi_sarcoma': 2}

        # If label_map provided, use it to convert labels to class indices
        # Otherwise assume labels are already in the 3-class format
        if label_map is not None:
            self.label_map = label_map
            self.df['label_idx'] = self.df['label'].map(label_map)
            # Keep original label for reporting
            self.df['label_orig'] = self.df['label']
        else:
            self.label_map = None
            self.df['label_idx'] = self.df['label'].map(self.classes)
            self.df['label_orig'] = self.df['label']

        # Scan for corrupted images at init time
        self.corrupted_images = self._scan_corrupted_images()

    def _scan_corrupted_images(self):
        """Scan all images and return list of corrupted image_ids."""
        corrupted = []
        for img_id in self.df['image_id']:
            img_path = os.path.join(self.img_dir, f"{img_id}.jpg")
            try:
                with Image.open(img_path) as img:
                    img.load()
            except OSError as e:
                corrupted.append((img_id, str(e)))
        if corrupted:
            warnings.warn(f"Found {len(corrupted)} corrupted images in {self.img_dir}: {[c[0] for c in corrupted]}")
        return corrupted

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        img_path = os.path.join(self.img_dir, f"{row['image_id']}.jpg")
        try:
            img = Image.open(img_path).convert('RGB')
            img.load()  # Force load to catch truncated images early
        except OSError as e:
            # Re-raise instead of silently skipping - caller must handle
            raise RuntimeError(f"Corrupted image {row['image_id']}: {e}")

        img = np.array(img)  # Convert PIL to numpy for Albumentations

        if self.transform:
            img = self.transform(image=img)['image']

        label = int(row['label_idx'])
        label_orig = row['label_orig']
        fitz = int(row['fitzpatrick_type'])  # ensure Python int, not numpy

        return img, label, fitz, label_orig


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
        self.df = pd.read_csv(csv_path)
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

        try:
            img = Image.open(img_path).convert('RGB')
            img.load()  # Force load to catch truncated images early
        except OSError as e:
            # Re-raise instead of silently skipping
            raise RuntimeError(f"Corrupted image {row['image_id']}: {e}")

        img = np.array(img)  # Convert PIL to numpy for Albumentations

        if self.transform:
            img = self.transform(image=img)['image']

        label = self.classes[row['label']]
        fitz = int(row['fitzpatrick_type'])

        return img, label, fitz