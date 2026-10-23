"""Test adresowania HDLC, profili i zachowania WRAPPER w formularzu."""
import json
import os
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('DLMS_BASE_URL', 'http://127.0.0.1:8099/')
HEADERS = {'Content-Type': 'application/json', 'X-DLMS-Request': '1'}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('DLMS_BROWSER_PATH'))
    for width in (1280, 390):
        context = browser.new_context(locale='pl-PL', viewport={'width': width, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        assert page.request.post(BASE+'api/config', headers=HEADERS, data=json.dumps({
            'transport': 'tcp_hdlc', 'server_address': 168, 'hdlc_address_size': 0,
            'host': 'meter.example', 'port': 4444, 'mqtt_enabled': False})).ok
        page.goto(BASE)
        expect(page.locator('#connection-status')).to_have_text('Odczyt zatrzymany')
        logical = page.locator('#hdlc-logical-address')
        physical = page.locator('#hdlc-physical-address')
        size = page.locator('[data-config="hdlc_address_size"]')
        wrapper = page.locator('[data-config="server_address"]')
        expect(logical).to_have_value('1')
        expect(physical).to_have_value('40')
        expect(wrapper).to_be_hidden()
        physical.fill('41')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        assert page.request.get(BASE+'api/config').json()['server_address'] == 169
        page.reload()
        expect(physical).to_have_value('41')
        page.get_by_text('Parametry zaawansowane', exact=True).click()
        size.select_option('2')
        logical.fill('128')
        page.locator('#save').click()
        expect(page.locator('#message')).to_contain_text('0–127')
        assert page.request.get(BASE+'api/config').json()['server_address'] == 169
        logical.fill('1')
        physical.fill('40')
        size.select_option('4')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        assert page.request.get(BASE+'api/config').json()['server_address'] == 16424
        page.reload()
        expect(logical).to_have_value('1')
        expect(physical).to_have_value('40')
        expect(size).to_have_value('4')
        legacy = {'version': 1, 'name': 'Profil HDLC', 'settings': {
            'transport': 'tcp_hdlc', 'server_address': 168}}
        page.locator('#profile-file').set_input_files({'name': 'profile.json', 'mimeType': 'application/json',
                                                     'buffer': json.dumps(legacy).encode()})
        expect(page.locator('#message')).to_contain_text('Wczytano profil')
        expect(logical).to_have_value('1')
        expect(physical).to_have_value('40')
        expect(size).to_have_value('0')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        assert page.request.get(BASE+'api/config').json()['server_address'] == 168
        for transport in ('serial_hdlc', 'tcp_wrapper', 'tcp_hdlc'):
            page.locator('[data-config="transport"]').select_option(transport)
            if transport == 'tcp_wrapper':
                expect(logical).to_be_hidden()
                expect(physical).to_be_hidden()
                expect(wrapper).to_be_visible()
                wrapper.fill('1234')
                page.locator('#save').click()
                expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
                assert page.request.get(BASE+'api/config').json()['server_address'] == 1234
            else:
                expect(logical).to_be_visible()
                expect(physical).to_be_visible()
        logical.fill('1')
        physical.fill('40')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not errors, errors
        Path('captures/hdlc').mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f'captures/hdlc/connection-{width}.png', full_page=True)
        print(width, 'HDLC migration, validation, address lengths, profiles, WRAPPER: PASS')
        context.close()
    browser.close()
