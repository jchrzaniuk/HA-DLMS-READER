"""Test API konfiguracji i edytora parametrów HA każdego rejestru."""
import json
import os
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

BASE=os.environ.get('DLMS_BASE_URL','http://127.0.0.1:8099/')
HEADERS={'Content-Type':'application/json','X-DLMS-Request':'1'}
REGISTERS=[{'key':key,'name':name,'obis':obis,'class_id':3} for key,name,obis in (
    ('energy','Energia pobrana','1.0.1.8.0.255'),
    ('reactive','Energia bierna','1.0.3.8.0.255'),
    ('net','Bilans energii','1.0.16.8.0.255'),
    ('power','Moc','1.0.1.7.0.255'),
    ('factor','Współczynnik mocy','1.0.13.7.0.255'))]

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('DLMS_BROWSER_PATH'))
    for width in (1280,390):
        context=browser.new_context(locale='pl-PL',viewport={'width':width,'height':1000})
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        catalog={'ready':True,'fetched_at':'2026-10-23T16:00:00Z','objects':[
            {**register,'group':'power' if register['key']=='power' else 'other' if register['key']=='factor' else 'energy'} for register in REGISTERS]}
        page.route('**/api/catalog',lambda route:route.fulfill(json=catalog))
        page.route('**/api/status',lambda route:route.fulfill(json={'running':False,'phase':'stopped','error':None,'test':None,'measurements':[],'last_poll':None}))
        assert page.request.post(BASE+'api/config',headers=HEADERS,data=json.dumps({'registers':REGISTERS})).ok
        page.goto(BASE)
        expect(page.locator('#connection-status')).to_have_text('Odczyt zatrzymany')
        page.locator('[data-step="2"]').click()
        page.locator('[data-group="energy"] > summary').click()
        row=page.locator('#registers tbody tr').first
        row.locator('summary').click()
        classes=row.locator('[data-metadata-field="device_class"]')
        state=row.locator('[data-metadata-field="state_class"]')
        unit=row.locator('[data-metadata-field="unit"]')
        expect(classes).to_have_value('')
        classes.select_option('energy');state.select_option('total');unit.select_option('Wh')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        saved=page.request.get(BASE+'api/config').json()['registers'][0]
        assert (saved['device_class'],saved['state_class'],saved['unit'])==('energy','total','Wh')
        classes.select_option('power');unit.select_option('kWh')
        page.locator('#save').click()
        expect(page.locator('#message')).to_contain_text('nie pasuje')
        assert page.request.get(BASE+'api/config').json()['registers'][0]==saved
        classes.select_option('__none__');state.select_option('__none__');unit.select_option('')
        page.locator('#save').click()
        expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        page.reload();page.locator('[data-step="2"]').click();page.locator('[data-group="energy"] > summary').click();row=page.locator('#registers tbody tr').first
        row.locator('summary').click()
        expect(row.locator('[data-metadata-field="device_class"]')).to_have_value('__none__')
        expect(row.locator('[data-metadata-field="state_class"]')).to_have_value('__none__')
        expect(row.locator('[data-metadata-field="unit"]')).to_have_value('')
        row.locator('[data-metadata-field="device_class"]').select_option('')
        row.locator('[data-metadata-field="state_class"]').select_option('')
        page.locator('#save').click();expect(page.locator('#message')).to_have_text('Ustawienia zapisane.')
        assert all(k not in page.request.get(BASE+'api/config').json()['registers'][0] for k in ('unit','device_class','state_class'))
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        assert not page.locator('.register-table').evaluate('(e)=>e.scrollWidth>e.clientWidth+1')
        assert not errors,errors
        Path('tmp/ui-metadata').mkdir(parents=True,exist_ok=True)
        page.screenshot(path=f'tmp/ui-metadata/editor-{width}.png',full_page=True)
        print(width,'metadata editor, validation, null/auto persistence: PASS')
        context.close()
    browser.close()
