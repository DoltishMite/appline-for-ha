"""Setting it up: a code (personal sync or one shared thing), then which apps go in the sidebar (options)."""
from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict, SelectSelector, SelectSelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType,
)

from . import api
from .const import CONF_CODE, CONF_KIND, CONF_PANELS, DOMAIN
from .hpcrypto import SYNC, TOGETHER, SealError, keys_for, norm, open_doc
from .parsers import PARSERS

CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})


class ApplineConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = norm(user_input[CONF_CODE])
            if len(code) < 6:
                errors[CONF_CODE] = "invalid_code"
            else:
                try:
                    kind, title = await self._probe(code)
                except api.Refused:
                    errors["base"] = "refused"
                except api.ApiError:
                    errors["base"] = "cannot_connect"
                except SealError:
                    errors[CONF_CODE] = "invalid_code"
                else:
                    if kind is None:
                        errors[CONF_CODE] = "not_found"
                    else:
                        # a hash of the document id: finds a duplicate without keeping anything that leads back to the code
                        await self.async_set_unique_id(hashlib.sha256(keys_for(code, kind).id.encode()).hexdigest()[:20])
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(title=title, data={CONF_CODE: code, CONF_KIND: kind})
        return self.async_show_form(step_id="user", data_schema=CODE_SCHEMA, errors=errors)

    async def _probe(self, code: str) -> tuple[str | None, str]:
        """Is this a personal sync code or a share code? Opens the copy to be sure the code is right."""
        session = async_get_clientsession(self.hass)
        for kind in (SYNC, TOGETHER):
            keys = keys_for(code, kind)
            v, doc = await api.get_doc(session, keys)
            if not v:
                continue
            obj = await self.hass.async_add_executor_job(open_doc, doc, keys)
            if kind == SYNC:
                name = obj.get("name") if isinstance(obj, dict) else None
                return SYNC, f"Sync: {name}" if isinstance(name, str) and name.strip() else "Personal sync"
            app = PARSERS.get(obj.get("app")) if isinstance(obj, dict) else None
            item = obj.get("item") if isinstance(obj, dict) else None
            what = item.get("name") if isinstance(item, dict) else None
            return TOGETHER, f"Shared: {what}" if isinstance(what, str) and what else f"Shared {app.NAME if app else 'thing'}"
        return None, ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ApplineOptionsFlow:
        return ApplineOptionsFlow()


class ApplineOptionsFlow(OptionsFlowWithReload):
    """Which apps appear in the sidebar."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        try:
            apps = await api.get_apps(async_get_clientsession(self.hass))
        except api.ApiError:
            return self.async_abort(reason="cannot_connect")
        by_id = {a["id"]: a for a in apps}
        if user_input is not None:
            chosen = [by_id[i] for i in user_input.get(CONF_PANELS, []) if i in by_id]
            return self.async_create_entry(data={**self.config_entry.options, CONF_PANELS: chosen})
        current = [p["id"] for p in self.config_entry.options.get(CONF_PANELS, []) if p["id"] in by_id]
        schema = vol.Schema({vol.Optional(CONF_PANELS, default=current): SelectSelector(SelectSelectorConfig(
            options=[SelectOptionDict(value=a["id"], label=a["name"]) for a in sorted(apps, key=lambda a: a["name"].lower())],
            multiple=True))})
        return self.async_show_form(step_id="init", data_schema=schema)
