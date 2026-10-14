"""Reading and saving sealed documents on the apps' server (only copies that already exist: a person's HA link, a shared thing)."""
from __future__ import annotations

import json
from typing import Any

import aiohttp

from .const import APPS_URL, HEADERS, SYNC_URL
from .hpcrypto import Keys


class ApiError(Exception):
    """The server couldn't be reached or answered badly."""


class Refused(ApiError):
    """The server refused this client (it hasn't been updated to let the integration read)."""


TIMEOUT = aiohttp.ClientTimeout(total=20)


async def get_doc(session: aiohttp.ClientSession, keys: Keys) -> tuple[int, str | None]:
    """(version, sealed document) for these keys; (0, None) when nothing is saved under them."""
    try:
        async with session.get(SYNC_URL, params={"id": keys.id}, headers=HEADERS, timeout=TIMEOUT) as r:
            if r.status == 403:
                raise Refused("the server refused the request")
            if r.status != 200:
                raise ApiError(f"server answered {r.status}")
            j: dict[str, Any] = await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ApiError(f"can't reach the server ({type(err).__name__})") from err
    v = int(j.get("v") or 0)
    doc = j.get("doc")
    return (v, doc) if v and isinstance(doc, str) else (0, None)


async def put_doc(session: aiohttp.ClientSession, keys: Keys, base: int, doc: str) -> tuple[int, int, str | None]:
    """Save over version base. (200, new version, None), or (409, the current version, its document) when someone saved first."""
    try:
        async with session.put(SYNC_URL, params={"id": keys.id}, headers={**HEADERS, "Content-Type": "application/json"},
                               data=json.dumps({"base": base, "doc": doc}), timeout=TIMEOUT) as r:
            if r.status == 403:
                raise Refused("the server refused the save")
            j: dict[str, Any] = await r.json(content_type=None)
            if r.status == 409:
                return 409, int(j.get("v") or 0), j.get("doc") if isinstance(j.get("doc"), str) else None
            if r.status != 200:
                raise ApiError(j.get("error") or f"server answered {r.status}")
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ApiError(f"can't reach the server ({type(err).__name__})") from err
    return 200, int(j.get("v") or 0), None


async def get_apps(session: aiohttp.ClientSession) -> list[dict[str, Any]]:
    """The app list (kit/apps.json): [{ id, name, path }]."""
    try:
        async with session.get(APPS_URL, timeout=TIMEOUT) as r:
            if r.status != 200:
                raise ApiError(f"server answered {r.status}")
            j = await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise ApiError(f"can't reach the server ({type(err).__name__})") from err
    apps = j.get("apps") if isinstance(j, dict) else j
    return [{"id": a["id"], "name": a.get("name") or a["id"], "path": a.get("path") or a["id"]}
            for a in apps or [] if isinstance(a, dict) and isinstance(a.get("id"), str) and not a.get("hidden") and not a.get("draft")]
