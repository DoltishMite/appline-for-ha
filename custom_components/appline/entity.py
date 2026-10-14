"""The entity every Appline sensor is built on: it follows one Thing (by key) in the coordinator's data."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ApplineCoordinator
from .parsers import Thing


def device_identifier(entry_id: str, key: str) -> tuple[str, str]:
    return (DOMAIN, f"{entry_id}_{key}")


class ApplineEntity(CoordinatorEntity[ApplineCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ApplineCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self.key = key
        entry_id = coordinator.config_entry.entry_id
        t = coordinator.data.things[key]
        d = coordinator.data.devices[t.device]
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_translation_key = t.translation_key
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(entry_id, d.key)},
            name=d.name,
            model=d.model,
            manufacturer="Appline",
            entry_type=DeviceEntryType.SERVICE,
            via_device=device_identifier(entry_id, d.via) if d.via else None,
        )
        self._attr_entity_registry_enabled_default = t.enabled
        self._apply(t)

    @property
    def thing(self) -> Thing | None:
        return self.coordinator.data.things.get(self.key) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return super().available and self.thing is not None

    def _apply(self, t: Thing) -> None:
        self._attr_translation_placeholders = dict(t.placeholders)
        self._attr_extra_state_attributes = dict(t.attrs)
        if t.icon:
            self._attr_icon = t.icon

    @callback
    def _handle_coordinator_update(self) -> None:
        t = self.thing
        if t is not None:
            self._apply(t)
        super()._handle_coordinator_update()
