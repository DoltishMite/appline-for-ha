"""Plantline (plant care) -> devices and entities. Pure Python.

Saved data (web/plantline/plants.html): plantline_plants_v1 [{ id, name, em, room, water (days, in summer), feed (weeks in the growing
season; 0 = never), repot, prune (months; 0 = never), added 'YYYY-MM-DD', log: [{ d 'YYYY-MM-DD', what: water | feed | snooze | repot |
prune }] }], plantline_options_v1 { hemisphere (N | S), winter (1.5: how much longer the gap between waterings gets in winter), soonDays }.
season() / next_water() / next_feed() / next_every() port plants.html (watering stretched by the season, feeding and repotting waiting
for the growing season, "Not yet" asking again tomorrow); log() its logIt. Keep them the same.
Devices: "Plantline" (the app) and one per plant. Entities per plant: days until it needs water (and food, repotting, pruning when it
has them), Watered / Fed / Not yet buttons; for the app: how many need something today; a calendar.
"""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from .common import household, js, share_codes as _share_codes, single, who, ymd
from .model import BUTTON, CALENDAR, COUNT, DAYS, EVENTS, PRESS, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "plantline", "Plantline"
LIST_KEY, OPTS = "plantline_plants_v1", "plantline_options_v1"
JOBS = {"water": ("💧", "Water"), "feed": ("🧪", "Feed"), "repot": ("🏺", "Repot"), "prune": ("✂️", "Prune")}


def options(data: dict[str, str]) -> dict:
    o = js(data.get(OPTS), {})
    o = o if isinstance(o, dict) else {}
    w = o.get("winter")
    return {"hemisphere": "S" if o.get("hemisphere") == "S" else "N", "winter": float(w) if isinstance(w, (int, float)) else 1.5,
            "soonDays": o.get("soonDays") if isinstance(o.get("soonDays"), int) else 2}


def season(s: str, o: dict) -> str:
    m = ymd(s).month - 1
    if o["hemisphere"] == "S":
        m = (m + 6) % 12
    return "winter" if m in (11, 0, 1) else "spring" if m in (2, 3, 4) else "summer" if m in (5, 6, 7) else "autumn"


def stretch(s: str, o: dict) -> float:
    w = o["winter"]
    return {"winter": w, "spring": 1 + (w - 1) / 3, "summer": 1, "autumn": 1 + (w - 1) / 2}[season(s, o)]


def growing(s: str, o: dict) -> bool:
    return season(s, o) in ("spring", "summer")


def _plus(s: str, n: int) -> str:
    return (ymd(s) + timedelta(days=n)).isoformat()


def last(p: dict, what: str) -> str | None:
    e = sorted(x["d"] for x in p.get("log") or [] if isinstance(x, dict) and x.get("what") == what and isinstance(x.get("d"), str))
    return e[-1] if e else None


def _js_round(x: float) -> int:
    """Math.round: halves go up."""
    import math
    return math.floor(x + 0.5)


def next_water(p: dict, today: date, o: dict) -> str:
    lw, sn = last(p, "water"), last(p, "snooze")
    if not lw:
        return today.isoformat()
    try:
        every = float(p.get("water") or 0)
    except (TypeError, ValueError):
        every = 0
    due = _plus(lw, max(1, _js_round(every * stretch(lw, o))))
    if sn and sn >= lw and _plus(sn, 1) > due:
        due = _plus(sn, 1)
    return due


def next_feed(p: dict, today: date, o: dict) -> str | None:
    if not p.get("feed"):
        return None
    lf = last(p, "feed") or p.get("added") or today.isoformat()
    due = _plus(lf, int(p["feed"]) * 7)
    for _ in range(400):
        if growing(due, o):
            break
        due = _plus(due, 1)
    return due


def _set_month(s: str, months: int) -> str:
    """As JS's d.setMonth(d.getMonth() + months): a day past the end of the month rolls into the next."""
    d = ymd(s)
    m0 = d.month - 1 + months
    y, m = d.year + m0 // 12, m0 % 12 + 1
    dim = monthrange(y, m)[1]
    return (date(y, m, dim) + timedelta(days=d.day - dim)).isoformat() if d.day > dim else date(y, m, d.day).isoformat()


def next_every(p: dict, what: str, today: date, o: dict) -> str | None:
    months = p.get(what)
    if not months:
        return None
    frm = last(p, what) or p.get("added") or today.isoformat()
    due, t = _set_month(frm, int(months)), today.isoformat()
    if due < t and not growing(t, o):
        due = t
    for _ in range(400):
        if growing(due, o):
            break
        due = _plus(due, 1)
    return due


def due_of(p: dict, what: str, today: date, o: dict) -> str | None:
    return next_water(p, today, o) if what == "water" else next_feed(p, today, o) if what == "feed" else next_every(p, what, today, o)


def log(p: dict, what: str, today: date) -> bool:
    if what not in ("water", "feed", "snooze", "repot", "prune"):
        return False
    p["log"] = (list(p.get("log") or []) + [{"d": today.isoformat(), "what": what}])[-200:]
    return True


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    names = [str(e["item"].get("name") or "Plant") for e in ents]
    today, t, todo, cal = now.date(), now.date().isoformat(), [], []
    for e in ents:
        p, dev, o = e["item"], e["key"], options(e["data"])
        pname = str(p.get("name") or "Plant")
        if names.count(pname) > 1:
            pname += f" ({p.get('room')})" if p.get("room") else f" ({e['owner']})" if e["owner"] else ""
        out.add_device(Device(dev, pname, "Plant", via=APP))
        for what, (icon, label) in JOBS.items():
            d = due_of(p, what, today, o)
            if d is None:
                continue
            if d <= t:
                todo.append(f"{label} {p.get('name') or 'Plant'}")
            attrs = {"date": d, "last": last(p, what), "room": p.get("room") or None, **({"season": season(t, o)} if what == "water" else {}), **who(e)}
            out.add(Thing(f"{dev}.{what}", dev, SENSOR, DAYS, f"plant_{what}", (ymd(d) - today).days, {}, attrs,
                          {"water": "mdi:watering-can", "feed": "mdi:flask", "repot": "mdi:pot-mix", "prune": "mdi:content-cut"}[what]))
            if e["target"] and what in ("water", "feed"):
                out.add(Thing(f"{dev}.{what}.done", dev, BUTTON, PRESS, f"plant_{what}_done", None, {}, {}, "mdi:check-circle-outline", app=APP,
                              data={"target": e["target"], "do": what}))
            cal.append({"plant": pname, "em": p.get("em") or "🪴", "what": what, "date": d, "id": p.get("id")})
        if e["target"]:
            out.add(Thing(f"{dev}.snooze", dev, BUTTON, PRESS, "plant_not_yet", None, {}, {}, "mdi:clock-plus-outline", app=APP,
                          data={"target": e["target"], "do": "snooze"}))
    out.add(Thing(f"{APP}.today", APP, SENSOR, COUNT, "plants_today", len(todo), {}, {"jobs": todo}, "mdi:sprout"))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "plant_calendar", None, icon="mdi:sprout", app=APP, data={"items": cal}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def press(p: dict, act: dict, by: str, now_ms: int, new_id: str) -> bool:
    return log(p, act["do"], datetime.fromtimestamp(now_ms / 1000).date())


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    """Each plant's next water, feed, repot and prune (the next one only: the app works each out from when it was last done)."""
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date().isoformat(), end.astimezone(tz).date().isoformat()
    for x in data.get("items") or []:
        if a <= x["date"] <= b:
            d = ymd(x["date"])
            out.append(Event(f"{x['id']}-{x['what']}-{x['date']}", f"{JOBS[x['what']][0]} {JOBS[x['what']][1]} {x['plant']}", d, d + timedelta(days=1)))
    return sorted(out, key=lambda e: e.start)
