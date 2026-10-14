"""Buttons: do something in an app from Home Assistant (Petline: tick a task off, as its Done does). Use them on dashboards, or in
automations with button.press. The tick says who: the name linked to the pressing user's person in Configure → Who's who, else the
Home Assistant user's name, or "Home Assistant" for an automation."""
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
        uid = self._context.user_id if self._context else None
        user = await self.hass.auth.async_get_user(uid) if uid else None
        by = self.coordinator.name_for_user(uid, user.name if user else None)   # the app name linked in Who's who, if any
        now_ms, act = int(time.time() * 1000), t.data
        await self.coordinator.async_change(act["target"], lambda item: mod.press(item, act, by, now_ms, new_id()))


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, BUTTON, ApplineButton, async_add_entities))
