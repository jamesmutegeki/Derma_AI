import pandas as pd
import os
from PIL import Image
import torch
from torch.utils.data import Dataset


class DermDataset(Dataset):
    def __init__(self, csv_path, img_dir, transform=None):
        self.df = pd.read_csv(csv_path)
        # CSV columns: image_id, label, fitzpatrick_type (1-6)
        self.img_dir = img_dir
        self.transform = transform
        self.classes = {'benign': 0, 'melanoma': 1, 'kaposi_sarcoma': 2}

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
