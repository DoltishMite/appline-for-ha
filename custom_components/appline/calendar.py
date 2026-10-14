"""Calendars: what an app has coming up and what was done (Petline: every pet's care, and one per pet)."""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import ApplineConfigEntry
from .const import CONF_CAL_DAILY
from .entity import ApplineEntity
from .parsers import PARSERS, Event
from .parsers.model import CALENDAR
from .platform import follow


def _event(e: Event) -> CalendarEvent:
    return CalendarEvent(start=e.start, end=e.end, summary=e.summary, description=e.description or None, uid=e.uid)


class ApplineCalendar(ApplineEntity, CalendarEntity):
    def _events(self, start: datetime, end: datetime) -> list[Event]:
        t = self.thing
        mod = PARSERS.get(t.app) if t else None
        if not mod:
            return []
        daily = self.coordinator.config_entry.options.get(CONF_CAL_DAILY, True)
        return mod.events(t.data, start, end, dt_util.now(), daily)

    @property
    def event(self) -> CalendarEvent | None:
        """What's on now, or next."""
        now = dt_util.now()
        for days in (2, 60, 400):
            for e in self._events(now, now + timedelta(days=days)):
                return _event(e)
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        return [_event(e) for e in self._events(start_date, end_date)]


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, CALENDAR, ApplineCalendar, async_add_entities))
