"""Wardyn (the network monitor; it was Netline's until 2026-11-02, same app id and keys) -> presence entities. Pure Python.

Saved data (web/siteline/APP.md, "Devices"): siteline_presence_v1 [{ id (the device's hardware address), name, home, last (ms, when any
computer last saw it on the network), ip, net }]: the devices the person tracks (Netline: Devices → 🏠 Track presence in Home Assistant).
Netline Agent rebuilds the list with every scan (about every 10 minutes) and puts the ticked ones in the person's HA link itself, so it
stays fresh with no page open. Home = seen in the last 20 minutes (as the agent works it out): worked out again here from `last`, so a
device that stops being seen goes away even if no new list arrives (a computer switched off).
Entities on the Netline device: per tracked device, home (binary_sensor, presence); how many are home (sensor, count).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .common import household, single, who
from .model import BINARY, COUNT, PRESENCE, SENSOR, Device, Parsed, Thing

APP, NAME = "siteline", "Wardyn"   # (Netline's network monitor, its own site since 2026-11-02: the device's name)
LIST_KEY = "siteline_presence_v1"
HOME_FOR = timedelta(minutes=20)   # as Netline Agent (Devices/DevicesModule.cs HomeFor)


def share_codes(data: dict[str, str]) -> dict[str, str]:
    return {}   # nothing in Netline is shared this way


def from_shared(item: dict, item_id: str) -> dict[str, str]:
    return {LIST_KEY: json.dumps([dict(item, id=item_id)])}


def seen_at(item: dict, tz) -> datetime | None:
    last = item.get("last")
    return datetime.fromtimestamp(last / 1000, tz=tz) if isinstance(last, (int, float)) and last > 0 else None


def is_home(item: dict, now: datetime) -> bool:
    at = seen_at(item, now.tzinfo)
    return at is not None and now - at <= HOME_FOR   # (a clock a little ahead counts as now)


def _emit(ents: list[dict], now: datetime, out: Parsed, app_name: str | None) -> None:
    out.add_device(Device(APP, app_name or NAME, NAME))
    home = 0
    for e in ents:
        it = e["item"]
        at = seen_at(it, now.tzinfo)
        h = is_home(it, now)
        home += h
        attrs = {"last_seen": at.isoformat() if at else None, "ip": it.get("ip"), "hardware_address": it.get("id"), **who(e)}
        out.add(Thing(f"{e['key']}.home", APP, BINARY, PRESENCE, "device_home", h, {"name": str(it.get("name") or "Device")}, attrs,
                      "mdi:home-account" if h else "mdi:home-export-outline"))
    if ents:
        out.add(Thing(f"{APP}.home", APP, SENSOR, COUNT, "devices_home", home, {}, {}, "mdi:home-group"))


def parse(data: dict[str, str], shared: dict[str, dict], now: datetime, out: Parsed, app_name: str | None = None) -> None:
    _emit(single(APP, LIST_KEY, data, shared), now, out, app_name)


def parse_people(people, refs, shared_items, now, out, app_name=None) -> None:
    _emit(household(APP, LIST_KEY, people, refs, shared_items), now, out, app_name)
