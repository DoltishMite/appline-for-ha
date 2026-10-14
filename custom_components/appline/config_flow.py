"""Setting it up: a household and its first person (an HA link code from their apps); then Configure: add or remove people,
which apps go in the sidebar, and calendar options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, SelectOptionDict, SelectSelector, SelectSelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType,
)

from . import api
from .const import CONF_CAL_DAILY, CONF_CODE, CONF_HOUSEHOLD, CONF_NAMES, CONF_PANELS, CONF_PEOPLE, DOMAIN
from .hpcrypto import HALINK, SealError, keys_for, norm, open_doc

CODE = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def probe(hass: HomeAssistant, raw: str) -> tuple[str | None, str | None]:
    """(normalised code, the person's name) for a working link code, or (None, error key)."""
    code = norm(raw)
    if len(code) < 16:
        return None, "invalid_code"
    keys = keys_for(code, HALINK)
    try:
        v, doc = await api.get_doc(async_get_clientsession(hass), keys)
        if not v:
            return None, "not_found"
        obj = await hass.async_add_executor_job(open_doc, doc, keys)
    except api.Refused:
        return None, "refused"
    except api.ApiError:
        return None, "cannot_connect"
    except SealError:
        return None, "invalid_code"
    if not isinstance(obj, dict) or obj.get("link") != 1:
        return None, "not_a_link"
    name = obj.get("name")
    return code, name if isinstance(name, str) and name.strip() else "Someone"


class ApplineConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code, res = await probe(self.hass, user_input[CONF_CODE])
            if code is None:
                errors[CONF_CODE if res in ("invalid_code", "not_found", "not_a_link") else "base"] = res
            else:
                title = str(user_input.get(CONF_HOUSEHOLD) or "").strip() or "Home"
                return self.async_create_entry(title=title, data={}, options={CONF_PEOPLE: [{CONF_CODE: code}]})
        schema = vol.Schema({vol.Required(CONF_HOUSEHOLD, default="Home"): str, vol.Required(CONF_CODE): CODE})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ApplineOptionsFlow:
        return ApplineOptionsFlow()


class ApplineOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["add_person", "remove_person", "names", "settings"])

    async def async_step_names(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Who's who: link each name the apps use (who ticked something) to a Home Assistant person."""
        coord = getattr(self.config_entry, "runtime_data", None)
        current = dict(self.config_entry.options.get(CONF_NAMES) or {})
        seen = sorted(set(coord.names_seen() if coord else []) | set(current), key=str.lower)
        if not seen:
            return self.async_abort(reason="no_names")
        if user_input is not None:
            names = {n: user_input[n] for n in seen if user_input.get(n)}
            return self.async_create_entry(data={**self.config_entry.options, CONF_NAMES: names})
        schema = vol.Schema({(vol.Optional(n, description={"suggested_value": current[n]}) if n in current else vol.Optional(n)):
                             EntitySelector(EntitySelectorConfig(domain="person")) for n in seen})
        return self.async_show_form(step_id="names", data_schema=schema)

    async def async_step_add_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code, res = await probe(self.hass, user_input[CONF_CODE])
            people = list(self.config_entry.options.get(CONF_PEOPLE, []))
            if code is None:
                errors[CONF_CODE if res in ("invalid_code", "not_found", "not_a_link") else "base"] = res
            elif any(norm(p[CONF_CODE]) == code for p in people):
                errors[CONF_CODE] = "already_added"
            else:
                return self.async_create_entry(data={**self.config_entry.options, CONF_PEOPLE: people + [{CONF_CODE: code}]})
        return self.async_show_form(step_id="add_person", data_schema=vol.Schema({vol.Required(CONF_CODE): CODE}), errors=errors)

    async def async_step_remove_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        people = list(self.config_entry.options.get(CONF_PEOPLE, []))
        coord = getattr(self.config_entry, "runtime_data", None)
        names = coord.person_names() if coord else {}
        from .coordinator import person_key   # (late: coordinator imports Home Assistant's helpers)
        labels = {}
        for i, p in enumerate(people):
            labels[str(i)] = names.get(person_key(keys_for(p[CONF_CODE], HALINK)), f"Person {i + 1}")
        if user_input is not None:
            gone = set(user_input.get("remove", []))
            if len(gone) >= len(people):
                return self.async_show_form(step_id="remove_person", data_schema=self._remove_schema(labels), errors={"base": "keep_one"})
            return self.async_create_entry(data={**self.config_entry.options,
                                                 CONF_PEOPLE: [p for i, p in enumerate(people) if str(i) not in gone]})
        return self.async_show_form(step_id="remove_person", data_schema=self._remove_schema(labels))

    @staticmethod
    def _remove_schema(labels: dict[str, str]) -> vol.Schema:
        return vol.Schema({vol.Optional("remove", default=[]): SelectSelector(SelectSelectorConfig(
            options=[SelectOptionDict(value=k, label=v) for k, v in labels.items()], multiple=True))})

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        try:
            apps = await api.get_apps(async_get_clientsession(self.hass))
        except api.ApiError:
            return self.async_abort(reason="cannot_connect")
        by_id = {a["id"]: a for a in apps}
        if user_input is not None:
            chosen = [by_id[i] for i in user_input.get(CONF_PANELS, []) if i in by_id]
            return self.async_create_entry(data={**self.config_entry.options, CONF_PANELS: chosen,
                                                 CONF_CAL_DAILY: bool(user_input.get(CONF_CAL_DAILY, True))})
        current = [p["id"] for p in self.config_entry.options.get(CONF_PANELS, []) if p["id"] in by_id]
        schema = vol.Schema({
            vol.Optional(CONF_PANELS, default=current): SelectSelector(SelectSelectorConfig(
                options=[SelectOptionDict(value=a["id"], label=a["name"]) for a in sorted(apps, key=lambda a: a["name"].lower())],
                multiple=True)),
            vol.Optional(CONF_CAL_DAILY, default=self.config_entry.options.get(CONF_CAL_DAILY, True)): bool})
        return self.async_show_form(step_id="settings", data_schema=schema)
