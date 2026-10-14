"""Turning the apps' synced data into devices and entities. Pure Python (no Home Assistant imports).

Each app with a parser is a module here with:
  APP, NAME                     its id (apps.json) and default name
  parse(data, shared, now, out, app_name)   add its devices and things to out (a Parsed)
  share_codes(data)             { item id: share code } for the things it shares (the kit's <app>_shared_v1)
  from_shared(item, item_id)    one shared thing on its own (a share code entered in HA) as the app's saved data
  events(data, start, end, now, daily)   only if it makes CALENDAR things: their events (model.Event) in that window
Everything is rebuilt from the documents on every change, so entities follow what's in the apps: a new pet, task or preset
appears, a removed one goes, a renamed one keeps its entity (keys are the apps' own ids).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from . import binline, birthline, carline, cookline, countline, deadline, homeline, listline, petline, plantline
from .model import Device, Event, Parsed, Thing

PARSERS = {m.APP: m for m in (petline, countline, birthline, deadline, listline, carline, binline, homeline, plantline, cookline)}

__all__ = ["PARSERS", "Device", "Event", "Parsed", "Thing", "app_data", "app_name", "parse_household", "parse_sync", "parse_shared", "sync_share_codes"]


def app_data(sync_doc: Any, app: str) -> dict[str, str] | None:
    """One app's saved keys from a personal sync copy, or None if the setup doesn't have that app."""
    apps = sync_doc.get("apps") if isinstance(sync_doc, dict) else None
    entry = apps.get(app) if isinstance(apps, dict) else None
    data = entry.get("data") if isinstance(entry, dict) else None
    return {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else None


def app_name(data: dict[str, str], app: str) -> str | None:
    """The name the user gave the app (Settings → General), if any."""
    v = data.get(f"{app}_app_name_v1")
    if not v:
        return None
    try:
        v = json.loads(v)
    except ValueError:
        pass
    return v.strip() if isinstance(v, str) and v.strip() else None


def sync_share_codes(sync_doc: Any) -> dict[tuple[str, str], str]:
    """{ (app, item id): share code } for everything shared in this setup, for the apps with a parser."""
    out: dict[tuple[str, str], str] = {}
    for app, mod in PARSERS.items():
        data = app_data(sync_doc, app)
        if data:
            out.update({(app, iid): code for iid, code in mod.share_codes(data).items()})
    return out


def parse_sync(sync_doc: Any, shared: dict[tuple[str, str], dict], now: datetime) -> Parsed:
    """Everything in a personal sync copy. shared: { (app, item id): item } from the shared copies (newer than the synced ones)."""
    out = Parsed()
    for app, mod in PARSERS.items():
        data = app_data(sync_doc, app)
        if data is None:
            continue
        mine = {iid: item for (a, iid), item in shared.items() if a == app}
        mod.parse(data, mine, now, out, app_name(data, app))
    return out


def parse_household(people: list[tuple[str, Any]], refs: dict[tuple[str, str, str], str], shared_items: dict[str, dict],
                    now: datetime) -> Parsed:
    """A household: people = [(person key, their HA link copy)] (the same shape as a sync copy, with only what they ticked, and
    their name); refs = { (person key, app, item id): shared copy id } for the shared things in them; shared_items = { shared copy id:
    item }. Apps without parse_people are skipped."""
    out = Parsed()
    for app, mod in PARSERS.items():
        if not hasattr(mod, "parse_people"):
            continue
        rows, name = [], None
        for pk, doc in people:
            data = app_data(doc, app)
            if data is not None:
                who = doc.get("name") if isinstance(doc, dict) and isinstance(doc.get("name"), str) and doc["name"].strip() else "Someone"
                rows.append((pk, who, data))
                name = name or app_name(data, app)
        if rows:
            mod.parse_people(rows, {(pk, iid): sid for (pk, a, iid), sid in refs.items() if a == app}, shared_items, now, out, name)
    return out


def parse_shared(shared_doc: Any, now: datetime) -> Parsed:
    """One shared thing (a share code's copy: { format: 2, app, id, item })."""
    out = Parsed()
    if not isinstance(shared_doc, dict):
        return out
    mod = PARSERS.get(shared_doc.get("app"))
    item = shared_doc.get("item")
    if mod and isinstance(item, dict) and isinstance(shared_doc.get("id"), str):
        mod.parse(mod.from_shared(item, shared_doc["id"]), {}, now, out, None)
    return out
