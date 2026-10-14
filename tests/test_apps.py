"""Countline, Dayline (birthline), Renewline (deadline) and Listline: their ports agree with the apps' own code (parity, run in Node
on functions copied from each page), and their entities and changes."""
import json
import os
import random
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from conftest import SITE
from fixtures import NOW, TZ, ms
from parsers import birthline, countline, deadline, listline, parse_household
from parsers.model import Parsed

JS = Path(__file__).parent / "js" / "app-fns.mjs"
WEB = SITE / "web"
needs_site = pytest.mark.skipif(not shutil.which("node") or not WEB.exists(), reason="needs node and the apps' project")


def run_js(page: str, names: list[str], calls: list[dict], prelude: str = "", tmp=None) -> list:
    spec = tmp / "spec.json"
    spec.write_text(json.dumps({"names": names, "prelude": prelude, "calls": calls}), encoding="utf-8")
    r = subprocess.run(["node", str(JS), str(WEB / page), str(spec)], capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, TZ="Europe/London"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def moments(n=60, seed=1):
    rnd = random.Random(seed)
    base = datetime(2026, 1, 1, tzinfo=TZ)
    return [base + timedelta(minutes=rnd.randrange(0, 3 * 365 * 24 * 60)) for _ in range(n)]


# ---------- Countline ----------
def countdowns(seed=2):
    rnd = random.Random(seed)
    out = []
    for i in range(80):
        d = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 900))
        if rnd.random() < 0.15:
            d = date(2028, 2, 29)
        e = {"id": f"c{i}", "name": f"E{i}", "date": d.isoformat(), "repeat": rnd.choice(["", "week", "2week", "month", "lastwork", "year"])}
        if rnd.random() < 0.5:
            e["time"] = f"{rnd.randrange(24):02d}:{rnd.choice([0, 15, 30, 45]):02d}"
        if e["repeat"] in ("month", "year") and rnd.random() < 0.5:
            e["day0"] = rnd.choice([28, 29, 30, 31])
        out.append(e)
    return out


@needs_site
def test_countline_parity(tmp_path):
    evs, ats = countdowns(), moments(25)
    calls, want = [], []
    for at in ats:
        for e in evs:
            js_e = json.dumps(e)
            calls.append({"at": ms(at), "expr": f"(() => {{ const e = {js_e}; const r = [nextDate(e), over(e)]; "
                                                 f"for (let g = 0; g < 600 && e.repeat && over(e); g++){{ const n = nextDate(e); if (n === e.date) break; e.date = n; }} r.push(e.date); return r; }})()"})
            nd = countline.next_date(e)
            want.append([nd.isoformat() if nd else None, countline.over(e, at), countline.roll(e, at)["date"]])
    got = run_js("countline/countdown.html", ["pad", "ymdOf", "todayStr", "dnum", "days", "when", "over", "lastWeekday", "nextDate"], calls, tmp=tmp_path)
    bad = [(c["expr"][:80], g, w) for c, g, w in zip(calls, got, want) if g != w]
    assert not bad, bad[:5]


def test_countline_entities_and_calendar():
    data = {"countline_events_v1": json.dumps([
        {"id": "a", "name": "Holiday", "emoji": "🏖", "date": "2026-10-20"},
        {"id": "b", "name": "Payday", "date": "2026-09-30", "repeat": "lastwork"},
        {"id": "c", "name": "Gig", "date": "2026-10-14", "time": "11:00"}])}
    out = Parsed()
    countline.parse(data, {}, NOW, out)
    assert out.things["countline.a.days"].state == 6 and out.things["countline.a.days"].placeholders == {"name": "Holiday"}
    assert out.things["countline.b.days"].attrs["date"] == "2026-10-30"   # rolled on to the last weekday of October
    assert out.things["countline.c.days"].attrs["passed"] is True and out.things["countline.c.at"].state == NOW.replace(hour=11)
    ev = countline.events(out.things["countline.calendar"].data, NOW, NOW + timedelta(days=80), NOW)
    assert [e.summary for e in ev if "Payday" in e.summary] == ["Payday"] * 3     # Oct, Nov, Dec
    assert any(e.summary == "🏖 Holiday" and e.start == date(2026, 10, 20) for e in ev)


# ---------- Dayline ----------
def people(seed=3):
    rnd = random.Random(seed)
    out = [{"id": "leap", "name": "Lea", "kind": "birthday", "day": 29, "month": 2, "year": 2000}]
    for i in range(60):
        m = rnd.randrange(1, 13)
        out.append({"id": f"p{i}", "name": f"P{i}", "kind": rnd.choice(["birthday", "anniversary", "other"]), "month": m,
                    "day": rnd.randrange(1, [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1] + 1), "year": rnd.choice([None, 1980, 2010])})
    return out


@needs_site
@pytest.mark.parametrize("leap", ["feb28", "mar1"])
def test_dayline_next_parity(tmp_path, leap):
    ps, ats = people(), moments(30, seed=4)
    calls, want = [], []
    for at in ats:
        for p in ps:
            calls.append({"at": ms(at), "expr": f"(() => {{ const x = next({json.dumps(p)}); return [x.at, x.days, x.n]; }})()"})
            when, days, n = birthline.next_yearly(p, at.date(), leap)
            want.append([[when.year, when.month, when.day], days, n])
    got = run_js("birthline/" + next(f.name for f in (WEB / "birthline").glob("*.html")),
                 ["isLeap", "dayNum", "todayYMD", "onYear", "next"], calls, prelude=f"const opts = {{ leap: '{leap}' }}; const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];", tmp=tmp_path)
    bad = [(c["expr"][:70], g, w) for c, g, w in zip(calls, got, want) if g != w]
    assert not bad, bad[:5]


@needs_site
def test_dayline_starts_parity(tmp_path):
    rnd = random.Random(5)
    evs = []
    for i in range(60):
        d = date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 500))
        if rnd.random() < 0.2:   # month ends (29th-31st, where the month has them)
            d = date(d.year, d.month, min(rnd.choice([29, 30, 31]), [31, 29 if d.year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][d.month - 1]))
        e = {"id": f"e{i}", "title": f"T{i}", "date": d.isoformat(), "repeat": rnd.choice(["", "daily", "weekdays", "weekly", "fortnightly", "monthly", "yearly"])}
        if rnd.random() < 0.3:
            e["end"] = (d + timedelta(days=rnd.randrange(1, 4))).isoformat()
        if rnd.random() < 0.3:
            e["until"] = (d + timedelta(days=rnd.randrange(30, 400))).isoformat()
        if rnd.random() < 0.3:
            e["skip"] = [(d + timedelta(days=7 * k)).isoformat() for k in range(1, 4)]
        evs.append(e)
    windows = [(date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 600)), rnd.randrange(1, 120)) for _ in range(12)]
    calls, want = [], []
    for a, n in windows:
        b = a + timedelta(days=n)
        for e in evs:
            calls.append({"at": ms(NOW), "expr": f"starts({json.dumps(e)}, '{a.isoformat()}', '{b.isoformat()}')"})
            want.append(birthline.starts(e, a.isoformat(), b.isoformat()))
    page = "birthline/" + next(f.name for f in (WEB / "birthline").glob("*.html"))
    got = run_js(page, ["pad", "ymdOf", "parseD", "addDays", "starts"], calls, tmp=tmp_path)
    bad = [(c["expr"][:90], g, w) for c, g, w in zip(calls, got, want) if g != w]
    assert not bad, bad[:5]


def test_dayline_entities():
    data = {"birthline_people_v1": json.dumps([{"id": "p1", "name": "Max", "kind": "birthday", "day": 16, "month": 10, "year": 2015}]),
            "birthline_events_v1": json.dumps([{"id": "e1", "title": "Swimming", "icon": "🏊", "date": "2026-10-01", "time": "17:00", "endTime": "18:00", "repeat": "weekly"}])}
    out = Parsed()
    birthline.parse(data, {}, NOW, out)
    t = out.things["birthline.p1.days"]
    assert t.state == 2 and t.attrs["turning"] == 11 and t.placeholders == {"name": "Max", "kind": "birthday"}
    ev = birthline.events(out.things["birthline.calendar"].data, NOW.replace(hour=0), NOW + timedelta(days=8), NOW)
    assert [e.summary for e in ev] == ["🏊 Swimming", "🎂 Max (11)"]      # swimming on the 15th, the birthday on the 16th
    assert ev[0].start == datetime(2026, 10, 15, 17, 0, tzinfo=TZ) and ev[0].end == datetime(2026, 10, 15, 18, 0, tzinfo=TZ)
    assert ev[1].start == date(2026, 10, 16)


# ---------- Renewline ----------
@needs_site
def test_renewline_status_parity(tmp_path):
    rnd = random.Random(6)
    items = []
    for i in range(80):
        it = {"id": f"r{i}", "name": f"R{i}", "date": (date(2026, 6, 1) + timedelta(days=rnd.randrange(0, 400))).isoformat() if rnd.random() > 0.1 else ""}
        if rnd.random() < 0.3:
            it["renew"] = "auto"
        if rnd.random() < 0.15:
            it["snooze"] = (date(2026, 6, 1) + timedelta(days=rnd.randrange(0, 300))).isoformat()
        items.append(it)
    opts = {"warnDays": 21, "soonDays": 60}
    calls, want = [], []
    for at in moments(30, seed=7):
        for it in items:
            calls.append({"at": ms(at), "expr": f"[status({json.dumps(it)}), daysLeft({json.dumps(it)})]"})
            want.append([deadline.status(it, at.date(), opts), deadline.days_left(it, at.date())])
    got = run_js("deadline/renewals.html", ["DAY", "today0", "daysLeft", "daysTo", "isSnoozed", "status"], calls,
                 prelude=f"const opts = {json.dumps(opts)};", tmp=tmp_path)
    bad = [(c["expr"][:80], g, w) for c, g, w in zip(calls, got, want) if g != w]
    assert not bad, bad[:5]


def test_renewline_entities():
    data = {"deadline_items_v1": json.dumps([{"id": "a", "name": "Passport", "date": "2026-10-01"}, {"id": "b", "name": "Car tax", "date": "2026-10-30"},
                                             {"id": "c", "name": "Phone", "date": "2026-10-20", "renew": "auto"}, {"id": "d", "name": "Boiler", "date": "2027-06-01"}])}
    out = Parsed()
    deadline.parse(data, {}, NOW, out)
    st = {k: t.attrs["status"] for k, t in out.things.items() if k.endswith(".days")}
    assert st == {"deadline.a.days": "bad", "deadline.b.days": "warn", "deadline.c.days": "maint", "deadline.d.days": "ok"}
    assert out.things["deadline.a.days"].state == -13 and out.things["deadline.expired"].state == 1 and out.things["deadline.due"].state == 2
    assert out.things["deadline.attention"].state is True


# ---------- Listline ----------
def test_listline_lists_and_changes():
    lists = [{"id": "l1", "name": "Shopping", "kind": "shopping", "items": [{"id": "i1", "text": "2 milk", "done": False}, {"id": "i2", "text": "eggs", "done": True}],
              "repeat": {"milk": {"text": "milk", "every": 7, "last": "2026-10-01"}}},
             {"id": "l2", "name": "Jobs", "kind": "todo", "items": []}]
    sam = {"format": 1, "link": 1, "name": "Sam", "apps": {"listline": {"t": 0, "data": {"listline_lists_v1": json.dumps(lists)}}}}
    p = parse_household([("sam", sam)], {}, {}, NOW)
    t = p.things["listline.sam.l1.todo"]
    assert t.state == 1 and t.data["target"] == ["link", "sam", "listline", "l1"] and p.things["listline.sam.l1.left"].attrs["items"] == ["2 milk"]
    l1, l2 = lists[0], lists[1]
    assert listline.update_item(l1, "i1", None, True, "keep", 5, NOW.date()) and l1["items"][0]["done"] and l1["repeat"]["milk"]["last"] == NOW.date().isoformat()
    assert not listline.update_item(l1, "i1", None, True, "keep", 6, NOW.date())          # already done: nothing to change
    assert listline.new_item(l2, "h1", " Paint fence ", date(2026, 11, 1), 7) and l2["items"][0] == {"id": "h1", "text": "Paint fence", "due": "2026-11-01", "done": False, "at": 7}
    assert listline.new_item(l1, "h2", "bread", date(2026, 11, 1), 8) and l1["items"][-1]["due"] == ""     # shopping lists have no due dates
    assert not listline.new_item(l1, "h3", "   ", None, 9)
    assert listline.move_item(l1, "h2", None) and [i["id"] for i in l1["items"]] == ["h2", "i1", "i2"]
    assert listline.move_item(l1, "h2", "i2") and [i["id"] for i in l1["items"]] == ["i1", "i2", "h2"]
    assert listline.delete_items(l1, ["i2", "nope"]) and [i["id"] for i in l1["items"]] == ["i1", "h2"]
    assert listline.key("3x Milk ") == "milk" and listline.key("2 milk") == "milk"
