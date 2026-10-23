"""Pobranie listy przed wyborem, rozwijane grupy i trwałość zaznaczeń."""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('DLMS_BASE_URL', 'http://127.0.0.1:8099/')
HEADERS = {'Content-Type': 'application/json', 'X-DLMS-Request': '1'}
OBJECTS = [{'key': 'obis_'+obis.replace('.', '_')+'_3', 'obis': obis, 'class_id': 3,
            'name': name, 'short_name': None, 'group': group}
           for group, obis, name in (
               ('energy', '1.0.1.8.0.255', 'Energia pobrana'),
               ('energy', '1.0.2.8.0.255', 'Energia oddana'),
               ('energy', '1.0.23.8.0.255', 'Energia bierna L1'),
               ('power', '1.0.1.7.0.255', 'Moc czynna'),
               ('power', '1.0.3.7.0.255', 'Moc bierna'),
               ('current_voltage', '1.0.31.7.0.255', 'Prąd L1'),
               ('current_voltage', '1.0.72.7.0.255', 'Napięcie L3'),
               ('other', '1.0.14.7.0.255', 'Częstotliwość'),
               ('other', '1.0.13.7.0.255', 'Współczynnik mocy'))]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('DLMS_BROWSER_PATH'))
    for width in (1280, 390):
        context = browser.new_context(locale='pl-PL', viewport={'width': width, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        selected = [{'key': 'original_energy', 'obis': '1.0.1.8.0.255', 'class_id': 3,
                     'name': 'Własna nazwa energii', 'unit': 'Wh'},
                    {'key': 'unavailable', 'obis': '1.0.123.7.0.255', 'class_id': 3, 'name': 'Stary rejestr'}]
        assert page.request.post(BASE+'api/config', headers=HEADERS, data=json.dumps({
            'transport': 'tcp_wrapper', 'server_address': 1, 'host': 'meter.example',
            'referencing': 'ln', 'registers': selected})).ok
        catalog = {'ready': False, 'objects': [], 'fetched_at': None, 'count': 0}
        state = {'running': False, 'phase': 'stopped', 'test': None, 'measurements': [],
                 'last_poll': None, 'error': None}
        started = [None]
        def status(route):
            if started[0] and time.monotonic() - started[0] > .4:
                catalog.update(ready=True, objects=OBJECTS, count=9, fetched_at='2026-10-23T16:00:00Z')
                state['test'] = {'state': 'ok', 'finished': '2026-10-23T16:00:00Z', 'objects': OBJECTS}
            route.fulfill(json=state)
        def discover(route):
            started[0] = time.monotonic()
            state['test'] = {'state': 'running', 'operation': 'objects'}
            route.fulfill(json=state)
        page.route('**/api/catalog', lambda route: route.fulfill(json=catalog))
        page.route('**/api/status', status)
        page.route('**/api/objects', discover)
        page.goto(BASE)
        expect(page.locator('#connection-status')).to_have_text('Odczyt zatrzymany')
        page.locator('[data-step="2"]').click()
        expect(page.locator('#registers .register-group')).to_have_count(0)
        expect(page.locator('#register-empty')).to_be_visible()
        expect(page.locator('#start')).to_be_disabled()
        assert page.locator('#add-register').count() == 0
        page.locator('#objects').click()
        expect(page.locator('#objects')).to_be_disabled()
        expect(page.locator('#registers .register-group')).to_have_count(4, timeout=10000)
        expect(page.locator('#objects')).to_be_enabled()
        expect(page.locator('#register-count')).to_have_text('Wybrane: 1')
        assert page.locator('#registers tr').count() == 0
        energy = page.locator('[data-group="energy"]')
        energy.locator(':scope > summary').click()
        expect(energy.locator('tbody tr')).to_have_count(3)
        row = energy.locator('tbody tr').filter(has=page.get_by_text('1.0.1.8.0.255', exact=True))
        expect(row.locator('input[type="checkbox"]')).to_be_checked()
        expect(row.locator('input:not([type="checkbox"])')).to_have_value('Własna nazwa energii')
        expect(page.get_by_text('1.0.123.7.0.255', exact=True)).to_have_count(0)
        row.locator('summary').click()
        expect(row.locator('[data-metadata-field="unit"]')).to_have_value('Wh')
        energy.locator(':scope > summary').click()
        page.locator('#register-search').fill('1.0.72')
        current = page.locator('[data-group="current_voltage"]')
        expect(current.locator('tbody tr')).to_have_count(1)
        current.locator('input[type="checkbox"]').check()
        expect(page.locator('#register-count')).to_have_text('Wybrane: 2')
        page.locator('#register-search').fill('')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        saved = page.request.get(BASE+'api/config').json()['registers']
        assert len(saved) == 2
        assert saved[0]['key'] == 'original_energy' and saved[0]['unit'] == 'Wh'
        assert all('group' not in register for register in saved)
        page.reload()
        page.locator('[data-step="2"]').click()
        expect(page.locator('#register-count')).to_have_text('Wybrane: 2')
        expect(page.locator('#registers .register-group')).to_have_count(4)
        page.locator('[data-group="current_voltage"] > summary').click()
        expect(page.get_by_role('checkbox', name='Odczyt 1.0.72.7.0.255', exact=True)).to_be_checked()
        page.locator('[data-group="current_voltage"] > summary').click()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not errors, errors
        Path('captures/groups').mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f'captures/groups/collapsed-{width}.png', full_page=True)
        page.locator('[data-group="current_voltage"] > summary').click()
        page.screenshot(path=f'captures/groups/expanded-{width}.png', full_page=True)
        page.locator('[data-step="0"]').click()
        page.locator('[data-config="host"]').fill('another-meter.example')
        page.locator('[data-step="2"]').click()
        expect(page.locator('#registers .register-group')).to_have_count(0)
        expect(page.locator('#start')).to_be_disabled()
        print(width, 'fetch-before-selection, groups, search, saved identity/metadata, reload, connection invalidation: PASS')
        context.close()
    browser.close()
