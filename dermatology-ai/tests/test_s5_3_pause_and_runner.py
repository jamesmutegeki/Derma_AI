"""S5-3 -- the pause is documented, and the T4 runner cannot lie.

Two things are easy to get wrong here:

* a decision that lives only in a chat message, so the next person "just trains
  it and serves it";
* a one-command runner that quietly produces something servable from a partial
  download.

So: the decision must be in the repository, the runner must refuse a partial
corpus, and the runner must never pass `--serve`.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def test_the_pause_is_recorded_in_the_training_procedure(app_dir):
    text = (app_dir / "docs" / "TRAINING.md").read_text(encoding="utf-8")
    assert "PAUSED" in text
    assert "2026-10-31" in text
    assert "kaposi" in text.lower()
    head = text.split("## 2c.", 1)[0].lower()
    assert "serving" in head and "503" in head


def test_the_status_document_shows_the_pause(app_dir):
    text = (app_dir / "REMEDIATION_STATUS.md").read_text(encoding="utf-8")
    gates = text.split("## Gate before real patient data", 1)[1]
    assert "paused 2026-10-31" in gates.lower()
    decisions = text.split("## Scope decisions", 1)[1]
    assert "Kaposi sarcoma cohort" in decisions
    assert "serving.enabled = false" in decisions


def test_the_shipped_manifest_is_not_servable(app_dir):
    import json

    manifest = json.loads((app_dir / "model_manifest.json").read_text())
    assert manifest["status"] == "placeholder"
    assert manifest["serving"]["enabled"] is False
    assert "paused" in manifest["serving"]["reason"].lower()


def test_runner_is_valid_shell_and_checks_its_corpus(app_dir):
    runner = app_dir / "scripts" / "train_on_t4.sh"
    subprocess.run(["bash", "-n", str(runner)], check=True)
    text = runner.read_text(encoding="utf-8")
    # A partial download must stop the run, not silently train on 40 images.
    assert "refusing to continue" in text
    assert re.search(r"IMAGE_COUNT.*-lt\s+\d{4}", text), "no minimum image count"
    assert "fewer than 8000 converted rows" in text


def test_runner_never_enables_serving(app_dir):
    text = (app_dir / "scripts" / "train_on_t4.sh").read_text(encoding="utf-8")
    # Any line that is part of a command (continuation lines end with a
    # backslash) must not turn serving on.
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            assert "--serve" not in line, f"runner enables serving: {line!r}"
    assert "--hold-reason" in text
    assert "--allow-untrained-classes" in text
    assert "not pass --serve" in text, "the runner must warn against it in words too"


def test_runner_check_mode_works_and_claims_nothing(app_dir):
    result = subprocess.run(
        ["bash", str(app_dir / "scripts" / "train_on_t4.sh"), "--check"],
        capture_output=True, text=True, timeout=300,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp",
             "PYTHON": "python3"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = (result.stdout + result.stderr).lower()
    assert "check only" in output
    assert "held" in output
    # It must not download, train, or touch the network in check mode.
    assert "fetching" not in output
    assert "==> train" not in output


def test_runner_output_is_ignored_by_git(app_dir):
    for relative in ("dermatology-ai/runs/x/report.json",
                     "dermatology-ai/datasets/ham10000/metadata.csv"):
        completed = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=app_dir.parent, capture_output=True, text=True,
        )
        assert completed.returncode == 0, f"{relative} would be committed"
