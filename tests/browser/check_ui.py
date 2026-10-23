"""Test interfejsu. Wymaga lokalnego serwera, Playwright i Chromium."""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('DLMS_BASE_URL', 'http://127.0.0.1:8099/')
VALUES = [0.0006900000000000001, 1.23456789, 1234567.123456, -0.00000001]
EXPECTED = {'pl-PL': ['0,00069', '1,23457', '1\xa0234\xa0567,12346', '0'],
            'en-US': ['0.00069', '1.23457', '1,234,567.12346', '0'],
            'de-DE': ['0,00069', '1,23457', '1.234.567,12346', '0']}

with sync_playwright() as p:
    options = {'headless': True}
    if os.environ.get('DLMS_BROWSER_PATH'):
        options['executable_path'] = os.environ['DLMS_BROWSER_PATH']
    browser = p.chromium.launch(**options)
    for locale in EXPECTED:
        for width in (1280, 390):
            context = browser.new_context(locale=locale, viewport={'width': width, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            state = {'phase': 'online', 'running': True, 'error': None, 'test': None,
                     'last_poll': '2026-10-22T08:00:00Z',
                     'measurements': [{'name': f'Pomiar {i}', 'value': v, 'unit': 'kWh'} for i, v in enumerate(VALUES)]}
            state['stop_at'] = None
            state['test_at'] = None
            def status_route(route):
                if state['stop_at'] and time.monotonic() - state['stop_at'] > .8:
                    state.update(running=False, phase='stopped')
                if state['test_at'] and time.monotonic() - state['test_at'] > .8:
                    state['test'] = {'state': 'ok', 'finished': '2026-10-22T08:00:00Z', 'measurements': state['measurements']}
                route.fulfill(json=state)
            def stop_route(route):
                state.update(phase='stopping', stop_at=time.monotonic())
                route.fulfill(json=state)
            def test_route(route):
                state.update(test={'state': 'running'}, test_at=time.monotonic())
                route.fulfill(json=state)
            def config_route(route):
                if route.request.method == 'GET':
                    route.continue_()
                else:
                    body = route.request.post_data_json
                    body.update(configured_secrets={}, mqtt={**body['mqtt'], 'password_configured': False})
                    route.fulfill(json=body)
            page.route('**/api/status', status_route)
            page.route('**/api/stop', stop_route)
            page.route('**/api/test', test_route)
            page.route('**/api/config', config_route)
            page.goto(BASE)
            expect(page.locator('#connection-status')).to_have_text('Odczyt działa')
            page.locator('[data-step="2"]').click()
            expect(page.locator('#test')).to_be_disabled()
            assert page.locator('#test').evaluate('(e)=>getComputedStyle(e).cursor') == 'default'
            expect(page.locator('#operation-description')).to_contain_text('wymagają zatrzymania')
            page.locator('#edit').click()
            expect(page.locator('#test')).to_be_enabled(timeout=10000)
            expect(page.locator('#operation-description')).to_contain_text('dostępne do edycji')
            page.locator('#test').click()
            expect(page.locator('#test')).to_be_disabled()
            expect(page.locator('#test')).to_be_enabled(timeout=10000)
            for value in EXPECTED[locale]:
                assert value in page.locator('#test-result').inner_text()
            page.locator('[data-step="3"]').click()
            assert [s.strip().removesuffix(' kWh') for s in page.locator('#measurements td:last-child').all_text_contents()] == EXPECTED[locale]
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not errors, errors
            if locale == 'pl-PL':
                Path('tmp/ui-011').mkdir(parents=True, exist_ok=True)
                page.screenshot(path=f'tmp/ui-011/measurements-{width}.png', full_page=True)
            print(locale, width, 'lock/edit/test/number format: PASS')
            context.close()
    browser.close()
