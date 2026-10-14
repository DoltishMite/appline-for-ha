"""Sensors: a task's state (enum), when it's next due (timestamp), how many things need doing (count)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant

from . import ApplineConfigEntry
from .entity import ApplineEntity
from .parsers.model import COUNT, DAYS, ENUM, SENSOR, TIMESTAMP
from .platform import follow


class ApplineSensor(ApplineEntity, SensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        t = self.thing
        if t.kind == ENUM:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(t.options or [])
        elif t.kind == TIMESTAMP:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif t.kind == COUNT:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif t.kind == DAYS:   # days until (negative: since); shown as a duration
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.DAYS

    @property
    def native_value(self):
        t = self.thing
        return t.state if t else None


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, SENSOR, ApplineSensor, async_add_entities))
