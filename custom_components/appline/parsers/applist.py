"""The apps (and sites) that can be sidebar panels, from kit/apps.json. Pure Python.

apps.json: { apps: [{ id, name, path, launcher?, hidden?, draft?, embed? }], sites: [{ id, name, href, panel? }] }.
An app is shown at the hub (launcher.hedgepig.uk/<path>/; the launcher itself at the front page). A site of its own (0.7.0: Wardyn, Netline's
network monitor, at wardyn.hedgepig.uk) is offered when apps.json marks it "panel": true, at its own address (only a hedgepig.uk one).
Each comes out as { id, name, path } (and url for a site).
"""
from __future__ import annotations

import re
from typing import Any

SITE_URL = re.compile(r"^https://[a-z0-9-]+\.hedgepig\.uk/$")


def panel_apps(j: Any) -> list[dict[str, Any]]:
    apps = j.get("apps") if isinstance(j, dict) else j
    out = [{"id": a["id"], "name": a.get("name") or a["id"], "path": "" if a.get("launcher") else (a.get("path") or a["id"])}
           for a in apps or [] if isinstance(a, dict) and isinstance(a.get("id"), str) and not a.get("hidden") and not a.get("draft")
           and a.get("embed") is not False]   # "embed": false: can't work in a panel (the camera scanner)
    sites = j.get("sites") if isinstance(j, dict) else None
    out += [{"id": s["id"], "name": s.get("name") or s["id"], "path": "", "url": s["href"]}
            for s in sites or [] if isinstance(s, dict) and isinstance(s.get("id"), str) and s.get("panel") is True
            and isinstance(s.get("href"), str) and SITE_URL.match(s["href"])]
    return out


def panel_url(p: dict, base: str) -> str:
    """Where a panel points: a site at its own address, an app at the hub (the launcher at the front page: saved before 0.2.2 as
    path "tools", which doesn't exist). ?hp=ha: the pages hide what a Home Assistant panel can't do (kit.js HPEmbed)."""
    url = p.get("url")
    if isinstance(url, str) and SITE_URL.match(url):
        return url + "?hp=ha"
    path = "" if p.get("id") == "tools" else str(p.get("path") or "").strip("/")
    return (f"{base}/{path}/" if path else f"{base}/") + "?hp=ha"
