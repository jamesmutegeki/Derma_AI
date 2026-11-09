#!/usr/bin/env python3
"""Build the Derma_AI Evidence Atlas from one versioned JSON source.

Usage:
    python3 docs/roadmap/build.py
    python3 docs/roadmap/build.py --check

The generated files are docs/roadmap/index.html and ROADMAP.md. Browser edits
are drafts: export status.json, replace the source, rebuild, review, and commit
all three together. This script uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STATUSES = {"done", "partial", "reported", "todo", "blocked", "failed"}
LABELS = {"done": "Done", "partial": "Partial", "reported": "Reported", "todo": "To do", "blocked": "Blocked", "failed": "Needs repair"}


def load_and_validate(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    for key in ("project", "status_legend", "gates", "phases", "explanation", "resources", "evidence_ledger", "changelog"):
        if key not in data:
            raise ValueError(f"missing top-level key: {key}")
    ids: set[str] = set()
    phase_ids: set[str] = set()
    for phase in data["phases"]:
        if phase["id"] in phase_ids:
            raise ValueError(f"duplicate phase id: {phase['id']}")
        phase_ids.add(phase["id"])
        if phase.get("status") not in STATUSES:
            raise ValueError(f"invalid phase status: {phase['id']}")
        for field in ("station", "name", "window", "outcome", "why"):
            if not phase.get(field):
                raise ValueError(f"missing {field} in {phase['id']}")
        for task in phase["tasks"]:
            tid = task.get("id")
            if not tid or tid in ids:
                raise ValueError(f"missing/duplicate task id: {tid}")
            ids.add(tid)
            if task.get("status") not in STATUSES:
                raise ValueError(f"invalid status in {tid}")
            for field in ("title", "priority", "owner", "effort"):
                if not task.get(field):
                    raise ValueError(f"missing {field} in {tid}")
            for field in ("how", "done_when", "evidence", "artifacts"):
                if not isinstance(task.get(field), list) or not task[field]:
                    raise ValueError(f"{tid}.{field} must be a non-empty list")
    for phase in data["phases"]:
        for dep in phase.get("depends_on", []):
            if dep not in ids and dep not in phase_ids:
                raise ValueError(f"unknown dependency {dep} in {phase['id']}")
    for tid in data.get("next_moves", []):
        if tid not in ids:
            raise ValueError(f"unknown next move: {tid}")
    for gate in data["gates"]:
        if gate.get("status") not in STATUSES:
            raise ValueError(f"invalid gate status: {gate.get('id')}")
    return data


def md_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_table(table: dict) -> list[str]:
    lines = ["| " + " | ".join(md_escape(h) for h in table["headers"]) + " |",
             "| " + " | ".join("---" for _ in table["headers"]) + " |"]
    lines.extend("| " + " | ".join(md_escape(c) for c in row) + " |" for row in table["rows"])
    return lines


def build_markdown(data: dict) -> str:
    project = data["project"]
    snap = project["snapshot"]
    tasks = [t for p in data["phases"] for t in p["tasks"]]
    c = Counter(t["status"] for t in tasks)
    pct = round(100 * c["done"] / len(tasks)) if tasks else 0
    lines = [
        f"# {project['name']}", "", f"> {project['tagline']}", "",
        f"**Project:** {project['subtitle']}  ",
        f"**Lead:** {project['owner']} · {project['context']}  ",
        f"**Status snapshot:** `{snap['remote_branch']}@{snap['short_commit']}`, checked {snap['checked_on']}  ",
        f"**Training:** {snap['training_state']} · **Validated real-data metrics:** {snap['validated_metrics']}", "",
        f"> **Research boundary:** {project['disclaimer']}", "",
        "**Interactive view:** [open the Evidence Atlas](docs/roadmap/index.html). **Canonical source:** `docs/roadmap/status.json`.", "",
        "## Snapshot interpretation", "", snap["scope"], "",
        f"**Evidence-backed checklist:** {c['done']}/{len(tasks)} ({pct}%). This measures accepted tasks, not code volume or clinical readiness.", "",
        "| Status | Count | Meaning |", "| --- | ---: | --- |",
    ]
    for status in ("done", "partial", "reported", "todo", "blocked", "failed"):
        lines.append(f"| {LABELS[status]} | {c[status]} | {data['status_legend'][status]} |")
    lines += ["", "## North star", "", project["north_star"], "", "## Evidence gates", "",
              "| Gate | Status | Rule |", "| --- | --- | --- |"]
    for g in data["gates"]:
        lines.append(f"| {g['id']} · {md_escape(g['name'])} | {LABELS[g['status']]} | {md_escape(g['rule'])} |")
    lines += ["", "## The seven-station route", "",
              "| Station | Window | Outcome | Progress |", "| --- | --- | --- | --- |"]
    for p in data["phases"]:
        done = sum(t["status"] == "done" for t in p["tasks"])
        lines.append(f"| {p['id']} · {md_escape(p['station'])}: {md_escape(p['name'])} | {md_escape(p['window'])} | {md_escape(p['outcome'])} | {done}/{len(p['tasks'])} |")
    lines += ["", "Windows are indicative. External data, ethics, annotation, and stakeholder gates can extend the schedule.",
              "", "## Next moves", ""]
    task_by_id = {t["id"]: t for t in tasks}
    for i, tid in enumerate(data.get("next_moves", []), 1):
        t = task_by_id[tid]
        lines.append(f"{i}. **{tid} — {t['title']}** ({LABELS[t['status']]}): {t['how'][0]}")
    lines += ["", "## Detailed roadmap", ""]
    for p in data["phases"]:
        done = sum(t["status"] == "done" for t in p["tasks"])
        deps = ", ".join(p.get("depends_on", [])) or "Entry station"
        lines += [f"### {p['id']} · {p['station']} — {p['name']}", "",
                  f"**Window:** {p['window']} · **Status:** {LABELS[p['status']]} · **Progress:** {done}/{len(p['tasks'])} · **Depends on:** {deps}", "",
                  f"**Outcome:** {p['outcome']}", "", f"*Why this station matters:* {p['why']}", ""]
        for t in p["tasks"]:
            box = "x" if t["status"] == "done" else " "
            lines += [f"- [{box}] **{t['id']} — {t['title']}** · `{LABELS[t['status']]}` · {t['priority']} · {t['owner']} · effort {t['effort']}",
                      "", "  **How:**"]
            lines.extend(f"  {i}. {step}" for i, step in enumerate(t["how"], 1))
            lines += ["", "  **Done when:**"]
            lines.extend(f"  - {'[x]' if t['status'] == 'done' else '[ ]'} {item}" for item in t["done_when"])
            lines += ["", "  **Evidence on record:**"]
            lines.extend(f"  - {item}" for item in t["evidence"])
            if t.get("local_note"):
                lines += ["", f"  **Imported draft note:** {t['local_note']}"]
            lines += ["", "  **Artifacts:** " + "; ".join(f"`{a}`" for a in t["artifacts"]), ""]
    lines += ["## Full project explanation", ""]
    for section in data["explanation"]:
        lines += [f"### {section['title']}", ""]
        lines += [p for p in section.get("paragraphs", []) for p in (p, "")]
        if section.get("bullets"):
            lines += [f"- {b}" for b in section["bullets"]] + [""]
        if section.get("table"):
            lines += md_table(section["table"]) + [""]
    lines += ["## Resource map", "", "| Resource | Role | Source | Caution |", "| --- | --- | --- | --- |"]
    for r in data["resources"]:
        source = f"[{md_escape(r['name'])}]({r['url']})" if r.get("url") else md_escape(r["name"])
        lines.append(f"| {md_escape(r['name'])} | {md_escape(r['use'])} | {source} | {md_escape(r['note'])} |")
    lines += ["", "## Evidence ledger", "", "### Verified in this audit", ""]
    lines += [f"- {x}" for x in data["evidence_ledger"]["verified"]]
    lines += ["", "### Reported, not independently reproduced", ""]
    lines += [f"- {x}" for x in data["evidence_ledger"]["reported"]]
    lines += ["", "### Claims that must be corrected", ""]
    lines += [f"- {x}" for x in data["evidence_ledger"]["corrections"]]
    lines += ["", "## Update protocol", "",
              "1. Update the task in the dashboard or edit `docs/roadmap/status.json` directly.",
              "2. If using the dashboard, export `status.json` and replace the canonical file.",
              "3. Run `python3 docs/roadmap/build.py`.",
              "4. Review the diff and commit JSON, `docs/roadmap/index.html`, and `ROADMAP.md` together.",
              "5. Use `python3 docs/roadmap/build.py --check` in CI to catch drift.",
              "6. Close a gate only with evidence and a named reviewer; never convert a reported result to verified by relabeling it.", "",
              "Do not place patient data, secrets, restricted images, or access tokens in this tracker.", "",
              "## Changelog", "", "| Date | Change | Evidence |", "| --- | --- | --- |"]
    for entry in data["changelog"]:
        lines.append(f"| {md_escape(entry['date'])} | {md_escape(entry['change'])} | {md_escape(entry['evidence'])} |")
    lines += ["", "---", "*Generated from `docs/roadmap/status.json`. Edit the source, not the generated files.*", ""]
    return "\n".join(lines)


def build_html(data: dict, template: str) -> str:
    token = "/*__ROADMAP_DATA__*/null"
    if template.count(token) != 1:
        raise ValueError("template must contain exactly one data injection token")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(token, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files differ from the JSON source")
    parser.add_argument("--status", type=Path, default=HERE / "status.json")
    args = parser.parse_args()
    data = load_and_validate(args.status)
    outputs = {
        HERE / "index.html": build_html(data, (HERE / "template.html").read_text(encoding="utf-8")),
        ROOT / "ROADMAP.md": build_markdown(data),
    }
    if args.check:
        stale = [str(path.relative_to(ROOT)) for path, content in outputs.items()
                 if not path.exists() or path.read_text(encoding="utf-8") != content]
        if stale:
            print("Roadmap outputs are stale: " + ", ".join(stale))
            return 1
        print("Roadmap outputs match status.json")
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")
    tasks = [t for p in data["phases"] for t in p["tasks"]]
    c = Counter(t["status"] for t in tasks)
    print(f"{len(data['phases'])} stations · {len(tasks)} tasks · {c['done']} done · {c['blocked']} blocked · {c['failed']} needs repair")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
