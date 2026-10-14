"""Keeps a household's things in Home Assistant up to date, and saves the changes made here.

One config entry = one household: a list of people, each with an HA link code made in their apps (Appline → Settings → Sync & Backup →
Integrations → Home Assistant). Their link copies hold only what they ticked; the shared things in them carry their share codes, so the
shared copies are followed too (newer than anyone's link copy while others are ticking things off) and a thing shared by several people
in the household shows once.
Changes arrive over the live link (wss /api/live) the moment they're saved; a pull every 5 minutes is the safety net, and the entities
are worked out again every minute so time-based states (due → late) move on without a new save.
Saving (a button, a calendar event): the thing is changed in its own copy, the person's link copy (by: 'ha'; their apps merge it in) or
the shared copy (everyone's apps merge it in), against the version just read, again after a clash.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .const import CONF_CODE, CONF_NAMES, CONF_PEOPLE, DOMAIN, HEADERS, LIVE_URL, LOGGER
from .hpcrypto import HALINK, TOGETHER, Keys, SealError, keys_for, norm, open_doc, seal_doc
from .parsers import PARSERS, Parsed, parse_household, sync_share_codes

POLL = timedelta(minutes=5)
GRACE = timedelta(minutes=30)   # how long the last copies stand in when the server can't be reached
TICK = timedelta(minutes=1)


def person_key(keys: Keys) -> str:
    """A short, stable key for a person (part of a hash of their link: leads back to nothing)."""
    return keys.id[:10]


def new_id() -> str:
    return "h" + format(int(time.time() * 1000), "x") + secrets.token_hex(2)


class ApplineCoordinator(DataUpdateCoordinator[Parsed]):
    """Fetches, opens and parses; data is a Parsed (devices + things)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=POLL)
        self.session = async_get_clientsession(hass)
        self.people: dict[str, Keys] = {}
        self.codes = sorted(norm(p[CONF_CODE]) for p in entry.options.get(CONF_PEOPLE, []))   # to notice a change of people
        self._last_ok: float | None = None
        self._away = False    # when the server last answered (monotonic), to ride out short outages
        for p in entry.options.get(CONF_PEOPLE, []):
            k = keys_for(p[CONF_CODE], HALINK)
            self.people[person_key(k)] = k
        self.shared: dict[str, Keys] = {}                     # shared copy id → its keys
        self.refs: dict[tuple[str, str, str], str] = {}       # (person, app, item id) → shared copy id
        self.docs: dict[str, tuple[int, Any]] = {}            # document id → (version, opened JSON)
        self.live = False
        self.panels: list[str] = []                          # sidebar panels this entry added (removed on unload)
        self.names: dict[str, dict[str, str]] = {}            # thing key → name placeholders, to notice a rename
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    def person_names(self) -> dict[str, str]:
        """{ person key: the name they gave in their apps } for the people whose copies are here."""
        out = {}
        for pk, k in self.people.items():
            d = self.docs.get(k.id)
            name = d[1].get("name") if d and isinstance(d[1], dict) else None
            out[pk] = name if isinstance(name, str) and name.strip() else "Someone"
        return out

    # ---------- fetching ----------
    async def _open(self, keys: Keys, doc: str) -> Any:
        return await self.hass.async_add_executor_job(open_doc, doc, keys)

    async def _pull(self, keys: Keys) -> None:
        v, doc = await api.get_doc(self.session, keys)
        if not v:
            self.docs.pop(keys.id, None)
        elif self.docs.get(keys.id, (0, None))[0] != v:
            self.docs[keys.id] = (v, await self._open(keys, doc))

    async def _follow_shared(self) -> bool:
        """Follow the shared things in everyone's link copies (new ones fetched, gone ones dropped). True if the list changed."""
        refs, want = {}, {}
        for pk, k in self.people.items():
            d = self.docs.get(k.id)
            if not d:
                continue
            for (app, iid), code in sync_share_codes(d[1]).items():
                sk = keys_for(code, TOGETHER)
                refs[(pk, app, iid)] = sk.id
                want[sk.id] = sk
        changed = set(want) != set(self.shared)
        for sid in set(self.shared) - set(want):
            self.docs.pop(sid, None)
        self.shared, self.refs = want, refs
        for sk in want.values():
            try:
                await self._pull(sk)
            except (api.ApiError, SealError):
                self.docs.pop(sk.id, None)   # that thing falls back to the person's own copy
        return changed

    async def _async_update_data(self) -> Parsed:
        opened = 0
        for k in self.people.values():
            try:
                await self._pull(k)
                opened += 1
            except api.Refused as err:
                raise UpdateFailed("The apps' server refused Home Assistant: it needs the update that lets the integration in") from err
            except api.ApiError as err:
                # The apps' server is away for a moment (a restart, the PC asleep): keep what was fetched last, worked out afresh
                # (states move on with the clock), for up to half an hour, rather than every entity blinking unavailable.
                if self.docs and self._last_ok is not None and time.monotonic() - self._last_ok < GRACE.total_seconds():
                    if not self._away:
                        LOGGER.info("Can't reach the apps' server (%s): showing what was fetched last", err)
                        self._away = True
                    return self.build()
                raise UpdateFailed(str(err)) from err
            except SealError:
                self.docs.pop(k.id, None)
                LOGGER.warning("One person's link copy can't be opened (made by a newer version of the apps?)")
        if self.people and not opened:
            raise UpdateFailed("None of the household's link copies could be opened")
        if await self._follow_shared():
            await self._subscribe()
        self._last_ok, self._away = time.monotonic(), False
        return self.build()

    def names_seen(self) -> list[str]:
        """Every name the apps use for who did something, and the people's own names (for Configure → Who's who)."""
        seen = set(self.person_names().values()) - {"Someone"}
        for t in (self.data.things.values() if self.data else []):
            by = t.attrs.get("done_by") if isinstance(t.attrs, dict) else None
            if isinstance(by, str) and by.strip():
                seen.add(by.strip())
        return sorted(seen, key=str.lower)

    def link_names(self, parsed: Parsed) -> Parsed:
        """done_by_person beside done_by, for names linked to a Home Assistant person."""
        names = self.config_entry.options.get(CONF_NAMES) or {}
        if names:
            for t in parsed.things.values():
                by = t.attrs.get("done_by") if isinstance(t.attrs, dict) else None
                if isinstance(by, str) and names.get(by):
                    t.attrs["done_by_person"] = names[by]
        return parsed

    def name_for_user(self, user_id: str | None, user_name: str | None) -> str:
        """The name a tick made here is saved with: the app name linked to this user's person, else their Home Assistant name."""
        if user_id:
            person = next((s.entity_id for s in self.hass.states.async_all("person") if s.attributes.get("user_id") == user_id), None)
            names = self.config_entry.options.get(CONF_NAMES) or {}
            linked = next((n for n, p in names.items() if person and p == person), None)
            if linked:
                return linked
        return user_name or "Home Assistant"

    @callback
    def build(self) -> Parsed:
        people = [(pk, self.docs[k.id][1]) for pk, k in self.people.items() if k.id in self.docs]
        items = {}
        for sid in self.shared:
            d = self.docs.get(sid)
            item = d[1].get("item") if d and isinstance(d[1], dict) else None
            if isinstance(item, dict):
                items[sid] = item
        return self.link_names(parse_household(people, self.refs, items, dt_util.now()))

    # ---------- saving a change made in Home Assistant ----------
    async def async_change(self, target: list, change: Callable[[dict], bool]) -> None:
        """target: ["link", person, app, item id] or ["shared", copy id, app]; change(item) edits it in place (False: nothing to do).
        ["link", person, app, None, key]: change(list) edits a whole saved list, e.g. a log (missing: an empty one)."""
        kind = target[0]
        keys = self.people.get(target[1]) if kind == "link" else self.shared.get(target[1])
        mod = PARSERS.get(target[2])
        if keys is None or mod is None:
            raise HomeAssistantError("That isn't in Home Assistant any more")
        v, doc = await api.get_doc(self.session, keys)
        for _ in range(5):
            if not v:
                raise HomeAssistantError("Its copy has gone from the apps' server")
            obj = await self._open(keys, doc)
            if kind == "link" and len(target) > 4 and target[3] is None:
                try:
                    data = obj["apps"][target[2]]["data"]
                except (KeyError, TypeError) as err:
                    raise HomeAssistantError("It isn't in that person's link any more") from err
                whole = json.loads(data.get(target[4]) or "[]")
                if not isinstance(whole, list) or not change(whole):
                    return
                data[target[4]] = json.dumps(whole, ensure_ascii=False)
            elif kind == "link":
                try:
                    data = obj["apps"][target[2]]["data"]
                    items = json.loads(data[mod.LIST_KEY])
                except (KeyError, TypeError, ValueError) as err:
                    raise HomeAssistantError("It isn't in that person's link any more") from err
                item = next((x for x in items if isinstance(x, dict) and x.get("id") == target[3]), None)
                if item is None:
                    raise HomeAssistantError("It isn't in that person's link any more")
                if not change(item):
                    return
                data[mod.LIST_KEY] = json.dumps(items, ensure_ascii=False)
            else:
                if not isinstance(obj, dict) or not isinstance(obj.get("item"), dict):
                    raise HomeAssistantError("The shared copy can't be read")
                if not change(obj["item"]):
                    return
            obj["by"] = "ha"
            sealed = await self.hass.async_add_executor_job(seal_doc, obj, keys)
            try:
                status, nv, cur = await api.put_doc(self.session, keys, v, sealed)
            except api.Refused as err:
                raise HomeAssistantError("The apps' server doesn't let Home Assistant save yet") from err
            except api.ApiError as err:
                raise HomeAssistantError(str(err)) from err
            if status == 200:
                self.docs[keys.id] = (nv, obj)
                self.async_set_updated_data(self.build())
                return
            v, doc = nv, cur   # someone saved first: make the change on their version
        raise HomeAssistantError("Kept clashing with another change: try again")

    # ---------- the live link ----------
    def _ids(self) -> list[str]:
        return [*(k.id for k in self.people.values()), *self.shared]

    async def _subscribe(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps({"op": "sub", "ids": self._ids()}))

    async def run_live(self) -> None:
        """Runs for as long as the entry is loaded (a background task). Reconnects from 1 s up to 5 minutes apart."""
        wait = 1
        while True:
            try:
                async with self.session.ws_connect(LIVE_URL, headers=HEADERS, heartbeat=60) as ws:   # heartbeat: finds a link that died quietly
                    self._ws = ws
                    await self._subscribe()
                    self.live, wait = True, 1
                    await self.async_request_refresh()   # catch anything missed while it was down
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._on_message(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 — any failure just means "try again later"; the poll keeps things going
                if self.live:
                    LOGGER.debug("Live link down (%s)", type(err).__name__)
            self._ws, self.live = None, False
            await asyncio.sleep(wait)
            wait = min(wait * 2, 300)

    async def _on_message(self, text: str) -> None:
        try:
            m = json.loads(text)
        except ValueError:
            return
        op, did = m.get("op"), m.get("id")
        keys = next((k for k in (*self.people.values(), *self.shared.values()) if k.id == did), None)
        if keys is None:
            return
        if op == "gone":
            self.docs.pop(did, None)
        elif op == "changed":
            v = int(m.get("v") or 0)
            if v and v == self.docs.get(did, (0, None))[0]:
                return
            try:
                if isinstance(m.get("doc"), str):
                    self.docs[did] = (v, await self._open(keys, m["doc"]))
                else:
                    await self._pull(keys)
                if keys.kind == HALINK and await self._follow_shared():
                    await self._subscribe()
            except (api.ApiError, SealError):
                return   # the next poll tries again
        else:
            return
        self.async_set_updated_data(self.build())

    @callback
    def start_tick(self) -> None:
        """Work the states out again every minute (late, due, done today → tomorrow), with no new data needed."""
        @callback
        def _tick(_now) -> None:
            if self.last_update_success and self.docs:
                self.data = self.build()          # not async_set_updated_data: that would keep pushing the 5-minute pull back
                self.async_update_listeners()
        self.config_entry.async_on_unload(async_track_time_interval(self.hass, _tick, TICK))
