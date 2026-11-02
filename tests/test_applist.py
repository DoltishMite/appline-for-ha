"""The sidebar's choices: the apps from kit/apps.json, and the sites of their own marked as panels (Wardyn), each at the right address."""
import json

from conftest import SITE
from parsers.applist import panel_apps, panel_url

BASE = "https://launcher.hedgepig.uk"


def test_apps_and_sites():
    j = {"apps": [{"id": "tools", "name": "Appline", "launcher": True}, {"id": "siteline", "name": "Netline", "path": "netline"},
                  {"id": "scan", "name": "Scanline", "embed": False}, {"id": "x", "draft": True}],
         "sites": [{"id": "site-games", "name": "Games", "href": "https://games.hedgepig.uk/"},
                   {"id": "site-wardyn", "name": "Wardyn", "href": "https://wardyn.hedgepig.uk/", "panel": True},
                   {"id": "evil", "name": "Evil", "href": "https://example.com/", "panel": True}]}
    out = panel_apps(j)
    assert [p["id"] for p in out] == ["tools", "siteline", "site-wardyn"]
    by = {p["id"]: p for p in out}
    assert panel_url(by["tools"], BASE) == BASE + "/?hp=ha"
    assert panel_url(by["siteline"], BASE) == BASE + "/netline/?hp=ha"
    assert panel_url(by["site-wardyn"], BASE) == "https://wardyn.hedgepig.uk/?hp=ha"
    # saved before 0.7.0 (no url), and a url that isn't one of the sites' (never used)
    assert panel_url({"id": "pingline", "path": "uptime"}, BASE) == BASE + "/uptime/?hp=ha"
    assert panel_url({"id": "z", "path": "z", "url": "https://example.com/"}, BASE) == BASE + "/z/?hp=ha"


def test_real_apps_json_offers_wardyn():
    f = SITE / "web" / "kit" / "apps.json"
    if not f.exists():
        return
    out = panel_apps(json.loads(f.read_text(encoding="utf-8")))
    assert any(p["id"] == "site-wardyn" and p["url"] == "https://wardyn.hedgepig.uk/" for p in out)
    assert not any(p["id"] == "site-games" for p in out)
