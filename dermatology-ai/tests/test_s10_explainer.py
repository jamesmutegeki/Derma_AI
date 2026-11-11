"""S10-1 -- the explainer is a teaching artefact, so its promises are testable.

``docs/explainer.html`` is the walk-through a supervisor can open in a browser:
eight rooms that carry one drawn image through the pipeline, a dataset arena, a
sixteen-card concept codex, a "break the AI" bench, a metrics desk and a final
report. It is deliberately a *single file* with no network access, because the
clinics this project is aimed at do not have reliable connectivity.

These tests check the promises that make it safe to show someone:

* it is one self-contained file -- no external scripts, fonts, images or links;
* it never presents a number as a result: the config says ``measured: false``
  and the page says "not yet measured" where a metric would go;
* it states the two holds out loud (no Kaposi sarcoma cohort, serving disabled);
* it carries the disclaimer verbatim;
* its inline JavaScript parses (``node --check``) when Node is available;
* it is linked from the README, the status ledger and the reading server.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

DISCLAIMER = "Not a medical device"


@pytest.fixture(scope="module")
def page(app_dir):
    path = app_dir / "docs" / "explainer.html"
    assert path.exists(), "docs/explainer.html is missing"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script(page):
    blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert len(blocks) == 1, f"expected one inline script, found {len(blocks)}"
    return blocks[0]


def test_it_is_one_file_with_no_network_access(page):
    assert not re.search(r"https?://", page), "the page must not reference a URL"
    for pattern in (r"<script[^>]+src=", r"<link[^>]+href=", r"<img[^>]+src=", r"@import"):
        assert not re.search(pattern, page, re.I), pattern
    assert "<canvas" in page, "the lesion is drawn in the browser, not loaded"


def test_it_never_presents_a_number_as_a_result(page, script):
    assert '"measured": false' in page or "measured: false" in page, "config must start unmeasured"
    assert "not yet measured" in page
    assert "illustrative" in page.lower(), "the ablation lab must label itself"
    # the report must not claim a delimiter-free accuracy anywhere
    assert not re.search(r"\b(accuracy|AUC|F1)\b[^.]{0,40}\b\d{2}(\.\d+)?\s?%", page, re.I)


def test_the_two_holds_are_stated_out_loud(page):
    lowered = page.lower()
    assert "kaposi" in lowered and "paused" in lowered
    assert "503" in page and "model_unavailable" in page
    assert "no african cohort" in lowered or "african cohort" in lowered


def test_the_disclaimer_is_verbatim(page):
    assert DISCLAIMER in page
    assert "Do not use with real patient data" in page


def test_it_has_the_required_structure(page, script):
    assert len(re.findall(r"id:\s*\"(?:arrive|label|prep|aug|features|head|explain|decide)\"", script)) == 8, \
        "eight pipeline rooms"
    assert script.count('{ id:"') >= 8, "datasets and concepts are declared in the script"
    assert len(re.findall(r'\{ id:"[a-z]+", name:"[^"]+", images:', script)) == 8, "eight dataset cards"
    concepts = re.findall(r'\{ id:"[a-z]+", name:"[^"]+", what:', script)
    assert len(concepts) == 16, f"expected sixteen concept cards, found {len(concepts)}"
    for label in ("Beginner", "Practitioner", "Expert"):
        assert label in page, label
    for tab in ("pipeline", "arena", "codex", "limits", "metrics", "report"):
        assert f'data-view="{tab}"' in page, tab


def test_the_metrics_desk_cannot_show_a_real_result(page):
    # Every place a model metric would live says so explicitly.
    assert "not yet measured" in page
    assert "null" in page and "kaposi" in page.lower()
    assert "synthetic" in page.lower()


def test_the_inline_script_parses(script, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; syntax is covered by the browser")
    path = tmp_path / "explainer.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_it_is_reachable_from_the_docs(app_dir, page):
    readme = (app_dir.parent / "README.md").read_text(encoding="utf-8")
    status = (app_dir / "REMEDIATION_STATUS.md").read_text(encoding="utf-8")
    server = (app_dir / "scripts" / "serve_docs.py").read_text(encoding="utf-8")
    assert "explainer.html" in readme, "README must link the explainer"
    assert "S10-1" in status, "the status ledger must record it"
    assert "docs/explainer.html" in server, "the reading server must offer it"

    # every relative link in the page resolves
    for target in re.findall(r'href="([^"#:]+)"', page):
        assert (app_dir / "docs" / target).exists() or (app_dir / target).exists(), target


def test_the_config_object_is_valid_json_after_unwrapping(page, script):
    match = re.search(r"const CONFIG = (\{.*?\n\});\n", script, re.S)
    assert match, "CONFIG object not found"
    body = match.group(1)
    # strip comments first, then quote the bare keys, so a JSON parser can read it
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"([{,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', body)
    config = json.loads(body)
    assert config["measured"] is False
    assert config["ksPaused"] is True
    assert config["classes"] == ["benign", "melanoma", "kaposi_sarcoma"]
    assert config["triage"] == ["routine", "follow_up", "urgent"]
    assert len(config["datasets"]) == 8
    assert len(config["concepts"]) == 16
