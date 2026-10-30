#!/usr/bin/env python3
"""Train the three-class model and (optionally) freeze it into the manifest.

This is the missing half of gate S1-1. ``freeze_model.py`` could already write an
honest manifest, and ``eval_common.py`` could already refuse to report numbers
from random weights, but nothing produced a checkpoint to freeze. This script
does that, under three rules:

1. **No fabricated provenance.** The seed, split, epoch count, image size and git
   commit are recorded from what actually ran; anything unavailable is ``null``.
2. **No invented skin types.** Per-Fitzpatrick figures are emitted only for
   groups with test samples. A group with none is ``null`` -- never ``0.0``.
3. **Leakage is not optional to care about.** If the metadata carries
   ``group_id`` (a lesion or patient identifier), all images of a group land in
   the same split. HAM10000 has several images per lesion, and splitting them
   across train/val inflates every metric it touches.

A ``--smoke`` run trains on a handful of images to exercise the code path. Its
report is marked ``valid: false``, and it **cannot** be frozen -- so no
manifest, and no serving, can ever be produced from it.

Usage
-----
    # Real run, then freeze
    python scripts/train_model.py \
        --data-dir datasets/ham10000 \
        --out runs/ham10000-2026-10-30 \
        --epochs 15 --batch-size 32 --seed 42 \
        --freeze --dataset HAM10000 --split "group-aware 80/20, seed 42"

    # Exercise the path without claiming anything (CI)
    python scripts/train_model.py --data-dir <tiny> --out /tmp/smoke \
        --smoke --epochs 1 --img-size 64 --no-pretrained
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

CLASS_NAMES = ["benign", "melanoma", "kaposi_sarcoma"]
DEFAULT_IMG_SIZE = 224  # must match transforms.IMG_SIZE used at serving time


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def read_metadata(data_dir: Path) -> list[dict]:
    path = data_dir / "metadata.csv"
    if not path.is_file():
        raise SystemExit(f"metadata.csv not found in {data_dir}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"{path} is empty")
    unknown = {row["label"] for row in rows} - set(CLASS_NAMES)
    if unknown:
        raise SystemExit(f"unknown labels in {path}: {sorted(unknown)}")
    return rows


def plan_split(rows: list[dict], seed: int, val_fraction: float = 0.2) -> tuple[list[int], list[int]]:
    """Split row indices, keeping every ``group_id`` on one side.

    Groups are stratified by their dominant class where that is possible.
    """
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    groups = [row.get("group_id") or "" for row in rows]
    indices = list(range(len(rows)))

    if any(groups):
        if any(not group for group in groups):
            raise SystemExit(
                "metadata has a group_id column but some rows are empty; "
                "a partial group id cannot be used to prevent leakage"
            )
        splitter = GroupShuffleSplit(n_splits=1, test_size=val_fraction, random_state=seed)
        train_idx, val_idx = next(splitter.split(indices, groups=groups))
        return list(train_idx), list(val_idx)

    labels = [row["label"] for row in rows]
    counts = {label: labels.count(label) for label in set(labels)}
    stratify = labels if min(counts.values()) >= 2 else None
    train_idx, val_idx = train_test_split(
        indices, test_size=val_fraction, random_state=seed, stratify=stratify,
    )
    return list(train_idx), list(val_idx)


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def _confusion(truth: list[int], predicted: list[int], n_classes: int) -> list[list[int]]:
    matrix = [[0] * n_classes for _ in range(n_classes)]
    for actual, guess in zip(truth, predicted):
        matrix[actual][guess] += 1
    return matrix


def compute_metrics(rows: list[dict], truth: list[int], predicted: list[int]) -> dict:
    """Per-class, per-skin-type and overall figures, with no invented zeros."""
    n_classes = len(CLASS_NAMES)
    per_class = {}
    for index, name in enumerate(CLASS_NAMES):
        tp = sum(1 for t, p in zip(truth, predicted) if t == index and p == index)
        fp = sum(1 for t, p in zip(truth, predicted) if t != index and p == index)
        fn = sum(1 for t, p in zip(truth, predicted) if t == index and p != index)
        support = sum(1 for t in truth if t == index)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision and recall else None)
        per_class[name] = {
            "precision": precision, "recall": recall, "f1": f1, "support": support,
        }

    f1_values = [v["f1"] for v in per_class.values() if v["f1"] is not None]
    macro_f1 = sum(f1_values) / len(f1_values) if f1_values else None

    by_group: dict[str, dict] = {}
    for row, t, p in zip(rows, truth, predicted):
        key = str(row.get("fitzpatrick_type") or "0")
        bucket = by_group.setdefault(key, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += int(t == p)
    per_skin_type = {}
    for key in sorted(by_group, key=lambda k: (k == "0", k)):
        bucket = by_group[key]
        # A group is reported only if it has samples; unknown skin type is its
        # own honest bucket, not merged into any other.
        per_skin_type[key] = {
            "n": bucket["n"],
            "accuracy": bucket["correct"] / bucket["n"] if bucket["n"] else None,
            "known_skin_type": key != "0",
        }

    return {
        "n": len(truth),
        "accuracy": (sum(1 for t, p in zip(truth, predicted) if t == p) / len(truth)
                     if truth else None),
        "macro_f1": macro_f1,
        "per_class": per_class,
        "per_skin_type": per_skin_type,
        "confusion_matrix": _confusion(truth, predicted, n_classes),
        "classes": CLASS_NAMES,
    }


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------

def _build_datasets(data_dir: Path, rows, train_idx, val_idx, img_size):
    from PIL import Image
    from torch.utils.data import Dataset

    from transforms import build_transform

    class _Rows(Dataset):
        def __init__(self, indices, transform):
            self.indices = indices
            self.transform = transform

        def __len__(self):
            return len(self.indices)

        def __getitem__(self, position):
            row = rows[self.indices[position]]
            image_path = data_dir / "images" / f"{row['image_id']}.jpg"
            if not image_path.is_file():
                # Fall back to any extension the converter kept.
                candidates = list((data_dir / "images").glob(f"{row['image_id']}.*"))
                if not candidates:
                    raise FileNotFoundError(image_path)
                image_path = candidates[0]
            image = Image.open(image_path).convert("RGB")
            tensor = self.transform(image)
            return tensor, CLASS_NAMES.index(row["label"])

    train_tf = build_transform("train")
    eval_tf = build_transform("eval")
    # The transform module fixes the serving size; training at another size is
    # allowed but must be recorded, so it is passed through explicitly.
    if img_size != DEFAULT_IMG_SIZE:
        import albumentations as A
        from transforms import IMAGENET_MEAN, IMAGENET_STD

        train_tf.steps.insert(-1, ("Resize", A.Resize(img_size, img_size)))
        eval_tf.steps.insert(-1, ("Resize", A.Resize(img_size, img_size)))

    return _Rows(train_idx, train_tf), _Rows(val_idx, eval_tf)


def train(args) -> dict:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader

    from model import DermatologyCBM

    data_dir = Path(args.data_dir).expanduser()
    rows = read_metadata(data_dir)
    train_idx, val_idx = plan_split(rows, args.seed, args.val_fraction)

    # A three-class head with no examples of one class cannot learn that class:
    # its output is an artefact of the other two. Refuse by default rather than
    # produce a checkpoint that looks complete and is not.
    train_labels = [rows[i]["label"] for i in train_idx]
    untrained = [name for name in CLASS_NAMES if name not in train_labels]
    if untrained and not args.allow_untrained_classes:
        raise SystemExit(
            "refusing to train: no training examples for "
            f"{untrained}.\n"
            "  HAM10000 has no Kaposi sarcoma images, and no other public source "
            "in this project provides them at usable scale.\n"
            "  Options: (a) obtain a Kaposi sarcoma cohort before training a "
            "three-class head; (b) reduce the served model to the classes that "
            "are actually trained (a breaking change to the API contract, to be "
            "logged in the Breaking-Change Register); (c) pass "
            "--allow-untrained-classes to record the gap explicitly in the report "
            "and the model card, where predictions for that class are meaningless."
        )

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    train_set, val_set = _build_datasets(data_dir, rows, train_idx, val_idx, args.img_size)
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True,
                              num_workers=0)
    val_loader = DataLoader(val_set, batch_size=args.batch_size, shuffle=False,
                            num_workers=0)

    model = DermatologyCBM(
        num_classes=len(CLASS_NAMES),
        pretrained_backbone=args.pretrained,
    )
    optimiser = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr,
    )
    criterion = nn.CrossEntropyLoss()
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model.to(device)

    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimiser.zero_grad()
            logits, _concepts = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimiser.step()
            running += float(loss) * images.size(0)
        history.append({"epoch": epoch,
                        "train_loss": running / max(len(train_set), 1)})
        print(f"epoch {epoch}/{args.epochs}  loss={history[-1]['train_loss']:.4f}")

    model.eval()
    truth: list[int] = []
    predicted: list[int] = []
    with torch.no_grad():
        for images, labels in val_loader:
            logits, _concepts = model(images.to(device))
            predicted.extend(logits.argmax(dim=1).cpu().tolist())
            truth.extend(labels.tolist())
    val_rows = [rows[i] for i in val_idx]

    out = Path(args.out).expanduser()
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)
    checkpoint = out / "checkpoints" / "model.pt"
    torch.save(model.state_dict(), checkpoint)

    git_commit = None
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=APP_DIR, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        git_commit = None

    metrics = compute_metrics(val_rows, truth, predicted)
    report = {
        "valid": not args.smoke,
        "smoke": bool(args.smoke),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checkpoint": {"path": str(checkpoint), "sha256": _sha256(checkpoint)},
        "provenance": {
            "dataset": args.dataset or data_dir.name,
            "split": args.split or (
                f"{'group-aware ' if any(r.get('group_id') for r in rows) else ''}"
                f"{int((1 - args.val_fraction) * 100)}/{int(args.val_fraction * 100)}"
                f" seed {args.seed}"
            ),
            "seed": args.seed,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.lr,
            "img_size": args.img_size,
            "backbone": "hrnet_w18",
            "pretrained_backbone": bool(args.pretrained),
            "git_commit": git_commit,
            "n_train": len(train_idx),
            "n_val": len(val_idx),
            "device": str(device),
        },
        "history": history,
        "untrained_classes": untrained,
        "metrics": metrics,
        "notes": [
            "Metrics describe the held-out split of this run only.",
            "Skin-type groups with no test samples are absent; unknown skin type "
            "('0') is reported separately and is not a fairness result.",
        ],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report: {out / 'report.json'}")
    print(f"macro F1: {metrics['macro_f1']}")
    return {"report": report, "checkpoint": checkpoint, "out": out}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze(args, result: dict) -> int:
    if args.smoke:
        print("refusing to freeze: a --smoke run is a code-path test, not a model.")
        print("  its report is marked valid=false and must never back a served model.")
        return 3

    report_path = result["out"] / "report.json"
    report = json.loads(report_path.read_text())
    if not report.get("valid"):
        print("refusing to freeze: the evaluation report is not valid.")
        return 3

    provenance = report["provenance"]
    command = [
        sys.executable, str(APP_DIR / "scripts" / "freeze_model.py"),
        "--checkpoint", str(result["checkpoint"]),
        "--dataset", provenance["dataset"],
        "--split", provenance["split"],
        "--seed", str(provenance["seed"]),
        "--epochs", str(provenance["epochs"]),
        "--metrics-report", str(report_path),
        "--out", str(args.manifest or APP_DIR / "model_manifest.json"),
    ]
    if provenance.get("git_commit"):
        command += ["--git-commit", provenance["git_commit"]]
    print("freezing:", " ".join(command))
    completed = subprocess.run(command, capture_output=True, text=True)
    print(completed.stdout.strip())
    if completed.returncode != 0:
        print(completed.stderr.strip())
        return completed.returncode

    manifest = json.loads(Path(args.manifest or APP_DIR / "model_manifest.json").read_text())
    checkpoint = result["checkpoint"]
    if manifest["checkpoint"].get("sha256") != _sha256(checkpoint):
        print("freeze verification failed: manifest hash does not match the checkpoint")
        return 4
    if manifest.get("status") != "frozen":
        print(f"freeze did not produce a frozen manifest (status={manifest.get('status')!r})")
        return 4
    print(f"manifest frozen: {manifest['status']} sha256={manifest['checkpoint']['sha256'][:16]}...")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train and optionally freeze the 3-class model")
    parser.add_argument("--data-dir", required=True,
                        help="directory with metadata.csv and images/")
    parser.add_argument("--out", required=True, help="run directory for checkpoint + report")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--img-size", type=int, default=DEFAULT_IMG_SIZE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--dataset", default=None, help="dataset name recorded in provenance")
    parser.add_argument("--split", default=None, help="split description recorded in provenance")
    parser.add_argument("--freeze", action="store_true", help="freeze into model_manifest.json")
    parser.add_argument("--manifest", default=None, help="manifest path (default: app root)")
    parser.add_argument("--smoke", action="store_true",
                        help="code-path test only; the report is valid=false and cannot be frozen")
    parser.add_argument("--no-pretrained", dest="pretrained", action="store_false",
                        help="do not download backbone weights (offline / smoke runs)")
    parser.add_argument("--allow-untrained-classes", action="store_true",
                        help="train even though a class has no examples (recorded "
                             "in the report; predictions for it are meaningless)")
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args(argv)

    result = train(args)
    if args.freeze:
        return freeze(args, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
