"""Keeps the apps' data in Home Assistant up to date.

One config entry = one code: a personal sync code (everything in that setup, plus the copies of the things it shares, which are
newer than the synced ones while another person is ticking things off) or one shared thing's code.
Changes arrive over the live link (wss /api/live) the moment they're saved; a pull every 5 minutes is the safety net, and the
entities are worked out again every minute so time-based states (due → late) move on without a new save.
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .const import CONF_CODE, CONF_KIND, DOMAIN, HEADERS, LIVE_URL, LOGGER
from .hpcrypto import SYNC, TOGETHER, Keys, SealError, keys_for, open_doc
from .parsers import Parsed, parse_shared, parse_sync, sync_share_codes

POLL = timedelta(minutes=5)
TICK = timedelta(minutes=1)


class ApplineCoordinator(DataUpdateCoordinator[Parsed]):
    """Fetches, opens and parses; data is a Parsed (devices + things)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=POLL)
        self.session = async_get_clientsession(hass)
        self.kind: str = entry.data.get(CONF_KIND, SYNC)
        self.main: Keys = keys_for(entry.data[CONF_CODE], self.kind)
        self.shared: dict[tuple[str, str], Keys] = {}       # (app, item id) → keys of that thing's shared copy
        self.docs: dict[str, tuple[int, Any]] = {}          # document id → (version, opened JSON)
        self.live = False
        self.names: dict[str, dict[str, str]] = {}          # thing key → name placeholders, to notice a rename
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    # ---------- fetching ----------
    async def _open(self, keys: Keys, doc: str) -> Any:
        return await self.hass.async_add_executor_job(open_doc, doc, keys)

    async def _pull(self, keys: Keys) -> None:
        v, doc = await api.get_doc(self.session, keys)
        if not v:
            self.docs.pop(keys.id, None)
        elif self.docs.get(keys.id, (0, None))[0] != v:
            self.docs[keys.id] = (v, await self._open(keys, doc))

    def _wanted_shared(self) -> dict[tuple[str, str], Keys]:
        main = self.docs.get(self.main.id)
        if self.kind != SYNC or not main:
            return {}
        return {k: self.shared.get(k) or keys_for(code, TOGETHER) for k, code in sync_share_codes(main[1]).items()}

    async def _pull_shared(self) -> bool:
        """Follow the setup's shared things (new ones fetched, gone ones dropped). True if the list changed."""
        want = self._wanted_shared()
        changed = {k.id for k in want.values()} != {k.id for k in self.shared.values()}
        for k in self.shared.values():
            if k.id not in {w.id for w in want.values()}:
                self.docs.pop(k.id, None)
        self.shared = want
        for keys in want.values():
            try:
                await self._pull(keys)
            except (api.ApiError, SealError):
                self.docs.pop(keys.id, None)   # that thing falls back to the synced copy
        return changed

    async def _async_update_data(self) -> Parsed:
        try:
            await self._pull(self.main)
            if await self._pull_shared():
                await self._subscribe()
        except api.Refused as err:
            raise UpdateFailed("The apps' server refused Home Assistant: it needs the update that lets the integration read") from err
        except api.ApiError as err:
            raise UpdateFailed(str(err)) from err
        except SealError as err:
            raise UpdateFailed(f"The synced copy {err}") from err
        return self.build()

    @callback
    def build(self) -> Parsed:
        now = dt_util.now()
        main = self.docs.get(self.main.id)
        if not main:
            return Parsed()
        if self.kind == TOGETHER:
            return parse_shared(main[1], now)
        shared = {}
        for k, keys in self.shared.items():
            d = self.docs.get(keys.id)
            item = d[1].get("item") if d and isinstance(d[1], dict) else None
            if isinstance(item, dict):
                shared[k] = item
        return parse_sync(main[1], shared, now)

    # ---------- the live link ----------
    def _ids(self) -> list[str]:
        return [self.main.id, *(k.id for k in self.shared.values())]

    async def _subscribe(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps({"op": "sub", "ids": self._ids()}))

    async def run_live(self) -> None:
        """Runs for as long as the entry is loaded (a background task). Reconnects from 1 s up to 5 minutes apart."""
        wait = 1
        while True:
            try:
                async with self.session.ws_connect(LIVE_URL, headers=HEADERS, heartbeat=60) as ws:   # finds a link that died quietly
                    self._ws = ws
                    await self._subscribe()
                    if not self.live:
                        LOGGER.debug("Live link up")
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
        keys = next((k for k in (self.main, *self.shared.values()) if k.id == did), None)
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
                if keys is self.main and await self._pull_shared():
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
