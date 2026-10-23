"""Opisy z potwierdzonym źródłem, bez zgadywania podobnych kodów."""
import copy
import tempfile
import unittest
from pathlib import Path

from dlms_reader.app.catalog import RegisterCatalog
from dlms_reader.app.configuration import DEFAULT, ConfigStore
from dlms_reader.app.obis_pl import DATA, description, localize


class ObisPolishTests(unittest.TestCase):
    def test_energy_tariffs_use_published_range(self):
        self.assertEqual(description('1.0.1.8.0.255')['text'], 'Energia czynna dla kierunku pobór — bezstrefowo')
        self.assertIn('strefa 4', description('1.0.2.8.4.255')['text'])
        self.assertIsNone(description('1.0.1.8.5.255'))

    def test_harmonics_and_thd_are_not_treated_as_tariffs(self):
        harmonic = description('1.0.32.7.1.255')
        thd = description('1.0.32.7.124.255')
        self.assertEqual(harmonic['text'], '1. harmoniczna w napięciu (faza 1)')
        self.assertEqual(harmonic['page'], 91)
        self.assertEqual(thd['text'], 'THD w napięciu (faza 1)')
        self.assertEqual(thd['page'], 90)
        self.assertIsNone(description('1.0.32.7.64.255'))

    def test_custom_ranges_media_and_unverified_periods_keep_original(self):
        for obis in ('0.0.128.0.1.255', '1.0.129.7.0.255', '1.0.1.128.0.255',
                     '1.65.1.8.0.255', '1.128.32.7.0.255', '7.0.1.8.0.255',
                     '1.0.1.8.0.0', '1.0.81.7.4.255', '1.0.32.23.0.255'):
            with self.subTest(obis=obis):
                value = localize({'obis': obis, 'name': 'Original description'})
                self.assertEqual(value['name'], 'Original description')
                self.assertIsNone(value['obis_description'])

    def test_channel_is_retained_and_different_families_remain_distinct(self):
        self.assertIn('kanał 2', description('1.2.32.7.0.255')['text'])
        self.assertIsNotNone(description('0.0.96.6.0.255'))
        self.assertIsNone(description('1.0.96.6.0.255'))

    def test_cached_english_catalog_is_localized_without_mutating_storage_or_config(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            store.save({'registers': [{'key': 'custom_key', 'obis': '1.0.72.7.0.255', 'class_id': 3,
                                      'name': 'Własna nazwa', 'unit': 'V'}]})
            before = copy.deepcopy(store.value)
            catalog = RegisterCatalog(Path(directory))
            catalog.save(store.value, [{'obis': '1.0.72.7.0.255', 'class_id': 3,
                                       'name': 'Ch. 0 L3 Voltage Inst. value'}], '2026-10-23T16:00:00Z')
            cached_bytes = catalog.path.read_bytes()
            result = RegisterCatalog(Path(directory)).snapshot(store.value)['objects'][0]
            self.assertEqual(result['name'], 'Napięcie (faza 3)')
            self.assertEqual(result['original_name'], 'Ch. 0 L3 Voltage Inst. value')
            self.assertTrue(result['obis_description']['url'].endswith('#page=91'))
            self.assertEqual(catalog.path.read_bytes(), cached_bytes)
            self.assertEqual(ConfigStore(directory).value, before)

    def test_all_labels_have_pinned_document_and_page(self):
        for key, value in DATA['entries'].items():
            with self.subTest(key=key):
                self.assertEqual(value['source'], 'pozyton-le23-008')
                self.assertIn(value['page'], (86, 87, 89, 90, 91))
                self.assertTrue(value['text'])
                self.assertEqual(len(DATA['sources'][value['source']]['sha256']), 64)
                medium, rest = key.split(':')
                c, d, e = map(int, rest.split('.'))
                self.assertLess(c, 128)
                self.assertLess(d, 128)
                self.assertLess(e, 128)


if __name__ == '__main__':
    unittest.main()
