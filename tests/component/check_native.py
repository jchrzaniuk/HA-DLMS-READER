"""Test w środowisku HA Core, z katalogiem custom_components w PYTHONPATH."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import shutil
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from aiohttp import ClientSession, web
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.helpers import entity_registry as er, device_registry as dr
from custom_components.dlms_reader.api import ReaderClient, ReaderAuthError, ReaderError
from custom_components.dlms_reader.config_flow import ReaderConfigFlow
from custom_components.dlms_reader.migration import async_migrate_mqtt, async_cleanup_mqtt
from custom_components.dlms_reader.sensor import ReaderSensor, fresh_sample
import custom_components.dlms_reader as component
from homeassistant import loader


def entry(domain, unique_id):
    return ConfigEntry(version=1, minor_version=1, domain=domain, title=domain, data={}, options={},
                       source='user', unique_id=unique_id, discovery_keys=MappingProxyType({}), subentries_data=[])


async def main():
    with tempfile.TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        shutil.copytree(Path(component.__file__).parent, Path(directory)/'custom_components'/'dlms_reader')
        loader.async_setup(hass)
        integration = await loader.async_get_integration(hass, 'dlms_reader')
        assert integration.manifest['config_flow']
        hass.config_entries = ConfigEntries(hass, {})
        await hass.config_entries.async_initialize()
        dr.async_setup(hass)
        devices = dr.async_get(hass)
        await devices.async_load()
        registry = er.async_get(hass)
        await registry.async_load()
        mqtt_entry, native_entry = entry('mqtt', 'mqtt-test'), entry('dlms_reader', 'meter')
        hass.config_entries._entries[mqtt_entry.entry_id] = mqtt_entry
        hass.config_entries._entries[native_entry.entry_id] = native_entry
        device = devices.async_get_or_create(config_entry_id=mqtt_entry.entry_id, identifiers={('mqtt','meter')}, name='Meter')
        previous = registry.async_get_or_create('sensor','mqtt','meter_energy', config_entry=mqtt_entry,
                                                device_id=device.id, suggested_object_id='meter_energy')
        registry.async_update_entity(previous.entity_id, name='User name', labels={'test'})
        original_uuid = previous.id
        data = {'api_version':1,'device':{'id':'meter','name':'Meter','manufacturer':'Example','model':'DLMS'},
                'running':True,'phase':'online','poll_interval':30,'expire_after':105,'mqtt_enabled':False,
                'registers':[{'key':'energy','name':'Energy','obis':'1.0.1.8.0.255','class_id':3,
                 'sample':{'key':'energy','value':0.0006900000000000001,'unit':'kWh','device_class':'energy',
                           'state_class':'total_increasing','sampled_at':datetime.now(timezone.utc).isoformat()}}]}
        assert fresh_sample(data,data['registers'][0])
        assert not fresh_sample(data,data['registers'][0],datetime.now(timezone.utc)+timedelta(seconds=106))
        stopped={**data,'running':False};assert not fresh_sample(stopped,stopped['registers'][0])
        coordinator=SimpleNamespace(data=data,last_update_success=True,config_entry=native_entry)
        sensor=ReaderSensor(coordinator,data['registers'][0])
        assert sensor.available and sensor.native_value==data['registers'][0]['sample']['value']
        assert sensor.suggested_display_precision==5
        cleared=[]
        async def mqtt_publish(call):cleared.append(call.data)
        hass.services.async_register('mqtt','publish',mqtt_publish)
        await async_migrate_mqtt(hass,native_entry,data)
        assert await async_cleanup_mqtt(hass,native_entry)
        current=registry.async_get(previous.entity_id)
        assert current.id==original_uuid and current.platform=='dlms_reader'
        assert current.config_entry_id==native_entry.entry_id and current.unique_id=='meter_energy'
        assert current.name=='User name' and current.labels=={'test'} and current.disabled_by is None
        assert current.device_id==device.id and ('dlms_reader','meter') in devices.async_get(device.id).identifiers
        assert len(cleared)==1 and cleared[0]['payload']=='' and cleared[0]['retain']
        print('Registry migration preserves UUID, entity ID, device, name and labels: PASS',flush=True)
        print('Sensor units, precision, availability and stale samples: PASS',flush=True)
        fault_device=devices.async_get_or_create(config_entry_id=mqtt_entry.entry_id,identifiers={('mqtt','fault')})
        fault_entity=registry.async_get_or_create('sensor','mqtt','fault_energy',config_entry=mqtt_entry,
                                                 device_id=fault_device.id,suggested_object_id='fault_energy')
        fault_data=copy.deepcopy(data);fault_data['device']['id']='fault'
        original_update=devices.async_update_device
        def fail_device_move(device_id,**kwargs):
            if device_id==fault_device.id and kwargs.get('new_config_entry_id')==native_entry.entry_id:
                raise RuntimeError('injected migration failure')
            return original_update(device_id,**kwargs)
        with patch.object(devices,'async_update_device',side_effect=fail_device_move):
            try:await async_migrate_mqtt(hass,native_entry,fault_data)
            except RuntimeError:pass
            else:raise AssertionError('Expected an injected migration error')
        restored=registry.async_get(fault_entity.entity_id)
        assert restored.id==fault_entity.id and restored.platform=='mqtt' and restored.disabled_by is None
        assert restored.device_id==fault_device.id and restored.config_entry_id==mqtt_entry.entry_id
        print('Failed migration restores original registry ownership and availability: PASS',flush=True)
        async def endpoint(request):
            if request.headers.get('Authorization')!='Bearer test-token':raise web.HTTPUnauthorized()
            return web.json_response(data)
        app=web.Application();app.router.add_get('/v1/data',endpoint)
        runner=web.AppRunner(app);await runner.setup()
        site=web.TCPSite(runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1]
        async with ClientSession() as session:
            client=ReaderClient(session,'127.0.0.1',port,'test-token')
            assert (await client.get_data())['device']['id']=='meter'
            try:await ReaderClient(session,'127.0.0.1',port,'wrong').get_data()
            except ReaderAuthError:pass
            else:raise AssertionError('Bad token accepted')
            for token,expected in [('wrong','form'),('test-token','create_entry')]:
                flow=ReaderConfigFlow();flow.hass=hass;flow.context={'source':'user'}
                with patch('custom_components.dlms_reader.config_flow.async_get_clientsession',return_value=session):
                    # Udana konfiguracja używa nowego identyfikatora urządzenia.
                    data['device']['id']='flow-meter'
                    result=await flow.async_step_user({'host':'127.0.0.1','port':port,'token':token,'migrate_mqtt':False})
                assert result['type']==expected,result
            print('API client and config flow: valid/invalid token: PASS',flush=True)
        await runner.cleanup()
        await hass.async_stop()

asyncio.run(main())
