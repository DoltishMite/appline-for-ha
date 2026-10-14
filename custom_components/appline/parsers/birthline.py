"""Dayline (calendar: birthdays, anniversaries and events; app id birthline) -> entities. Pure Python.

Saved data (web/birthline/APP.md): birthline_people_v1 [{ id, name, kind (birthday | anniversary | other), day, month, year, notes }],
birthline_events_v1 [{ id, title, icon, date, end (multi-day), time / endTime (none = all day), repeat ('' | daily | weekdays | weekly
| fortnightly | monthly | yearly), until, skip [dates], where, notes }], birthline_options_v1 { leap: feb28 | mar1, soonDays }.
next_yearly() ports the page's onYear / next (29 February in other years: 28 Feb or 1 Mar), starts() its starts(e, a, b): keep them
the same. Entities on the Dayline device: per birthday or yearly date, days until it (with the age turning); a calendar of both.
"""
from __future__ import annotations

import json
from calendar import isleap, monthrange
from datetime import date, datetime, timedelta

from .common import at, household, js, share_codes as _share_codes, single, who, ymd
from .model import CALENDAR, DAYS, EVENTS, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "birthline", "Dayline"
PEOPLE, EVENTS_KEY, OPTS = "birthline_people_v1", "birthline_events_v1", "birthline_options_v1"
LIST_KEY = PEOPLE   # what Home Assistant changes (nothing yet: read-only)
KINDS = {"birthday": ("🎂", "Birthday"), "anniversary": ("💍", "Anniversary"), "other": ("📌", "Yearly date")}


def _leap(data) -> str:
    o = js(data.get(OPTS), {})
    return o.get("leap") if isinstance(o, dict) and o.get("leap") in ("feb28", "mar1") else "feb28"


def on_year(p: dict, y: int, leap: str) -> date:
    m, d = int(p["month"]), int(p["day"])
    if m == 2 and d == 29 and not isleap(y):
        return date(y, 3, 1) if leap == "mar1" else date(y, 2, 28)
    return date(y, m, d)


def next_yearly(p: dict, today: date, leap: str) -> tuple[date, int, int | None] | None:
    """(the next day it falls on, days until, the age or years turning then) — as the page's next(p)."""
    try:
        when = on_year(p, today.year, leap)
        if when < today:
            when = on_year(p, today.year + 1, leap)
    except (KeyError, TypeError, ValueError):
        return None
    n = when.year - int(p["year"]) if p.get("year") else None
    return when, (when - today).days, n


def starts(e: dict, a: str, b: str) -> list[str]:
    """The days event e starts on from a to b (YYYY-MM-DD, inclusive), as the page's starts(e, a, b)."""
    first = e.get("date")
    d0 = ymd(first)
    if d0 is None:
        return []
    end = ymd(e.get("end"))
    span = (end - d0).days if end and e.get("end") > first else 0
    frm = (ymd(a) - timedelta(days=span)).isoformat()
    stop = e["until"] if e.get("until") and e["until"] < b else b
    skip = e.get("skip") or []
    rep = e.get("repeat")
    if not rep:
        return [first] if frm <= first <= stop else []
    out = []
    if rep in ("monthly", "yearly"):
        y, m, dom = d0.year, d0.month - 1, d0.day
        for _ in range(2400):
            last = monthrange(y, m + 1)[1]
            s = date(y, m + 1, min(dom, last)).isoformat()
            if s > stop:
                break
            if s >= frm and s >= first and s not in skip and (dom <= last or rep == "monthly"):
                out.append(s)
            if rep == "monthly":
                m += 1
            else:
                y += 1
            if m > 11:
                m, y = 0, y + 1
        return out
    step = 7 if rep == "weekly" else 14 if rep == "fortnightly" else 1
    s = first
    if frm > first:
        gap = (ymd(frm) - d0).days
        s = (d0 + timedelta(days=(gap // step) * step)).isoformat()
    for _ in range(800):
        if s > stop:
            break
        if not (s < frm or s < first or s in skip) and not (rep == "weekdays" and ymd(s).weekday() >= 5):
            out.append(s)
        s = (ymd(s) + timedelta(days=step)).isoformat()
    return out


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {PEOPLE: json.dumps([dict(item, id=item_id)])}


def _emit(people_e: list[dict], events_e: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    today, yearly = now.date(), []
    for e in people_e:
        p, leap = e["item"], _leap(e["data"])
        nx = next_yearly(p, today, leap)
        if nx is None:
            continue
        when, days, n = nx
        icon, kind = KINDS.get(p.get("kind"), KINDS["other"])
        ph = {"name": str(p.get("name") or "Someone"), "kind": kind.lower()}
        attrs = {"date": when.isoformat(), "kind": p.get("kind") or "other", "turning": n if n is not None and n >= 0 else None, **who(e)}
        out.add(Thing(f"{e['key']}.days", APP, SENSOR, DAYS, "yearly_days", days, ph, attrs, "mdi:cake-variant" if p.get("kind") == "birthday" else "mdi:calendar-heart"))
        yearly.append({"item": p, "leap": leap, "icon": icon})
    evs = [e["item"] for e in events_e]
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "dayline_calendar", None, icon="mdi:calendar-star", app=APP,
                  data={"yearly": yearly, "events": evs}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, PEOPLE, data, shared), single(APP, EVENTS_KEY, data, {}), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, PEOPLE, people, refs, shared_items), household(APP, EVENTS_KEY, people, refs, shared_items), now, out, app_name)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    tz, out = now.tzinfo, []
    as_dt = lambda x: x if isinstance(x, datetime) else datetime.combine(x, datetime.min.time(), tzinfo=tz)
    a, b = start.astimezone(tz).date(), end.astimezone(tz).date()
    for y in data.get("yearly") or []:
        p = y["item"]
        for yr in range(a.year, b.year + 1):
            try:
                d = on_year(p, yr, y["leap"])
            except (KeyError, TypeError, ValueError):
                break
            if a <= d <= b:
                n = yr - int(p["year"]) if p.get("year") else None
                kind = KINDS.get(p.get("kind"), KINDS["other"])[1]
                title = f"{y['icon']} {p.get('name') or 'Someone'}" + (f" ({n})" if n and n > 0 else "") + ("" if p.get("kind") == "birthday" else f": {kind}")
                out.append(Event(f"{p['id']}-{d.isoformat()}", title, d, d + timedelta(days=1), str(p.get("notes") or "")))
    for e in data.get("events") or []:
        span = 0
        if ymd(e.get("end")) and e["end"] > e.get("date", ""):
            span = (ymd(e["end"]) - ymd(e["date"])).days
        for s in starts(e, a.isoformat(), b.isoformat()):
            d = ymd(s)
            title = f"{e.get('icon') + ' ' if e.get('icon') else ''}{e.get('title') or 'Event'}"
            if e.get("time"):
                st = at(d, e["time"], tz)
                fin = at(d + timedelta(days=span), e.get("endTime") or e["time"], tz)
                if fin is None or fin <= st:
                    fin = st + timedelta(hours=1)
            else:
                st, fin = d, d + timedelta(days=span + 1)
            if as_dt(fin) > start and as_dt(st) < end:
                out.append(Event(f"{e.get('id')}-{s}", title, st, fin, str(e.get("notes") or "")))
    return sorted(out, key=lambda x: as_dt(x.start))
