"""Carline (car dates & costs) -> devices and entities. Pure Python.

Saved data (web/carline/APP.md, car.html "data"): carline_cars_v1 [{ id, name, reg, icon, fuel, dues: [{ id, kind (mot | tax |
insurance | service | breakdown | warranty | lease | parking | other), name, date 'YYYY-MM-DD', months (comes round every N months,
0 = once), atMiles (service: also due at a mileage), note }], log: [{ id, date, kind, cost, miles, note }], odo: [{ date, miles }] }].
due_state() ports car.html dueState (over: date passed or mileage reached; soon: within 30 days or 1,000 miles); renew() ports
doneDialog with its defaults (renewals keep their anniversary, an MOT up to a month early keeps its date, a service counts from today,
a one-off goes; a mileage due moves on 10,000 miles; logged with no cost). Keep them the same.
Odometer readings are the car's own and the log's; Fuelline fill-ups and Chargeline charges (which the app adds when linked) aren't
sent to Home Assistant, so miles left can lag until a reading is added in Carline.
Devices: "Carline" (the app), and one per car. Entities per due date: days left (with miles left), a Renewed button; per car: the
latest mileage, a needs-attention sensor; a calendar of every car's dates.
"""
from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta

from .common import household, single, share_codes as _share_codes, who, ymd
from .model import BINARY, BUTTON, CALENDAR, DAYS, DISTANCE, EVENTS, PRESS, PROBLEM, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "carline", "Carline"
LIST_KEY = "carline_cars_v1"
KIND = {"mot": ("🔧", "MOT"), "tax": ("🪪", "Road tax"), "insurance": ("🛡", "Insurance"), "service": ("🛠", "Service"),
        "breakdown": ("🚨", "Breakdown cover"), "warranty": ("📜", "Warranty"), "lease": ("📄", "Finance or lease"),
        "parking": ("🅿️", "Parking permit"), "other": ("📌", "Other")}
LOGK = {"service", "mot", "repair", "tyres", "tax", "insurance", "breakdown", "parts", "wash", "parking", "fuel", "charge", "other"}
ANNIV = {"tax", "insurance", "breakdown", "parking", "lease"}
# car.html SPECS (the Details tab): key → label
SPECS = {"make": "Make", "model": "Model", "year": "Year", "colour": "Colour", "engine": "Engine", "gearbox": "Gearbox", "vin": "VIN / chassis",
         "tyres": "Tyre size", "pressures": "Tyre pressures", "oil": "Oil", "fuelcap": "Tank / battery", "wipers": "Wiper blades", "bulbs": "Bulbs",
         "radio": "Radio / alarm code", "keys": "Spare key", "insurer": "Insurer and policy", "breakdown": "Breakdown cover", "garage": "Garage"}
ICONS = {"mot": "mdi:car-wrench", "tax": "mdi:card-account-details", "insurance": "mdi:shield-car", "service": "mdi:oil",
         "breakdown": "mdi:tow-truck", "warranty": "mdi:file-certificate", "lease": "mdi:file-document", "parking": "mdi:parking"}


def add_months(s: str, n: int) -> str:
    d = ymd(s)
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1])).isoformat()


def readings(c: dict) -> list[dict]:
    r = [{"date": o.get("date"), "miles": _num(o.get("miles"))} for o in c.get("odo") or [] if isinstance(o, dict)]
    r += [{"date": l.get("date"), "miles": _num(l.get("miles"))} for l in c.get("log") or [] if isinstance(l, dict) and l.get("miles")]
    r = [x for x in r if x["miles"] and x["miles"] > 0 and isinstance(x["date"], str)]
    return sorted(r, key=lambda x: (x["date"], x["miles"]))


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def name_of(d: dict) -> str:
    return d.get("name") or KIND.get(d.get("kind"), KIND["other"])[1]


def due_state(c: dict, d: dict, today: date) -> dict | None:
    when = ymd(d.get("date"))
    if when is None:
        return None
    left = (when - today).days
    r = readings(c)
    lo = r[-1] if r else None
    at = _num(d.get("atMiles"))
    miles_left = at - lo["miles"] if at and lo else None
    over = left < 0 or (miles_left is not None and miles_left <= 0)
    soon = left <= 30 or (miles_left is not None and miles_left <= 1000)
    return {"left": left, "miles_left": miles_left, "state": "over" if over else "soon" if soon else "ok"}


def renew(car: dict, due_id: str, today: date, new_id: str, by: str = "") -> bool:
    """The app's Done / Renewed with its defaults: a log entry, and the date moved on (or a one-off removed)."""
    d = next((x for x in car.get("dues") or [] if isinstance(x, dict) and x.get("id") == due_id), None)
    if d is None or not ymd(d.get("date")):
        return False
    t, kind, months = today.isoformat(), d.get("kind"), int(d.get("months") or 0)
    left = (ymd(d["date"]) - today).days
    keep = kind in ANNIV or (kind == "mot" and 0 <= left <= 30)
    nxt = add_months(d["date"] if keep else t, months) if months else ""
    while keep and nxt and nxt < t:
        nxt = add_months(nxt, months)
    note = " · ".join(x for x in ["" if kind in LOGK else name_of(d), f"via Home Assistant{' (' + by + ')' if by else ''}"] if x)[:80]
    car["log"] = list(car.get("log") or []) + [{"id": new_id, "date": t, "kind": kind if kind in LOGK else "other", "cost": 0, "miles": None, "note": note}]
    if months:
        d["date"] = nxt
        if d.get("atMiles"):
            d["atMiles"] = int(_num(d["atMiles"]) + 10000)
    else:
        car["dues"] = [x for x in car["dues"] if x is not d]
    return True


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    names = [str(e["item"].get("name") or "Car") for e in ents]
    today, cal = now.date(), []
    for e in ents:
        c, dev = e["item"], e["key"]
        cname = str(c.get("name") or "Car")
        if names.count(cname) > 1:
            cname += f" ({e['owner']})" if e["owner"] else " (shared)"
        out.add_device(Device(dev, cname, "Car", via=APP))
        attention = []
        for d in c.get("dues") or []:
            if not isinstance(d, dict) or not isinstance(d.get("id"), str):
                continue
            s = due_state(c, d, today)
            if s is None:
                continue
            dname = name_of(d)
            if s["state"] != "ok":
                attention.append(dname)
            attrs = {"car": c.get("name"), "reg": c.get("reg") or None, "kind": d.get("kind"), "date": d.get("date"), "state": s["state"],
                     "miles_left": round(s["miles_left"]) if s["miles_left"] is not None else None, "at_miles": d.get("atMiles") or None,
                     "every_months": d.get("months") or None, "note": d.get("note") or None, **who(e)}
            ph = {"due": dname}
            out.add(Thing(f"{dev}.{d['id']}.days", dev, SENSOR, DAYS, "car_due_days", s["left"], ph, attrs, ICONS.get(d.get("kind"), "mdi:car-clock")))
            if e["target"]:
                out.add(Thing(f"{dev}.{d['id']}.renew", dev, BUTTON, PRESS, "car_due_renew", None, ph, {}, "mdi:check-circle-outline", app=APP,
                              data={"target": e["target"], "due": d["id"]}))
            cal.append({"car": cname, "due": d, "state": s["state"]})
        r = readings(c)
        out.add(Thing(f"{dev}.odo", dev, SENSOR, DISTANCE, "car_mileage", round(r[-1]["miles"]) if r else None, {}, {"as_of": r[-1]["date"] if r else None}, "mdi:counter"))
        out.add(Thing(f"{dev}.attention", dev, BINARY, PROBLEM, "car_attention", bool(attention), {}, {"due": attention}))
        # the Details tab and notes: the registration as the state, every detail filled in (and the notes) as attributes
        specs = c.get("specs") if isinstance(c.get("specs"), dict) else {}
        details = {label: str(specs[k]) for k, label in SPECS.items() if specs.get(k)}
        out.add(Thing(f"{dev}.details", dev, SENSOR, "text", "car_details", (c.get("reg") or " ".join(x for x in (specs.get("make"), specs.get("model")) if x) or cname)[:255], {},
                      {"fuel": c.get("fuel"), **details, "notes": str(c.get("notes") or "") or None}, "mdi:card-text-outline"))
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "car_calendar", None, icon="mdi:car-clock", app=APP, data={"items": cal}))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def press(car: dict, act: dict, by: str, now_ms: int, new_id: str) -> bool:
    today = datetime.fromtimestamp(now_ms / 1000).date()
    return renew(car, act["due"], today, new_id, by)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date(), end.astimezone(tz).date()
    for x in data.get("items") or []:
        d = x["due"]
        when = ymd(d.get("date"))
        if when and a <= when <= b:
            icon = KIND.get(d.get("kind"), KIND["other"])[0]
            out.append(Event(f"{d['id']}-{when.isoformat()}", f"{icon} {x['car']}: {name_of(d)}", when, when + timedelta(days=1), str(d.get("note") or "")))
    return sorted(out, key=lambda e: e.start)
