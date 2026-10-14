"""To-do lists (Listline): each list as a Home Assistant to-do list, both ways. Adding, ticking, editing, removing and reordering
here change the list in the app (its link copy, or the shared copy for a list shared with others)."""
from __future__ import annotations

import datetime as dt
import time

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import ApplineConfigEntry
from .coordinator import new_id
from .entity import ApplineEntity
from .parsers import PARSERS
from .parsers.model import TODO
from .platform import follow

FEATURES = (TodoListEntityFeature.CREATE_TODO_ITEM | TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.DELETE_TODO_ITEM
            | TodoListEntityFeature.MOVE_TODO_ITEM)


class ApplineTodo(ApplineEntity, TodoListEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        t = self.thing
        due = t.data.get("kind") == "todo"   # only to-do lists have due dates in the app
        self._attr_supported_features = FEATURES | (TodoListEntityFeature.SET_DUE_DATE_ON_ITEM if due else 0) if t.data.get("target") else TodoListEntityFeature(0)

    @property
    def _mod(self):
        return PARSERS.get(self.thing.app) if self.thing else None

    @property
    def todo_items(self) -> list[TodoItem] | None:
        t = self.thing
        if not t:
            return None
        out = []
        for i in t.data.get("items") or []:
            done = bool(i.get("done"))
            when = i.get("doneAt")
            out.append(TodoItem(uid=i["id"], summary=str(i.get("text") or ""), status=TodoItemStatus.COMPLETED if done else TodoItemStatus.NEEDS_ACTION,
                                due=self._mod.due_of(i), completed=dt_util.utc_from_timestamp(when / 1000) if done and isinstance(when, (int, float)) else None))
        return out

    async def _change(self, fn) -> None:
        await self.coordinator.async_change(self.thing.data["target"], fn)

    async def async_create_todo_item(self, item: TodoItem) -> None:
        due = item.due.date() if isinstance(item.due, dt.datetime) else item.due
        now_ms = int(time.time() * 1000)
        await self._change(lambda lst: self._mod.new_item(lst, new_id(), item.summary or "", due, now_ms))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        due = item.due.date() if isinstance(item.due, dt.datetime) else item.due
        done = None if item.status is None else item.status == TodoItemStatus.COMPLETED
        now_ms, today = int(time.time() * 1000), dt_util.now().date()
        await self._change(lambda lst: self._mod.update_item(lst, item.uid, item.summary, done, due, now_ms, today))

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        await self._change(lambda lst: self._mod.delete_items(lst, list(uids)))

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        await self._change(lambda lst: self._mod.move_item(lst, uid, previous_uid))


async def async_setup_entry(hass: HomeAssistant, entry: ApplineConfigEntry, async_add_entities) -> None:
    entry.async_on_unload(follow(entry.runtime_data, TODO, ApplineTodo, async_add_entities))
