"""Testy rozpoznawania OBIS, walidacji parametrów HA i przeliczania jednostek."""
import copy
import tempfile
import unittest
from unittest.mock import patch

from dlms_reader.app.configuration import DEFAULT, ConfigStore, validate
from dlms_reader.app.metadata import (
    UNITS, MetadataError, automatic_metadata, describe_reading, metadata_options,
)
from dlms_reader.app.publishing import discovery, scaled
from dlms_reader.app.runtime import Runtime


def register(obis='1.0.1.8.0.255', **overrides):
    return {'key':'test', 'name':'Test', 'obis':obis, 'class_id':3, **overrides}


def reading(obis, unit_code, raw=1000, **overrides):
    value, metadata = scaled(raw, [0, unit_code])
    return describe_reading(register(obis, **overrides), value, metadata)


class MetadataTests(unittest.TestCase):
    def test_import_export_tariffs_and_phases_are_increasing(self):
        for quantity in (1, 2, 15, 17, 18, 19, 20, 21, 22, 35, 41, 42, 61, 62):
            for tariff in (0, 1, 2):
                data = reading(f'1.0.{quantity}.8.{tariff}.255', 30)
                self.assertEqual((data['device_class'],data['state_class'],data['unit']),
                                 ('energy','total_increasing','kWh'))

    def test_signed_net_energy_uses_total_including_negative_values(self):
        for quantity in (16, 36, 56, 76):
            data = reading(f'1.0.{quantity}.8.0.255', 30, -1234)
            self.assertEqual(data['state_class'], 'total')
            self.assertAlmostEqual(data['value'], -1.234)

    def test_reactive_and_apparent_energy(self):
        self.assertEqual(reading('1.0.3.8.1.255',32)['device_class'], 'reactive_energy')
        self.assertEqual(reading('1.0.3.8.1.255',32)['state_class'], 'total_increasing')
        data=reading('1.0.9.8.0.255',31)
        self.assertIsNone(data['device_class'])
        self.assertEqual((data['unit'],data['state_class']), ('kVAh','total_increasing'))

    def test_power_factor_without_profile_inference_and_percent_conversion(self):
        for quantity in (13, 33, 53, 73, 84, 85, 86, 87):
            data=reading(f'1.0.{quantity}.7.0.255',255,.95,unit='%')
            self.assertEqual(data['device_class'], 'power_factor')
            self.assertAlmostEqual(data['value'],95)
        self.assertAlmostEqual(reading('1.0.13.7.0.255',56,95,unit=None)['value'],.95)
        self.assertIsNone(reading('7.0.13.7.0.255',255)['device_class'])

    def test_unknown_semantics_do_not_guess_statistics(self):
        for obis, unit in (('1.0.128.8.0.255',30),('1.0.1.29.0.255',30),
                           ('0.0.1.8.0.255',32),('1.0.13.7.0.255',254)):
            data=reading(obis,unit)
            self.assertIsNone(data['state_class'])

    def test_instantaneous_units_use_measurement(self):
        for code, expected in ((27,'power'),(28,'apparent_power'),(29,'reactive_power'),
                               (33,'current'),(35,'voltage'),(44,'frequency')):
            data=reading('1.0.1.7.0.255',code)
            self.assertEqual((data['device_class'],data['state_class']), (expected,'measurement'))

    def test_water_gas_and_temperature_units(self):
        self.assertEqual(reading('7.0.1.8.0.255',13)['device_class'],'gas')
        self.assertEqual(reading('8.0.1.8.0.255',13)['device_class'],'water')
        self.assertAlmostEqual(reading('6.0.1.7.0.255',9,20,unit='°F')['value'],68)

    def test_manual_units_convert_value_instead_of_changing_label(self):
        self.assertAlmostEqual(reading('1.0.1.7.0.255',27,1234,unit='kW')['value'],1.234)
        self.assertEqual(reading('1.0.1.8.0.255',30,1234,unit='Wh')['value'],1234)
        with self.assertRaises(MetadataError):reading('1.0.1.7.0.255',27,unit='kWh')
        with self.assertRaises(MetadataError):reading('1.0.128.7.0.255',254,unit='W')

    def test_manual_state_and_explicit_no_class_or_statistics(self):
        data=reading('1.0.1.8.0.255',30,state_class='total',device_class=None)
        self.assertEqual(data['state_class'],'total')
        self.assertIsNone(data['device_class'])
        self.assertIsNone(reading('1.0.1.8.0.255',30,state_class=None)['state_class'])
        self.assertEqual(reading('1.0.128.8.0.255',30,state_class='total')['state_class'],'total')
        with self.assertRaises(MetadataError):reading('1.0.1.8.0.255',30,state_class='measurement')
        with self.assertRaises(MetadataError):reading('1.0.16.8.0.255',30,-1,state_class='total_increasing')
        storage=reading('1.0.1.8.0.255',30,device_class='energy_storage')
        self.assertEqual(storage['state_class'],'measurement')

    def test_invalid_manual_metadata_rejected_on_save(self):
        for overrides in ({'device_class':'invented'}, {'state_class':'total incrasing'},
                          {'unit':123}, {'device_class':'power','unit':'kWh'},
                          {'device_class':'energy','state_class':'measurement'}):
            config=copy.deepcopy(DEFAULT);config['registers']=[register(**overrides)]
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):validate(config)

    def test_profile_round_trip_retains_manual_corrections(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConfigStore(directory)
            store.save({'registers':[register(unit='Wh',state_class='total',device_class=None)]})
            key=store.save_profile('User profile')
            reloaded=ConfigStore(directory)
            self.assertEqual(reloaded.profiles[key]['settings']['registers'],store.value['registers'])

    def test_native_and_mqtt_share_resolved_metadata_and_unknown_omits_statistics(self):
        config=copy.deepcopy(DEFAULT)
        data=reading('1.0.3.8.0.255',32)
        _, payload=discovery(config,register('1.0.3.8.0.255'),UNITS[32])
        self.assertEqual(payload['device_class'],data['device_class'])
        self.assertEqual(payload['state_class'],data['state_class'])
        _, unknown=discovery(config,register('1.0.128.8.0.255'),UNITS[30])
        self.assertNotIn('state_class',unknown)

    def test_poll_applies_manual_conversion_and_exposes_automatic_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConfigStore(directory)
            store.save({'registers':[register('1.0.1.7.0.255',unit='kW')]})
            runtime=Runtime(store)
            with patch('dlms_reader.app.runtime.session') as session:
                session.return_value.__enter__.return_value.read.side_effect=[[0,27],2300]
                sample=runtime.poll(None,store.value,{}, {})[0]
            self.assertAlmostEqual(sample['value'],2.3)
            self.assertEqual(sample['unit'],'kW')
            self.assertEqual(sample['auto_metadata']['unit'],'W')

    def test_metadata_catalog_has_shared_validation_choices(self):
        options=metadata_options()
        self.assertIn('reactive_energy',options['device_classes'])
        self.assertNotIn('measurement',options['class_states']['energy'])
        self.assertIn(None,options['class_units']['power_factor'])
