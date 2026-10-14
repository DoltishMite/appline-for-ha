"""Diagnostics: counts and link state only. Never the code, ids or anything from the apps' data."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ApplineConfigEntry
from .const import CONF_CODE

REDACT = {CONF_CODE, "unique_id", "title"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ApplineConfigEntry) -> dict[str, Any]:
    c = entry.runtime_data
    data = c.data
    return {
        "entry": async_redact_data(entry.as_dict(), REDACT),
        "people": len(c.people),
        "live": c.live,
        "last_update_success": c.last_update_success,
        "shared_followed": len(c.shared),
        "documents_open": len(c.docs),
        "devices": len(data.devices) if data else 0,
        "entities": {p: sum(1 for t in data.things.values() if t.platform == p) for p in ("sensor", "binary_sensor")} if data else {},
    }
