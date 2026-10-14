"""Listline (lists) -> Home Assistant to-do lists, both ways. Pure Python.

Saved data (web/listline/APP.md, lists.html): listline_lists_v1 [{ id, name, kind (shopping | todo | …), items: [{ id, text, aisle,
due 'YYYY-MM-DD' (to-do lists), done, doneAt (ms), at (ms), back }], repeat: { <key(text)>: { text, every, last } }, counts, aisles }].
The changes below make what the app's own controls make (new items like its add box, ticking like its checkbox: a thing set to
come back gets its repeat's last = today). Entities on the Listline device: a to-do list per list, and how many things are left on it.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from .common import household, share_codes as _share_codes, single, who, ymd
from .model import COUNT, LIST, SENSOR, TODO, Device, Parsed, Thing

APP, NAME = "listline", "Listline"
LIST_KEY = "listline_lists_v1"


def key(text: str) -> str:
    """As the page's key(): "2 milk" and "milk" are the same thing."""
    return re.sub(r"^\d+\s*(x\s*)?", "", str(text).strip().lower())


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    for e in ents:
        lst = e["item"]
        items = [i for i in lst.get("items") or [] if isinstance(i, dict) and isinstance(i.get("id"), str)]
        left = [i for i in items if not i.get("done")]
        name = str(lst.get("name") or "List")
        ph = {"name": name}
        out.add(Thing(f"{e['key']}.todo", APP, TODO, LIST, "list_todo", len(left), ph, who(e), "mdi:format-list-checks", app=APP,
                      data={"target": e["target"], "kind": lst.get("kind"), "items": items}))
        out.add(Thing(f"{e['key']}.left", APP, SENSOR, COUNT, "list_left", len(left), ph, {"items": [str(i.get("text")) for i in left][:50], **who(e)},
                      "mdi:cart-outline" if lst.get("kind") == "shopping" else "mdi:format-list-bulleted"))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


# ---------- changes from Home Assistant (each edits one list in place; False: nothing to do) ----------
def new_item(lst: dict, item_id: str, text: str, due: date | None, now_ms: int) -> bool:
    text = str(text or "").strip()[:100]
    if not text:
        return False
    lst["items"] = list(lst.get("items") or []) + [{"id": item_id, "text": text, "due": due.isoformat() if due and lst.get("kind") == "todo" else "",
                                                    "done": False, "at": now_ms}]
    return True


def update_item(lst: dict, item_id: str, text: str | None, done: bool | None, due: date | None | str, now_ms: int, today: date) -> bool:
    it = next((i for i in lst.get("items") or [] if isinstance(i, dict) and i.get("id") == item_id), None)
    if it is None:
        return False
    changed = False
    if text is not None and text.strip() and text.strip()[:100] != it.get("text"):
        it["text"], changed = text.strip()[:100], True
    if due != "keep" and lst.get("kind") == "todo":
        d = due.isoformat() if isinstance(due, date) else ""
        if d != (it.get("due") or ""):
            it["due"], changed = d, True
    if done is not None and bool(done) != bool(it.get("done")):
        it["done"], it["doneAt"], changed = bool(done), now_ms, True
        rp = (lst.get("repeat") or {}).get(key(it.get("text", "")))
        if done and isinstance(rp, dict):
            rp["last"] = today.isoformat()   # as the app's checkbox: a thing that comes back counts from today
    return changed


def delete_items(lst: dict, ids: list[str]) -> bool:
    before = len(lst.get("items") or [])
    lst["items"] = [i for i in lst.get("items") or [] if not (isinstance(i, dict) and i.get("id") in ids)]
    return len(lst["items"]) != before


def move_item(lst: dict, item_id: str, after_id: str | None) -> bool:
    items = list(lst.get("items") or [])
    it = next((i for i in items if isinstance(i, dict) and i.get("id") == item_id), None)
    if it is None:
        return False
    items.remove(it)
    pos = 0 if after_id is None else next((k + 1 for k, i in enumerate(items) if isinstance(i, dict) and i.get("id") == after_id), len(items))
    items.insert(pos, it)
    lst["items"] = items
    return True


def due_of(it: dict) -> date | None:
    return ymd(it.get("due")) if it.get("due") else None
