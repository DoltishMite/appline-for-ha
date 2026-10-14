"""What a parser hands to Home Assistant: devices and the things (entities) on them. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SENSOR, BINARY, CALENDAR, BUTTON = "sensor", "binary_sensor", "calendar", "button"
ENUM, TIMESTAMP, COUNT, PROBLEM, EVENTS, PRESS = "enum", "timestamp", "count", "problem", "events", "press"
DAYS, LIST, DISTANCE = "days", "list", "distance"   # DAYS: a number of days (a duration); LIST: a to-do list (TODO)
TODO = "todo"


@dataclass
class Device:
    key: str                       # unique within the config entry, e.g. "petline" or "petline.pb"
    name: str
    model: str
    via: str | None = None         # the device it hangs off (an app's own device)


@dataclass
class Thing:
    key: str                       # unique within the config entry and stable: built from the apps' item ids, never names
    device: str                    # Device.key
    platform: str                  # SENSOR or BINARY
    kind: str                      # ENUM, TIMESTAMP, COUNT or PROBLEM
    translation_key: str
    state: Any
    placeholders: dict[str, str] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    icon: str | None = None
    options: list[str] | None = None   # ENUM only
    app: str = ""                      # the app it came from (CALENDAR: whose events() works out its events)
    data: Any = None                   # CALENDAR: what its events() needs; a task or BUTTON: where a change is saved (not shown)
    enabled: bool = True               # False: the entity starts disabled (the user can switch it on)


@dataclass
class Event:
    uid: str
    summary: str
    start: Any                         # datetime (aware) or date (all day)
    end: Any
    description: str = ""


@dataclass
class Parsed:
    devices: dict[str, Device] = field(default_factory=dict)
    things: dict[str, Thing] = field(default_factory=dict)

    def add_device(self, d: Device) -> None:
        self.devices[d.key] = d

    def add(self, t: Thing) -> None:
        self.things[t.key] = t
