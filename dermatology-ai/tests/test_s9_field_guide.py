"""S9 -- the project explains itself, in plain words, offline.

The field guide is the artefact you hand to somebody who is not going to read a
model card: a supervisor, a clinician, a relative at dinner. It fails this suite
if it drifts into any of the four usual traps:

* it needs the network (it must open from a USB stick in a clinic);
* it quotes a performance number, or lets an illustration masquerade as a
  measurement;
* it forgets the two holds (Kaposi sarcoma paused, serving disabled) or the
  missing African cohort;
* it links to files that do not exist, so the reader hits a dead end.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

GUIDE = "docs/field-guide.html"
ROOMS = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "glossary"]
SVG_NS = "http://www.w3.org/2000/svg"


def _guide(app_dir) -> str:
    path = app_dir / GUIDE
    assert path.is_file(), f"missing {GUIDE}"
    return path.read_text(encoding="utf-8")


def test_the_guide_is_offline_and_self_contained(app_dir):
    html = _guide(app_dir)
    rest = html.replace(SVG_NS, "")
    assert "http://" not in rest and "https://" not in rest, re.findall(r"https?://[^\"'\s]+", rest)
    assert "<link" not in html and "@import" not in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html
    # One image: none at all. Everything is drawn in SVG or CSS.
    assert not re.search(r"<img\b", html)
    assert "@media print" in html


def test_every_room_is_present(app_dir):
    html = _guide(app_dir)
    for room in ROOMS:
        assert f'id="{room}"' in html, f"room {room} missing"
    assert html.count('class="room"') >= 7
    assert html.count('class="toy"') == 7, "seven rooms, seven toys"


def test_the_toys_announce_themselves_as_demonstrations(app_dir):
    html = _guide(app_dir)
    assert html.count('class="demo"') == 7
    # The interval toy is arithmetic, and says so; nothing reads as a result.
    assert "not a measurement" in html
    assert "arithmetic, not a result" in html
    assert html.count('aria-live="polite"') >= 3


def test_no_performance_figures_anywhere(app_dir):
    html = _guide(app_dir)
    assert not re.search(
        r"(accuracy|AUC|AUROC|sensitivity|specificity|recall|F1)\s*(of|:|=|is|was)?\s*0?\.\d+",
        html, re.I,
    )
    assert "not yet measured" in html.lower()
    # Toy 1 shows the diagnostic claim this project refuses to make, with no number attached.
    assert "never says this" in html
    assert "carries no number at all" in html


def test_both_holds_and_the_missing_cohort_are_stated(app_dir):
    html = _guide(app_dir)
    assert "gate 1A, 2026-10-31" in html
    assert "paused" in html.lower()
    assert "serving" in html.lower()
    assert "--allow-untrained-classes" not in html
    assert "No African cohort" in html
    assert "Brazilian" in html
    assert "scrap" in html.lower()  # scraping KS images is named as forbidden


def test_the_disclaimer_is_verbatim(app_dir):
    html = _guide(app_dir)
    assert (
        "Research prototype · Not a medical device · No Business Associate Agreement (BAA) · "
        "Do not use with real patient data."
    ) in html


def test_the_real_dataset_counts_are_the_published_ones(app_dir):
    html = _guide(app_dir)
    for count in ("845", "730", "244", "235", "192", "52"):
        assert count in html, f"published count {count} missing"
    assert "PAD-UFES-20" in html and "CC BY 4.0" in html
    assert "2,298" in html


def test_the_glossary_defines_fourteen_concepts(app_dir):
    html = _guide(app_dir)
    # The glossary is built from a JS array, so check the authored entries.
    entries = re.findall(r'\{\s*term: "([^"]+)"', html)
    assert len(entries) >= 14, f"only {len(entries)} glossary terms"
    assert len(set(entries)) == len(entries), "duplicate glossary term"
    for name in ("Triage ordering", "Leakage", "Grouped split", "Calibration",
                 "Grad-CAM", "Confidence interval", "Frozen artefact"):
        assert name in entries, f"missing concept: {name}"
    # Every term carries a plain-language gloss and a reason to care.
    assert len(re.findall(r'\bshort: "', html)) >= len(entries)
    assert len(re.findall(r'\bwhy: "', html)) >= len(entries)
    assert "Why it matters: " in html


def test_every_link_resolves_to_a_real_file(app_dir):
    html = _guide(app_dir)
    hrefs = re.findall(r'href="([^"#][^"]*)"', html)
    local = [h for h in hrefs if not h.startswith(("http", "mailto:")) and not h.startswith("#")]
    assert local, "the guide should point at the deeper artefacts"
    for href in sorted(set(local)):
        target = (app_dir / "docs" / href).resolve()
        assert target.exists(), f"{href} does not resolve ({target})"
    # The links a reader actually needs.
    for expected in ("./roadmap.html", "./ROADMAP.md", "./GATE_OPTIONS.md", "../MODEL_CARD.md"):
        assert expected in html, f"missing link to {expected}"


def test_the_inline_script_parses(app_dir, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to syntax-check the field guide script")
    scripts = re.findall(r"<script>(.*?)</script>", _guide(app_dir), re.S)
    assert scripts, "the guide lost its script"
    probe = tmp_path / "field-guide.js"
    probe.write_text(scripts[-1], encoding="utf-8")
    result = subprocess.run([node, "--check", str(probe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_the_guide_is_linked_from_the_repositories(app_dir):
    readme = (app_dir.parent / "README.md").read_text(encoding="utf-8")
    assert "field-guide.html" in readme
    status = (app_dir / "REMEDIATION_STATUS.md").read_text(encoding="utf-8")
    assert "field-guide.html" in status
