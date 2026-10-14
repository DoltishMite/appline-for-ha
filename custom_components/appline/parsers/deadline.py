"""Renewline (renewals & expiry tracker; app id deadline) -> entities. Pure Python.

Saved data (web/deadline/APP.md): deadline_items_v1 [{ id, type, name, target, date 'YYYY-MM-DD' (when it runs out), group, cost,
period, renew ('auto' renews by itself), notes, snooze 'YYYY-MM-DD' }], deadline_options_v1 { warnDays (30), soonDays (90) }.
status() ports renewals.html status(): zz (snoozed) | unknown (no date) | bad (expired) | warn (within warnDays; maint if it renews
itself) | soon (within soonDays) | ok. Keep the two the same.
Entities on the Renewline device: per item, days left (with its state); how many have expired and how many are due soon; a
calendar of the dates.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .common import household, js, share_codes as _share_codes, single, who, ymd
from .model import BINARY, CALENDAR, COUNT, DAYS, EVENTS, PROBLEM, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "deadline", "Renewline"
LIST_KEY, OPTS = "deadline_items_v1", "deadline_options_v1"
STATES = ["bad", "warn", "maint", "soon", "ok", "zz", "unknown"]


def options(data: dict[str, str]) -> dict:
    o = js(data.get(OPTS), {})
    o = o if isinstance(o, dict) else {}
    num = lambda k, d: o[k] if isinstance(o.get(k), (int, float)) else d
    return {"warnDays": num("warnDays", 30), "soonDays": num("soonDays", 90)}


def days_left(it: dict, today: date) -> int | None:
    d = ymd(it.get("date"))
    return None if d is None else (d - today).days


def status(it: dict, today: date, opts: dict) -> str:
    sn = ymd(it.get("snooze"))
    if sn and (sn - today).days > 0:
        return "zz"
    n = days_left(it, today)
    if n is None:
        return "unknown"
    if n < 0:
        return "bad"
    if n <= opts["warnDays"]:
        return "maint" if it.get("renew") == "auto" else "warn"
    if n <= opts["soonDays"]:
        return "soon"
    return "ok"


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    today, bad, due, cal = now.date(), [], [], []
    for e in ents:
        it, o = e["item"], options(e["data"])
        st, n = status(it, today, o), days_left(it, today)
        name = str(it.get("name") or "Renewal")
        if st == "bad":
            bad.append(name)
        elif st in ("warn", "maint"):
            due.append(name)
        attrs = {"status": st, "date": it.get("date"), "type": it.get("type"), "group": it.get("group") or None, "cost": it.get("cost"),
                 "period": it.get("period"), "renews_itself": it.get("renew") == "auto", "snoozed_until": it.get("snooze") if st == "zz" else None, **who(e)}
        out.add(Thing(f"{e['key']}.days", APP, SENSOR, DAYS, "renewal_days", n, {"name": name}, attrs, "mdi:calendar-alert"))
        if it.get("date"):
            cal.append(it)
    out.add(Thing(f"{APP}.expired", APP, SENSOR, COUNT, "renewals_expired", len(bad), {}, {"items": bad}, "mdi:calendar-remove"))
    out.add(Thing(f"{APP}.due", APP, SENSOR, COUNT, "renewals_due", len(due), {}, {"items": due}, "mdi:calendar-alert"))
    out.add(Thing(f"{APP}.attention", APP, BINARY, PROBLEM, "renewals_attention", bool(bad or due), {}, {"expired": bad, "due": due}))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "renewal_calendar", None, icon="mdi:calendar-alert", app=APP, data={"items": cal}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date(), end.astimezone(tz).date()
    for it in data.get("items") or []:
        d = ymd(it.get("date"))
        if d and a <= d <= b:
            what = " (renews itself)" if it.get("renew") == "auto" else ""
            out.append(Event(f"{it['id']}-{d.isoformat()}", f"{it.get('name') or 'Renewal'} runs out{what}", d, d + timedelta(days=1), str(it.get("notes") or "")))
    return sorted(out, key=lambda x: x.start)
