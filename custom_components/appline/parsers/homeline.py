"""Homeline (jobs around the house) -> devices and entities. Pure Python.

Saved data (web/homeline/home.html "data"): homeline_homes_v1 [{ id, name, jobs: [{ id, name, icon, every, unit (d | w | m | y),
first 'YYYY-MM-DD' (first due, until done once), snooze 'YYYY-MM-DD' (put off until), outdoor, note, hist: [{ id, date, who, cost,
note }] }] }]. next_of() / state_of() port home.html nextOf / stateOf (over; month = within two weeks; later); done() and later() its
Done (with no cost) and Later (a week). Keep them the same.
Devices: "Homeline" (the app) and one per home. Entities per job: days until due (with its state), Done and Later buttons; per home:
overdue and due-soon counts, needs attention; a calendar of every home's jobs.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .carline import add_months
from .common import household, share_codes as _share_codes, single, who, ymd
from .model import BINARY, BUTTON, CALENDAR, COUNT, DAYS, EVENTS, PRESS, PROBLEM, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "homeline", "Homeline"
LIST_KEY = "homeline_homes_v1"
UNITS = {"d": ("day", "days"), "w": ("week", "weeks"), "m": ("month", "months"), "y": ("year", "years")}


def _every(j: dict) -> int:
    try:
        return max(1, int(j.get("every") or 1))
    except (TypeError, ValueError):
        return 1


def step(day: str, j: dict, k: int = 1) -> str:
    u, n = j.get("unit"), _every(j)
    if u == "d":
        return (ymd(day) + timedelta(days=n * k)).isoformat()
    if u == "w":
        return (ymd(day) + timedelta(days=7 * n * k)).isoformat()
    return add_months(day, (12 if u == "y" else 1) * n * k)


def last_of(j: dict) -> dict | None:
    hist = [h for h in j.get("hist") or [] if isinstance(h, dict) and isinstance(h.get("date"), str)]
    best = None
    for h in hist:   # as reduce(…, h.date > a.date ? h : a): the first of equal dates wins
        if best is None or h["date"] > best["date"]:
            best = h
    return best


def next_of(j: dict, today: date) -> str:
    l = last_of(j)
    base = step(l["date"], j) if l else (j.get("first") or today.isoformat())
    return j["snooze"] if j.get("snooze") and j["snooze"] > base else base


def state_of(j: dict, today: date) -> dict:
    n = next_of(j, today)
    left = (ymd(n) - today).days
    return {"next": n, "left": left, "state": "over" if left < 0 else "month" if left <= 14 else "later"}


def _job(home: dict, job_id: str) -> dict | None:
    return next((j for j in home.get("jobs") or [] if isinstance(j, dict) and j.get("id") == job_id), None)


def done(home: dict, job_id: str, today: date, by: str, new_id: str) -> bool:
    j = _job(home, job_id)
    if j is None:
        return False
    j["hist"] = (list(j.get("hist") or []) + [{"id": new_id, "date": today.isoformat(), "who": (by or "")[:30], "cost": 0, "note": ""}])[-100:]
    j.pop("snooze", None)
    return True


def later(home: dict, job_id: str, today: date) -> bool:
    j = _job(home, job_id)
    if j is None:
        return False
    n, t = next_of(j, today), today.isoformat()
    j["snooze"] = (ymd(t if t > n else n) + timedelta(days=7)).isoformat()
    return True


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    names = [str(e["item"].get("name") or "Home") for e in ents]
    today, cal = now.date(), []
    for e in ents:
        h, dev = e["item"], e["key"]
        hname = str(h.get("name") or "Home")
        if names.count(hname) > 1:
            hname += f" ({e['owner']})" if e["owner"] else " (shared)"
        out.add_device(Device(dev, hname, "Home", via=APP))
        over, soon = [], []
        for j in h.get("jobs") or []:
            if not isinstance(j, dict) or not isinstance(j.get("id"), str):
                continue
            s = state_of(j, today)
            jname = str(j.get("name") or "Job")
            (over if s["state"] == "over" else soon if s["state"] == "month" else []).append(jname)
            l = last_of(j)
            n, unit = _every(j), UNITS.get(j.get("unit"), UNITS["m"])
            attrs = {"home": h.get("name"), "date": s["next"], "state": s["state"], "every": f"every {unit[0]}" if n == 1 else f"every {n} {unit[1]}",
                     "last_done": l["date"] if l else None, "done_by": (l.get("who") or None) if l else None, "outdoor": bool(j.get("outdoor")),
                     "put_off_until": j.get("snooze") or None, "note": j.get("note") or None, **who(e)}
            ph = {"job": jname}
            out.add(Thing(f"{dev}.{j['id']}.days", dev, SENSOR, DAYS, "home_job_days", s["left"], ph, attrs, "mdi:hammer-wrench"))
            if e["target"]:
                act = {"target": e["target"], "job": j["id"]}
                out.add(Thing(f"{dev}.{j['id']}.done", dev, BUTTON, PRESS, "home_job_done", None, ph, {}, "mdi:check-circle-outline", app=APP, data=dict(act, do="done")))
                out.add(Thing(f"{dev}.{j['id']}.later", dev, BUTTON, PRESS, "home_job_later", None, ph, {}, "mdi:clock-plus-outline", app=APP, data=dict(act, do="later")))
            cal.append({"home": hname, "job": j, "next": s["next"]})
        out.add(Thing(f"{dev}.overdue", dev, SENSOR, COUNT, "home_overdue", len(over), {}, {"jobs": over}, "mdi:alert-circle-outline"))
        out.add(Thing(f"{dev}.soon", dev, SENSOR, COUNT, "home_soon", len(soon), {}, {"jobs": soon}, "mdi:calendar-clock"))
        out.add(Thing(f"{dev}.attention", dev, BINARY, PROBLEM, "home_attention", bool(over), {}, {"overdue": over}))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "home_calendar", None, icon="mdi:home-clock", app=APP, data={"items": cal}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def press(home: dict, act: dict, by: str, now_ms: int, new_id: str) -> bool:
    today = datetime.fromtimestamp(now_ms / 1000).date()
    return later(home, act["job"], today) if act.get("do") == "later" else done(home, act["job"], today, by, new_id)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    """Each job on its next due day, then every time after it comes round in the window."""
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date().isoformat(), end.astimezone(tz).date().isoformat()
    for x in data.get("items") or []:
        j, d = x["job"], x["next"]
        for _ in range(400):
            if d > b:
                break
            if d >= a:
                day = ymd(d)
                out.append(Event(f"{j['id']}-{d}", f"{j.get('icon') or '🔧'} {x['home']}: {j.get('name') or 'Job'}", day, day + timedelta(days=1), str(j.get("note") or "")))
            d = step(d, j)
    return sorted(out, key=lambda e: e.start)
