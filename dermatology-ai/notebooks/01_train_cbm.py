#!/usr/bin/env python3
"""
01_train_cbm.py -- Equity-driven Dermatology CBM + fairness-weighted PPO triage.

Pipeline (mirrors the section-01 walkthrough exactly):
    split  : build stratified 85/15 HAM10000 splits (binary: melanoma / benign)
    passion: download and prepare PASSION dataset (run download_passion.py first)
    train  : train frozen-backbone DermatologyCBM on combined datasets (3-class)
    ppo    : embed synthetic cases through the CBM -> PPO Case list; train PPO
    fair   : fairness audit (per-Fitzpatrick accuracy + critical-miss rates)
    all    : split -> passion -> train -> ppo -> fair

Run from the repository root (paths are resolved relative to this file, so the
working directory does not matter):

    python dermatology-ai/notebooks/01_train_cbm.py --phase all
    python dermatology-ai/notebooks/01_train_cbm.py --phase smoke   # sanity check
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasetEquity import DermDataset, MultiSourceDermDataset
from model import NUM_CONCEPTS
from transforms import build_transform
from rl_module import Case, DermTriageEnv, PPOAgent, Rollout, TRUE_LABEL_TO_TRIAGE, TRIAGE_NAMES

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------

DATA_DIR = ROOT / "datasets"
HAM_DIR = DATA_DIR / "ham10000"
HAM_META = HAM_DIR / "HAM10000_metadata.csv"
PASSION_DIR = DATA_DIR / "passion"
PASSION_META = PASSION_DIR / "metadata.csv"
PASSION_TRAIN_META = PASSION_DIR / "train_meta.csv"
PASSION_VAL_META = PASSION_DIR / "val_meta.csv"
SYN_DIR = DATA_DIR / "synthetic" / "images"
SYN_META = DATA_DIR / "synthetic" / "synthetic_metadata.csv"
# Combined train/val (created by combine_datasets)
TRAIN_META = DATA_DIR / "train_meta.csv"
VAL_META = DATA_DIR / "val_meta.csv"
CKPT_DIR = ROOT / "model_checkpoints"
CBM_CKPT = CKPT_DIR / "cbm_3class.pt"       # 3-class checkpoint
PPO_CKPT = CKPT_DIR / "ppo_triage.pt"
SMOKE_CBM_CKPT = CKPT_DIR / "smoke_cbm.pt"

IMG_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
LABEL_TO_INT = {"benign": 0, "melanoma": 1, "kaposi_sarcoma": 2}
INT_TO_LABEL = {v: k for k, v in LABEL_TO_INT.items()}
FITZ_PLACEHOLDER_HAM = 3  # HAM10000 has no Fitzpatrick type; use neutral 3

# ML FIX: HAM10000 binary training caveats (see P1.2 in REMEDIATION_PROMPT.md)
# - HAM10000 has 7 dx classes: mel, nv, bkl, bcc, akiec, vasc, df
# - Binary mapping collapses all non-melanoma to 'benign', conflating BCC/AK with nevi
# - Kaposi sarcoma (label 2) has ZERO real HAM10000 samples; only synthetic data provides KS
# - FITZ_PLACEHOLDER_HAM = 3 assigns neutral skin type to all HAM10000 rows, skewing fairness metrics
# - Kaposi sarcoma predictions should include confidence_caveat in API response
#   stating the class is synthetic-data-only and unvalidated on real images.

DEVICE = torch.device("cpu")
TORCH_SEED = 0


def _seed(seed: int = TORCH_SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


_seed()


# ---------------------------------------------------------------------------
# 1) Stratified HAM split (binary label) -- no sklearn dependency
# ---------------------------------------------------------------------------

def make_ham_split(test_size: float = 0.15, seed: int = TORCH_SEED) -> None:
    """Build train_meta.csv / val_meta.csv with cols: image_id, label, fitzpatrick_type.

    Binary mapping: dx == 'mel' -> 'melanoma', everything else -> 'benign'.
    Stratified on the original dx group, then intra-group 85/15.
    """
    meta = pd.read_csv(HAM_META)
    meta["label"] = meta["dx"].map(lambda d: "melanoma" if d == "mel" else "benign")

    train_idx, val_idx = [], []
    for _, grp in meta.groupby("dx"):
        idx = grp.index.tolist()
        n_train = int(round(len(idx) * (1.0 - test_size)))
        rng = random.Random(seed)
        rng.shuffle(idx)
        train_idx.extend(idx[:n_train])
        val_idx.extend(idx[n_train:])

    cols = ["image_id", "label"]
    train_df = meta.loc[train_idx, cols].assign(fitzpatrick_type=FITZ_PLACEHOLDER_HAM).reset_index(drop=True)
    val_df = meta.loc[val_idx, cols].assign(fitzpatrick_type=FITZ_PLACEHOLDER_HAM).reset_index(drop=True)

    train_df.to_csv(TRAIN_META, index=False)
    val_df.to_csv(VAL_META, index=False)

    tr_bin = train_df["label"].value_counts().to_dict()
    va_bin = val_df["label"].value_counts().to_dict()
    print(f"[split] wrote {TRAIN_META.name} n={len(train_df)} {tr_bin}")
    print(f"[split] wrote {VAL_META.name}   n={len(val_df)} {va_bin}")


# ---------------------------------------------------------------------------
# 2) PASSION dataset preparation
# ---------------------------------------------------------------------------

def prepare_passion() -> None:
    """Check PASSION dataset and create train/val splits if metadata exists."""
    if not PASSION_META.exists():
        print(f"[passion] Metadata not found at {PASSION_META}")
        print("         Run: python scripts/download_passion.py")
        return

    if not PASSION_TRAIN_META.exists() or not PASSION_VAL_META.exists():
        print("[passion] Creating train/val splits...")
        from sklearn.model_selection import train_test_split
        df = pd.read_csv(PASSION_META)
        # Stratify on label + fitzpatrick
        train_df, val_df = train_test_split(
            df, train_size=0.8, random_state=TORCH_SEED,
            stratify=df[["label", "fitzpatrick_type"]]
        )
        train_df.to_csv(PASSION_TRAIN_META, index=False)
        val_df.to_csv(PASSION_VAL_META, index=False)
        print(f"[passion] Train: {len(train_df)} | Val: {len(val_df)}")
        print(f"  Train label dist: {train_df['label'].value_counts().to_dict()}")
        print(f"  Val label dist:   {val_df['label'].value_counts().to_dict()}")

    print("[passion] PASSION dataset ready.")


# ---------------------------------------------------------------------------
# 3) Combine datasets for 3-class training
# ---------------------------------------------------------------------------

def combine_datasets() -> None:
    """Combine HAM10000 (binary) + PASSION (3-class) + Synthetic (3-class) into unified train/val."""
    datasets = []

    # HAM10000 (binary: benign/melanoma)
    if TRAIN_META.exists() and VAL_META.exists():
        # Check if these are the original HAM splits or already combined
        train_df = pd.read_csv(TRAIN_META)
        val_df = pd.read_csv(VAL_META)
        if "kaposi_sarcoma" not in train_df["label"].values:
            # These are HAM-only splits, reload from HAM_META
            make_ham_split()
            train_df = pd.read_csv(TRAIN_META)
            val_df = pd.read_csv(VAL_META)
    else:
        make_ham_split()
        train_df = pd.read_csv(TRAIN_META)
        val_df = pd.read_csv(VAL_META)

    # Add source column
    train_df["source"] = "ham10000"
    val_df["source"] = "ham10000"

    print(f"[combine] HAM10000: train={len(train_df)}, val={len(val_df)}")
    print(f"  Label dist: {train_df['label'].value_counts().to_dict()}")
    datasets.append(("HAM10000", train_df, val_df))

    # PASSION (3-class)
    if PASSION_TRAIN_META.exists() and PASSION_VAL_META.exists():
        p_train = pd.read_csv(PASSION_TRAIN_META)
        p_val = pd.read_csv(PASSION_VAL_META)
        p_train["source"] = "passion"
        p_val["source"] = "passion"
        print(f"[combine] PASSION: train={len(p_train)}, val={len(p_val)}")
        print(f"  Label dist: {p_train['label'].value_counts().to_dict()}")
        datasets.append(("PASSION", p_train, p_val))

    # Synthetic (3-class, balanced Fitzpatrick)
    if SYN_META.exists():
        s_train = pd.read_csv(SYN_META)
        # Use 80/20 split for synthetic
        from sklearn.model_selection import train_test_split
        s_train_df, s_val_df = train_test_split(
            s_train, train_size=0.8, random_state=TORCH_SEED,
            stratify=s_train[["label", "fitzpatrick_type"]]
        )
        s_train_df["source"] = "synthetic"
        s_val_df["source"] = "synthetic"
        print(f"[combine] Synthetic: train={len(s_train_df)}, val={len(s_val_df)}")
        print(f"  Label dist: {s_train_df['label'].value_counts().to_dict()}")
        datasets.append(("Synthetic", s_train_df, s_val_df))

    # Combine all
    if len(datasets) == 1:
        print("[combine] Only one dataset available, using as-is")
        combined_train = datasets[0][1]
        combined_val = datasets[0][2]
    else:
        combined_train = pd.concat([d[1] for d in datasets], ignore_index=True)
        combined_val = pd.concat([d[2] for d in datasets], ignore_index=True)

    # Shuffle
    combined_train = combined_train.sample(frac=1, random_state=TORCH_SEED).reset_index(drop=True)
    combined_val = combined_val.sample(frac=1, random_state=TORCH_SEED).reset_index(drop=True)

    combined_train.to_csv(TRAIN_META, index=False)
    combined_val.to_csv(VAL_META, index=False)

    print(f"\n[combine] Combined train: {len(combined_train)} | val: {len(combined_val)}")
    print(f"  Train label dist: {combined_train['label'].value_counts().to_dict()}")
    print(f"  Val label dist:   {combined_val['label'].value_counts().to_dict()}")
    print(f"  Train Fitz dist:  {combined_train['fitzpatrick_type'].value_counts().sort_index().to_dict()}")
    print(f"  Val Fitz dist:    {combined_val['fitzpatrick_type'].value_counts().sort_index().to_dict()}")
    print(f"  Train source dist: {combined_train['source'].value_counts().to_dict()}")
    print(f"  Val source dist:   {combined_val['source'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# 4) Transforms -- single source of truth in ``transforms.py``
# ---------------------------------------------------------------------------
# Train and serve pipelines differ only in the random augmentations listed in
# TRANSFORM_PARITY.md; MelaninNormalization and Normalize are applied in both.

def pipeline(train: bool):
    return build_transform("train" if train else "eval")


def make_loader(csv_path: Path, batch_size: int, train: bool):
    ds = MultiSourceDermDataset(str(csv_path), DATA_DIR, transform=pipeline(train))
    sampler = None
    if train:
        counts = ds.df["label"].value_counts()
        weights = 1.0 / ds.df["label"].map(counts).astype(np.float64)
        sampler = torch.utils.data.WeightedRandomSampler(
            torch.from_numpy(weights.to_numpy()).double(), len(ds), replacement=True
        )
    return torch.utils.data.DataLoader(
        ds, batch_size=batch_size, shuffle=(not train), num_workers=0,
        sampler=sampler,
    )


# ---------------------------------------------------------------------------
# 5) CBM model
# ---------------------------------------------------------------------------

def load_cbm(freeze_backbone: bool = True, num_classes: int = 3):
    from model import DermatologyCBM
    cbm = DermatologyCBM(num_classes=num_classes, num_concepts=NUM_CONCEPTS,
                         hrnet_name="hrnet_w18", pretrained_backbone=True,
                         freeze_backbone=freeze_backbone)
    return cbm.to(DEVICE)


def evaluate_cbm(cbm, loader) -> float:
    cbm.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y, _ in loader:
            out = cbm(x)[0]
            correct += (out.argmax(1) == y).sum().item()
            total += y.size(0)
    return correct / max(total, 1)


# ---------------------------------------------------------------------------
# 6) Headless entrypoint: CBM training (3-class)
# ---------------------------------------------------------------------------

def train_cbm(args) -> None:
    cbm = load_cbm(freeze_backbone=True, num_classes=3)
    optim = torch.optim.AdamW([p for p in cbm.parameters() if p.requires_grad], lr=1e-3)
    crit = torch.nn.CrossEntropyLoss()

    train_loader = make_loader(TRAIN_META, args.batch, train=True)
    val_loader = make_loader(VAL_META, args.batch, train=False)
    best = -1.0

    for epoch in range(1, args.epochs + 1):
        cbm.train()
        run_loss = 0.0
        n = 0
        for x, y, _ in train_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            logits = cbm(x)[0]
            loss = crit(logits, y)
            optim.zero_grad()
            loss.backward()
            optim.step()
            run_loss += loss.item() * len(y)
            n += len(y)
        train_acc = evaluate_cbm(cbm, train_loader)
        val_acc = evaluate_cbm(cbm, val_loader)
        print(f"[train] epoch {epoch}/{args.epochs} | CE {run_loss/n:.4f} | "
              f"train_acc {train_acc:.4f} | val_acc {val_acc:.4f}")
        if val_acc > best:
            best = val_acc
            torch.save(cbm.state_dict(), CBM_CKPT)
            print(f"[train] saved best cbm -> {CBM_CKPT.name} ({val_acc:.4f})")

    print(f"[train] DONE best val_acc {best:.4f}")

    # Prove concept extraction works end-to-end on the trained CBM
    # SECURITY FIX: Use weights_only=True to prevent arbitrary code execution
    cbm.load_state_dict(torch.load(CBM_CKPT, map_location=DEVICE, weights_only=True))
    cbm.eval()
    xb, _, _ = next(iter(val_loader))
    with torch.no_grad():
        concepts = cbm.get_concepts(xb)
        print(f"[train] get_concepts -> shape {tuple(concepts.shape)} on device {DEVICE.type}")


# ---------------------------------------------------------------------------
# 7) CBM embedding -> PPO Case list (synthetic cases carry real Fitzpatrick type)
# ---------------------------------------------------------------------------

def build_cases(cbm, csv_path: Path, img_dir: Path, limit: int | None = None):
    cbm.eval()
    meta = pd.read_csv(csv_path)
    if limit:
        meta = meta.sample(n=min(limit, len(meta)), random_state=TORCH_SEED)
    ds = DermDataset(str(csv_path), str(img_dir), transform=pipeline(train=False))
    loader = torch.utils.data.DataLoader(ds, batch_size=32, num_workers=0)
    cases: list[Case] = []
    with torch.no_grad():
        for x, y, fitz in loader:
            emb = cbm.get_concepts(x).cpu().numpy().astype(np.float32)
            for e, lab, f in zip(emb, y.numpy(), fitz.numpy()):
                cases.append(Case(concept_embedding=e, fitz_type=int(f),
                                  true_label=int(lab), patient_id=f"SYN-{len(cases)}"))
            if limit and len(cases) >= limit:
                break
    print(f"[cases] built {len(cases)} PPO cases (source={csv_path.name})")
    return cases


def train_ppo_loop(cases, episodes: int = 2000, update_interval: int = 64):
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    agent = PPOAgent(env.state_dim, env.action_dim)
    env.seed(cases)

    rollouts: list[Rollout] = []
    ep_rewards = []
    for episode in range(1, episodes + 1):
        state = env.reset()
        action, log_prob, value = agent.select_action(state)
        _, reward, done, _ = env.step(action)
        rollouts.append(Rollout(
            states=[state], actions=[action], rewards=[reward],
            dones=[True], log_probs=[log_prob], values=[value],
        ))
        ep_rewards.append(reward)
        if episode % update_interval == 0 and rollouts:
            metrics = agent.update(rollouts)
            avg_reward = float(np.mean(ep_rewards[-update_interval:]))
            print(f"    [ppo] ep {episode:5d} | avg_reward {avg_reward:6.2f} | "
                  f"policy_loss {metrics.get('policy_loss', 0.0):.4f} | "
                  f"value_loss {metrics.get('value_loss', 0.0):.4f}")
            rollouts = []
    return agent


def train_ppo(args) -> None:
    cbm = load_cbm(num_classes=3)
    cbm.load_state_dict(torch.load(CBM_CKPT, map_location=DEVICE, weights_only=True))
    cases = build_cases(cbm, SYN_META, SYN_DIR, limit=args.limit)
    agent = train_ppo_loop(cases, episodes=args.episodes, update_interval=args.interval)
    agent.save(str(PPO_CKPT))
    print(f"[ppo] saved agent -> {PPO_CKPT.name}")
    _fairness_report(agent, cases, title="post-training (train cases)")


def fair_audit(args) -> None:
    cbm = load_cbm(num_classes=3)
    cbm.load_state_dict(torch.load(CBM_CKPT, map_location=DEVICE, weights_only=True))
    cases = build_cases(cbm, SYN_META, SYN_DIR, limit=args.limit)
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    agent = PPOAgent(env.state_dim, env.action_dim)
    agent.load(str(PPO_CKPT))
    print(f"[fair] loaded agent from {PPO_CKPT.name}")
    _fairness_report(agent, cases, title="fairness audit")


def _fairness_report(agent, cases, title: str) -> None:
    env = DermTriageEnv(num_concepts=NUM_CONCEPTS)
    rows = []
    for fitz in range(1, 7):
        subset = [c for c in cases if c.fitz_type == fitz]
        if not subset:
            continue
        n = len(subset)
        acc = sum(1 for c in subset
                  if agent.evaluate(env._build_state(c)) == TRUE_LABEL_TO_TRIAGE[c.true_label]) / n
        critical = sum(1 for c in subset
                       if c.true_label in (1, 2) and agent.evaluate(env._build_state(c)) != 2) / n
        rows.append((fitz, n, acc, critical))
    print(f"\n[fair] == {title} ==")
    print("  NOTE: synthetic cases generated from label-conditional ranges; "
          "these numbers are NOT clinical or fairness evidence.")
    print("  Fitz  n     triage_acc  critical_miss")
    for fitz, n, acc, crit in rows:
        print(f"  {fitz:<4} {n:<5} {acc:<11.4f} {crit:.4f}")
    if rows:
        iv_plus = [r for r in rows if r[0] >= 4]
        i_iii = [r for r in rows if r[0] <= 3]
        cm_iv_plus = sum(r[1] * r[3] for r in iv_plus) / max(sum(r[1] for r in iv_plus), 1)
        cm_i_iii = sum(r[1] * r[3] for r in i_iii) / max(sum(r[1] for r in i_iii), 1)
        verdict = "PASS" if cm_iv_plus <= cm_i_iii + 1e-9 else "FAIL"
        print(f"  critical-miss  Fitz IV-VI {cm_iv_plus:.4f}  vs  Fitz I-III {cm_i_iii:.4f}  -> {verdict}")


# ---------------------------------------------------------------------------
# 8) Smoke test
# ---------------------------------------------------------------------------

def run_smoke(args) -> None:
    # CBM forward/backward + concept extraction on a tiny real batch
    cbm = load_cbm(freeze_backbone=True, num_classes=3)
    loader = make_loader(VAL_META, 4, train=False)
    x, y, _ = next(iter(loader))
    logits, concepts = cbm(x)
    crit = torch.nn.CrossEntropyLoss()
    loss = crit(logits, y)
    loss.backward()
    print(f"[smoke] CBM OK: logits {tuple(logits.shape)} concepts {tuple(concepts.shape)} "
          f"CE {loss.item():.4f}")
    torch.save(cbm.state_dict(), SMOKE_CBM_CKPT)
    print(f"[smoke] saved smoke cbm -> {SMOKE_CBM_CKPT.name}")

    # Tiny PPO loop on real synthetic cases (fast path, limit=16)
    cases = build_cases(cbm, SYN_META, SYN_DIR, limit=16)
    train_ppo_loop(cases, episodes=64, update_interval=16)
    print("[smoke] SMOKE OK -- pipeline wired correctly (real training is heavy on CPU)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="CBM + fairness-weighted PPO training scaffold")
    ap.add_argument("--phase", choices=["all", "split", "passion", "combine", "smoke", "train", "ppo", "fair"],
                    default="all")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--episodes", type=int, default=2000)
    ap.add_argument("--interval", type=int, default=64)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=TORCH_SEED)
    args = ap.parse_args()

    _seed(args.seed)

    phase = args.phase
    if phase in ("all", "split"):
        make_ham_split()
        if phase == "split":
            return
    if phase in ("all", "passion"):
        prepare_passion()
        if phase == "passion":
            return
    if phase in ("all", "combine"):
        combine_datasets()
        if phase == "combine":
            return
    if phase == "smoke":
        run_smoke(args)
    elif phase == "train":
        train_cbm(args)
    elif phase == "ppo":
        train_ppo(args)
    elif phase == "fair":
        fair_audit(args)
    elif phase == "all":
        train_cbm(args)
        train_ppo(args)
        fair_audit(args)


if __name__ == "__main__":
    main()