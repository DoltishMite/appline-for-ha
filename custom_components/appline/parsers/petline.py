"""Petline (pet care & reminders) -> devices and entities. Pure Python.

The app's saved data (web/petline/APP.md, pets.html "data"):
  petline_pets_v1    [{ id, name, icon, notes, tasks: [{ id, name, icon, type: meal|cycle|appt, times, days, next, time, done, note }],
                        log: [{ id, task, t (ms), by }] }]
  petline_options_v1 { remindAt: 'HH:MM' (when a treatment or an appointment without a time is due), ... }
  petline_shared_v1  { <pet id>: { code, ... } }   a shared pet's share code (the kit's HPTogether)
status() is a port of pets.html status(): keep the two the same (states, the one-hour window for meals, 7 / 3 days for "soon").

Devices: "Petline" (the app), and one per pet under it. Entities, per task: its state (enum) and when it's next due (timestamp);
per pet: how many things need doing now, a "needs care" problem sensor and a calendar (off at first); for the app: the total and a
calendar of every pet's care (events() below: what was done, from the log, and what's coming, worked out the way status() does).
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any

from .model import BINARY, CALENDAR, COUNT, ENUM, EVENTS, PROBLEM, SENSOR, TIMESTAMP, Device, Event, Parsed, Thing

APP = "petline"
NAME = "Petline"
PETS, OPTS, SHARED = "petline_pets_v1", "petline_options_v1", "petline_shared_v1"
STATES = ["over", "late", "due", "soon", "later", "done"]
NEEDS = {"due", "late", "over"}

_ICONS = [("feed", "mdi:food-variant"), ("walk", "mdi:dog-side"), ("litter", "mdi:broom"), ("medic", "mdi:pill"),
          ("flea", "mdi:bug"), ("worm", "mdi:medication"), ("vacc", "mdi:needle"), ("nail", "mdi:content-cut"),
          ("groom", "mdi:shower-head"), ("weigh", "mdi:scale-bathroom"), ("clean", "mdi:spray-bottle"),
          ("insur", "mdi:shield-check"), ("vet", "mdi:stethoscope")]
_TYPE_ICON = {"meal": "mdi:clock-outline", "cycle": "mdi:calendar-sync", "appt": "mdi:calendar-clock"}


def _json(s: Any, default: Any) -> Any:
    if not isinstance(s, str):
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


def _ymd(s: Any) -> date | None:
    try:
        return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (TypeError, ValueError, IndexError):
        return None


def _at(day: date, hm: Any, tz) -> datetime | None:
    try:
        h, m = (int(x) for x in str(hm).split(":")[:2])
        return datetime.combine(day, time(h, m), tzinfo=tz)
    except ValueError:
        return None


def _icon(task: dict) -> str:
    n = str(task.get("name") or "").lower()
    for word, icon in _ICONS:
        if word in n:
            return icon
    return _TYPE_ICON.get(task.get("type"), "mdi:paw")


def status(pet: dict, task: dict, now: datetime, remind_at: str = "09:00") -> dict | None:
    """{ state, due (datetime or None), last (datetime or None), by, slot } or None for a task that can't be read."""
    tz = now.tzinfo
    today = now.date()
    day_of = lambda ms: datetime.fromtimestamp(ms / 1000, tz).date()
    logs = sorted((l for l in pet.get("log") or [] if isinstance(l, dict) and l.get("task") == task.get("id")
                   and isinstance(l.get("t"), (int, float))), key=lambda l: l["t"])
    last = logs[-1] if logs else None
    last_at = datetime.fromtimestamp(last["t"] / 1000, tz) if last else None
    done_today = [l for l in logs if day_of(l["t"]) == today]
    kind = task.get("type")

    if kind == "meal":
        times = sorted(str(t) for t in task.get("times") or [])
        n = len(done_today)
        if n >= len(times):
            nxt = _at(today + timedelta(days=1), times[0], tz) if times else None
            return {"state": "done", "due": nxt, "last": last_at, "by": done_today[-1].get("by") if done_today else None,
                    "slot": None}
        at = _at(today, times[n], tz)
        if at is None:
            return None
        hour = timedelta(hours=1)
        state = "late" if at + hour < now else "due" if at <= now + hour else "soon"
        return {"state": state, "due": at, "last": last_at, "by": done_today[n - 1].get("by") if n else None,
                "slot": f"{n + 1} of {len(times)}" if len(times) > 1 else None}

    if kind == "appt":
        d = _ymd(task.get("next"))
        if d is None:
            return None
        due = _at(d, task.get("time") or remind_at, tz)
        if task.get("done"):
            return {"state": "done", "due": due, "last": last_at, "by": last.get("by") if last else None, "slot": None}
        left = (d - today).days
        state = "over" if left < 0 else "due" if left == 0 else "soon" if left <= 7 else "later"
        return {"state": state, "due": due, "last": last_at, "by": None, "slot": None}

    # cycle: every N days from when it was last done (first due on "next")
    try:
        every = int(task.get("days") or 0)
    except (TypeError, ValueError):
        every = 0
    if last and day_of(last["t"]) == today:
        return {"state": "done", "due": _at(today + timedelta(days=every), remind_at, tz), "last": last_at,
                "by": last.get("by"), "slot": None}
    base = (day_of(last["t"]) + timedelta(days=every)) if last else (_ymd(task.get("next")) or today)
    left = (base - today).days
    state = "over" if left < 0 else "due" if left == 0 else "soon" if left <= 3 else "later"
    return {"state": state, "due": _at(base, remind_at, tz), "last": last_at, "by": last.get("by") if last else None,
            "slot": None}


def share_codes(data: dict[str, str]) -> dict[str, str]:
    """{ pet id: share code } for the pets this setup shares (read from the synced copy)."""
    s = _json(data.get(SHARED), {})
    return {pid: v["code"] for pid, v in (s.items() if isinstance(s, dict) else [])
            if isinstance(v, dict) and isinstance(v.get("code"), str) and v["code"]}


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    """A shared pet on its own (a share code entered in HA) as the app's saved data."""
    return {PETS: json.dumps([dict(item, id=item_id)])}


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    """Add Petline's devices and entities to out. shared: { pet id: the shared copy's item } (newer than the synced copy)."""
    pets = _json(data.get(PETS), [])
    shown = []
    opts = _json(data.get(OPTS), {})
    remind_at = opts.get("remindAt") if isinstance(opts, dict) and isinstance(opts.get("remindAt"), str) else "09:00"
    if not isinstance(pets, list):
        pets = []
    out.add_device(Device(APP, app_name or NAME, NAME))
    total = 0
    for pet in pets:
        if not isinstance(pet, dict) or not isinstance(pet.get("id"), str):
            continue
        pid = pet["id"]
        if isinstance(shared.get(pid), dict):
            pet = dict(shared[pid], id=pid)
        shown.append(pet)
        dev = f"{APP}.{pid}"
        out.add_device(Device(dev, str(pet.get("name") or "Pet"), "Pet", via=APP))
        todo = []
        for task in pet.get("tasks") or []:
            if not isinstance(task, dict) or not isinstance(task.get("id"), str):
                continue
            s = status(pet, task, now, remind_at)
            if s is None:
                continue
            tid, tname = task["id"], str(task.get("name") or "Task")
            if s["state"] in NEEDS:
                todo.append(tname)
            attrs = {"pet": pet.get("name"), "type": task.get("type"), "last_done": s["last"].isoformat() if s["last"] else None,
                     "done_by": s["by"], "due": s["due"].isoformat() if s["due"] else None}
            if s["slot"]:
                attrs["slot"] = s["slot"]
            if task.get("type") == "meal":
                attrs["times"] = sorted(task.get("times") or [])
            elif task.get("type") == "cycle":
                attrs["every_days"] = task.get("days")
            if task.get("note"):
                attrs["note"] = task.get("note")
            ph = {"task": tname}
            icon = _icon(task)
            out.add(Thing(f"{dev}.{tid}.status", dev, SENSOR, ENUM, "pet_task", s["state"], ph, attrs, icon, STATES))
            out.add(Thing(f"{dev}.{tid}.next", dev, SENSOR, TIMESTAMP, "pet_task_next", s["due"], ph, {}, "mdi:calendar-clock"))
        total += len(todo)
        out.add(Thing(f"{dev}.todo", dev, SENSOR, COUNT, "pet_todo", len(todo), {}, {"tasks": todo}, "mdi:paw"))
        out.add(Thing(f"{dev}.needs_care", dev, BINARY, PROBLEM, "pet_needs_care", bool(todo), {}, {"tasks": todo}))
        out.add(Thing(f"{dev}.calendar", dev, CALENDAR, EVENTS, "pet_calendar", None, icon="mdi:paw", app=APP,
                      data={"pets": [pet], "remind_at": remind_at, "prefix": False}, enabled=False))
    out.add(Thing(f"{APP}.todo", APP, SENSOR, COUNT, "pets_todo", total, {}, {}, "mdi:paw"))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "pets_calendar", None, icon="mdi:calendar-heart", app=APP,
                  data={"pets": shown, "remind_at": remind_at, "prefix": True}))


# ---------- the calendar ----------
MEAL_MINUTES, APPT_MINUTES, DONE_MINUTES = 30, 60, 15
MAX_DAYS = 400   # how far daily routines are repeated in one request


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    """Events between start and end (aware datetimes): ticks from the log (✓, who), and what's coming: each meal / walk slot
    (daily=True), treatments all day on the day they're due and then every N days, appointments. Something overdue sits on today."""
    tz = now.tzinfo
    today = now.date()
    out: list[Event] = []
    for pet in data.get("pets") or []:
        pre = f"{pet.get('name') or 'Pet'}: " if data.get("prefix") else ""
        pid = pet.get("id")
        tasks = {t["id"]: t for t in pet.get("tasks") or [] if isinstance(t, dict) and isinstance(t.get("id"), str)}
        for l in pet.get("log") or []:
            t = tasks.get(l.get("task")) if isinstance(l, dict) else None
            if not t or not isinstance(l.get("t"), (int, float)) or t.get("type") == "appt" or (t.get("type") == "meal" and not daily):
                continue
            at = datetime.fromtimestamp(l["t"] / 1000, tz)
            who = f" ({l['by']})" if l.get("by") else ""
            out.append(Event(f"{pid}-{l.get('id')}", f"✓ {pre}{t.get('name')}{who}", at, at + timedelta(minutes=DONE_MINUTES)))
        for t in tasks.values():
            s = status(pet, t, now, data.get("remind_at") or "09:00")
            if s is None:
                continue
            name, note = f"{pre}{t.get('name') or 'Task'}", str(t.get("note") or "")
            kind = t.get("type")
            if kind == "meal":
                if not daily:
                    continue
                times = sorted(str(x) for x in t.get("times") or [])
                done = sum(1 for l in pet.get("log") or [] if isinstance(l, dict) and l.get("task") == t["id"]
                           and isinstance(l.get("t"), (int, float)) and datetime.fromtimestamp(l["t"] / 1000, tz).date() == today)
                d, last = max(start.astimezone(tz).date(), today), min(end.astimezone(tz).date(), today + timedelta(days=MAX_DAYS))
                while d <= last:
                    for i, hm in enumerate(times):
                        if d == today and i < done:
                            continue   # already ticked (it's in the log)
                        at = _at(d, hm, tz)
                        if at:
                            out.append(Event(f"{pid}-{t['id']}-{d.isoformat()}-{i}", name, at, at + timedelta(minutes=MEAL_MINUTES), note))
                    d += timedelta(days=1)
            elif kind == "appt":
                d = _ymd(t.get("next"))
                label = ("✓ " if t.get("done") else "") + name
                if t.get("time"):
                    at = _at(d, t["time"], tz)
                    if at:
                        out.append(Event(f"{pid}-{t['id']}-{d.isoformat()}", label, at, at + timedelta(minutes=APPT_MINUTES), note))
                else:
                    out.append(Event(f"{pid}-{t['id']}-{d.isoformat()}", label, d, d + timedelta(days=1), note))
            else:
                if s["due"] is None:
                    continue
                d = s["due"].date()
                try:
                    every = int(t.get("days") or 0)
                except (TypeError, ValueError):
                    every = 0
                if d < today:   # overdue: on today, marked, then the cycle carries on from today
                    out.append(Event(f"{pid}-{t['id']}-over", f"{name} (overdue since {d.isoformat()})", today, today + timedelta(days=1), note))
                    d = today + timedelta(days=every) if every > 0 else None
                last = end.astimezone(tz).date()
                n = 0
                while d is not None and d <= last and n < 1000:
                    out.append(Event(f"{pid}-{t['id']}-{d.isoformat()}", name, d, d + timedelta(days=1), note))
                    if every <= 0:
                        break
                    d += timedelta(days=every)
                    n += 1

    def as_dt(x):
        return x if isinstance(x, datetime) else datetime.combine(x, time(0), tzinfo=tz)
    hit = [e for e in out if as_dt(e.end) > start and as_dt(e.start) < end]
    return sorted(hit, key=lambda e: (as_dt(e.start), e.summary))
