"""S9-2 -- the reading server is a reading aid, and behaves like one.

``scripts/serve_docs.py`` exists so the offline artefacts can be read at a URL:
in a preview pane, on a phone in the same room, or by a supervisor who was sent
a link. It is not a deployment, so the tests are about the promises that make it
safe to run at all:

* it serves the real files, with a content type a browser can render;
* it refuses to walk out of the repository, however the path is spelled;
* it does not stop a preview from embedding it (no ``X-Frame-Options``);
* it never lets a browser serve a stale page from cache while you are editing.
"""

from __future__ import annotations

import importlib.util
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest


@pytest.fixture(scope="module")
def server(app_dir):
    spec = importlib.util.spec_from_file_location("serve_docs", app_dir / "scripts" / "serve_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield module, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, dict, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def test_the_front_page_links_only_files_that_exist(server, app_dir):
    module, base = server
    status, headers, body = _get(base + "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    text = body.decode("utf-8")
    for href, _, _ in module.FRONT_PAGE:
        if (app_dir / href).exists():
            assert f'href="/{href}"' in text, href
    assert "Not a medical device" in text


def test_it_serves_the_artefacts_with_a_renderable_type(server):
    _, base = server
    for path, expected in {
        "/docs/roadmap.html": "text/html",
        "/docs/field-guide.html": "text/html",
        "/docs/roadmap_wallchart.html": "text/html",
        "/docs/ROADMAP.md": "text/plain",
        "/assets/logo-mark.png": "image/png",
    }.items():
        status, headers, body = _get(base + path)
        assert status == 200, path
        assert headers["Content-Type"].startswith(expected), path
        assert body, path


def test_it_refuses_to_leave_the_repository(server):
    _, base = server
    for attempt in (
        "/../README.md",
        "/%2e%2e/%2e%2e/etc/passwd",
        "/docs/../../../../etc/passwd",
        "/docs/",
    ):
        status, _, body = _get(base + attempt)
        assert status == 404, f"{attempt} was served ({status})"
        assert b"root:" not in body


def test_it_stays_embeddable_and_fresh(server):
    _, base = server
    status, headers, _ = _get(base + "/docs/roadmap.html")
    assert status == 200
    # A preview pane embeds this; nothing may forbid framing.
    assert "X-Frame-Options" not in headers
    assert "frame-ancestors" not in headers.get("Content-Security-Policy", "")
    # Edits show up on reload without a hard-refresh dance.
    assert headers.get("Cache-Control") == "no-store"
