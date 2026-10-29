"""S0-4 -- the dashboard cannot execute injected markup.

Acceptance criteria
-------------------
1. Every user/API-controlled string that reaches the DOM goes through ``esc()``
   (or ``textContent``); the shared render helpers are unit-tested with hostile
   payloads.
2. Image sources are restricted to ``data:image/...;base64`` URLs, so
   ``javascript:`` and attribute-breaking payloads are dropped.
3. No inline event handlers contain interpolated data and the page ships no
   inline ``<script>`` body, so the strict CSP (``script-src 'self'``) holds.
4. The page does not load third-party scripts or fonts.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    '"><script>alert(1)</script>',
    "javascript:alert(1)",
    "' onmouseover='alert(1)",
    "</td></tr><script>fetch('//evil')</script>",
    "`+alert(1)+`",
]


def _node() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the dashboard XSS tests")
    return node


@pytest.fixture(scope="module")
def helpers_js(app_dir) -> str:
    source = (app_dir / "dashboard.js").read_text(encoding="utf-8")
    start = source.index("// ==== RENDER HELPERS")
    end = source.index("// ==== END RENDER HELPERS")
    return source[start:end]


def _run_js(script: str) -> dict:
    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_escaping_helpers_neutralise_payloads(helpers_js):
    script = helpers_js + """
const out = {};
out.escaped = PAYLOADS.map(p => esc(p));
out.queue = PAYLOADS.map(p => renderQueueItem({ name: p, id: p, age: '34 yrs', gender: 'female', fitz: p, visits: [] }, 'x'));
out.timeline = PAYLOADS.map(p => renderTimelineItem({ date: p, desc: p, tag: p, id: p }, p));
out.doctor = PAYLOADS.map(p => renderDoctorRow({ id: p, name: p, username: p, email: p, nin: p, title: p, last_login: null, permissions: {} }));
out.activity = PAYLOADS.map(p => renderActivityItem({ event: p, level: p, timestamp: null }));
out.session = PAYLOADS.map(p => renderSessionRow({ name: p, role: p, sid: p }));
console.log(JSON.stringify(out));
"""
    prelude = "const PAYLOADS = " + json.dumps(PAYLOADS) + ";\n" \
        "const ALL_PERMISSIONS = [{ key: 'view_patient', label: 'View' }, { key: 'edit_patient', label: 'Edit' }];\n"
    script = prelude + script
    out = _run_js(script)

    for group, rows in out.items():
        for row in rows:
            assert "<img" not in row.lower(), f"{group}: raw <img> survived: {row}"
            assert "<script" not in row.lower(), f"{group}: raw <script> survived: {row}"
            assert "onerror=" not in row.lower(), f"{group}: onerror handler survived: {row}"
            assert "onmouseover=" not in row.lower(), f"{group}: onmouseover survived: {row}"
            # Escaped *text* may legitimately read "javascript:alert(1)"; what
            # matters is that it never lands in an executable attribute.
            assert 'href="javascript' not in row.lower(), row
            assert 'src="javascript' not in row.lower(), row
            assert "onerror=" not in row.lower(), row

    # esc() must emit entities, not the raw characters.
    assert all("<" not in value and ">" not in value for value in out["escaped"])


def test_image_urls_are_restricted(helpers_js):
    script = helpers_js + """
const cases = ["javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "https://evil.example/x.png", "", null, "data:image/png;base64,iVBORw0KGgo="];
console.log(JSON.stringify(cases.map(c => safeImageUrl(c))));
"""
    result = _run_js(script)
    assert result[0] == ""
    assert result[1] == ""
    assert result[2] == ""
    assert result[3] == ""
    assert result[4] == ""
    assert result[5] == "data:image/png;base64,iVBORw0KGgo="


def test_no_inline_script_or_event_handlers(app_dir):
    html = (app_dir / "dashboard.html").read_text(encoding="utf-8")
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S | re.I)
    assert not inline, "dashboard.html still ships inline <script> bodies"
    assert "onclick=" not in html.lower() or "${" not in html, "inline handler interpolates data"
    assert "onclick=" not in (app_dir / "dashboard.js").read_text(encoding="utf-8").lower(), \
        "dashboard.js still builds inline onclick handlers"


def test_no_third_party_assets(app_dir):
    html = (app_dir / "dashboard.html").read_text(encoding="utf-8").lower()
    assert "cdn.jsdelivr.net" not in html
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_csp_forbids_inline_scripts(client):
    response = client.get("/")
    csp = response.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_dashboard_script_is_served_as_static_file(client):
    response = client.get("/dashboard.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "function esc(" in response.text


def test_raw_html_is_never_assembled_from_api_data(app_dir):
    """Guard against re-introducing ``innerHTML = <template with ${data}>``."""
    js = (app_dir / "dashboard.js").read_text(encoding="utf-8")
    offenders = []
    for match in re.finditer(r"\.innerHTML\s*=\s*(`[^`]*`)", js):
        template = match.group(1)
        if re.search(r"\$\{\s*(?!esc\(|safeImageUrl\(|Number\()", template):
            offenders.append(template[:80])
    assert not offenders, "unescaped interpolation in innerHTML templates:\n" + "\n".join(offenders)
