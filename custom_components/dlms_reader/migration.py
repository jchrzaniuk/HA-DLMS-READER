"""Przenoszenie encji MQTT przez API rejestru HA, z zachowaniem identyfikatorów."""

import asyncio
import logging

from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.helpers.entity import entity_sources
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def migration_candidates(hass, data):
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    expected = {f"{data['device']['id']}_{r['key']}" for r in data['registers']}
    result = []
    for entity in registry.entities.values():
        if entity.domain != Platform.SENSOR or entity.platform != 'mqtt' or entity.unique_id not in expected:
            continue
        device = devices.async_get(entity.device_id) if entity.device_id else None
        if device and ('mqtt', data['device']['id']) in device.identifiers:
            result.append(entity)
    return result


async def async_migrate_mqtt(hass, entry, data):
    candidates = migration_candidates(hass, data)
    if not candidates:
        return
    if data.get('mqtt_enabled'):
        raise ConfigEntryNotReady('Przed przeniesieniem encji wyłącz publikację MQTT w dodatku.')
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    device_ids = {entity.device_id for entity in candidates}
    candidate_ids = {entity.entity_id for entity in candidates}
    if any(entity.device_id in device_ids and entity.entity_id not in candidate_ids
           for entity in registry.entities.values()):
        raise ConfigEntryNotReady('Urządzenie MQTT zawiera też encje spoza czytnika. Nie można przenieść go automatycznie.')
    old_devices = {device_id: devices.async_get(device_id) for device_id in device_ids}
    if any(registry.async_get_entity_id('sensor', DOMAIN, entity.unique_id) for entity in candidates):
        raise ConfigEntryNotReady('Encje integracji już istnieją. Nie można automatycznie przenieść encji MQTT.')
    backups = [{'entity_id': e.entity_id, 'unique_id': e.unique_id, 'platform': e.platform,
                'config_entry_id': e.config_entry_id, 'device_id': e.device_id,
                'disabled_by': e.disabled_by} for e in candidates]
    store = Store(hass, 1, f'{DOMAIN}.migration.{entry.entry_id}')
    await store.async_save({'entities': backups, 'cleanup_pending': False})
    migrated = []
    try:
        for entity in candidates:
            if entity.disabled_by is None:
                registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
        for _ in range(100):
            if all(e.entity_id not in entity_sources(hass) for e in candidates):
                break
            await asyncio.sleep(.1)
        else:
            raise ConfigEntryNotReady('Encje MQTT są nadal wczytane. Integracja ponowi próbę przeniesienia.')
        for entity in candidates:
            # Najpierw odłącz encje: zmiana właściciela urządzenia usuwa wpisy
            # przypisane do poprzedniej platformy w obecnych wersjach HA.
            registry.async_update_entity_platform(entity.entity_id, DOMAIN, new_config_entry_id=entry.entry_id,
                                                   new_device_id=None)
            migrated.append(entity)
        for device in old_devices.values():
            devices.async_update_device(device.id, new_config_entry_id=entry.entry_id,
                                        new_identifiers=device.identifiers | {(DOMAIN, data['device']['id'])})
        # Przywróć wcześniejszy stan włączenia encji wraz z ustawieniami użytkownika.
        for entity in candidates:
            registry.async_update_entity(entity.entity_id, device_id=entity.device_id, disabled_by=entity.disabled_by)
    except Exception:
        for entity in migrated:
            registry.async_update_entity(entity.entity_id, device_id=None)
        for device in old_devices.values():
            devices.async_update_device(device.id, new_config_entry_id=device.config_entry_id,
                                        new_identifiers=device.identifiers)
        for entity in reversed(migrated):
            registry.async_update_entity_platform(entity.entity_id, 'mqtt', new_config_entry_id=entity.config_entry_id,
                                                   new_device_id=entity.device_id)
        for entity in candidates:
            registry.async_update_entity(entity.entity_id, disabled_by=entity.disabled_by)
        raise
    prefix = data.get('mqtt_discovery_prefix', 'homeassistant')
    topics = [f"{prefix}/sensor/{data['device']['id']}/{r['key']}/config" for r in data['registers']]
    await store.async_save({'entities': backups, 'cleanup_pending': True, 'topics': topics})


async def async_cleanup_mqtt(hass, entry):
    """Usuwa starszą konfigurację Discovery niezależnie od aktualizacji encji."""
    store = Store(hass, 1, f'{DOMAIN}.migration.{entry.entry_id}')
    record = await store.async_load()
    if not record or not record.get('cleanup_pending'):
        return True
    if not hass.services.has_service('mqtt', 'publish'):
        return False
    for topic in record['topics']:
        await hass.services.async_call('mqtt', 'publish', {'topic': topic, 'payload': '', 'qos': 1, 'retain': True}, blocking=True)
    await store.async_save({**record, 'cleanup_pending': False})
    return True


async def async_cleanup_loop(hass, entry):
    warned = False
    while True:
        try:
            if await async_cleanup_mqtt(hass, entry):
                return
        except Exception:
            if not warned:
                _LOGGER.warning('Usuwanie starszej konfiguracji Discovery odłożono. Aktualizacja encji nadal działa.')
                warned = True
        await asyncio.sleep(30)
