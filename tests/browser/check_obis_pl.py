"""Polskie opisy ze źródłami, fallback i zachowanie nazw użytkownika."""
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dlms_reader.app.obis_pl import localize, source_documents

BASE = os.environ.get('DLMS_BASE_URL', 'http://127.0.0.1:8099/')
HEADERS = {'Content-Type':'application/json','X-DLMS-Request':'1'}
OBJECTS = [localize({'key':key,'obis':obis,'class_id':3,'name':name,'group':group})
           for key,obis,name,group in (
               ('energy','1.0.1.8.0.255','Ch. 0 Active energy import','energy'),
               ('voltage','1.0.72.7.0.255','Ch. 0 L3 Voltage Inst. value','current_voltage'),
               ('vendor','0.0.128.0.1.255','Manufacturer specific','other'))]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=os.environ.get('DLMS_BROWSER_PATH'))
    for width in (1280,390):
        context = browser.new_context(locale='pl-PL', viewport={'width':width,'height':1000})
        page = context.new_page()
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        own = {'key':'own_voltage','obis':'1.0.72.7.0.255','class_id':3,'name':'Napięcie w rozdzielnicy'}
        assert page.request.post(BASE+'api/config',headers=HEADERS,data=json.dumps({'registers':[own]})).ok
        page.route('**/api/catalog',lambda route:route.fulfill(json={
            'ready':True,'objects':OBJECTS,'fetched_at':'2026-10-23T16:00:00Z','description_sources':source_documents()}))
        page.route('**/api/status',lambda route:route.fulfill(json={
            'running':False,'phase':'stopped','test':None,'measurements':[],'last_poll':None,'error':None}))
        page.goto(BASE)
        expect(page.locator('#connection-status')).to_have_text('Odczyt zatrzymany')
        page.locator('[data-step="2"]').click()
        page.locator('#obis-sources > summary').click()
        expect(page.locator('#obis-source-list a')).to_have_count(2)
        page.locator('[data-group="energy"] > summary').click()
        energy = page.locator('[data-group="energy"] tbody tr')
        expect(energy.locator('input:not([type="checkbox"])')).to_have_value('Energia czynna dla kierunku pobór — bezstrefowo')
        page.locator('[data-group="energy"] > summary').click()
        page.locator('[data-group="current_voltage"] > summary').click()
        voltage = page.locator('[data-group="current_voltage"] tbody tr')
        expect(voltage.locator('input:not([type="checkbox"])')).to_have_value('Napięcie w rozdzielnicy')
        voltage.locator('summary').click()
        expect(voltage.locator('.register-metadata')).to_contain_text('Opis OBIS: Napięcie (faza 3)')
        expect(voltage.locator('.register-metadata')).to_contain_text('Ch. 0 L3 Voltage Inst. value')
        expect(voltage.locator('.register-metadata a')).to_have_attribute('href',
            'https://pozyton.com.pl/wp-content/uploads/2024/05/instrukcja-operatorska-le-23-4.pdf#page=91')
        page.locator('[data-group="other"] > summary').click()
        vendor = page.locator('[data-group="other"] tbody tr')
        expect(vendor.locator('input:not([type="checkbox"])')).to_have_value('Manufacturer specific')
        vendor.locator('summary').click()
        expect(vendor.locator('.register-metadata')).to_contain_text('Brak potwierdzonego polskiego opisu')
        page.locator('[data-group="other"] > summary').click()
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        saved=page.request.get(BASE+'api/config').json()['registers']
        assert saved == [own]
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        assert not page.locator('.register-table').first.evaluate('(table)=>table.scrollWidth>table.clientWidth+1')
        assert not errors, errors
        Path('captures/obis-pl').mkdir(parents=True,exist_ok=True)
        page.screenshot(path=f'captures/obis-pl/sources-{width}.png',full_page=True)
        print(width,'published Polish labels, provenance, original fallback, custom names and clean persistence: PASS')
        context.close()
    browser.close()
