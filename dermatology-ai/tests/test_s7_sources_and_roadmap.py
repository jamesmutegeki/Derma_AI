"""S7 -- the data answer and the plan are both in the repository.

Two failure modes this pins:

* recommending a dataset that is actually request-gated (the PASSION trap), so
  the "immediate" list must name only sources whose access is open and whose
  licence is stated;
* a roadmap that is aspirational prose with no dates, no evidence files and no
  kill criteria -- i.e. a plan that cannot fail and therefore cannot be managed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

IMMEDIATE_SOURCES = {
    "docs/DATASET_SOURCES_IMMEDIATE.md": ("PAD-UFES-20", "DermaMNIST", "SCIN"),
    "docs/DATASET_CARD_PAD_UFES_20.md": ("CC BY 4.0", "biopsy"),
    "docs/DATASET_CARD_DERMAMNIST.md": ("CC BY-NC 4.0", "medmnist"),
}


def test_every_immediate_source_is_documented(app_dir):
    for relative, needles in IMMEDIATE_SOURCES.items():
        path = app_dir / relative
        assert path.is_file(), f"missing {relative}"
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            assert needle.lower() in text.lower(), f"{relative} does not mention {needle}"


def test_immediate_list_does_not_smuggle_in_request_gated_sources(app_dir):
    """PASSION, DDI and Fitzpatrick17k may appear, but only in the exclusion table."""
    text = (app_dir / "docs" / "DATASET_SOURCES_IMMEDIATE.md").read_text(encoding="utf-8")
    ranked = text.split("## Sources deliberately", 1)[0]
    for gated in ("PASSION", "Fitzpatrick17k"):
        # They are named in prose as the reason for this page, never in the table.
        table_rows = [line for line in ranked.splitlines()
                      if line.startswith("| **") or line.startswith("| 1 ") or line.startswith("| 2 ")]
        assert not any(gated.lower() in row.lower() for row in table_rows), gated


def test_pad_ufes_label_map_excludes_the_malignant_classes(app_dir):
    mapping = json.loads((app_dir / "scripts" / "label_maps" / "padufes20.json").read_text())
    assert mapping["mel"] == "melanoma"
    assert mapping["nev"] == "benign"
    # BCC and SCC are malignant: folding them into "benign" would be a false
    # reassurance, and ACK is pre-malignant.
    for label in ("bcc", "scc", "ack"):
        assert mapping[label] == "skip", label
    assert "kaposi_sarcoma" not in mapping.values()


def test_dermamnist_map_matches_the_ham10000_mapping(app_dir):
    maps = app_dir / "scripts" / "label_maps"
    ham = {k: v for k, v in json.loads((maps / "ham10000.json").read_text()).items()
           if not k.startswith("_")}
    derm = {k: v for k, v in json.loads((maps / "dermamnist.json").read_text()).items()
            if not k.startswith("_")}
    assert ham == derm, "the same seven classes must map the same way"


# --------------------------------------------------------------------------
# The roadmap must be manageable, not just inspiring
# --------------------------------------------------------------------------

def test_roadmap_exists_and_covers_the_whole_horizon(app_dir):
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "2026-11-03" in text
    for act in ("Act 0", "Act 1", "Act 2", "Act 3", "Act 4", "Act 5"):
        assert act in text, act
    # Twelve dated weeks, not "soon".
    weeks = re.findall(
        r"^\| \d{1,2} \| (?:\d{1,2}[–-]\d{1,2} \w{3}|\d{1,2} \w{3}[–-]\d{1,2} \w{3})",
        text, re.M)
    assert len(weeks) == 12, f"expected 12 dated weeks, found {len(weeks)}"


def test_roadmap_has_kill_criteria_and_risks(app_dir):
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert text.lower().count("kill criterion") >= 3
    assert "Risk register" in text
    assert "Sunk-cost" in text or "sunk-cost" in text


def test_roadmap_keeps_the_two_lanes_and_the_pause(app_dir):
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Lane A" in text and "Lane B" in text
    assert "serving.enabled: false" in text
    assert "Never:" in text and "scrape" in text.lower()


def test_roadmap_makes_no_unmeasured_claim(app_dir):
    """A plan may set targets; it may not assert a performance figure."""
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert not re.search(r"(accuracy|AUC|sensitivity|recall)\s*(of|:|=)?\s*0?\.\d+", text, re.I)
    assert not re.search(r"\b\d{2}(\.\d)?\s*%\s*(accuracy|AUC|sensitivity)", text, re.I)


def test_roadmap_definition_of_done_matches_the_gates(app_dir):
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    tail = text.split("## Definition of done for the *project*", 1)[1]
    assert "definition_of_done.sh" in tail
    assert "serving.enabled: false" in tail
    assert "[ ]" in tail  # an actual checklist, not a paragraph
