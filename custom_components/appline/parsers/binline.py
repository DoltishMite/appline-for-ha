"""Binline (bin collection days) -> entities. Pure Python.

Saved data (web/binline/APP.md, bins.html): binline_bins_v1 [{ id, name, colour, icon, first 'YYYY-MM-DD' (one collection from the
council's calendar), every (1-4 weeks), note, pauseFrom, pauseTo }], binline_changes_v1 [{ date, bin (id | '*'), skip: true | move:
'YYYY-MM-DD' }], binline_options_v1 { holidayShift (true), division (england-and-wales | scotland | northern-ireland), putOutEvening
(true), outFor (the collection date marked "They're out") }, binline_bank_holidays_v1 { at, d: gov.uk's bank-holidays.json }.
collections() ports bins.html collections(from, days) exactly (calendar-day steps from `first`, one-off skips and moves, pauses, a bank
holiday on or before collection day in the same week pushing it a day later); put_out() its "Put out tonight" banner (from noon the day
before, or before 9 on the day, until marked out). Keep them the same.
Entities on the Binline device: the next collection (days until, which bins), per bin its next collection, Put out tonight, a calendar.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from .common import household, js, share_codes as _share_codes, single, ymd
from .model import BINARY, BUTTON, CALENDAR, DAYS, EVENTS, PRESS, SENSOR, Device, Event, Parsed, Thing

APP, NAME = "binline", "Binline"
LIST_KEY, CHANGES, OPTS, HOLS, OUT = "binline_bins_v1", "binline_changes_v1", "binline_options_v1", "binline_bank_holidays_v1", "binline_out_v1"
DAY = timedelta(days=1)


def options(data: dict[str, str]) -> dict:
    o = js(data.get(OPTS), {})
    o = o if isinstance(o, dict) else {}
    return {"holidayShift": o.get("holidayShift", True) is not False, "division": o.get("division") or "england-and-wales",
            "putOutEvening": o.get("putOutEvening", True) is not False, "outFor": o.get("outFor") or ""}


def clean(b: dict, today: date) -> dict | None:
    """As cleanBin: a bin needs a name; every is 1-4 weeks (else 2); a missing first date is today."""
    if not isinstance(b, dict) or not b.get("name"):
        return None
    every = b.get("every")
    try:
        every = int(every)
    except (TypeError, ValueError):
        every = 2
    first = b.get("first") if ymd(b.get("first")) else today.isoformat()
    ok = lambda s: s if ymd(s) else ""
    return dict(b, every=every if every in (1, 2, 3, 4) else 2, first=first, pauseFrom=ok(b.get("pauseFrom")), pauseTo=ok(b.get("pauseTo")))


def _midnight(d: date, tz) -> datetime:
    return datetime.combine(d, time(0), tzinfo=tz)


def _plus(dt: datetime, td: timedelta) -> datetime:
    """dt + td in real elapsed time (as JS's new Date(+d + ms)), not on the wall clock."""
    return (dt.astimezone(timezone.utc) + td).astimezone(dt.tzinfo)


def collections(bins: list[dict], changes: list[dict], opts: dict, hols: dict | None, start: date, days: int, tz) -> list[dict]:
    """[{ date, bins: [bin], notes: [text] }] from start for `days`, sorted (bins in their saved order)."""
    frm = _midnight(start, tz)
    to = _plus(frm, days * DAY)
    events = ((hols or {}).get("d") or {}).get(opts["division"]) or {}
    hol = {e.get("date"): e for e in events.get("events") or [] if isinstance(e, dict)}
    out: dict[str, dict] = {}
    for b in bins:
        step, f = b["every"] * 7, ymd(b["first"])
        fm = _midnight(f, tz)
        diff = round((frm - fm).total_seconds() / 86400)
        k = -((-(diff - 7)) // step)   # ceil((diff - 7) / step), a week early so a moved collection isn't missed
        while True:
            d = f + timedelta(days=k * step)
            if _midnight(d, tz) >= _plus(to, 7 * DAY):
                break
            k += 1
            base = d.isoformat()
            ch = next((c for c in changes if isinstance(c, dict) and c.get("date") == base and c.get("bin") in (b["id"], "*")), None)
            if ch and ch.get("skip"):
                continue
            if b["pauseFrom"] and base >= b["pauseFrom"] and (not b["pauseTo"] or base <= b["pauseTo"]):
                continue
            note = ""
            if ch and ch.get("move") and ymd(ch["move"]):
                d, note = ymd(ch["move"]), "moved"
            elif opts["holidayShift"]:
                mon = d - timedelta(days=d.weekday())
                x = mon
                while x <= d:
                    h = hol.get(x.isoformat())
                    if h:
                        d, note = d + DAY, f"a day late: {h.get('title')}"
                        break
                    x += DAY
            if frm <= _midnight(d, tz) < to:
                e = out.setdefault(d.isoformat(), {"date": d, "bins": [], "notes": []})
                if b["id"] not in e["bins"]:
                    e["bins"].append(b["id"])
                if note and note not in e["notes"]:
                    e["notes"].append(note)
    order = [b["id"] for b in bins]
    res = sorted(out.values(), key=lambda e: e["date"])
    for e in res:
        e["bins"] = [b for b in bins if b["id"] in e["bins"]]
        e["bins"].sort(key=lambda b: order.index(b["id"]))
    return res


def put_out(next_c: dict | None, now: datetime, opts: dict) -> bool:
    if not next_c:
        return False
    n = (next_c["date"] - now.date()).days
    tonight = (opts["putOutEvening"] and n == 1 and now.hour >= 12) or (n == 0 and now.hour < 9)
    return bool(tonight and opts["outFor"] != next_c["date"].isoformat())


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return _share_codes(data, APP)


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def _sig(b: dict) -> str:
    """The same real bin in two people's Binline: same name, same collection date and how often."""
    import hashlib
    return hashlib.sha256(f"{str(b.get('name') or '').strip().lower()}|{b.get('first')}|{b.get('every')}".encode()).hexdigest()[:12]


def out_log(data: dict[str, str]) -> list[dict]:
    v = js(data.get(OUT), [])
    return [x for x in v if isinstance(x, dict) and ymd(x.get("date"))] if isinstance(v, list) else []


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    """Bins are nobody's to share (the app has no 👥 Share), so two people living together each have the same bins: a bin with the
    same name, date and how often is shown once, with who has it, and marked out when anyone marks it."""
    out.add_device(Device(APP, app_name or NAME, NAME))
    today, tz = now.date(), now.tzinfo
    groups: dict[int, tuple[dict, list]] = {}
    for e in ents:
        groups.setdefault(id(e["data"]), (e["data"], []))[1].append(e)
    merged: dict[str, dict] = {}            # signature → { bin, next, notes, people, owners, data }
    days: dict[str, dict] = {}              # collection day → { bins: {sig: bin}, notes }
    outs, targets, logs = set(), [], []
    for data, es in groups.values():
        opts, changes = options(data), js(data.get(CHANGES), [])
        changes = changes if isinstance(changes, list) else []
        hols = js(data.get(HOLS), None)
        bins = [b for b in (clean(dict(e["item"]), today) for e in es) if b]
        owner = {e["item"]["id"]: e for e in es}
        cs = collections(bins, changes, opts, hols if isinstance(hols, dict) else None, today, 120, tz)
        if opts["outFor"]:
            outs.add(opts["outFor"])
        for x in out_log(data):
            outs.add(x["date"])
            logs.append(dict(x, _who=x.get("by") or (es[0].get("owner") or "")))
        t0 = es[0]["target"]
        if t0 and t0[0] == "link":
            targets.append(["link", t0[1], APP, None, OUT])
        for b in bins:
            sig = _sig(b)
            e = owner[b["id"]]
            nx = next((c for c in cs if any(x["id"] == b["id"] for x in c["bins"])), None)
            m = merged.setdefault(sig, {"bin": b, "next": nx, "people": [], "e": e})
            if e.get("owner") and e["owner"] not in m["people"]:
                m["people"].append(e["owner"])
            if nx and (m["next"] is None or nx["date"] < m["next"]["date"]):
                m["next"] = nx
        for c in cs:
            d = days.setdefault(c["date"].isoformat(), {"bins": {}, "notes": []})
            for b in c["bins"]:
                d["bins"].setdefault(_sig(b), b)
            d["notes"] += [n for n in c["notes"] if n not in d["notes"]]
    for sig, m in merged.items():
        b, nx = m["bin"], m["next"]
        who_ = {"owner": m["people"][0]} if len(m["people"]) == 1 else {"shared_with": m["people"]} if m["people"] else {}
        attrs = {"date": nx["date"].isoformat() if nx else None, "colour": b.get("colour"), "icon": b.get("icon"), "every_weeks": b["every"],
                 "paused": bool(b["pauseFrom"]), "note": (", ".join(nx["notes"]) if nx else "") or None, **who_}
        key = f"{APP}.{sig}" if m["e"]["target"] else m["e"]["key"]
        out.add(Thing(f"{key}.next", APP, SENSOR, DAYS, "bin_next", (nx["date"] - today).days if nx else None, {"name": str(b.get("name"))}, attrs, "mdi:trash-can"))
    upcoming = sorted(days)
    if upcoming:
        nd = upcoming[0]
        names = [str(b.get("name")) for b in days[nd]["bins"].values()]
        n = (ymd(nd) - today).days
        any_opts = [options(d) for d, _ in groups.values()]
        tonight = (any(o["putOutEvening"] for o in any_opts) and n == 1 and now.hour >= 12) or (n == 0 and now.hour < 9)
        out.add(Thing(f"{APP}.next", APP, SENSOR, DAYS, "bins_next", n, {}, {"date": nd, "bins": names, "out": nd in outs}, "mdi:delete-clock"))
        out.add(Thing(f"{APP}.put_out", APP, BINARY, "put_out", "bins_put_out", bool(tonight and nd not in outs), {}, {"bins": names, "date": nd}, "mdi:delete-restore"))
        if targets:
            out.add(Thing(f"{APP}.out", APP, BUTTON, PRESS, "bins_out", None, {}, {"date": nd, "bins": names}, "mdi:delete-circle", app=APP,
                          data={"targets": targets, "date": nd}))
    cal = [{"date": d, "bins": [(b.get("icon") or "") + " " + str(b.get("name")) for b in v["bins"].values()], "notes": v["notes"]} for d, v in sorted(days.items())]
    out.add(Thing(f"{APP}.calendar", APP, CALENDAR, EVENTS, "bin_calendar", None, icon="mdi:trash-can", app=APP, data={"days": cal, "out": logs}))


def press(log: list, act: dict, by: str, now_ms: int, new_id: str) -> bool:
    """They're out: the collection on act['date'] marked out (as the app's button), once."""
    if any(isinstance(x, dict) and x.get("date") == act["date"] for x in log):
        return False
    log.append({"id": new_id, "date": act["date"], "t": now_ms, "by": by})
    del log[:-100]
    return True


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)


def events(data: dict, start: datetime, end: datetime, now: datetime, daily: bool = True) -> list[Event]:
    tz, out = now.tzinfo, []
    a, b = start.astimezone(tz).date(), end.astimezone(tz).date()
    for c in data.get("days") or []:
        d = ymd(c["date"])
        if d and a <= d <= b:
            out.append(Event(f"bins-{c['date']}-{len(out)}", "🗑 " + " + ".join(s.strip() for s in c["bins"]), d, d + DAY, ", ".join(c["notes"])))
    for x in data.get("out") or []:   # ✓ They're out, when it was marked (as the ticks in Petline's calendar)
        t = datetime.fromtimestamp(x["t"] / 1000, tz) if isinstance(x.get("t"), (int, float)) and x["t"] > 10**11 else None
        if t and start <= t < end:
            who_ = f" ({x['_who']})" if x.get("_who") else ""
            out.append(Event(f"out-{x.get('id')}", f"✓ Bins out{who_}", t, t + timedelta(minutes=15)))
    as_dt = lambda v: v if isinstance(v, datetime) else datetime.combine(v, time(0), tzinfo=tz)
    return sorted(out, key=lambda e: as_dt(e.start))
