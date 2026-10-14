"""Cookline (kitchen: timers, recipe books, the week planner) -> entities. Pure Python.

Saved data (web/cookline/kitchen.html): cookline_timers_v1 [{ id, name, dur (s), end (ms, running) | left (s, paused), rang }] (synced, so
a timer set on a phone shows here), cookline_books_v1 [{ id, name, recipes: [{ id, name, serves, ingredients, method }] }] (what's
ticked: recipe names), cookline_week_v1 { 'YYYY-MM-DD': { items: [{ meal, r (recipe id) | '', text, serves }] } | (older) { r, text,
serves } }, cookline_options_v1 { meals (the day's meals; Breakfast, Lunch, Tea to start) }. day_items() ports dayItems.
Entities on the Cookline device: timers running, when the next one ends, a timer finished; today's meals; a Meals calendar.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .common import household, js, share_codes as _share_codes, single, ymd
from .model import BINARY, CALENDAR, COUNT, EVENTS, SENSOR, TIMESTAMP, Device, Event, Parsed, Thing

APP, NAME = "cookline", "Cookline"
LIST_KEY, TIMERS, WEEK, OPTS = "cookline_books_v1", "cookline_timers_v1", "cookline_week_v1", "cookline_options_v1"


def meals_of(data: dict[str, str]) -> list[str]:
    o = js(data.get(OPTS), {})
    m = o.get("meals") if isinstance(o, dict) else None
    return [str(x) for x in m] if isinstance(m, list) and m else ["Breakfast", "Lunch", "Tea"]


def day_items(week: dict, k: str, meals: list[str]) -> list[dict]:
    w = week.get(k) if isinstance(week, dict) else None
    if not isinstance(w, dict):
        return []
    if isinstance(w.get("items"), list):
        return [it for it in w["items"] if isinstance(it, dict) and (it.get("r") or it.get("text"))]
    return [{"meal": meals[-1], "r": w.get("r") or "", "text": w.get("text") or "", "serves": w.get("serves")}] if w.get("r") or w.get("text") else []


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], people_data: list[tuple[str, dict]], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    names = {}   # recipe id → name, from every ticked book
    for e in ents:
        for r in e["item"].get("recipes") or []:
            if isinstance(r, dict) and r.get("id"):
                names[r["id"]] = str(r.get("name") or "Recipe")
    now_ms, timers, days = now.timestamp() * 1000, [], {}
    for who_, data in people_data:
        for t in js(data.get(TIMERS), []) if isinstance(js(data.get(TIMERS), []), list) else []:
            if isinstance(t, dict) and t.get("id") and not any(x["id"] == t["id"] for x in timers):
                timers.append(dict(t, _who=who_))
        meals, week = meals_of(data), js(data.get(WEEK), {})
        for k in (week.keys() if isinstance(week, dict) else []):
            if not ymd(k):
                continue
            for it in day_items(week, k, meals):
                what = names.get(it.get("r")) if it.get("r") else None
                what = what or str(it.get("text") or "") or "A recipe"
                entry = {"meal": str(it.get("meal") or meals[-1]), "what": what, "serves": it.get("serves")}
                lst = days.setdefault(k, [])
                if entry not in lst:
                    lst.append(entry)
                lst.sort(key=lambda x: meals.index(x["meal"]) if x["meal"] in meals else 99)
    running = [t for t in timers if isinstance(t.get("end"), (int, float))]
    paused = [t for t in timers if not isinstance(t.get("end"), (int, float))]
    ahead = sorted((t for t in running if t["end"] > now_ms), key=lambda t: t["end"])
    done = [str(t.get("name") or "Timer") for t in running if t["end"] <= now_ms]
    nxt = ahead[0] if ahead else None
    out.add(Thing(f"{APP}.timers", APP, SENSOR, COUNT, "cook_timers", len(ahead), {}, {
        "timers": [{"name": t.get("name"), "ends": datetime.fromtimestamp(t["end"] / 1000, now.tzinfo).isoformat()} for t in ahead],
        "paused": [str(t.get("name") or "Timer") for t in paused], "finished": done}, "mdi:timer-outline"))
    out.add(Thing(f"{APP}.timer_next", APP, SENSOR, TIMESTAMP, "cook_timer_next", datetime.fromtimestamp(nxt["end"] / 1000, now.tzinfo) if nxt else None, {},
                  {"name": nxt.get("name") if nxt else None}, "mdi:timer-sand"))
    out.add(Thing(f"{APP}.timer_done", APP, BINARY, "running", "cook_timer_done", bool(done), {}, {"timers": done}, "mdi:timer-alert-outline"))
    today = days.get(now.date().isoformat(), [])
    out.add(Thing(f"{APP}.today", APP, SENSOR, "text", "cook_today", (", ".join(f"{m['meal']}: {m['what']}" for m in today) or "Nothing planned")[:255], {},
                  {"meals": today, "tomorrow": days.get((now.date() + timedelta(days=1)).isoformat(), [])}, "mdi:silverware-fork-knife"))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "cook_calendar", None, icon="mdi:silverware-fork-knife", app=APP, data={"days": days}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), [("", data)], now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), [(name, data) for _, name, data in people], now, out, app_name)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    """Each planned dish as an all-day event, "Tea: Spaghetti Bolognese"."""
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date().isoformat(), end.astimezone(tz).date().isoformat()
    for k, lst in (data.get("days") or {}).items():
        if a <= k <= b:
            d = ymd(k)
            for i, m in enumerate(lst):
                serves = f" (for {m['serves']})" if m.get("serves") else ""
                out.append(Event(f"meal-{k}-{i}", f"{m['meal']}: {m['what']}{serves}", d, d + timedelta(days=1)))
    return sorted(out, key=lambda e: (e.start, e.uid))
