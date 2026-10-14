"""Binary sensors: something needs attention (a pet that needs care now)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant

from . import ApplineConfigEntry
from .entity import ApplineEntity
from .parsers.model import BINARY, PROBLEM
from .platform import follow


class ApplineBinarySensor(ApplineEntity, BinarySensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        if self.thing.kind == PROBLEM:
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        t = self.thing
        return bool(t.state) if t else None


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, BINARY, ApplineBinarySensor, async_add_entities))
