"""Testy API, uwierzytelniania i odczytu niezależnego od sposobu publikacji."""

import copy
import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from dlms_reader.app.configuration import ConfigStore, DEFAULT
from dlms_reader.app.integration_api import AccessToken, serve_api
from dlms_reader.app.runtime import Runtime


class IntegrationAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ConfigStore(self.temp.name)
        self.store.save({'password': 'FADE', 'mqtt': {'password': 'MQTT_SECRET'}, 'registers': [
            {'key': 'energy', 'name': 'Energy', 'obis': '1.0.1.8.0.255', 'class_id': 3}]})
        self.runtime = Runtime(self.store)
        self.token = AccessToken(self.store.directory)
        self.server = serve_api(self.runtime, self.token, port=0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/v1/data'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def get(self, token=None):
        request = urllib.request.Request(self.url, headers={'Authorization': f'Bearer {token or self.token.value}'})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_authentication_is_required(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.get('invalid')
        self.assertEqual(result.exception.code, 401)
        result.exception.close()
        self.assertFalse(self.token.accepts('Bearer żółć'))

    def test_token_survives_restart_and_is_private(self):
        self.assertEqual(AccessToken(self.store.directory).value, self.token.value)
        self.assertEqual((self.store.directory/'integration-token.json').stat().st_mode & 0o777, 0o600)

    def test_versioned_snapshot_never_contains_configuration_secrets(self):
        data = self.get()
        self.assertEqual(data['api_version'], 1)
        self.assertEqual(data['device']['id'], 'dlms_meter')
        self.assertEqual(data['registers'][0]['key'], 'energy')
        for secret in ('FADE', 'MQTT_SECRET', self.token.value, 'authentication_key', 'password'):
            self.assertNotIn(secret, json.dumps(data))

    def test_api_preserves_raw_precision_and_register_metadata(self):
        sample = {'key':'energy','value':0.0006900000000000001,'unit':'kWh', 'device_class':'energy',
                  'state_class':'total_increasing','sampled_at':'2026-10-22T08:00:00+00:00'}
        self.runtime.latest['energy'] = sample
        self.assertEqual(self.get()['registers'][0]['sample'], sample)

    def test_api_cannot_write_configuration(self):
        request = urllib.request.Request(self.url, data=b'{}', headers={'Authorization':f'Bearer {self.token.value}'})
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(request)
        self.assertEqual(result.exception.code, 405)
        result.exception.close()

    def run_one_cycle(self, mqtt_enabled):
        config = copy.deepcopy(self.store.value)
        config['mqtt_enabled'] = mqtt_enabled
        sample = {'key':'energy','name':'Energy','obis':'1.0.1.8.0.255','value':1.0,'unit':'kWh',
                  'device_class':'energy','state_class':'total_increasing','sampled_at':'2026-10-22T08:00:00+00:00'}
        def stop_after_cycle(delay):
            self.runtime.stop_event.set()
        with patch.object(self.runtime, 'poll', return_value=[sample]), \
                patch.object(self.runtime.stop_event, 'wait', side_effect=stop_after_cycle):
            self.runtime.run(config)

    def test_acquisition_needs_no_mqtt_broker(self):
        with patch('dlms_reader.app.runtime.Publisher') as publisher, patch('dlms_reader.app.runtime.mqtt_settings') as settings:
            self.run_one_cycle(False)
        publisher.assert_not_called()
        settings.assert_not_called()
        self.assertEqual(self.get()['registers'][0]['sample']['value'], 1)
        self.assertIsNotNone(self.runtime.status['last_poll'])

    def test_mqtt_failure_does_not_discard_measurements(self):
        with patch('dlms_reader.app.runtime.mqtt_settings', side_effect=ConnectionError('broker unavailable')):
            self.run_one_cycle(True)
        self.assertEqual(self.get()['registers'][0]['sample']['value'], 1)
        self.assertIsNotNone(self.runtime.status['mqtt_error'])

    def test_new_installs_default_to_native_output(self):
        self.assertFalse(DEFAULT['mqtt_enabled'])
        self.assertFalse(DEFAULT['mqtt_discovery'])

    def test_optional_mqtt_does_not_create_duplicate_discovery_entities(self):
        publisher = Mock()
        publisher.generation = 1
        reading = {'key':'energy','name':'Energy','obis':'1.0.1.8.0.255','value':1,'unit':'kWh',
                   'device_class':'energy','state_class':'total_increasing'}
        config = copy.deepcopy(self.store.value)
        config.update(mqtt_enabled=True, mqtt_discovery=False)
        self.runtime.publish_reading(publisher, config, reading, {})
        self.assertTrue(publisher.publish.called)
        self.assertFalse(any(call.args[0].endswith('/config') for call in publisher.publish.call_args_list))

    def test_existing_config_keeps_mqtt_until_explicit_cutover(self):
        config = copy.deepcopy(DEFAULT)
        config.pop('mqtt_enabled')
        self.store.path.write_text(json.dumps(config))
        self.assertTrue(ConfigStore(self.temp.name).value['mqtt_enabled'])
