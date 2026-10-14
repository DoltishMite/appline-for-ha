"""What a parser hands to Home Assistant: devices and the things (entities) on them. Pure Python."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SENSOR, BINARY = "sensor", "binary_sensor"
ENUM, TIMESTAMP, COUNT, PROBLEM = "enum", "timestamp", "count", "problem"


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


@dataclass
class Parsed:
    devices: dict[str, Device] = field(default_factory=dict)
    things: dict[str, Thing] = field(default_factory=dict)

    def add_device(self, d: Device) -> None:
        self.devices[d.key] = d

    def add(self, t: Thing) -> None:
        self.things[t.key] = t
