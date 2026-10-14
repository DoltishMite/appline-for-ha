"""Carline and Binline: ports agree with the apps' own code (parity), and their entities and changes."""
import json
import random
from datetime import date, timedelta

from fixtures import NOW, TZ, ms
from parsers import binline, carline, parse_household
from parsers.model import Parsed
from test_apps import moments, needs_site, run_js


# ---------- Carline ----------
def cars(seed=11):
    rnd = random.Random(seed)
    out = []
    for i in range(25):
        c = {"id": f"c{i}", "name": f"Car{i}", "dues": [], "log": [], "odo": []}
        for k in range(rnd.randrange(1, 5)):
            d = {"id": f"d{i}{k}", "kind": rnd.choice(["mot", "tax", "insurance", "service", "warranty", "other"]),
                 "date": (date(2026, 6, 1) + timedelta(days=rnd.randrange(0, 500))).isoformat(), "months": rnd.choice([0, 12, 6])}
            if d["kind"] == "service" and rnd.random() < 0.6:
                d["atMiles"] = rnd.randrange(20000, 60000)
            c["dues"].append(d)
        for _ in range(rnd.randrange(0, 4)):
            c["odo"].append({"date": (date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 300))).isoformat(), "miles": rnd.randrange(15000, 61000)})
        for _ in range(rnd.randrange(0, 3)):
            c["log"].append({"id": "l", "date": (date(2026, 1, 1) + timedelta(days=rnd.randrange(0, 300))).isoformat(), "kind": "service", "miles": rnd.choice([None, rnd.randrange(15000, 61000)])})
        out.append(c)
    return out


@needs_site
def test_carline_parity(tmp_path):
    cs, calls, want = cars(), [], []
    for at in moments(15, seed=12):
        for c in cs:
            for d in c["dues"]:
                calls.append({"at": ms(at), "expr": f"(() => {{ const s = dueState({json.dumps(c)}, {json.dumps(d)}); return [s.left, s.milesLeft, s.state]; }})()"})
                s = carline.due_state(c, d, at.date())
                want.append([s["left"], s["miles_left"], s["state"]])
    rnd = random.Random(13)
    for _ in range(300):
        s = (date(2024, 1, 1) + timedelta(days=rnd.randrange(0, 1500))).isoformat()
        n = rnd.choice([1, 3, 6, 12, 18, 24])
        calls.append({"at": ms(NOW), "expr": f"addMonths('{s}', {n})"})
        want.append(carline.add_months(s, n))
    got = run_js("carline/car.html", ["pad", "ymd", "today", "parseD", "addDays", "addMonths", "daysBetween", "extraCosts", "readings", "lastOdo", "dueState"],
                 calls, prelude="const opts = {}; const HPLink = { linked: () => false, read: () => [] };", tmp=tmp_path)
    norm = lambda v: [v[0], None if v[1] is None else float(v[1]), v[2]] if isinstance(v, list) else v
    bad = [(c["expr"][:90], g, w) for c, g, w in zip(calls, got, want) if norm(g) != norm(w)]
    assert not bad, bad[:5]


def test_carline_entities_and_renew():
    car = {"id": "golf", "name": "Golf", "reg": "AB12 CDE", "icon": "🚗", "odo": [{"date": "2026-09-01", "miles": 41500}], "log": [],
           "dues": [{"id": "mot", "kind": "mot", "date": "2026-10-30", "months": 12},
                    {"id": "tax", "kind": "tax", "date": "2026-10-01", "months": 12},
                    {"id": "svc", "kind": "service", "date": "2027-03-01", "months": 12, "atMiles": 42000},
                    {"id": "w", "kind": "warranty", "date": "2027-08-01", "months": 0}]}
    sam = {"format": 1, "link": 1, "name": "Sam", "apps": {"carline": {"t": 0, "data": {"carline_cars_v1": json.dumps([car])}}}}
    p = parse_household([("sam", sam)], {}, {}, NOW)
    st = {k.split(".")[3]: (t.state, t.attrs["state"]) for k, t in p.things.items() if k.endswith(".days")}
    assert st == {"mot": (16, "soon"), "tax": (-13, "over"), "svc": (138, "soon"), "w": (291, "ok")}   # service: 500 miles to go
    assert p.things["carline.sam.golf.svc.days"].attrs["miles_left"] == 500
    assert p.things["carline.sam.golf.odo"].state == 41500 and p.things["carline.sam.golf.attention"].state is True
    assert p.things["carline.sam.golf.mot.renew"].data == {"target": ["link", "sam", "carline", "golf"], "due": "mot"}
    car2 = dict(car, specs={"make": "Volkswagen", "model": "Golf", "tyres": "205/55 R16"}, notes="Spare key in the drawer")
    p2 = parse_household([("sam", {"format": 1, "link": 1, "name": "Sam", "apps": {"carline": {"t": 0, "data": {"carline_cars_v1": json.dumps([car2])}}}})], {}, {}, NOW)
    det = p2.things["carline.sam.golf.details"]
    assert det.state == "AB12 CDE" and det.attrs["Make"] == "Volkswagen" and det.attrs["Tyre size"] == "205/55 R16" and det.attrs["notes"] == "Spare key in the drawer"
    today = NOW.date()
    c = json.loads(json.dumps(car))
    assert carline.renew(c, "mot", today, "h1", "Steve")   # MOT 16 days early: keeps its date, a year on
    assert next(d for d in c["dues"] if d["id"] == "mot")["date"] == "2027-10-30" and c["log"][-1]["kind"] == "mot" and "Steve" in c["log"][-1]["note"]
    assert carline.renew(c, "tax", today, "h2")            # tax: keeps its anniversary, moved past today
    assert next(d for d in c["dues"] if d["id"] == "tax")["date"] == "2027-10-01"
    assert carline.renew(c, "svc", today, "h3")            # service: a year from today, mileage + 10,000
    s = next(d for d in c["dues"] if d["id"] == "svc")
    assert s["date"] == "2027-10-14" and s["atMiles"] == 52000
    assert carline.renew(c, "w", today, "h4") and not any(d["id"] == "w" for d in c["dues"])   # a one-off goes
    assert not carline.renew(c, "nope", today, "h5")
    ev = carline.events(p.things["carline.calendar"].data, NOW - timedelta(days=30), NOW + timedelta(days=30), NOW)
    assert [e.summary for e in ev] == ["🪪 Golf: Road tax", "🔧 Golf: MOT"]


# ---------- Binline ----------
HOLS = {"at": 0, "d": {"england-and-wales": {"events": [{"date": d, "title": "Bank holiday"} for d in
        ["2026-12-25", "2026-12-28", "2027-01-01", "2027-04-02", "2027-04-05", "2027-05-03", "2027-05-31", "2027-08-30", "2026-08-31", "2026-05-25"]]},
        "scotland": {"events": [{"date": "2026-11-30", "title": "St Andrew's Day"}]}}}


def binsets(seed=21):
    rnd = random.Random(seed)
    sets = []
    for s in range(12):
        bins = [{"id": f"b{s}{i}", "name": f"Bin{i}", "first": (date(2025, 1, 1) + timedelta(days=rnd.randrange(0, 600))).isoformat(),
                 "every": rnd.choice([1, 2, 3, 4]), "pauseFrom": "", "pauseTo": ""} for i in range(rnd.randrange(1, 5))]
        for b in bins:
            if rnd.random() < 0.2:
                pf = date(2026, 6, 1) + timedelta(days=rnd.randrange(0, 300))
                b["pauseFrom"], b["pauseTo"] = pf.isoformat(), rnd.choice(["", (pf + timedelta(days=rnd.randrange(7, 60))).isoformat()])
        changes = []
        for _ in range(rnd.randrange(0, 6)):
            b = rnd.choice(bins)
            k = rnd.randrange(0, 30)
            base = (date.fromisoformat(b["first"]) + timedelta(days=7 * b["every"] * k)).isoformat()
            changes.append({"date": base, "bin": rnd.choice([b["id"], "*"]), **({"skip": True} if rnd.random() < 0.5 else {"move": (date.fromisoformat(base) + timedelta(days=rnd.randrange(-3, 4))).isoformat()})})
        opts = {"holidayShift": rnd.random() < 0.8, "division": rnd.choice(["england-and-wales", "scotland"]), "putOutEvening": True}
        sets.append((bins, changes, opts))
    return sets


@needs_site
def test_binline_collections_parity(tmp_path):
    calls, want = [], []
    for bins, changes, opts in binsets():
        o = binline.options({"binline_options_v1": json.dumps(opts)})
        for at in moments(6, seed=22):
            calls.append({"at": ms(at), "expr": f"(() => {{ bins = {json.dumps(bins)}; changes = {json.dumps(changes)}; Object.assign(opts, {json.dumps(opts)}); "
                                                f"return collections(today(), 90).map(e => [ymd(e.date), e.bins.map(b => b.id), e.notes]); }})()"})
            cs = binline.collections(bins, changes, o, HOLS, at.date(), 90, TZ)
            want.append([[c["date"].isoformat(), [b["id"] for b in c["bins"]], c["notes"]] for c in cs])
    got = run_js("binline/bins.html", ["pad", "DAY", "ymd", "parse", "today", "holidayOn", "collections"], calls,
                 prelude=f"let bins = [], changes = []; const opts = {{}}; let HOLS = {json.dumps(HOLS)};", tmp=tmp_path)
    bad = [(i, g[:3] if isinstance(g, list) else g, w[:3]) for i, (g, w) in enumerate(zip(got, want)) if g != w]
    assert not bad, bad[:3]


def test_binline_entities():
    bins = [{"id": "g", "name": "General", "icon": "🗑️", "first": "2026-10-01", "every": 2},
            {"id": "r", "name": "Recycling", "icon": "♻️", "first": "2026-10-08", "every": 2}]
    data = {"binline_bins_v1": json.dumps(bins), "binline_options_v1": json.dumps({"holidayShift": True}),
            "binline_changes_v1": json.dumps([{"date": "2026-10-15", "bin": "g", "skip": True}])}
    out = Parsed()
    evening = NOW.replace(hour=19)   # Wednesday 14 October, 7 pm
    binline.parse(data, {}, evening, out)
    assert out.things["binline.r.next"].state == 8 and out.things["binline.r.next"].attrs["date"] == "2026-10-22"
    assert out.things["binline.g.next"].state == 15        # the 15th is skipped
    data["binline_changes_v1"] = "[]"
    out = Parsed()
    binline.parse(data, {}, evening, out)
    assert out.things["binline.next"].state == 1 and out.things["binline.next"].attrs["bins"] == ["General"]
    assert out.things["binline.put_out"].state is True
    data["binline_options_v1"] = json.dumps({"outFor": "2026-10-15"})
    out = Parsed()
    binline.parse(data, {}, evening, out)
    assert out.things["binline.put_out"].state is False    # marked "They're out"
    out = Parsed()
    binline.parse(data, {}, NOW.replace(hour=11), out)
    assert out.things["binline.put_out"].state is False    # not before noon the day before
    ev = binline.events(out.things["binline.calendar"].data, NOW, NOW + timedelta(days=20), NOW)
    assert [(e.start.isoformat(), e.summary) for e in ev] == [("2026-10-15", "🗑 🗑️ General"), ("2026-10-22", "🗑 ♻️ Recycling"), ("2026-10-29", "🗑 🗑️ General")]


def test_binline_household_same_bins_once_and_out():
    mine = [{"id": "g1", "name": "Rubbish Bin", "icon": "🗑️", "first": "2026-10-01", "every": 2}, {"id": "r1", "name": "Recycling", "icon": "♻️", "first": "2026-10-08", "every": 2}]
    hers = [{"id": "gX", "name": "rubbish bin ", "icon": "🗑️", "first": "2026-10-01", "every": 2}, {"id": "rX", "name": "Recycling", "icon": "♻️", "first": "2026-10-08", "every": 2},
            {"id": "f", "name": "Food Waste", "icon": "🍎", "first": "2026-10-08", "every": 1}]
    link = lambda name, bins, out=None: {"format": 1, "link": 1, "name": name, "apps": {"binline": {"t": 0, "data": dict({"binline_bins_v1": json.dumps(bins)}, **({"binline_out_v1": json.dumps(out)} if out else {}))}}}
    evening = NOW.replace(hour=19)
    p = parse_household([("steve", link("Steve", mine)), ("sam", link("Sam", hers))], {}, {}, evening)
    bins = {t.placeholders["name"]: t for k, t in p.things.items() if k.endswith(".next") and k != "binline.next"}
    assert sorted(bins) == ["Food Waste", "Recycling", "Rubbish Bin"]            # the same bins once, not twice
    assert bins["Recycling"].attrs["shared_with"] == ["Steve", "Sam"] and bins["Food Waste"].attrs["owner"] == "Sam"
    assert p.things["binline.next"].state == 1 and p.things["binline.put_out"].state is True
    btn = p.things["binline.out"]
    assert btn.data["targets"] == [["link", "steve", "binline", None, "binline_out_v1"], ["link", "sam", "binline", None, "binline_out_v1"]]
    log = []
    assert binline.press(log, btn.data, "Steve", ms(evening), "h1") and not binline.press(log, btn.data, "Steve", ms(evening), "h2")
    p = parse_household([("steve", link("Steve", mine, log)), ("sam", link("Sam", hers))], {}, {}, evening)
    assert p.things["binline.put_out"].state is False and p.things["binline.next"].attrs["out"] is True   # out for both
    ev = binline.events(p.things["binline.calendar"].data, evening - timedelta(hours=1), evening + timedelta(days=2), evening)
    assert [e.summary for e in ev] == ["✓ Bins out (Steve)", "🗑 🗑️ Rubbish Bin + 🍎 Food Waste"]
