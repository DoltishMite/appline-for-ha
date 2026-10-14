"""What every app's parser needs: reading saved values, and a household's items (whose, shared once, where a change is saved).
Pure Python."""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any


def js(s: Any, default: Any) -> Any:
    """A saved value (localStorage strings are JSON), or default."""
    if not isinstance(s, str):
        return default
    try:
        v = json.loads(s)
    except ValueError:
        return default
    return default if v is None else v


def ymd(s: Any) -> date | None:
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (TypeError, ValueError, IndexError):
        return None


def at(day: date | None, hm: Any, tz) -> datetime | None:
    if day is None:
        return None
    try:
        h, m = (int(x) for x in str(hm).split(":")[:2])
        return datetime.combine(day, time(h, m), tzinfo=tz)
    except ValueError:
        return None


def items_of(data: dict[str, str], key: str) -> list[dict]:
    v = js(data.get(key), [])
    return [x for x in v if isinstance(x, dict) and isinstance(x.get("id"), str)] if isinstance(v, list) else []


def household(app: str, key: str, people: list[tuple[str, str, dict[str, str]]], refs: dict[tuple[str, str], str],
              shared_items: dict[str, dict]) -> list[dict]:
    """The items under one saved list key across a household, each once:
    { key: '<app>.<person>.<id>' | '<app>.shared.<copy>', item, data (that person's saved data), owner | None,
      shared_with: [names] | None, people: [person keys], target: where Home Assistant saves a change to it }.
    A shared item (in someone's <app>_shared_v1) is keyed by its shared copy, so it shows once however many send it; its shared
    copy's content wins (it's newer than anyone's link copy while others change it)."""
    out, by_sid = [], {}
    for pk, name, data in people:
        for item in items_of(data, key):
            iid, sid = item["id"], refs.get((pk, item["id"]))
            if not sid:
                out.append({"key": f"{app}.{pk}.{iid}", "item": item, "data": data, "owner": name, "shared_with": None,
                            "people": [pk], "target": ["link", pk, app, iid]})
                continue
            if sid in by_sid:
                by_sid[sid]["shared_with"].append(name)
                by_sid[sid]["people"].append(pk)
                continue
            sh = shared_items.get(sid)
            e = {"key": f"{app}.shared.{sid[:12]}", "item": dict(sh, id=iid) if isinstance(sh, dict) else item, "data": data,
                 "owner": None, "shared_with": [name], "people": [pk],
                 "target": ["shared", sid, app] if isinstance(sh, dict) else ["link", pk, app, iid]}
            by_sid[sid] = e
            out.append(e)
    return out


def single(app: str, key: str, data: dict[str, str], shared: dict[str, dict]) -> list[dict]:
    """The same for one copy (a sync copy or one shared thing): keys '<app>.<id>', read-only."""
    out = []
    for item in items_of(data, key):
        iid = item["id"]
        it = dict(shared[iid], id=iid) if isinstance(shared.get(iid), dict) else item
        out.append({"key": f"{app}.{iid}", "item": it, "data": data, "owner": None, "shared_with": None, "people": [], "target": None})
    return out


def who(e: dict) -> dict:
    return {"owner": e["owner"]} if e.get("owner") else {"shared_with": list(e["shared_with"])} if e.get("shared_with") else {}


def share_codes(data: dict[str, str], app: str) -> dict[str, str]:
    """{ item id: share code } from <app>_shared_v1 (the kit's HPTogether)."""
    s = js(data.get(f"{app}_shared_v1"), {})
    return {iid: v["code"] for iid, v in (s.items() if isinstance(s, dict) else [])
            if isinstance(v, dict) and isinstance(v.get("code"), str) and v["code"]}
