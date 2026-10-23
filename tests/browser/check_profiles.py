"""Test profili w przeglądarce. Wymaga pustego lokalnego katalogu DLMS_DATA."""
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get('DLMS_BASE_URL', 'http://127.0.0.1:8099/')
HEADERS = {'Content-Type': 'application/json', 'X-DLMS-Request': '1'}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=os.environ.get('DLMS_BROWSER_PATH'))
    context = browser.new_context(locale='pl-PL', viewport={'width':1280, 'height':1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE)
    expect(page.locator('#profile option')).to_have_count(1)
    response = page.request.post(BASE+'api/config', headers=HEADERS, data=json.dumps({
        'manufacturer':'Example', 'model':'Model X', 'password':'CAFE', 'host':'meter.invalid',
        'client_address':2, 'registers':[{'key':'energy', 'obis':'1.0.1.8.0.255', 'class_id':3, 'name':'Energia'}],
    }))
    assert response.ok
    page.reload()
    expect(page.locator('#connection-status')).to_have_text('Odczyt zatrzymany')
    page.get_by_text('Zapis i przenoszenie profili', exact=True).click()
    profile_name = 'Własny profil <model>'
    page.locator('#profile-name').fill(profile_name)
    page.locator('#profile-save').click()
    expect(page.locator('#message')).to_have_text('Zapisano profil użytkownika.')
    expect(page.locator('#profile option')).to_have_count(2)
    expect(page.locator('#profile option:checked')).to_have_text(profile_name)
    with page.expect_download() as download:
        page.locator('#profile-export').click()
    document = json.loads(Path(download.value.path()).read_text())
    assert document['version'] == 1 and document['name'] == profile_name
    assert document['settings']['client_address'] == 2
    assert 'password' not in document['settings'] and 'host' not in document['settings']
    assert document['settings']['registers'][0]['key'] == 'energy'
    page.locator('#profile').select_option('custom')
    page.locator('[data-config="client_address"]').fill('9')
    page.locator('#profile-file').set_input_files({'name':'profile.json', 'mimeType':'application/json',
                                                'buffer':json.dumps(document).encode()})
    expect(page.locator('#profile option')).to_have_count(3)
    expect(page.locator('[data-config="client_address"]')).to_have_value('2')
    expect(page.locator('[data-config="host"]')).to_have_value('meter.invalid')
    page.locator('[data-step="1"]').click()
    expect(page.locator('[data-secret-status="password"]')).to_have_text('Brak zapisanej wartości.')
    page.locator('#save').click()
    expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
    saved = page.request.get(BASE+'api/config').json()
    assert not saved['configured_secrets']['password']
    assert saved['registers'][0]['key'] == 'energy'
    page.reload()
    page.locator('[data-step="0"]').click()
    expect(page.locator('#profile option:checked')).to_have_text(profile_name)
    page.get_by_text('Zapis i przenoszenie profili', exact=True).click()
    for width in (1280, 390):
        page.set_viewport_size({'width':width, 'height':1000})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        Path('tmp/ui-profiles').mkdir(parents=True, exist_ok=True)
        page.screenshot(path=f'tmp/ui-profiles/profiles-{width}.png', full_page=True)
    assert not errors, errors
    print('Profiles: empty install, save, export/import, credentials, persistence, desktop/mobile: PASS')
    browser.close()
