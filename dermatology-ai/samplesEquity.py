"""Albumentations building blocks for the dermatology pipeline.

``MelaninNormalization`` is the only transform defined here that belongs to the
*preprocessing* path; it is applied in both train and eval mode by
``transforms.build_transform`` so that serving matches training.

``dark_skin_augmentations`` is augmentation-only: it deliberately contains no
``Normalize``/``ToTensorV2`` step, because those belong to the mode-dependent
pipeline.  Use :func:`transforms.build_transform` rather than composing your own
pipelines -- see ``TRANSFORM_PARITY.md``.
"""

import cv2
import albumentations as A


class MelaninNormalization(A.ImageOnlyTransform):
    """LAB L-channel histogram equalisation.

    Non-differentiable (``cv2.equalizeHist``), so input-space gradients are not
    meaningful once an image has passed through it.  Grad-CAM is unaffected (it
    needs gradients w.r.t. a feature map), and Integrated Gradients is documented
    as an approximation -- see ``model.py``.
    """

    def __init__(self, p=1.0):
        # albumentations 2.x: ``always_apply`` was removed; ``p=1.0`` is enough.
        super().__init__(p=p)

    def apply(self, image, **params):
        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_channel = cv2.equalizeHist(l_channel)
        return cv2.cvtColor(cv2.merge([l_channel, a_channel, b_channel]), cv2.COLOR_LAB2RGB)

    def get_transform_init_args_names(self):
        return ()


#: Random augmentations applied during training only.
#:
#: No ``Normalize``/``ToTensorV2`` here on purpose: the normalisation constants
#: must be identical at train and serve time, and that parity is enforced by
#: ``transforms.build_transform`` and tested in ``tests/test_transforms.py``.
dark_skin_augmentations = A.Compose([
    A.RandomBrightnessContrast(brightness_limit=(-0.3, 0.1), contrast_limit=0.3, p=0.8),
    A.HueSaturationValue(
        hue_shift_limit=10,
        sat_shift_limit=(-30, 10),
        val_shift_limit=(-40, 0),
        p=0.7,
    ),
    A.ImageCompression(quality_range=(60, 100), p=0.3),
    A.GaussNoise(std_range=(0.02, 0.08), p=0.3),
    A.Rotate(limit=90),
    A.HorizontalFlip(),
])
