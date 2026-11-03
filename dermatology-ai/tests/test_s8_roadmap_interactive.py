"""S8-3 -- the roadmap is a working instrument, not a wall of prose.

The plan lives in ``docs/roadmap_data.json`` and is rendered into two artefacts by
``scripts/build_roadmap.py``: the interactive page and the task tables inside
``docs/ROADMAP.md``. This suite pins the four ways that arrangement usually rots:

* the artefacts drift from the data file, or from each other (one plan, three
  renderings, no second truth) -- ``--check`` fails on any drift;
* the page needs the network, or a CDN font, on a clinic laptop that has none;
* a task has no evidence file, no testable definition of done, or too little
  detail to start a Tuesday morning with;
* the page invents a performance figure, or forgets the two holds (Kaposi
  sarcoma paused 2026-10-31, serving disabled in code).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DATA_FILE = "docs/roadmap_data.json"
PAGE = "docs/roadmap.html"
MARKDOWN = "docs/ROADMAP.md"
BUILDER = "scripts/build_roadmap.py"
DATA_BLOCK = re.compile(
    r'<script type="application/json" id="roadmap-data">(.*?)</script>', re.S
)


def _data(app_dir) -> dict:
    return json.loads((app_dir / DATA_FILE).read_text(encoding="utf-8"))


def _page(app_dir) -> str:
    return (app_dir / PAGE).read_text(encoding="utf-8")


def _embedded(app_dir) -> dict:
    match = DATA_BLOCK.search(_page(app_dir))
    assert match, "the page must embed its data in #roadmap-data"
    return json.loads(match.group(1))


# --------------------------------------------------------------------------
# One source of truth, gated by the builder
# --------------------------------------------------------------------------

def test_the_data_file_validates(app_dir):
    result = subprocess.run(
        [sys.executable, str(app_dir / BUILDER), "--check"],
        capture_output=True, text=True, timeout=120, cwd=str(app_dir),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_page_embeds_exactly_the_data_file(app_dir):
    assert _embedded(app_dir) == _data(app_dir)


def test_markdown_task_tables_are_generated_from_the_same_data(app_dir):
    text = (app_dir / MARKDOWN).read_text(encoding="utf-8")
    plan = _data(app_dir)
    for act in plan["acts"]:
        act_id = act["id"]
        assert f"<!-- BEGIN:act-{act_id} tasks" in text, f"act {act_id} block missing"
        assert f"<!-- END:act-{act_id} tasks -->" in text
        block = text.split(f"<!-- BEGIN:act-{act_id} tasks", 1)[1]
        block = block.split(f"<!-- END:act-{act_id} tasks -->", 1)[0]
        for task in plan["tasks"]:
            if task["act"] != act_id:
                continue
            assert f"| {task['id']} | {task['title']} |" in block, task["id"]
            assert task["evidence"] in block, task["evidence"]


# --------------------------------------------------------------------------
# Offline and self-contained: a clinic laptop with no network
# --------------------------------------------------------------------------

SVG_NS = "http://www.w3.org/2000/svg"


def test_the_page_is_offline_and_self_contained(app_dir):
    html = _page(app_dir)
    # The only permitted URL-shaped string is the inert SVG namespace.
    rest = html.replace(SVG_NS, "")
    assert "http://" not in rest and "https://" not in rest, re.findall(r"https?://[^\"'\s]+", rest)
    assert "<link" not in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html and "@import" not in html
    assert re.findall(r"<img[^>]+src=\"([^\"]+)\"", html) == ["../assets/logo-mark.png"]
    assert "@media print" in html and "@page" in html


def test_it_degrades_without_javascript_or_storage(app_dir):
    html = _page(app_dir)
    assert "<noscript" in html
    assert "derma-roadmap-v2" in html
    assert html.count("try {") >= 2
    assert "localStorage" in html


def test_the_inline_script_is_syntactically_valid(app_dir, tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to syntax-check the roadmap script")
    scripts = re.findall(r"<script>(.*?)</script>", _page(app_dir), re.S)
    assert scripts, "the page lost its script"
    probe = tmp_path / "roadmap-inline.js"
    probe.write_text(scripts[-1], encoding="utf-8")
    result = subprocess.run([node, "--check", str(probe)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------
# The plan is detailed enough to run a week from
# --------------------------------------------------------------------------

def test_the_plan_is_detailed_enough_to_execute(app_dir):
    plan = _data(app_dir)
    tasks = plan["tasks"]
    assert len(tasks) >= 40, "twelve weeks need real tasks, not headlines"

    steps = sum(len(task["steps"]) for task in tasks)
    assert steps / len(tasks) >= 3, f"only {steps} steps across {len(tasks)} tasks"

    for task in tasks:
        assert len(task["steps"]) >= 3, f"{task['id']} has {len(task['steps'])} steps"
        assert task["size"] in plan["meta"]["sizes"], task["id"]
        assert len(task["risk"]) > 40, f"{task['id']} names no failure mode"
        start, end = task["weeks"]
        assert 1 <= start <= end <= plan["meta"]["weeks"], f"{task['id']}: {start}-{end}"
        assert re.search(r"[A-Za-z0-9_]+\.(json|md|py|yml|yaml|html|toml|sh)|/|§", task["evidence"]), (
            f"{task['id']} evidence {task['evidence']!r} is not a file or a document section"
        )
        assert len(task["done"]) > 20, f"{task['id']} has no testable definition of done"


def test_every_act_has_work_and_a_stated_goal(app_dir):
    plan = _data(app_dir)
    for act in plan["acts"]:
        in_act = [task for task in plan["tasks"] if task["act"] == act["id"]]
        assert len(in_act) >= 3, f"act {act['id']} has {len(in_act)} tasks"
        assert act["goal"].strip() and act["why"].strip()
    assert {task["lane"] for task in plan["tasks"]} == {"A", "B"}


def test_every_week_carries_its_own_plan(app_dir):
    plan = _data(app_dir)
    weeks = plan["weeks"]
    assert [entry["week"] for entry in weeks] == list(range(1, plan["meta"]["weeks"] + 1))
    dates = {entry["week"]: entry["dates"] for entry in plan["meta"]["weekDates"]}
    for entry in weeks:
        assert entry["dates"] == dates[entry["week"]], f"week {entry['week']} dates disagree"
        for field in ("laneA", "ethics", "study", "writing"):
            assert str(entry[field]).strip(), f"week {entry['week']} has no {field}"
        for column in entry.get("key", []):
            assert column in ("laneA", "ethics", "study", "writing")


def test_the_markdown_calendar_is_generated_from_the_same_weeks(app_dir):
    text = (app_dir / MARKDOWN).read_text(encoding="utf-8")
    assert "<!-- BEGIN:calendar (generated from docs/roadmap_data.json) -->" in text
    block = text.split("<!-- BEGIN:calendar", 1)[1].split("<!-- END:calendar -->", 1)[0]
    rows = re.findall(r"^\| (\d{1,2}) \| ", block, re.M)
    assert len(rows) == 12, f"expected 12 dated week rows, found {len(rows)}"
    for entry in _data(app_dir)["weeks"]:
        key = set(entry.get("key", []))
        cells = [
            f"**{entry[column]}**" if column in key else entry[column]
            for column in ("laneA", "ethics", "study", "writing")
        ]
        expected = f"| {entry['week']} | {entry['dates']} | " + " | ".join(cells) + " |"
        assert expected in block, f"week {entry['week']} drifted: {expected}"


def test_the_page_exposes_the_detail_it_promises(app_dir):
    html = _page(app_dir)
    # Views, the week sheet, dependency map, deep links, signals and progress export.
    for hook in ('data-view="map"', 'id="openWeek"', 'id="modalExport"', 'id="modalImport"',
                 '"w=" + n', '"t=" + id', "chainOf", "weekMarkdown",
                 'data-scope="overdue"', 'data-scope="slack"', 'data-scope="gate"',
                 'id="nextUp"', 'id="acts"', 'id="milestones"', "noSlack", "firstOpenStep"):
        assert hook in html, f"the page is missing {hook}"
    assert "derma-roadmap-v2" in html


def test_milestones_are_dated_and_inside_the_horizon(app_dir):
    plan = _data(app_dir)
    milestones = plan["meta"]["milestones"]
    assert len(milestones) >= 4, "a twelve-week plan needs its hard dates marked"
    dates = {entry["week"]: entry["dates"] for entry in plan["meta"]["weekDates"]}
    for milestone in milestones:
        assert 1 <= milestone["week"] <= plan["meta"]["weeks"]
        assert milestone["date"] == dates[milestone["week"]], milestone
        assert milestone["label"].strip()
    # The two cutoffs this project actually turns on.
    labels = " ".join(m["label"] for m in milestones).lower()
    assert "14 dec" in labels and "demo" in labels


def test_the_plan_cannot_contradict_itself(app_dir):
    """A dependency may not finish after the thing that depends on it starts."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_roadmap", app_dir / "scripts" / "build_roadmap.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    plan = _data(app_dir)
    builder.validate(plan)  # the committed plan is consistent

    broken = json.loads(json.dumps(plan))
    task = next(t for t in broken["tasks"] if t["id"] == "1.4")
    task["weeks"] = [2, 2]  # starts before dependency 1.3 (W2-3) is finished
    with pytest.raises(SystemExit) as error:
        builder.validate(broken)
    assert "1.4" in str(error.value) and "contradicts itself" in str(error.value)


def test_dependencies_scenarios_and_gates_all_resolve(app_dir):
    plan = _data(app_dir)
    ids = {task["id"] for task in plan["tasks"]}
    gates = {gate["id"] for gate in plan["gates"]}

    for task in plan["tasks"]:
        for dep in task["depends"]:
            assert dep in ids, f"{task['id']} depends on unknown {dep}"
            assert dep != task["id"]
        if task["gate"]:
            assert task["gate"] in gates, f"{task['id']} cites unknown gate {task['gate']}"

    for scenario in plan["scenarios"]:
        assert scenario["impact"], f"scenario {scenario['id']} parks nothing"
        for task_id in scenario["impact"]:
            assert task_id in ids, f"scenario {scenario['id']} parks unknown {task_id}"
        assert scenario["mitigation"].strip(), "a scenario must say what you do instead"


def test_the_two_holds_and_the_kill_criteria_are_on_the_page(app_dir):
    plan = _data(app_dir)
    html = _page(app_dir)
    assert "gate 1A, 2026-10-31" in html
    assert "serving" in html.lower()
    assert "--allow-untrained-classes" not in html
    assert len(plan["kill"]) >= 5
    for criterion in plan["kill"]:
        assert criterion["when"] in html and criterion["then"] in html


def test_no_performance_figures_and_unmeasured_wording(app_dir):
    html = _page(app_dir)
    assert not re.search(
        r"(accuracy|AUC|AUROC|sensitivity|specificity|recall|F1)\s*(of|:|=|is|was)?\s*0?\.\d+",
        html, re.I,
    )
    assert "not yet measured" in html.lower()
    assert "Not a medical device" in html
    assert "self-reported" in html.lower() or "this browser" in html.lower()


def test_markdown_and_page_agree_on_the_acts(app_dir):
    plan = _data(app_dir)
    text = (app_dir / MARKDOWN).read_text(encoding="utf-8")
    assert "roadmap.html" in text and "roadmap_wallchart.html" in text
    for act in plan["acts"]:
        assert f"## Act {act['id']} " in text, f"Act {act['id']} missing from ROADMAP.md"
