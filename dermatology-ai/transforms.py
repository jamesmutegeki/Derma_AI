"""Single source of truth for image preprocessing.

Train and serve pipelines must differ only in the random augmentations that
``TRANSFORM_PARITY.md`` lists.  Before this module existed, training applied
``MelaninNormalization`` + rotation/flip/noise while inference applied only
``Resize + Normalize``, which is a systematic domain shift at serving time.

Usage::

    from transforms import build_transform
    tensor = build_transform("eval")(pil_image)          # (3, 224, 224)

Environment
-----------
``MELANIN_NORMALIZATION``  "1" (default) or "0".  When enabled it is applied in
                           *both* modes, because a model trained on normalised
                           luminance must be served normalised images.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

IMG_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

#: Augmentations that are allowed to exist in train mode only.
TRAIN_ONLY_STEPS = [
    "RandomBrightnessContrast",
    "HueSaturationValue",
    "ImageCompression",
    "GaussNoise",
    "Rotate",
    "HorizontalFlip",
]


def melanin_normalization_enabled() -> bool:
    return os.environ.get("MELANIN_NORMALIZATION", "1") not in ("0", "false", "False")


@dataclass
class TransformPipeline:
    """Callable wrapper that also exposes the ordered step names."""

    mode: str
    step_names: List[str] = field(default_factory=list)
    _fn: Optional[Callable[[np.ndarray], object]] = None

    @property
    def steps(self) -> List[str]:
        return list(self.step_names)

    def __call__(self, image) -> object:
        if self._fn is None:  # pragma: no cover - defensive
            raise RuntimeError("TransformPipeline was not initialised")
        if not isinstance(image, np.ndarray):
            image = np.array(image.convert("RGB") if hasattr(image, "convert") else image)
        return self._fn(image=image)["image"]


def build_transform(mode: str = "eval", melanin_normalization: Optional[bool] = None) -> TransformPipeline:
    """Build the preprocessing pipeline for ``mode`` in {"train", "eval"}.

    Raises ``ImportError`` if albumentations is unavailable -- callers must
    treat that as a hard failure, never as a reason to fall back to fake data.
    """
    if mode not in ("train", "eval"):
        raise ValueError("mode must be 'train' or 'eval'")

    import albumentations as A
    from albumentations.pytorch import ToTensorV2

    from samplesEquity import MelaninNormalization

    if melanin_normalization is None:
        melanin_normalization = melanin_normalization_enabled()

    steps: list[tuple[str, object]] = []
    if mode == "train":
        steps += [
            ("RandomBrightnessContrast", A.RandomBrightnessContrast(
                brightness_limit=(-0.3, 0.1), contrast_limit=0.3, p=0.8)),
            ("HueSaturationValue", A.HueSaturationValue(
                hue_shift_limit=10, sat_shift_limit=(-30, 10), val_shift_limit=(-40, 0), p=0.7)),
            ("ImageCompression", A.ImageCompression(quality_range=(60, 100), p=0.3)),
            ("GaussNoise", A.GaussNoise(std_range=(0.02, 0.08), p=0.3)),
            ("Rotate", A.Rotate(limit=90)),
            ("HorizontalFlip", A.HorizontalFlip()),
        ]

    steps.append(("Resize", A.Resize(IMG_SIZE, IMG_SIZE)))
    if melanin_normalization:
        steps.append(("MelaninNormalization", MelaninNormalization(p=1.0)))
    steps.append(("Normalize", A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)))
    steps.append(("ToTensorV2", ToTensorV2()))

    pipeline = TransformPipeline(mode=mode, step_names=[name for name, _ in steps])
    pipeline._fn = A.Compose([transform for _, transform in steps])
    return pipeline
