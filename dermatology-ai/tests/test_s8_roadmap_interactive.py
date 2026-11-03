"""S8-3 -- the roadmap is a working instrument, not a wall of prose.

The interactive page is the planning artefact a supervisor can open, filter,
stress-test and print. It fails this suite if it drifts into any of the four
usual failure modes:

* it needs the network (a clinic laptop in Kampala may have none), or pulls a
  font/CDN instead of shipping everything inline;
* its data model stops matching the markdown roadmap (two truths, no truth), or
  references a task/dependency that does not exist;
* it invents a performance number instead of writing "not yet measured";
* it forgets the two holds -- Kaposi sarcoma paused 2026-10-31 and serving
  disabled in code -- so the page reads like permission to ship a model.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

ROADMAP_HTML = "docs/roadmap.html"
DATA_BLOCK = re.compile(
    r'<script type="application/json" id="roadmap-data">(.*?)</script>', re.S
)


def _html(app_dir) -> str:
    path = app_dir / ROADMAP_HTML
    assert path.is_file(), f"missing {ROADMAP_HTML}"
    return path.read_text(encoding="utf-8")


def _data(app_dir) -> dict:
    match = DATA_BLOCK.search(_html(app_dir))
    assert match, "roadmap.html must carry the data model in #roadmap-data"
    return json.loads(match.group(1))


def _tasks(app_dir) -> list[dict]:
    return _data(app_dir)["tasks"]


# --------------------------------------------------------------------------
# Offline, self-contained, print-safe
# --------------------------------------------------------------------------

def test_interactive_roadmap_is_self_contained(app_dir):
    html = _html(app_dir)
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html, "no external stylesheets"
    # The only image is the local mark.
    assert re.findall(r"<img[^>]+src=\"([^\"]+)\"", html) == ["../assets/logo-mark.png"]
    assert "@media print" in html
    assert "@page" in html


def test_interactive_roadmap_degrades_without_javascript_or_storage(app_dir):
    html = _html(app_dir)
    # localStorage is a convenience; a sandboxed iframe or private mode must not
    # leave the page blank, so every access is guarded.
    assert "localStorage" in html
    assert "derma-roadmap-v1" in html
    storage_reads = [line for line in html.splitlines() if "localStorage" in line]
    assert storage_reads
    assert html.count("try {") >= 2
    assert "<noscript" in html


# --------------------------------------------------------------------------
# The data model: complete, unique, internally resolved
# --------------------------------------------------------------------------

def test_data_model_parses_and_ids_are_unique(app_dir):
    data = _data(app_dir)
    assert set(data) >= {"meta", "acts", "gates", "kill", "scenarios", "tasks"}
    assert data["meta"]["weeks"] == 12
    assert data["meta"]["start"] == "2026-11-03"
    assert data["meta"]["end"] == "2027-01-26"

    ids = [task["id"] for task in data["tasks"]]
    assert len(ids) == len(set(ids)), "duplicate task id"


def test_plan_is_detailed_enough_to_run_a_week(app_dir):
    data = _data(app_dir)
    tasks = data["tasks"]
    assert len(tasks) >= 40, "the twelve weeks need real tasks, not headlines"
    for act in data["acts"]:
        in_act = [task for task in tasks if task["act"] == act["id"]]
        assert len(in_act) >= 3, f"act {act['id']} has {len(in_act)} tasks"
    lanes = {task["lane"] for task in tasks}
    assert lanes == {"A", "B"}, "the two lanes are the whole point"
    for task in tasks:
        start, end = task["weeks"]
        assert 1 <= start <= end <= 12, f"{task['id']} spans {start}-{end}"


def test_every_task_names_an_evidence_file_and_a_done_test(app_dir):
    for task in _tasks(app_dir):
        assert task["title"].strip(), f"{task['id']} has no title"
        assert re.search(
            r"[A-Za-z0-9_]+\.(json|md|py|yml|yaml|html|toml|sh)|\/|§", task["evidence"]
        ), (
            f"{task['id']} evidence {task['evidence']!r} is not a file or document section"
        )
        assert len(task["done"]) > 20, f"{task['id']} has no testable definition of done"


def test_dependencies_and_scenario_impacts_all_resolve(app_dir):
    data = _data(app_dir)
    ids = {task["id"] for task in data["tasks"]}
    gate_ids = {gate["id"] for gate in data["gates"]}
    act_ids = {act["id"] for act in data["acts"]}

    for task in data["tasks"]:
        for dep in task["depends"]:
            assert dep in ids, f"{task['id']} depends on unknown {dep}"
            assert dep != task["id"]
        if task.get("gate"):
            assert task["gate"] in gate_ids, f"{task['id']} cites unknown gate {task['gate']}"
        assert task["act"] in act_ids

    for scenario in data["scenarios"]:
        assert scenario["impact"], f"scenario {scenario['id']} parks nothing"
        for task_id in scenario["impact"]:
            assert task_id in ids, f"scenario {scenario['id']} parks unknown {task_id}"
        assert scenario["effect"].strip()


def test_gates_kill_criteria_and_the_two_holds_are_on_the_page(app_dir):
    data = _data(app_dir)
    assert len(data["gates"]) >= 4
    assert len(data["kill"]) >= 5, "a plan with no kill criteria cannot fail"

    html = _html(app_dir)
    assert "paused 2026-10-31" in html or "2026-10-31" in html
    assert "gate 1A" in html or "Gate 1A" in html
    assert "Lane A" in html and "Lane B" in html
    for criterion in data["kill"]:
        assert criterion["when"] in html and criterion["then"] in html


# --------------------------------------------------------------------------
# Honesty: no figures, disclaimer intact, progress is self-reported
# --------------------------------------------------------------------------

def test_no_performance_figures_and_until_measured_wording(app_dir):
    html = _html(app_dir)
    assert not re.search(
        r"(accuracy|AUC|AUROC|sensitivity|specificity|recall|F1)\s*(of|:|=|is|was)?\s*0?\.\d+",
        html,
        re.I,
    )
    assert "not yet measured" in html.lower()
    assert "Not a medical device" in html


def test_serving_hold_and_ks_pause_are_stated(app_dir):
    html = _html(app_dir)
    assert "serving" in html.lower()
    assert "Kaposi" in html
    # Committed procedures must never carry the untrained-class escape hatch.
    assert "--allow-untrained-classes" not in html


def test_progress_widget_is_self_reported(app_dir):
    html = _html(app_dir)
    assert "self-reported" in html.lower() or "this browser" in html.lower()


# --------------------------------------------------------------------------
# The script itself parses, and the markdown roadmap points here
# --------------------------------------------------------------------------

def test_inline_script_is_syntactically_valid(app_dir, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to syntax-check the roadmap script")
    scripts = re.findall(r"<script>(.*?)</script>", _html(app_dir), re.S)
    assert scripts, "roadmap.html lost its script"
    probe = tmp_path / "roadmap-inline.js"
    probe.write_text(scripts[-1], encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(probe)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_markdown_roadmap_links_the_interactive_version(app_dir):
    text = (app_dir / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "roadmap.html" in text
    assert "roadmap_wallchart.html" in text
    # Act headings in the markdown and act ids in the data model stay in step.
    for act in _data(app_dir)["acts"]:
        assert f"## Act {act['id']} " in text, f"Act {act['id']} missing from ROADMAP.md"
