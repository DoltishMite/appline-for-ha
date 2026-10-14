"""Appline for HA: the apps (launcher.hedgepig.uk) in Home Assistant.

Chosen apps become sidebar panels, and the apps' data becomes sensors that follow what's in them: a new pet or task gets entities,
a removed one loses them (and its device), a renamed one keeps its entity. Data is read with the code entered in the setup and
opened here; the server only ever holds sealed copies. Read-only: nothing is ever saved back.
"""
from __future__ import annotations

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import APP_ICONS, BASE, CONF_PANELS, DOMAIN, LOGGER, PANEL_PREFIX
from .coordinator import ApplineCoordinator
from .entity import device_identifier

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR]
type ApplineConfigEntry = ConfigEntry[ApplineCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry) -> bool:
    coordinator = ApplineCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(coordinator.async_add_listener(lambda: _tidy(hass, entry)))
    _tidy(hass, entry)
    coordinator.start_tick()
    entry.async_create_background_task(hass, coordinator.run_live(), f"{DOMAIN} live link")

    _add_panels(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApplineConfigEntry) -> bool:
    for p in entry.options.get(CONF_PANELS, []):
        frontend.async_remove_panel(hass, PANEL_PREFIX + p["id"], warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _add_panels(hass: HomeAssistant, entry: ApplineConfigEntry) -> None:
    for p in entry.options.get(CONF_PANELS, []):
        try:
            frontend.async_register_built_in_panel(
                hass, "iframe", sidebar_title=p["name"], sidebar_icon=APP_ICONS.get(p["id"], "mdi:apps"),
                frontend_url_path=PANEL_PREFIX + p["id"], config={"url": f"{BASE}/{p['path']}/"}, require_admin=False)
        except ValueError:
            LOGGER.warning("%s is already in the sidebar (from another Appline entry)", p["name"])


@callback
def _tidy(hass: HomeAssistant, entry: ApplineConfigEntry) -> None:
    """Remove entities and devices for things that are gone from the apps; keep device names in step with renames."""
    coordinator = entry.runtime_data
    data = coordinator.data
    if not coordinator.last_update_success or data is None:
        return   # never tidy from a failed update: that would wipe everything while the server is away
    prefix = f"{entry.entry_id}_"
    ents = er.async_get(hass)
    for e in er.async_entries_for_config_entry(ents, entry.entry_id):
        if e.unique_id.startswith(prefix) and e.unique_id[len(prefix):] not in data.things:
            ents.async_remove(e.entity_id)
    devs = dr.async_get(hass)
    want = {device_identifier(entry.entry_id, k): d for k, d in data.devices.items()}
    for d in dr.async_entries_for_config_entry(devs, entry.entry_id):
        ident = next((i for i in d.identifiers if i[0] == DOMAIN), None)
        if ident not in want:
            devs.async_update_device(d.id, remove_config_entry_id=entry.entry_id)
        elif d.name != want[ident].name:
            devs.async_update_device(d.id, name=want[ident].name)
    # Home Assistant keeps an entity's name once worked out: a task renamed in the app needs a reload to show (rare)
    names = {k: t.placeholders for k, t in data.things.items()}
    if any(k in names and names[k] != v for k, v in coordinator.names.items()):
        hass.config_entries.async_schedule_reload(entry.entry_id)
    coordinator.names = names
