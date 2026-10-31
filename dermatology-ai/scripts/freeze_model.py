#!/usr/bin/env python3
"""Freeze a trained checkpoint into a manifest.

Every figure a poster, slide or document quotes must be traceable to a script and
a frozen artefact.  This script writes that artefact: the SHA-256 of the weights,
the architecture it belongs to, the training provenance the operator supplies,
and (optionally) the path of an evaluation report whose numbers may be quoted.

It refuses to invent anything: missing provenance stays ``null`` and the manifest
stays ``status: "placeholder"`` unless every required field is supplied.

Usage
-----
    python scripts/freeze_model.py \
        --checkpoint /secure/models/cbm_3class.pt \
        --dataset HAM10000 --split "80/20 stratified, seed 42" --seed 42 \
        --epochs 30 --git-commit "$(git rev-parse HEAD)" \
        --metrics-report reports/eval_ham_2026-10-30.json \
        --out model_manifest.json

Exit codes: 0 written, 2 invalid input, 3 checkpoint missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = APP_DIR / "model_manifest.json"

REQUIRED_PROVENANCE = ("dataset", "split", "seed", "epochs", "git_commit")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(args) -> dict:
    checkpoint = Path(args.checkpoint).expanduser()
    if not checkpoint.is_file():
        raise SystemExit(f"checkpoint not found: {checkpoint}")

    manifest = json.loads(Path(args.template).read_text(encoding="utf-8"))
    manifest["checkpoint"].update({
        "filename": checkpoint.name,
        "sha256": sha256_file(checkpoint),
        "bytes": checkpoint.stat().st_size,
    })

    provenance = {
        "dataset": args.dataset,
        "split": args.split,
        "seed": args.seed,
        "epochs": args.epochs,
        "git_commit": args.git_commit,
        "date": args.date or date.today().isoformat(),
    }
    manifest["training"].update(provenance)

    metrics = None
    if args.metrics_report:
        report = Path(args.metrics_report)
        if not report.is_file():
            raise SystemExit(f"metrics report not found: {report}")
        # Numbers must come from the report, never from the command line.
        metrics = json.loads(report.read_text(encoding="utf-8"))
        if metrics.get("valid") is not True:
            # A smoke report (random weights) or any report that did not verify its
            # checkpoint must never become citable provenance.
            raise SystemExit(
                f"refusing metrics report {report}: it is not marked valid=true "
                "(smoke run or unverified checkpoint)"
            )
        manifest["evaluation"] = {"report": str(report), "metrics": metrics}

    manifest["serving"] = {
        "enabled": bool(args.serve),
        "reason": None if args.serve else (args.hold_reason or "serving disabled by the operator"),
    }

    complete = all(provenance.get(key) not in (None, "", []) for key in REQUIRED_PROVENANCE)
    manifest["status"] = "frozen" if complete else "placeholder"
    if not complete:
        manifest["note"] = (
            "Incomplete provenance: "
            + ", ".join(key for key in REQUIRED_PROVENANCE if not provenance.get(key))
            + " missing. This checkpoint must not be cited."
        )
    else:
        manifest["note"] = "Frozen artefact. Quote evaluation numbers only from the referenced report."
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze a checkpoint into model_manifest.json")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--template", default=str(DEFAULT_OUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--split", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--date", default=None, help="ISO date of training (default: today)")
    parser.add_argument("--serve", dest="serve", action="store_true", default=True,
                        help="allow the frozen artefact to be served (default)")
    parser.add_argument("--no-serve", dest="serve", action="store_false",
                        help="freeze the artefact but hold it out of serving; "
                             "the API keeps returning 503 with --hold-reason")
    parser.add_argument("--hold-reason", default=None,
                        help="why serving is held (shown by /api/ready and /api/diagnose)")
    parser.add_argument("--metrics-report", default=None,
                        help="JSON report produced by run_evaluation_*.py --json")
    args = parser.parse_args(argv)

    manifest = build_manifest(args)
    Path(args.out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} (status={manifest['status']}, sha256={manifest['checkpoint']['sha256'][:12]}...)")
    if manifest["status"] != "frozen":
        print("WARNING: incomplete provenance -- this manifest must not be cited.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
