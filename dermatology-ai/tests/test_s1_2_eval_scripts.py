"""S1-2 -- the evaluation scripts actually run.

Acceptance criteria
-------------------
1. ``run_evaluation_ham.py`` and ``run_evaluation_passion.py`` execute end-to-end
   (``--smoke``) and write a JSON report.  The old scripts died on an undefined
   ``Subset`` and on imports of a ``dermatology_ai`` package that does not exist.
2. Both use the shared preprocessing pipeline from ``transforms`` (no private
   ``A.Normalize`` / ``ToTensorV2`` recipe that can drift from training).
3. A smoke report is explicitly ``valid: false`` / ``smoke: true``, and
   ``freeze_model.py`` refuses to freeze it.
4. Neither script can claim results without a verified checkpoint.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

REPO_ROOT = None


@pytest.fixture(scope="module")
def repo_root(app_dir):
    return app_dir.parent


@pytest.fixture(scope="module")
def smoke_ham(tmp_path_factory, repo_root):
    out = tmp_path_factory.mktemp("ham")
    data = out / "data"
    report = out / "report.json"
    result = subprocess.run(
        [sys.executable, str(repo_root / "run_evaluation_ham.py"),
         "--smoke", "--data-dir", str(data), "--json", str(report)],
        capture_output=True, text=True, timeout=900,
    )
    return result, report


@pytest.fixture(scope="module")
def smoke_passion(tmp_path_factory, repo_root):
    out = tmp_path_factory.mktemp("passion")
    data = out / "data"
    report = out / "report.json"
    result = subprocess.run(
        [sys.executable, str(repo_root / "run_evaluation_passion.py"),
         "--smoke", "--data-dir", str(data), "--json", str(report)],
        capture_output=True, text=True, timeout=900,
    )
    return result, report


def test_ham_script_runs_and_reports(smoke_ham):
    result, report = smoke_ham
    assert result.returncode == 0, result.stderr[-2000:]
    assert "Overall accuracy" in result.stdout
    assert report.is_file()

    payload = json.loads(report.read_text())
    assert payload["dataset"] == "HAM10000"
    assert payload["smoke"] is True
    assert payload["valid"] is False, "random weights must never produce a citable report"
    assert payload["checkpoint"]["weights"] == "random"
    assert payload["metrics"]["n"] > 0
    assert "confusion_matrix" in payload["metrics"]


def test_passion_script_runs_and_reports(smoke_passion):
    result, report = smoke_passion
    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(report.read_text())
    assert payload["dataset"] == "PASSION"
    assert payload["valid"] is False
    assert payload["metrics"]["n"] > 0


def test_smoke_report_cannot_be_frozen(tmp_path, app_dir, smoke_ham):
    _result, report = smoke_ham
    checkpoint = tmp_path / "weights.pt"
    checkpoint.write_bytes(b"weights")
    result = subprocess.run(
        [sys.executable, str(app_dir / "scripts" / "freeze_model.py"),
         "--checkpoint", str(checkpoint), "--out", str(tmp_path / "m.json"),
         "--metrics-report", str(report)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "valid=true" in result.stderr


def test_scripts_use_the_shared_pipeline(repo_root):
    for name in ("run_evaluation_ham.py", "run_evaluation_passion.py"):
        source = (repo_root / name).read_text(encoding="utf-8")
        assert "build_transform" in source, f"{name} does not use transforms.build_transform"
        assert "A.Normalize(" not in source, f"{name} still normalises by hand"
        assert "ToTensorV2" not in source, f"{name} still builds its own tensor step"
        # The docstring may mention the old broken import; the code must not use it.
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith(("#", "\"\"\"", "* ")))
        assert "import dermatology_ai" not in code.replace("from dermatology_ai", "import dermatology_ai"), \
            f"{name} imports a package that does not exist"


def test_scripts_refuse_to_run_without_a_checkpoint(tmp_path, repo_root):
    result = subprocess.run(
        [sys.executable, str(repo_root / "run_evaluation_ham.py"),
         "--data-dir", str(tmp_path)], capture_output=True, text=True, timeout=300,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Checkpoint not found" in combined or "no val_meta.csv" in combined


def test_subset_is_imported(repo_root):
    source = (repo_root / "run_evaluation_ham.py").read_text(encoding="utf-8")
    assert "from torch.utils.data import DataLoader, Subset" in source
