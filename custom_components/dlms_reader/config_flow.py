"""Konfiguracja ręczna i wykrywanie dodatku przez Supervisora."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ReaderClient, ReaderError, ReaderAuthError
from .const import DOMAIN, DEFAULT_HOST, DEFAULT_PORT, CONF_MIGRATE_MQTT


class ReaderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                snapshot = await ReaderClient(async_get_clientsession(self.hass), user_input[CONF_HOST],
                                               user_input[CONF_PORT], user_input[CONF_TOKEN]).get_data()
                await self.async_set_unique_id(snapshot["device"]["id"])
                self._abort_if_unique_id_configured()
                if user_input.get(CONF_MIGRATE_MQTT) and snapshot.get("mqtt_enabled"):
                    errors["base"] = "mqtt_enabled"
                else:
                    return self.async_create_entry(title=snapshot["device"]["name"], data=user_input)
            except ReaderAuthError:
                errors["base"] = "invalid_auth"
            except (ReaderError, ValueError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_TOKEN): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional(CONF_MIGRATE_MQTT, default=False): bool,
        }))

    async def async_step_hassio(self, discovery_info):
        data = discovery_info.config
        self._discovered = {CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT], CONF_TOKEN: data[CONF_TOKEN]}
        try:
            snapshot = await ReaderClient(async_get_clientsession(self.hass), **self._discovered).get_data()
        except ReaderError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(snapshot["device"]["id"])
        self._abort_if_unique_id_configured(updates=self._discovered)
        self.context["title_placeholders"] = {"name": snapshot["device"]["name"]}
        self._discovered_name = snapshot["device"]["name"]
        self._mqtt_enabled = snapshot.get("mqtt_enabled", False)
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get(CONF_MIGRATE_MQTT) and self._mqtt_enabled:
                errors["base"] = "mqtt_enabled"
            else:
                return self.async_create_entry(title=self._discovered_name, data={**self._discovered, **user_input})
        return self.async_show_form(step_id="confirm", errors=errors, data_schema=vol.Schema({
            vol.Optional(CONF_MIGRATE_MQTT, default=False): bool}),
            description_placeholders={"name": self._discovered_name})

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                snapshot = await ReaderClient(async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN]).get_data()
                if snapshot["device"]["id"] != entry.unique_id:
                    return self.async_abort(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
            except ReaderAuthError:
                errors["base"] = "invalid_auth"
            except ReaderError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reauth_confirm", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_TOKEN): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}))
