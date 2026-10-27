import albumentations as A
from albumentations.pytorch import ToTensorV2
import numpy as np
import cv2


class MelaninNormalization(A.ImageOnlyTransform):
    """Albumentations-compatible melanin normalization via LAB L-channel histogram equalization."""

    def __init__(self, always_apply=False, p=1.0):
        super().__init__(always_apply=always_apply, p=p)

    def apply(self, image, **params):
        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.equalizeHist(l)
        normalized = cv2.merge([l, a, b])
        return cv2.cvtColor(normalized, cv2.COLOR_LAB2RGB)

    def get_transform_init_args_names(self):
        return ()


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

# ML FIX: Deterministic inference transform (no random augmentations, NO MelaninNormalization)
# IMPORTANT: MelaninNormalization uses cv2.equalizeHist (non-differentiable).
# XAI (Grad-CAM, Integrated Gradients) requires differentiable path.
# Training uses dark_skin_aug (includes MelaninNormalization) - OK for training.
# Inference/XAI uses inference_transform (NO MelaninNormalization) - required for XAI.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
inference_transform = A.Compose([
    A.Resize(224, 224),
    A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ToTensorV2()
])