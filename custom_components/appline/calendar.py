"""Calendars: what an app has coming up and what was done (Petline: the household's pet care, each person's, and one per pet).
A pet's own calendar takes new events too: each becomes an appointment in Petline (calendar.create_event, or + in the calendar)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    EVENT_DESCRIPTION, EVENT_START, EVENT_SUMMARY, CalendarEntity, CalendarEntityFeature, CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import ApplineConfigEntry
from .const import CONF_CAL_DAILY
from .coordinator import new_id
from .entity import ApplineEntity
from .parsers import PARSERS, Event
from .parsers.model import CALENDAR
from .platform import follow


def _event(e: Event) -> CalendarEvent:
    return CalendarEvent(start=e.start, end=e.end, summary=e.summary, description=e.description or None, uid=e.uid)


class ApplineCalendar(ApplineEntity, CalendarEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        t = self.thing
        if t and isinstance(t.data, dict) and t.data.get("target") and hasattr(PARSERS.get(t.app), "create_event"):
            self._attr_supported_features = CalendarEntityFeature.CREATE_EVENT

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

    async def async_create_event(self, **kwargs: Any) -> None:
        t = self.thing
        mod = PARSERS.get(t.app) if t else None
        start = kwargs[EVENT_START]
        if isinstance(start, datetime):
            local = dt_util.as_local(start)
            day, at = local.date(), local.strftime("%H:%M")
        else:
            day, at = start, None
        summary, note = str(kwargs.get(EVENT_SUMMARY) or ""), str(kwargs.get(EVENT_DESCRIPTION) or "")
        await self.coordinator.async_change(t.data["target"], lambda item: mod.create_event(item, new_id(), summary, day, at, note))


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, CALENDAR, ApplineCalendar, async_add_entities))
