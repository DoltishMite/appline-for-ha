"""Homeline and Plantline: ports agree with the apps' own code (parity), and their entities and changes."""
import json
import random
from datetime import date, timedelta

from fixtures import NOW, ms
from parsers import homeline, parse_household, plantline
from parsers.model import Parsed
from test_apps import moments, needs_site, run_js


def jobs(seed=31):
    rnd = random.Random(seed)
    out = []
    for i in range(60):
        j = {"id": f"j{i}", "name": f"J{i}", "every": rnd.randrange(1, 7), "unit": rnd.choice(["d", "w", "m", "y"]), "hist": []}
        if rnd.random() < 0.5:
            j["first"] = (date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 600))).isoformat()
        for _ in range(rnd.randrange(0, 4)):
            j["hist"].append({"id": "h", "date": (date(2025, 6, 1) + timedelta(days=rnd.randrange(0, 500))).isoformat(), "who": "x"})
        if rnd.random() < 0.3:
            j["snooze"] = (date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 600))).isoformat()
        if rnd.random() < 0.15:
            j["hist"].append({"id": "h", "date": (date(2026, 1, 31) + timedelta(days=rnd.choice([0, 28, 59]))).isoformat()})   # month ends
        out.append(j)
    return out


@needs_site
def test_homeline_parity(tmp_path):
    js_, calls, want = jobs(), [], []
    for at in moments(12, seed=32):
        for j in js_:
            calls.append({"at": ms(at), "expr": f"(() => {{ const s = stateOf({json.dumps(j)}); return [s.next, s.left, s.state]; }})()"})
            s = homeline.state_of(j, at.date())
            want.append([s["next"], s["left"], s["state"]])
    got = run_js("homeline/home.html", ["pad", "ymd", "today", "parseD", "addDays", "addMonths", "daysBetween", "step", "lastOf", "nextOf", "stateOf"], calls, tmp=tmp_path)
    bad = [(c["expr"][:90], g, w) for c, g, w in zip(calls, got, want) if g != w]
    assert not bad, bad[:5]


def test_homeline_entities_and_buttons():
    home = {"id": "h1", "name": "Home", "jobs": [
        {"id": "boil", "name": "Boiler service", "icon": "🔥", "every": 1, "unit": "y", "hist": [{"id": "x", "date": "2025-10-01", "who": "Sam"}]},
        {"id": "smoke", "name": "Test the smoke alarms", "every": 1, "unit": "m", "first": "2026-10-20"},
        {"id": "gut", "name": "Clear the gutters", "every": 6, "unit": "m", "first": "2027-02-01"}]}
    sam = {"format": 1, "link": 1, "name": "Sam", "apps": {"homeline": {"t": 0, "data": {"homeline_homes_v1": json.dumps([home])}}}}
    p = parse_household([("sam", sam)], {}, {}, NOW)
    st = {k.split(".")[3]: (t.state, t.attrs["state"]) for k, t in p.things.items() if k.endswith(".days")}
    assert st == {"boil": (-13, "over"), "smoke": (6, "month"), "gut": (110, "later")}
    assert p.things["homeline.sam.h1.boil.days"].attrs["done_by"] == "Sam" and p.things["homeline.sam.h1.boil.days"].attrs["every"] == "every year"
    assert p.things["homeline.sam.h1.overdue"].state == 1 and p.things["homeline.sam.h1.soon"].state == 1 and p.things["homeline.sam.h1.attention"].state is True
    h = json.loads(json.dumps(home))
    assert homeline.later(h, "boil", NOW.date()) and h["jobs"][0]["snooze"] == "2026-10-21"   # overdue: a week from today
    assert homeline.done(h, "boil", NOW.date(), "Steve", "n1") and "snooze" not in h["jobs"][0]
    assert homeline.state_of(h["jobs"][0], NOW.date())["next"] == "2027-10-14" and h["jobs"][0]["hist"][-1]["who"] == "Steve"
    ev = homeline.events(p.things["homeline.calendar"].data, NOW, NOW + timedelta(days=70), NOW)
    assert [e.start.isoformat() for e in ev if "smoke" in e.summary] == ["2026-10-20", "2026-11-20", "2026-12-20"]


def plants(seed=41):
    rnd = random.Random(seed)
    out = []
    for i in range(50):
        p = {"id": f"p{i}", "name": f"P{i}", "water": rnd.choice([2, 3, 4, 5, 7, 10, 14, 21]), "feed": rnd.choice([0, 2, 4, 8]),
             "repot": rnd.choice([0, 0, 12, 24]), "prune": rnd.choice([0, 6, 12]), "log": []}
        if rnd.random() < 0.7:
            p["added"] = (date(2025, 1, 1) + timedelta(days=rnd.randrange(0, 600))).isoformat()
        for _ in range(rnd.randrange(0, 6)):
            p["log"].append({"d": (date(2025, 6, 1) + timedelta(days=rnd.randrange(0, 600))).isoformat(), "what": rnd.choice(["water", "water", "feed", "snooze", "repot", "prune"])})
        if rnd.random() < 0.15:
            p["log"].append({"d": "2026-01-31", "what": "repot"})   # a month end, for setMonth
        out.append(p)
    return out


@needs_site
def test_plantline_parity(tmp_path):
    for opts in ({"hemisphere": "N", "winter": 1.5}, {"hemisphere": "S", "winter": 2}, {"hemisphere": "N", "winter": 1.25}):
        o = plantline.options({"plantline_options_v1": json.dumps(opts)})
        calls, want = [], []
        for at in moments(10, seed=42):
            for p in plants():
                calls.append({"at": ms(at), "expr": f"(() => {{ const p = {json.dumps(p)}; return [nextWater(p), nextFeed(p), nextEvery(p, 'repot'), nextEvery(p, 'prune')]; }})()"})
                want.append([plantline.next_water(p, at.date(), o), plantline.next_feed(p, at.date(), o), plantline.next_every(p, "repot", at.date(), o), plantline.next_every(p, "prune", at.date(), o)])
        got = run_js("plantline/plants.html", ["pad", "ymd", "parse", "today", "addDays", "daysBetween", "season", "stretch", "growing", "last", "nextWater", "nextFeed", "nextEvery"],
                     calls, prelude=f"const opts = {json.dumps(opts)};", tmp=tmp_path)
        bad = [(c["expr"][:70], g, w) for c, g, w in zip(calls, got, want) if g != w]
        assert not bad, (opts, bad[:4])


def test_plantline_entities_and_buttons():
    p = {"id": "mon", "name": "Monstera", "em": "🪴", "room": "Lounge", "water": 7, "feed": 4, "added": "2026-03-01",
         "log": [{"d": "2026-10-05", "what": "water"}, {"d": "2026-08-01", "what": "feed"}]}
    out = Parsed()
    plantline.parse({"plantline_plants_v1": json.dumps([p])}, {}, NOW, out)
    # October is autumn: a 7-day gap stretches to round(7 × 1.25) = 9 days → 14 Oct; feeding was due 4 weeks after 1 August
    assert out.things["plantline.mon.water"].state == 0 and out.things["plantline.mon.water"].attrs["date"] == "2026-10-14"
    assert out.things["plantline.mon.feed"].attrs["date"] == "2026-08-29" and out.things["plantline.mon.feed"].state == -46
    assert out.things["plantline.today"].state == 2 and out.things["plantline.today"].attrs["jobs"] == ["Water Monstera", "Feed Monstera"]
    q2 = dict(p, log=[{"d": "2026-10-05", "what": "water"}, {"d": "2026-10-01", "what": "feed"}])
    assert plantline.next_feed(q2, NOW.date(), plantline.options({})) == "2027-03-01"   # due in November: waits for spring
    q = json.loads(json.dumps(p))
    assert plantline.log(q, "snooze", NOW.date()) and plantline.next_water(q, NOW.date(), plantline.options({})) == "2026-10-15"   # Not yet: tomorrow
    assert plantline.log(q, "water", NOW.date()) and plantline.next_water(q, NOW.date(), plantline.options({})) == "2026-10-23"
    assert not plantline.log(q, "dance", NOW.date())


def test_cookline_timers_and_meals():
    from parsers import cookline
    books = [{"id": "bk", "name": "Ours", "recipes": [{"id": "r1", "name": "Spaghetti Bolognese"}]}]
    week = {"2026-10-14": {"items": [{"meal": "Tea", "r": "r1", "serves": 4}, {"meal": "Breakfast", "text": "Porridge"}]},
            "2026-10-15": {"r": "", "text": "Curry"}}
    t_end = int((NOW + timedelta(minutes=10)).timestamp() * 1000)
    timers = [{"id": "t1", "name": "Pasta", "dur": 600, "end": t_end}, {"id": "t2", "name": "Eggs", "dur": 300, "end": int((NOW - timedelta(minutes=1)).timestamp() * 1000)},
              {"id": "t3", "name": "Proving", "dur": 3600, "left": 1200}]
    data = {"cookline_books_v1": json.dumps(books), "cookline_week_v1": json.dumps(week), "cookline_timers_v1": json.dumps(timers)}
    out = Parsed()
    cookline.parse(data, {}, NOW, out)
    assert out.things["cookline.timers"].state == 1 and out.things["cookline.timers"].attrs["paused"] == ["Proving"]
    assert out.things["cookline.timer_next"].state == NOW + timedelta(minutes=10) and out.things["cookline.timer_done"].state is True
    assert out.things["cookline.today"].state == "Breakfast: Porridge, Tea: Spaghetti Bolognese"
    ev = cookline.events(out.things["cookline.calendar"].data, NOW.replace(hour=0), NOW + timedelta(days=2), NOW)
    assert [e.summary for e in ev] == ["Breakfast: Porridge", "Tea: Spaghetti Bolognese (for 4)", "Tea: Curry"]
