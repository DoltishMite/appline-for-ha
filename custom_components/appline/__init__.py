"""Appline for HA: the apps (launcher.hedgepig.uk) in Home Assistant.

Chosen apps become sidebar panels, and what each person in the household sends from their apps becomes sensors, calendars and
buttons that follow it: a new pet or task gets entities, a removed one loses them (and its device), a renamed one keeps its entity.
Each person chooses what's sent (and can stop any time); copies are sealed, so the server can't read them. Changes made here (a
button, a calendar event) go back into the apps.
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

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.BUTTON]
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
    # the panels this entry added (not today's options: after an app is unticked they no longer list it, so it would stay)
    for path in getattr(entry.runtime_data, "panels", []):
        frontend.async_remove_panel(hass, path, warn_if_unknown=False)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def panel_url(p: dict) -> str:
    """The app's hub address. The launcher is the front page (saved before 0.2.2 as path "tools", which doesn't exist)."""
    path = "" if p.get("id") == "tools" else str(p.get("path") or "").strip("/")
    # ?hp=ha: the apps hide what a Home Assistant panel can't do (camera, location, notifications…: kit.js HPEmbed)
    return (f"{BASE}/{path}/" if path else f"{BASE}/") + "?hp=ha"


@callback
def _add_panels(hass: HomeAssistant, entry: ApplineConfigEntry) -> None:
    entry.runtime_data.panels = []
    for p in entry.options.get(CONF_PANELS, []):
        path = PANEL_PREFIX + p["id"]
        try:
            frontend.async_register_built_in_panel(
                hass, "iframe", sidebar_title=p["name"], sidebar_icon=APP_ICONS.get(p["id"], "mdi:apps"),
                frontend_url_path=path, config={"url": panel_url(p)}, require_admin=False)
            entry.runtime_data.panels.append(path)
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
