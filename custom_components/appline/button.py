"""Buttons: do something in an app from Home Assistant (Petline: tick a task off, as its Done does). Use them on dashboards, or in
automations with button.press. The tick says who: the Home Assistant user who pressed it, or "Home Assistant" for an automation."""
from __future__ import annotations

import time

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from . import ApplineConfigEntry
from .coordinator import new_id
from .entity import ApplineEntity
from .parsers import PARSERS
from .parsers.model import BUTTON
from .platform import follow


class ApplineButton(ApplineEntity, ButtonEntity):
    async def async_press(self) -> None:
        t = self.thing
        mod = PARSERS.get(t.app) if t else None
        if not t or not mod or not t.data:
            return
        who = None
        if self._context and self._context.user_id:
            user = await self.hass.auth.async_get_user(self._context.user_id)
            who = user.name if user else None
        by, now_ms, act = who or "Home Assistant", int(time.time() * 1000), t.data
        await self.coordinator.async_change(act["target"], lambda item: mod.press(item, act, by, now_ms, new_id()))


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, BUTTON, ApplineButton, async_add_entities))
