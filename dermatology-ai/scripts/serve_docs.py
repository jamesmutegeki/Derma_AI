#!/usr/bin/env python3
"""Serve the offline artefacts in this repository for local reading.

The roadmap, the wall chart and the field guide are single files with no network
calls, so they can be opened straight from disk. This little server exists for
the cases where a URL is easier: a preview pane, a phone on the same network, a
supervisor who was sent a link.

    python scripts/serve_docs.py                    # http://0.0.0.0:8123/
    python scripts/serve_docs.py --port 9000        # somewhere else
    python scripts/serve_docs.py --root .           # serve the whole app dir

Deliberate choices:

* binds ``0.0.0.0`` so a preview proxy or a phone can reach it;
* sends ``Cache-Control: no-store`` so an edited page reloads without a fight;
* sends no ``X-Frame-Options`` / ``frame-ancestors``, because the point is to be
  embedded in a preview;
* refuses path traversal, and serves only plain files -- no directory listings.

It is a reading aid, not a deployment: no TLS, no authentication, no writes.
"""

from __future__ import annotations

import argparse
import mimetypes
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent

#: The artefacts worth landing on, in reading order.
FRONT_PAGE = [
    ("docs/field-guide.html", "The Honest Triage Machine",
     "Seven rooms explaining the project and its concepts, with one toy each"),
    ("docs/explainer.html", "Dr. Pixel's Skin Clinic",
     "An interactive walk-through: eight rooms, a dataset arena, a 16-card concept codex"),
    ("docs/roadmap.html", "The twelve-week roadmap",
     "43 tasks, week sheets, dependency map, scenarios, progress"),
    ("docs/roadmap_wallchart.html", "The wall chart",
     "A3 landscape, printable, offline"),
    ("docs/ROADMAP.md", "The written plan", "Narrative, risks, calendar, gates"),
    ("docs/DATASET_SOURCES_IMMEDIATE.md", "Where the data comes from",
     "PAD-UFES-20, DermaMNIST, SCIN, and the licence register"),
    ("MODEL_CARD.md", "Model card", "What the artefact is and is not"),
    ("docs/GATE_OPTIONS.md", "Gate 1A", "The Kaposi sarcoma pause and what ends it"),
    ("REMEDIATION_STATUS.md", "What is done", "Acceptance criteria and their tests"),
]

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in CONTENT_TYPES:
        return CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def index_page() -> bytes:
    rows = "\n".join(
        f'      <li><a href="/{href}"><b>{title}</b><span>{blurb}</span></a></li>'
        for href, title, blurb in FRONT_PAGE
        if (ROOT / href).exists()
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Derma AI — artefacts</title>
<style>
  :root {{ --navy:#113B65; --coral:#C1443F; --ink:#17202A; --muted:#5F6B76; --rule:#E3DCCC; --paper:#FBF8F2; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font:16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 56px 24px 80px; }}
  .kicker {{ font:11px ui-monospace, monospace; letter-spacing:.16em; text-transform:uppercase;
             color:var(--coral); margin-bottom:16px; }}
  h1 {{ font-family: "Iowan Old Style", Palatino, Georgia, serif; font-size:40px; line-height:1.05; margin:0 0 10px; }}
  p.lede {{ color:var(--muted); margin:0 0 28px; max-width: 34em; }}
  ul {{ list-style:none; margin:0; padding:0; border-top:1px solid var(--rule); }}
  li {{ border-bottom:1px solid var(--rule); }}
  a {{ display:flex; gap:14px; align-items:baseline; padding:14px 4px; text-decoration:none; color:inherit; }}
  a:hover {{ background:#fff; }}
  a b {{ font-size:16.5px; min-width:15em; }}
  a span {{ color:var(--muted); font-size:14px; }}
  footer {{ margin-top:34px; color:var(--muted); font-size:12.5px; }}
  footer b {{ color:var(--ink); }}
</style>
</head>
<body>
<main>
  <div class="kicker">Derma AI · local preview</div>
  <h1>Artefacts</h1>
  <p class="lede">Everything here is a single offline file. Start with the field guide;
    the roadmap is the instrument you work from.</p>
  <ul>
{rows}
  </ul>
  <footer>
    <b>Research prototype · Not a medical device · No Business Associate Agreement (BAA) · Do not use with real patient data.</b>
    <br>Served by scripts/serve_docs.py — no network calls, no writes.
  </footer>
</main>
</body>
</html>
"""
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "DermaDocs/1.0"

    def _resolve(self) -> Path | None:
        raw = unquote(urlparse(self.path).path)
        clean = posixpath.normpath(raw).lstrip("/")
        if clean in ("", "."):
            return None
        target = (ROOT / clean).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            return None
        return target if target.is_file() else None

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        path = unquote(urlparse(self.path).path)
        if path in ("/", "/index.html"):
            self._send(200, index_page(), "text/html; charset=utf-8")
            return
        target = self._resolve()
        if target is None:
            self._send(404, b"Not found. Start at /\n", "text/plain; charset=utf-8")
            return
        self._send(200, target.read_bytes(), content_type(target))

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def log_message(self, fmt: str, *args) -> None:  # keep the console readable
        print(f"  {self.address_string()}  {fmt % args}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the offline artefacts for reading.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {ROOT}")
    print(f"  front page   http://{args.host}:{args.port}/")
    for href, title, _ in FRONT_PAGE:
        if (ROOT / href).exists():
            print(f"  {title:<28} /{href}")
    print("  ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
