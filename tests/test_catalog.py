"""Lista z licznika, podział OBIS i powiązanie z parametrami sesji."""
import contextlib
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from dlms_reader.app.catalog import RegisterCatalog, clean_objects, register_group
from dlms_reader.app.configuration import DEFAULT, ConfigStore
from dlms_reader.app.runtime import Runtime

OBJECTS = [{'obis': obis, 'class_id': 3, 'name': name, 'short_name': 4096 + index*64}
           for index, (obis, name) in enumerate((
               ('1.0.1.8.0.255', 'Energia'), ('1.0.1.7.0.255', 'Moc'),
               ('1.0.31.7.0.255', 'Prąd'), ('1.0.72.7.0.255', 'Napięcie'),
               ('1.0.14.7.0.255', 'Częstotliwość')))]


class CatalogTests(unittest.TestCase):
    def test_obis_groups_include_phases_tariffs_and_unknown_codes(self):
        cases = {'1.0.1.8.0.255': 'energy', '1.0.23.8.2.255': 'energy',
                 '1.0.76.8.0.255': 'energy', '1.0.9.8.0.255': 'energy',
                 '1.0.1.9.0.255': 'energy', '1.0.2.29.0.255': 'energy',
                 '1.0.1.6.0.255': 'power', '1.0.63.7.0.255': 'power',
                 '1.0.31.7.0.255': 'current_voltage', '1.0.72.3.0.255': 'current_voltage',
                 '1.0.13.7.0.255': 'other', '1.0.14.7.0.255': 'other',
                 '1.0.99.7.0.255': 'other', '7.0.1.8.0.255': 'other', 'invalid': 'other'}
        for obis, expected in cases.items():
            with self.subTest(obis=obis):
                self.assertEqual(register_group(obis), expected)

    def test_catalog_excludes_non_register_objects_and_deduplicates_by_class(self):
        values = clean_objects([*OBJECTS, OBJECTS[0], {'obis': 'invalid', 'class_id': 3},
                                {'obis': '0.0.43.1.0.255', 'class_id': 1},
                                {**OBJECTS[0], 'class_id': 4}])
        self.assertEqual(len(values), 6)
        self.assertEqual(len({item['key'] for item in values}), 6)
        self.assertEqual({item['group'] for item in values}, {'energy', 'power', 'current_voltage', 'other'})

    def test_cache_survives_restart_but_not_connection_or_credentials_change(self):
        config = copy.deepcopy(DEFAULT)
        config['password'] = 'SECRET'
        with tempfile.TemporaryDirectory() as directory:
            catalog = RegisterCatalog(Path(directory))
            self.assertFalse(catalog.snapshot(config)['ready'])
            catalog.save(config, OBJECTS, '2026-10-23T16:00:00Z')
            loaded = RegisterCatalog(Path(directory))
            self.assertTrue(loaded.snapshot(config)['ready'])
            self.assertEqual(catalog.path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('SECRET', catalog.path.read_text())
            self.assertNotIn('identity', json.dumps(loaded.snapshot(config)))
            for field, value in (('host', 'other-host'), ('client_address', 1), ('password', 'NEW'),
                                 ('server_address', 168), ('authentication', 'lls'), ('referencing', 'sn')):
                with self.subTest(field=field):
                    changed = {**config, field: value}
                    self.assertFalse(loaded.snapshot(changed)['ready'])
                    self.assertEqual(loaded.snapshot(changed)['objects'], [])
            for changes in ({'name': 'New name'}, {'registers': OBJECTS}, {'poll_interval': 60}):
                self.assertTrue(loaded.snapshot({**config, **changes})['ready'])

    def test_only_discovered_registers_can_be_saved_after_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(ConfigStore(directory))
            runtime.catalog.save(runtime.store.value, OBJECTS, '2026-10-23T16:00:00Z')
            energy = {'key': 'saved_key', 'obis': OBJECTS[0]['obis'], 'class_id': 3, 'name': 'Własna nazwa'}
            runtime.save({'registers': [energy]})
            with self.assertRaises(ValueError):
                runtime.save({'registers': [{**energy, 'obis': '1.0.99.7.0.255'}]})
            self.assertEqual(runtime.store.value['registers'], [energy])

    def test_discovery_persists_catalog_and_failed_retry_preserves_it(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(ConfigStore(directory))
            config = copy.deepcopy(DEFAULT)
            meter = Mock()
            meter.objects.return_value = OBJECTS
            @contextlib.contextmanager
            def session(*args):
                yield meter
            with patch('dlms_reader.app.runtime.session', session):
                runtime.test_job(config, True)
                self.assertEqual(runtime.snapshot()['test']['state'], 'ok')
                self.assertEqual(runtime.catalog_snapshot()['count'], 5)
                before = runtime.catalog.path.read_bytes()
                meter.objects.side_effect = TimeoutError('private diagnostic detail')
                runtime.test_job(config, True)
            self.assertEqual(runtime.snapshot()['test']['state'], 'error')
            self.assertNotIn('private diagnostic detail', json.dumps(runtime.snapshot()))
            self.assertEqual(runtime.catalog.path.read_bytes(), before)
            self.assertTrue(Runtime(ConfigStore(directory)).catalog_snapshot()['ready'])

    def test_sn_discovery_fetches_short_names_before_register_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(ConfigStore(directory))
            runtime.save({'host': 'meter.example', 'referencing': 'sn', 'registers': []})
            meter = Mock()
            meter.objects.return_value = OBJECTS
            @contextlib.contextmanager
            def session(*args):
                yield meter
            with patch('dlms_reader.app.runtime.session', session):
                runtime.test(enumerate_objects=True)
                runtime.job.join(timeout=2)
            self.assertEqual(runtime.snapshot()['test']['state'], 'ok')
            energy = next(item for item in runtime.catalog_snapshot()['objects'] if item['obis'] == OBJECTS[0]['obis'])
            self.assertEqual(energy['short_name'], 4096)

    def test_invalid_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'register-catalog.json').write_text('{invalid')
            self.assertFalse(RegisterCatalog(Path(directory)).snapshot(DEFAULT)['ready'])


if __name__ == '__main__':
    unittest.main()
