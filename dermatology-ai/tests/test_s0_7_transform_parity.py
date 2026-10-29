"""S0-7 -- train and serve preprocessing cannot drift apart again.

Acceptance criteria
-------------------
1. There is exactly one place that builds a preprocessing pipeline
   (``transforms.build_transform``); training, evaluation, the Gradio UI and the
   notebook all use it.
2. ``MelaninNormalization`` is applied in **both** modes (a model trained on
   normalised luminance must be served normalised images).
3. The only differences between train and eval are the documented random
   augmentations; resize/normalise/tensor steps are identical and ordered.
4. ``samplesEquity`` no longer defines a second, divergent pipeline.
5. The eval pipeline produces a ``(3, 224, 224)`` float tensor.
"""

from __future__ import annotations

import ast

import numpy as np
import pytest
from PIL import Image

from transforms import IMG_SIZE, TRAIN_ONLY_STEPS, build_transform

pytest.importorskip("albumentations")
pytest.importorskip("torch")


def test_melanin_normalization_is_in_both_modes():
    train = build_transform("train", melanin_normalization=True)
    eval_ = build_transform("eval", melanin_normalization=True)
    assert "MelaninNormalization" in train.steps
    assert "MelaninNormalization" in eval_.steps


def test_shared_steps_have_identical_order():
    train = build_transform("train", melanin_normalization=True).steps
    eval_ = build_transform("eval", melanin_normalization=True).steps

    shared_train = [s for s in train if s not in TRAIN_ONLY_STEPS]
    assert shared_train == eval_, f"train/serve skew: {shared_train} != {eval_}"
    assert eval_[-2:] == ["Normalize", "ToTensorV2"]


def test_train_only_steps_do_not_leak_into_eval():
    eval_steps = build_transform("eval").steps
    for step in TRAIN_ONLY_STEPS:
        assert step not in eval_steps


def test_eval_pipeline_output_shape_and_dtype():
    tensor = build_transform("eval")(Image.new("RGB", (400, 300), (120, 90, 70)))
    assert tuple(tensor.shape) == (3, IMG_SIZE, IMG_SIZE)
    assert tensor.dtype.is_floating_point


def test_eval_pipeline_is_deterministic():
    image = Image.new("RGB", (256, 256), (90, 60, 40))
    first = build_transform("eval")(image)
    second = build_transform("eval")(image)
    assert np.allclose(first.numpy(), second.numpy())


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        build_transform("training")


def test_samples_equity_does_not_own_a_second_pipeline(app_dir):
    source = (app_dir / "samplesEquity.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    assert "MelaninNormalization" in names
    assert "ToTensorV2(" not in source, "samplesEquity must not apply ToTensorV2 (owned by transforms.py)"
    assert "A.Normalize(" not in source, "samplesEquity must not apply A.Normalize (owned by transforms.py)"


def test_every_entry_point_uses_the_shared_pipeline(app_dir):
    text = (app_dir / "ui.py").read_text(encoding="utf-8")
    assert "build_transform" in text, "ui.py builds its own preprocessing"

    notebook = (app_dir / "notebooks" / "01_train_cbm.py").read_text(encoding="utf-8")
    assert "build_transform" in notebook
    assert "Normalize(" not in notebook.replace("A.Normalize", ""), "notebook still normalises by hand"

    backend = (app_dir / "backend.py").read_text(encoding="utf-8")
    assert "build_transform" in backend, "serving path does not use the shared pipeline"


def test_notebook_has_no_stale_ipynb_copy(app_dir):
    ipynbs = list((app_dir / "notebooks").glob("*.ipynb"))
    assert not ipynbs, f"duplicated notebook sources: {[p.name for p in ipynbs]}"
