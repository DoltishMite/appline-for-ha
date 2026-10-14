"""Countline (countdowns) -> entities. Pure Python.

Saved data (web/countline/APP.md): countline_events_v1 [{ id, name, emoji, date 'YYYY-MM-DD', time 'HH:MM' (optional), repeat
('' | week | 2week | month | lastwork | year), day0 (the day of the month it started on), pinned, at }].
next_date() / over() / roll() port countdown.html nextDate / over / rollRepeats (the app moves a repeating countdown on to its next
date once it has passed): keep them the same. A countdown is its own day (no time) or a moment (with a time).
Entities on the Countline device: per countdown, how long until it (days) and when it is (timestamp); a calendar of them all.
"""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from .common import at, household, share_codes as _share_codes, single, who, ymd
from .model import CALENDAR, DAYS, EVENTS, SENSOR, TIMESTAMP, Device, Event, Parsed, Thing

APP, NAME = "countline", "Countline"
LIST_KEY = "countline_events_v1"


def _last_weekday(y: int, m: int) -> date:
    """The last Monday-to-Friday of month m (1-12)."""
    d = date(y, m, monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def next_date(e: dict) -> date | None:
    d0 = ymd(e.get("date"))
    if d0 is None:
        return None
    y, m, d = d0.year, d0.month, d0.day
    rep = e.get("repeat")
    if rep in ("week", "2week"):
        return d0 + timedelta(days=7 if rep == "week" else 14)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)   # next month
    if rep == "lastwork":
        return _last_weekday(ny, nm)
    if rep == "month":
        want = int(e.get("day0") or d)
        return date(ny, nm, min(want, monthrange(ny, nm)[1]))
    if rep == "year":
        if e.get("day0") and m == 2:
            return date(y + 1, 2, min(int(e["day0"]), monthrange(y + 1, 2)[1]))
        return date(y + 1, m, 1) + timedelta(days=d - 1)   # as JS's Date: 29 Feb in a common year rolls to 1 Mar
    return d0


def moment(e: dict, tz) -> datetime | None:
    return at(ymd(e.get("date")), e.get("time") or "00:00", tz)


def over(e: dict, now: datetime) -> bool:
    d = ymd(e.get("date"))
    if d is None:
        return False
    days = (d - now.date()).days
    return days < 0 or (days == 0 and bool(e.get("time")) and moment(e, now.tzinfo) < now)


def roll(e: dict, now: datetime) -> dict:
    """A repeating countdown moved on to its next date (as the app does on opening)."""
    e = dict(e)
    if not e.get("repeat") or not e.get("date"):
        return e
    for _ in range(600):
        if not over(e, now):
            break
        n = next_date(e)
        if n is None or n.isoformat() == e["date"]:
            break
        e["date"] = n.isoformat()
    return e


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    cal = []
    for e in ents:
        ev = roll(e["item"], now)
        d = ymd(ev.get("date"))
        if d is None:
            continue
        ph = {"name": str(ev.get("name") or "Countdown")}
        attrs = {"date": ev.get("date"), "time": ev.get("time") or None, "repeat": ev.get("repeat") or None, "emoji": ev.get("emoji"),
                 "passed": over(ev, now), **who(e)}
        out.add(Thing(f"{e['key']}.days", APP, SENSOR, DAYS, "countdown_days", (d - now.date()).days, ph, attrs, "mdi:timer-sand"))
        out.add(Thing(f"{e['key']}.at", APP, SENSOR, TIMESTAMP, "countdown_at", moment(ev, now.tzinfo), ph, {}, "mdi:calendar-clock"))
        cal.append(ev)
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "countdown_calendar", None, icon="mdi:timer-sand", app=APP,
                  data={"events": cal}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    """Each countdown on its day (a repeating one on each of its dates in the window)."""
    tz, out = now.tzinfo, []
    as_dt = lambda x: x if isinstance(x, datetime) else datetime.combine(x, datetime.min.time(), tzinfo=tz)
    for ev in data.get("events") or []:
        e = dict(ev)
        for _ in range(400):
            d = ymd(e.get("date"))
            if d is None:
                break
            s, f = (moment(e, tz), moment(e, tz) + timedelta(hours=1)) if e.get("time") else (d, d + timedelta(days=1))
            if as_dt(s) >= end:
                break
            if as_dt(f) > start:
                out.append(Event(f"{ev.get('id')}-{d.isoformat()}", f"{e.get('emoji') + ' ' if e.get('emoji') else ''}{e.get('name') or 'Countdown'}", s, f))
            n = next_date(e) if e.get("repeat") else None
            if n is None or n.isoformat() == e["date"]:
                break
            e["date"] = n.isoformat()
    return sorted(out, key=lambda x: as_dt(x.start))
