"""S1-4 -- the documentation says what is true.

Acceptance criteria
-------------------
1. The DDI dataset is described correctly everywhere (656 images / 570 patients,
   DOI 10.71718/kqee-3z39), not as "12k images, 30+ classes".
2. No document quotes a result that no script produced (no 84.3 %, no "<3 % gap",
   no 12 % override rate).
3. The README keeps the research/education disclaimer and tells the reader what
   is available, what is missing and what is broken.
4. No document points at a file that does not exist (the old ``AGENTS.md`` link).
5. Provenance files exist: ``LICENSE``, ``CITATION.cff``, ``MODEL_CARD.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FABRICATED = re.compile(r"84\.3|0\.843|0\.027|<3\s*%\s*(gap|accuracy)|12\s*%\s*override", re.I)


@pytest.fixture(scope="module")
def repo_root(app_dir):
    return app_dir.parent


def _docs(repo_root: Path) -> list[Path]:
    files = [repo_root / "README.md"]
    files += sorted((repo_root / "docs").rglob("*.md"))
    files += sorted((repo_root / "docs").rglob("*.tex"))
    files += [repo_root / "dermatology-ai" / name
              for name in ("MODEL_CARD.md", "SECURITY.md", "REMEDIATION_STATUS.md")]
    return [path for path in files if path.is_file()]


def test_ddi_is_described_correctly(repo_root):
    offenders = []
    for path in _docs(repo_root):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            low = line.lower()
            if "ddi" in low and ("12k" in low or "12 k" in low or "30+" in low):
                offenders.append(f"{path.name}: {line.strip()[:120]}")
    assert not offenders, "DDI is still mis-described:\n" + "\n".join(offenders)

    explained = (repo_root / "docs" / "Project_Explained.md").read_text(encoding="utf-8")
    assert "656" in explained and "570" in explained
    assert "10.71718/kqee-3z39" in explained


def test_no_document_quotes_a_fabricated_result(repo_root):
    offenders = []
    for path in _docs(repo_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in FABRICATED.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line}: {match.group(0)}")
    assert not offenders, "fabricated figures still quoted:\n" + "\n".join(offenders)


def test_readme_keeps_the_disclaimer_and_reports_status(repo_root):
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    lowered = readme.lower().replace("**", "").replace("*", "")
    assert "not a medical device" in lowered
    assert "research and educational purposes only" in lowered
    assert "## status" in lowered or "## project status" in lowered
    for word in ("available", "missing", "broken"):
        assert word in lowered, f"README must report what is {word}"


def test_readme_does_not_reference_missing_files(repo_root):
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"`([A-Za-z0-9_./-]+\.(?:md|py|json|ya?ml))`", readme))
    missing = [
        name for name in referenced
        if "/" in name and not (repo_root / name).exists()
    ]
    assert not missing, f"README references files that do not exist: {missing}"
    assert "AGENTS.md" not in readme or (repo_root / "AGENTS.md").exists()


def test_provenance_files_exist(repo_root, app_dir):
    assert (repo_root / "LICENSE").is_file() or (app_dir / "LICENSE").is_file()
    assert (repo_root / "CITATION.cff").is_file() or (app_dir / "CITATION.cff").is_file()
    assert (app_dir / "MODEL_CARD.md").is_file()


def test_no_debug_prints_or_windows_paths(repo_root, app_dir):
    offenders = []
    for path in list(repo_root.glob("*.py")) + list(app_dir.rglob("*.py")):
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "[DEBUG]" in text:
            offenders.append(f"{path.name}: [DEBUG] print")
        if re.search(r"D:\\\\|D:/", text):
            offenders.append(f"{path.name}: Windows absolute path")
    assert not offenders, "\n".join(offenders)


def test_notebook_documents_the_repo_relative_path(repo_root):
    notebook = (repo_root / "dermatology-ai" / "notebooks" / "01_train_cbm.py").read_text(encoding="utf-8")
    assert "D:\\" not in notebook
    assert "APP_DIR" in notebook or "Path(__file__)" in notebook
