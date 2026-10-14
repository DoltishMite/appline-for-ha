"""A household: several people's HA link copies, shared things shown once, and changes made in Home Assistant."""
import json
import shutil
import subprocess
from datetime import date

import pytest

from conftest import SITE
from fixtures import NOW, ms, pets
from hpcrypto import HALINK, keys_for, open_doc, seal_doc
from parsers import parse_household, sync_share_codes
from parsers.petline import add_appointment, events, mark_done, press

SID = "s" * 64


def link(name, pet_list, shared=None):
    data = {"petline_pets_v1": json.dumps(pet_list), "petline_options_v1": json.dumps({"remindAt": "09:00"})}
    if shared:
        data["petline_shared_v1"] = json.dumps(shared)
    return {"format": 1, "link": 1, "name": name, "by": "apps", "apps": {"petline": {"t": 0, "data": data}}}


def household():
    biscuit, mittens = pets()
    alex_dog = dict(biscuit, id="pa", log=[])                       # another Biscuit, Alex's own
    kids = {"id": "pk", "name": "Bun", "tasks": [{"id": "k1", "name": "Feeding", "type": "meal", "times": ["07:00"]}], "log": []}
    sam = link("Sam", [biscuit, kids], {"pk": {"code": "QQQQ-RRRR-SSSS-TTTT-PPPP"}})
    alex = link("Alex", [alex_dog, dict(kids, id="pk2")], {"pk2": {"code": "QQQQ-RRRR-SSSS-TTTT-PPPP"}})
    refs = {("sam", "petline", "pk"): SID, ("alex", "petline", "pk2"): SID}
    shared_item = {k: v for k, v in kids.items() if k != "id"}
    shared_item["log"] = [{"id": "x", "task": "k1", "t": ms(NOW.replace(hour=7, minute=5)), "by": "Max"}]   # newer than the link copies
    return [("sam", sam), ("alex", alex)], refs, {SID: shared_item}


def test_share_codes_from_a_link():
    people, _, _ = household()
    assert sync_share_codes(people[0][1]) == {("petline", "pk"): "QQQQ-RRRR-SSSS-TTTT-PPPP"}


def test_owners_shared_once_and_names():
    p = parse_household(*household(), NOW)
    devs = {k: d.name for k, d in p.devices.items()}
    assert devs["petline.sam.pb"] == "Biscuit (Sam)" and devs["petline.alex.pa"] == "Biscuit (Alex)"   # same name: say whose
    shared = [k for k in devs if k.startswith("petline.shared.")]
    assert shared == [f"petline.shared.{SID[:12]}"] and devs[shared[0]] == "Bun"                         # shared by both: once
    st = p.things[f"petline.shared.{SID[:12]}.k1.status"]
    assert st.attrs["shared_with"] == ["Sam", "Alex"] and st.state == "done" and st.attrs["done_by"] == "Max"   # the shared copy wins
    assert p.things["petline.sam.pb.t1.status"].attrs["owner"] == "Sam"
    assert p.things[f"petline.shared.{SID[:12]}.k1.done"].data["target"] == ["shared", SID, "petline"]
    assert p.things["petline.alex.pa.t1.done"].data["target"] == ["link", "alex", "petline", "pa"]


def test_calendars_per_person():
    p = parse_household(*household(), NOW)
    sam_cal, alex_cal = p.things["petline.sam.calendar"], p.things["petline.alex.calendar"]
    assert sam_cal.enabled and sam_cal.placeholders == {"person": "Sam"}
    names = lambda t: sorted({it["pet"]["name"] + ":" + it["dev"] for it in t.data["items"]})
    assert names(sam_cal) == sorted(["Biscuit:petline.sam.pb", f"Bun:petline.shared.{SID[:12]}"])
    assert names(alex_cal) == sorted(["Biscuit:petline.alex.pa", f"Bun:petline.shared.{SID[:12]}"])
    assert len(p.things["petline.calendar"].data["items"]) == 4 - 1    # household: three pets, Bun once
    ev = events(sam_cal.data, NOW.replace(hour=0), NOW.replace(hour=23), NOW)
    assert any(e.summary == "✓ Bun: Feeding (Max)" for e in ev)


def test_one_person_has_no_extra_calendar_switched_on():
    people, refs, items = household()
    p = parse_household(people[:1], {k: v for k, v in refs.items() if k[0] == "sam"}, items, NOW)
    assert p.things["petline.sam.calendar"].enabled is False


def test_mark_done_and_appointment():
    pet = pets()[0]
    assert press(pet, {"task": "t2"}, "Dad", 123, "h1") and pet["log"][-1] == {"id": "h1", "task": "t2", "t": 123, "by": "Dad"}
    assert not mark_done(pet, "nope", "Dad", 1, "h2")
    assert mark_done(pet, "t6", "Dad", 1, "h3") and pet["tasks"][5]["done"] is True
    assert not mark_done(pet, "t6", "Dad", 2, "h4")                        # already done: ignored
    add_appointment(pet, "h5", "Jabs", date(2026, 11, 2), "14:15", "bring card")
    assert pet["tasks"][-1] == {"id": "h5", "name": "Jabs", "icon": "🩺", "type": "appt", "next": "2026-11-02", "time": "14:15",
                                "done": False, "note": "bring card"}


def test_seal_round_trip():
    k = keys_for("ABCD-EFGH-JKMN-PQRS-TVWX", HALINK)
    obj = {"format": 1, "link": 1, "name": "Sam 🐶", "apps": {}}
    assert open_doc(seal_doc(obj, k), k) == obj


@pytest.mark.skipif(not shutil.which("node") or not (SITE / "backend/test/test-halink.mjs").exists(), reason="needs the apps' project")
def test_link_made_by_the_apps_opens_here(tmp_path):
    out = tmp_path / "link.json"
    r = subprocess.run(["node", str(SITE / "backend/test/test-halink.mjs"), str(out)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    v = json.loads(out.read_text(encoding="utf-8"))
    keys = keys_for(v["code"], HALINK)
    assert keys.id == v["id"]
    doc = open_doc(v["doc"], keys)
    assert doc["link"] == 1 and doc["name"] == "Sam"
    p = parse_household([("sam", doc)], {}, {}, NOW)
    assert "petline.sam.pb.t1.status" in p.things and p.devices["petline.sam.pb"].name == "Biscuit B"
