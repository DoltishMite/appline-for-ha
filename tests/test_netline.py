"""Netline presence: tracked devices home or away (seen in the last 20 minutes), how many are home, keys by hardware address."""
import json
from datetime import timedelta

from fixtures import NOW, ms
from parsers import siteline
from parsers.model import BINARY, COUNT, PRESENCE, SENSOR, Parsed


def data(*items):
    return {"siteline_presence_v1": json.dumps(list(items))}


def test_home_and_away():
    out = Parsed()
    siteline.parse(data(
        {"id": "aa:bb:cc:00:00:01", "name": "Sam’s phone", "home": True, "last": ms(NOW - timedelta(minutes=5)), "ip": "192.168.1.77"},
        {"id": "aa:bb:cc:00:00:02", "name": "Laptop", "home": True, "last": ms(NOW - timedelta(minutes=35))},   # stale "home": away now
        {"id": "aa:bb:cc:00:00:03", "name": "Never seen", "home": False, "last": 0},
    ), {}, NOW, out)
    t = out.things
    phone, laptop, never = t["siteline.aa:bb:cc:00:00:01.home"], t["siteline.aa:bb:cc:00:00:02.home"], t["siteline.aa:bb:cc:00:00:03.home"]
    assert (phone.platform, phone.kind, phone.state) == (BINARY, PRESENCE, True)
    assert phone.placeholders["name"] == "Sam’s phone" and phone.attrs["ip"] == "192.168.1.77" and phone.attrs["last_seen"]
    assert laptop.state is False and never.state is False and never.attrs["last_seen"] is None
    count = t["siteline.home"]
    assert (count.platform, count.kind, count.state) == (SENSOR, COUNT, 1)
    assert out.devices["siteline"].name == "Netline"


def test_edge_of_the_window():
    out = Parsed()
    siteline.parse(data({"id": "m1", "name": "A", "last": ms(NOW - timedelta(minutes=20))}, {"id": "m2", "name": "B", "last": ms(NOW - timedelta(minutes=20, seconds=1))}), {}, NOW, out)
    assert out.things["siteline.m1.home"].state is True and out.things["siteline.m2.home"].state is False


def test_nothing_tracked():
    out = Parsed()
    siteline.parse({}, {}, NOW, out)
    assert not out.things   # no count sensor until something is tracked
    siteline.parse({"siteline_presence_v1": "not json"}, {}, NOW, out)
    assert not out.things
