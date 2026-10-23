"""Integracja DLMS/COSEM Reader z Home Assistant."""

from homeassistant.const import Platform, CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ReaderClient
from .const import CONF_MIGRATE_MQTT
from .coordinator import ReaderCoordinator
from .migration import async_migrate_mqtt, async_cleanup_loop

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass, entry):
    client = ReaderClient(async_get_clientsession(hass), entry.data[CONF_HOST],
                          entry.data[CONF_PORT], entry.data[CONF_TOKEN])
    coordinator = ReaderCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    if entry.data.get(CONF_MIGRATE_MQTT):
        await async_migrate_mqtt(hass, entry, coordinator.data)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.data.get(CONF_MIGRATE_MQTT):
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MIGRATE_MQTT: False})
    task = hass.async_create_background_task(async_cleanup_loop(hass, entry), 'DLMS: usuwanie starszej konfiguracji Discovery')
    entry.async_on_unload(task.cancel)
    return True


async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
