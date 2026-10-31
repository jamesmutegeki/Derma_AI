"""S5-1 -- one logo, everywhere, and nothing that looks like the old one.

The system carried three different hand-drawn SVG marks (a blue/green gradient
circle on the login card, a slightly different one in each header, and two more
in the slides and poster). That is the kind of drift that makes a project look
unowned. This test pins the rebrand:

* the approved artwork is committed and its derived assets exist at the sizes
  the interface asks for;
* every surface references the same file -- dashboard, slides, poster, favicon;
* no old gradient mark survives;
* the server serves the files, and only those files.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

BRAND_FILES = ("logo.png", "logo-mark.png", "favicon.png")
SURFACES = ("dashboard.html", "slides.html", "poster.html")


def test_brand_assets_exist_at_the_expected_sizes(app_dir):
    assets = app_dir / "assets"
    for name in BRAND_FILES:
        path = assets / name
        assert path.is_file(), f"missing {name}"
        assert path.stat().st_size < 300 * 1024, f"{name} is too heavy to serve"

    with Image.open(assets / "logo-mark.png") as mark:
        assert mark.mode == "RGBA"
        assert mark.size == (512, 512)

    with Image.open(assets / "favicon.png") as icon:
        assert icon.size == (128, 128)


def test_mark_has_a_transparent_background(app_dir):
    with Image.open(app_dir / "assets" / "logo-mark.png") as mark:
        alpha = mark.convert("RGBA").getchannel("A")
        # The corners sit outside the circular emblem: they must be clear, not
        # a white box that would show up on the dark slides.
        for corner in ((0, 0), (511, 0), (0, 511), (511, 511)):
            assert alpha.getpixel(corner) == 0


def test_mark_is_the_approved_two_colour_artwork(app_dir):
    """Navy and coral, not the retired blue/green gradient."""
    with Image.open(app_dir / "assets" / "logo-mark.png") as mark:
        pixels = [p for p in mark.convert("RGBA").getdata() if p[3] > 200]
    assert len(pixels) > 1000
    navy = sum(1 for r, g, b, _ in pixels if b > r + 30 and b > 70 and r < 80)
    coral = sum(1 for r, g, b, _ in pixels if r > 180 and r > b + 60)
    assert navy > 500, "navy ink missing from the mark"
    assert coral > 500, "coral ink missing from the mark"
    bright_green = sum(1 for r, g, b, _ in pixels if g > 180 and r < 120)
    assert bright_green < 50, "the retired green gradient is still in the artwork"


def test_every_surface_uses_the_same_asset(app_dir):
    for name in SURFACES:
        html = (app_dir / name).read_text(encoding="utf-8")
        assert "/assets/logo-mark.png" in html, f"{name} still has no brand mark"
        assert 'href="/assets/favicon.png"' in html, f"{name} has no favicon"
        assert "url(#lg" not in html, f"{name} still contains the old gradient logo"


def test_dashboard_replaces_all_three_old_marks(app_dir):
    html = (app_dir / "dashboard.html").read_text(encoding="utf-8")
    assert html.count("/assets/logo-mark.png") == 3, "login + doctor + admin headers"
    assert "<h1>Dermatology System</h1>" in html
    assert "Derma-AI</h1>" not in html


def test_server_serves_the_assets_publicly(client, app_dir):
    response = client.get("/assets/logo-mark.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == (app_dir / "assets" / "logo-mark.png").read_bytes()

    icon = client.get("/favicon.ico")
    assert icon.status_code == 200
    assert icon.headers["content-type"] == "image/png"


def test_asset_route_refuses_anything_else(client):
    assert client.get("/assets/does-not-exist.png").status_code == 404
    assert client.get("/assets/server.py").status_code == 404
    assert client.get("/assets/..%2Fserver.py").status_code == 404
    assert client.get("/assets/..%2F..%2F.git%2Fconfig").status_code == 404
    assert client.get("/assets/%2E%2E%2Fserver.py").status_code == 404


def test_csp_still_allows_self_hosted_images(client):
    response = client.get("/api/health")
    assert "img-src 'self'" in response.headers["content-security-policy"]
