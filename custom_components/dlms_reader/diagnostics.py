"""Dane diagnostyczne bez tokenów API, haseł i kluczy licznika."""
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_TOKEN


async def async_get_config_entry_diagnostics(hass, entry):
    return {'entry': async_redact_data(dict(entry.data), {CONF_TOKEN}),
            'data': entry.runtime_data.data}
