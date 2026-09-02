import albumentations as A
from albumentations.pytorch import ToTensorV2
import numpy as np
import cv2


class MelaninNormalization:
    def __call__(self, image, **kwargs):
        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.equalizeHist(l)
        normalized = cv2.merge([l, a, b])
        return cv2.cvtColor(normalized, cv2.COLOR_LAB2RGB)


dark_skin_aug = A.Compose([
    A.RandomBrightnessContrast(brightness_limit=(-0.3, 0.1),
                               contrast_limit=0.3, p=0.8),
    A.HueSaturationValue(hue_shift_limit=10,
                         sat_shift_limit=(-30, 10),
                         val_shift_limit=(-40, 0), p=0.7),
    A.ImageCompression(quality_range=(60, 100), p=0.3),
    A.GaussNoise(std_range=(0.02, 0.08), p=0.3),
    A.Rotate(limit=90),
    A.HorizontalFlip(),
    A.Resize(224, 224),
    ToTensorV2()
])
