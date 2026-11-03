#!/usr/bin/env python3
"""Build the roadmap artefacts from one data file.

``docs/roadmap_data.json`` is the single source of truth for the twelve-week
plan. This script renders two things from it:

* ``docs/roadmap.html``  -- the interactive page (JSON inlined, no network calls)
* the task tables inside ``docs/ROADMAP.md`` -- between ``BEGIN``/``END``
  markers, so the markdown and the page can never drift apart

Run it after editing the data file::

    python scripts/build_roadmap.py            # write the artefacts
    python scripts/build_roadmap.py --check    # fail if they are out of date

``--check`` is what the test suite runs, so a hand-edited task table and a
stale page are both caught in CI rather than in a viva.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "docs" / "roadmap_data.json"
TEMPLATE_PATH = ROOT / "docs" / "roadmap_template.html"
PAGE_PATH = ROOT / "docs" / "roadmap.html"
MARKDOWN_PATH = ROOT / "docs" / "ROADMAP.md"

PLACEHOLDER = "<!--ROADMAP_DATA-->"
TABLE_HEADER = "| # | Deliverable | Evidence file | Done when |\n| --- | --- | --- | --- |\n"


def begin(act_id: str) -> str:
    return f"<!-- BEGIN:act-{act_id} tasks (generated from docs/roadmap_data.json) -->"


def end(act_id: str) -> str:
    return f"<!-- END:act-{act_id} tasks -->"


class PlanError(SystemExit):
    pass


def validate(plan: dict) -> None:
    """Everything the page assumes must be true here first."""
    problems: list[str] = []
    meta = plan.get("meta", {})
    for field in ("title", "owner", "start", "end", "updated", "weeks"):
        if field not in meta:
            problems.append(f"meta.{field} missing")

    weeks = int(meta.get("weeks", 0))
    week_dates = {int(w["week"]) for w in meta.get("weekDates", [])}
    if week_dates != set(range(1, weeks + 1)):
        problems.append("meta.weekDates must cover every week exactly once")

    acts = {str(act["id"]) for act in plan.get("acts", [])}
    gates = {gate["id"] for gate in plan.get("gates", [])}
    tasks = plan.get("tasks", [])
    ids = [task["id"] for task in tasks]

    if len(ids) != len(set(ids)):
        problems.append("task ids are not unique")
    if len(tasks) < 40:
        problems.append(f"only {len(tasks)} tasks: a twelve-week plan needs real work in it")

    for task in tasks:
        tid = task.get("id", "?")
        if str(task.get("act")) not in acts:
            problems.append(f"{tid}: unknown act {task.get('act')!r}")
        if task.get("lane") not in ("A", "B"):
            problems.append(f"{tid}: lane must be A or B")
        start, finish = task.get("weeks", (0, 0))
        if not (1 <= start <= finish <= weeks):
            problems.append(f"{tid}: weeks {start}-{finish} outside 1..{weeks}")
        if len(task.get("steps", [])) < 3:
            problems.append(f"{tid}: fewer than three steps")
        for field in ("title", "evidence", "done", "risk", "size"):
            if not str(task.get(field, "")).strip():
                problems.append(f"{tid}: {field} is empty")
        if task.get("size") not in meta.get("sizes", {}):
            problems.append(f"{tid}: size {task.get('size')!r} not in meta.sizes")
        if task.get("gate") and task["gate"] not in gates:
            problems.append(f"{tid}: unknown gate {task['gate']}")

    for task in tasks:
        for dep in task.get("depends", []):
            if dep not in ids:
                problems.append(f"{task['id']}: depends on unknown task {dep}")

    for scenario in plan.get("scenarios", []):
        if not scenario.get("impact"):
            problems.append(f"scenario {scenario.get('id')} parks nothing")
        for tid in scenario.get("impact", []):
            if tid not in ids:
                problems.append(f"scenario {scenario.get('id')} parks unknown task {tid}")
        for field in ("label", "effect", "mitigation"):
            if not str(scenario.get(field, "")).strip():
                problems.append(f"scenario {scenario.get('id')}: {field} is empty")

    for criterion in plan.get("kill", []):
        if not criterion.get("when") or not criterion.get("then"):
            problems.append(f"kill criterion {criterion.get('id')} is incomplete")

    if problems:
        raise PlanError("roadmap_data.json does not validate:\n  - " + "\n  - ".join(problems))


def inline_json(plan: dict) -> str:
    """JSON that is safe inside a <script> block and byte-stable between builds."""
    text = json.dumps(plan, indent=2, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace("&", "\\u0026")


def render_page(plan: dict, template: str) -> str:
    if PLACEHOLDER not in template:
        raise PlanError(f"template is missing the {PLACEHOLDER} placeholder")
    return template.replace(PLACEHOLDER, inline_json(plan), 1)


def table_rows(plan: dict, act_id: str) -> str:
    rows = []
    for task in plan["tasks"]:
        if str(task["act"]) != str(act_id):
            continue
        cells = [
            task["id"],
            task["title"].replace("|", "\\|"),
            f"`{task['evidence']}`",
            task["done"].replace("|", "\\|"),
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def generated_block(plan: dict, act_id: str) -> str:
    return "\n".join([
        begin(act_id),
        TABLE_HEADER.rstrip("\n"),
        table_rows(plan, act_id),
        end(act_id),
    ])


def update_markdown(text: str, plan: dict) -> str:
    for act in plan["acts"]:
        act_id = str(act["id"])
        pattern = re.compile(
            re.escape(begin(act_id)) + r".*?" + re.escape(end(act_id)), re.S
        )
        if not pattern.search(text):
            raise PlanError(f"ROADMAP.md has no {begin(act_id)} … {end(act_id)} block")
        text = pattern.sub(generated_block(plan, act_id), text, count=1)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="verify the artefacts match the data file; write nothing")
    args = parser.parse_args(argv)

    plan = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    validate(plan)

    page = render_page(plan, TEMPLATE_PATH.read_text(encoding="utf-8"))
    markdown = update_markdown(MARKDOWN_PATH.read_text(encoding="utf-8"), plan)

    if args.check:
        stale = []
        if not PAGE_PATH.exists() or PAGE_PATH.read_text(encoding="utf-8") != page:
            stale.append("docs/roadmap.html")
        if MARKDOWN_PATH.read_text(encoding="utf-8") != markdown:
            stale.append("docs/ROADMAP.md")
        if stale:
            print("out of date, run: python scripts/build_roadmap.py\n  " + "\n  ".join(stale),
                  file=sys.stderr)
            return 1
        print(f"roadmap artefacts are in step with docs/roadmap_data.json "
              f"({len(plan['tasks'])} tasks)")
        return 0

    PAGE_PATH.write_text(page, encoding="utf-8")
    MARKDOWN_PATH.write_text(markdown, encoding="utf-8")
    print(f"wrote {PAGE_PATH.relative_to(ROOT)} ({len(page)} bytes) and refreshed "
          f"{len(plan['acts'])} task tables in {MARKDOWN_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
