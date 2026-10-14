"""Petline → devices and entities."""
import json
from datetime import timedelta

from fixtures import NOW, TZ, day, ms, pets, sync_doc
from parsers import parse_shared, parse_sync, sync_share_codes
from parsers.petline import status


def states(parsed):
    return {k: t.state for k, t in parsed.things.items() if k.endswith(".status")}


def test_states_at_noon():
    p = parse_sync(sync_doc(), {}, NOW)
    assert states(p) == {
        "petline.pb.t1.status": "soon",    # breakfast done at 07:35, tea at 18:00
        "petline.pb.t2.status": "late",    # 08:00 walk not done (yesterday's doesn't count)
        "petline.pb.t3.status": "due",     # flea treatment first due today
        "petline.pb.t4.status": "later",
        "petline.pb.t5.status": "later",
        "petline.pb.t6.status": "soon",    # vet in 3 days
        "petline.pm.m1.status": "late",
        "petline.pm.m2.status": "later",
    }
    t1 = p.things["petline.pb.t1.status"]
    assert t1.attrs["slot"] == "2 of 2" and t1.attrs["done_by"] == "Alex" and t1.placeholders == {"task": "Feeding"}
    assert p.things["petline.pb.t1.next"].state == NOW.replace(hour=18)
    assert p.things["petline.pb.t6.next"].state == (NOW.replace(hour=10, minute=30) + timedelta(days=3))
    assert p.things["petline.pb.t3.next"].state == NOW.replace(hour=9)      # treatments are due at the reminder time
    assert p.things["petline.pb.todo"].state == 2 and p.things["petline.pb.todo"].attrs["tasks"] == ["Walk", "Flea treatment"]
    assert p.things["petline.pm.needs_care"].state is True
    assert p.things["petline.todo"].state == 3


def test_devices():
    p = parse_sync(sync_doc(), {}, NOW)
    assert {k: (d.name, d.via) for k, d in p.devices.items()} == {
        "petline": ("Petline", None), "petline.pb": ("Biscuit", "petline"), "petline.pm": ("Mittens", "petline")}


def test_meal_done_and_due_window():
    pet = pets()[0]
    feed = pet["tasks"][0]
    pet["log"].append({"id": "l3", "task": "t1", "t": ms(NOW.replace(hour=11, minute=50)), "by": "Sam"})
    s = status(pet, feed, NOW)
    assert s["state"] == "done" and s["by"] == "Sam" and s["due"] == NOW.replace(hour=7, minute=30) + timedelta(days=1)
    walk = pet["tasks"][1]
    assert status(pet, walk, NOW.replace(hour=7, minute=10))["state"] == "due"      # within the hour before
    assert status(pet, walk, NOW.replace(hour=6, minute=59))["state"] == "soon"
    assert status(pet, walk, NOW.replace(hour=9, minute=0))["state"] == "due"       # up to an hour after
    assert status(pet, walk, NOW.replace(hour=9, minute=1))["state"] == "late"


def test_cycle_done_today_and_overdue():
    pet = pets()[0]
    flea = pet["tasks"][2]
    pet["log"].append({"id": "l4", "task": "t3", "t": ms(NOW.replace(hour=10)), "by": "Sam"})
    s = status(pet, flea, NOW)
    assert s["state"] == "done" and s["due"] == NOW.replace(hour=9) + timedelta(days=30)
    assert status(pet, flea, NOW + timedelta(days=29))["state"] == "soon"
    assert status(pet, flea, NOW + timedelta(days=30))["state"] == "due"
    assert status(pet, flea, NOW + timedelta(days=31))["state"] == "over"


def test_appt_done_and_past():
    pet = pets()[0]
    vet = dict(pet["tasks"][5])
    assert status(pet, vet, NOW + timedelta(days=4))["state"] == "over"
    vet["done"] = True
    assert status(pet, vet, NOW)["state"] == "done"


def test_dynamic_add_remove_rename():
    p = pets()
    p[0]["tasks"].append({"id": "t7", "name": "Nail trim", "type": "cycle", "days": 28, "next": day(1)})
    p[0]["name"] = "Biscuit the Dog"
    del p[1]
    out = parse_sync(sync_doc(p), {}, NOW)
    assert "petline.pb.t7.status" in out.things and out.things["petline.pb.t7.status"].icon == "mdi:content-cut"
    assert not any(k.startswith("petline.pm") for k in out.things) and "petline.pm" not in out.devices
    assert out.devices["petline.pb"].name == "Biscuit the Dog"         # same key, so the same entities and device


def test_shared_copy_wins():
    shared = {"pb": {"code": "ABCD-EFGH-JKMN-PQRS-TVWX", "v": 3}}
    doc = sync_doc(shared=shared)
    assert sync_share_codes(doc) == {("petline", "pb"): "ABCD-EFGH-JKMN-PQRS-TVWX"}
    item = {k: v for k, v in pets()[0].items() if k != "id"}
    item["log"] = item["log"] + [{"id": "l9", "task": "t2", "t": ms(NOW.replace(hour=8, minute=5)), "by": "Partner"}]
    out = parse_sync(doc, {("petline", "pb"): item}, NOW)
    assert out.things["petline.pb.t2.status"].state == "soon"          # the partner's walk is in the shared copy
    assert out.things["petline.pb.t2.status"].attrs["done_by"] == "Partner"


def test_share_code_on_its_own():
    item = {k: v for k, v in pets()[1].items() if k != "id"}
    out = parse_shared({"format": 2, "app": "petline", "id": "pm", "item": item, "by": "x"}, NOW)
    assert set(out.devices) == {"petline", "petline.pm"} and out.things["petline.pm.m1.status"].state == "late"
    assert parse_shared({"format": 2, "app": "nope", "id": "x", "item": {}}, NOW).things == {}


def test_bad_data_doesnt_break():
    bad = {"format": 1, "apps": {"petline": {"t": 1, "data": {
        "petline_pets_v1": json.dumps([None, {"name": "no id"}, {"id": "a", "tasks": [None, {"id": "x", "type": "meal", "times": ["nonsense"]},
                                       {"id": "y", "type": "appt"}, {"id": "z", "type": "cycle", "days": "x"}], "log": [{"t": "x"}]}]),
        "petline_options_v1": "{not json"}}}}
    out = parse_sync(bad, {}, NOW)
    assert out.things["petline.a.z.status"].state == "due"
    assert "petline.a.x.status" not in out.things and "petline.a.y.status" not in out.things
    assert parse_sync({"apps": {}}, {}, NOW).things == {} and parse_sync(None, {}, NOW).things == {}


def test_app_renamed():
    doc = sync_doc()
    doc["apps"]["petline"]["data"]["petline_app_name_v1"] = "Pet jobs"
    assert parse_sync(doc, {}, NOW).devices["petline"].name == "Pet jobs"


def test_dst_change_day():
    # 2026-10-25: the clocks go back in the UK; a 08:00 slot is still 08:00 local
    pet = pets()[1]
    d = NOW.replace(day=25, hour=12)
    s = status(pet, pet["tasks"][0], d)
    assert s["due"].hour == 9 and s["due"].tzinfo == TZ and s["state"] == "late"
