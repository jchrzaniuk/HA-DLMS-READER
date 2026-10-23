'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const fields = $$('[data-config]');
let config, profiles, metadataOptions, registers = [], latestReadings = new Map(), page = 0, busy = false, active = false, testBusy = false, profileChanged = false, statusKnown = false, phase = 'loading';
let catalogue = {ready:false,objects:[]}, catalogConfig, catalogUsable = false, catalogLoading = null;
const openGroups = new Set();
const openMetadata = new Set();
const registerGroups = {energy:'Energia',power:'Moc',current_voltage:'Prąd i napięcie',other:'Pozostałe parametry'};
const connectionFields = ['transport','host','port','serial_device','baudrate','parity','bytesize','stopbits','client_address','server_address','hdlc_address_size','referencing','authentication','password_format','text_encoding','security','security_suite','client_system_title','server_system_title'];
const registerIdentity = register => `${register.obis}/${register.class_id}`;
function connectionMatchesSaved(patch) {
  return !profileChanged && catalogConfig && connectionFields.every(key=>patch[key]===catalogConfig[key]) &&
    ['password','block_cipher_key','authentication_key'].every(key=>!Object.hasOwn(patch,key));
}
function mergeRegisters(objects, previous) {
  const existing = new Map(previous.map(register=>[registerIdentity(register),register]));
  return objects.map(item=>{
    const saved=existing.get(registerIdentity(item));
    return {...item,...saved,group:item.group,short_name:item.short_name || saved?.short_name,selected:saved?.selected || false};
  });
}
async function refreshCatalog() {
  if (catalogLoading) return catalogLoading;
  catalogLoading = (async()=>{
    catalogue=await api('catalog');
    catalogUsable=catalogue.ready && connectionMatchesSaved(formPatch());
    if (catalogUsable) registers=mergeRegisters(catalogue.objects,registers);
    renderRegisters();dynamic();lockControls();
  })();
  try {await catalogLoading;} finally {catalogLoading=null;}
}
const measurementFormat = new Intl.NumberFormat(undefined, {maximumFractionDigits:5});
function formatMeasurement(value) {
  return typeof value === 'number' && Number.isFinite(value) ? measurementFormat.format(Math.abs(value) < 0.000005 ? 0 : value) : '—';
}
const numbers = new Set(['port','baudrate','bytesize','stopbits','client_address','server_address','hdlc_address_size','timeout','security_suite','fc_client_address','poll_interval','mqtt.port']);
const stepNames = ['dostęp','test i rejestry','Home Assistant'];
const transportNames = {tcp_wrapper:'TCP · WRAPPER',tcp_hdlc:'TCP · HDLC',serial_hdlc:'Port szeregowy · HDLC'};
const authNames = {none:'Sesja publiczna',lls:'LLS · hasło',hls_gmac:'HLS · GMAC',hls_sha256:'HLS · SHA-256',hls:'HLS · AES',hls_sha1:'HLS · SHA-1',hls_md5:'HLS · MD5'};
const valueAt = (object, key) => key.split('.').reduce((v, p) => v?.[p], object);
function assign(object, key, value) { const parts = key.split('.'); if (parts.length === 2) (object[parts[0]] ||= {})[parts[1]] = value; else object[key] = value; }
function message(text, error = false) { $('#message').hidden = !text; $('#message').textContent = text; $('#message').classList.toggle('error', error); }
async function api(path, body) {
  const options = body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-DLMS-Request':'1'},body:JSON.stringify(body)};
  const response = await fetch(`api/${path}`, {...options, signal:AbortSignal.timeout(15000)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Błąd HTTP ${response.status}`);
  return result;
}
function renderProfiles() {
  $('#profile').replaceChildren(new Option('Własna konfiguracja', 'custom'),
    ...Object.entries(profiles).map(([id, profile]) => new Option(profile.name, id)));
  $('#profile').value = config.profile;
  $('#profile-name').value = profiles[config.profile]?.name || '';
}
function loadProfile(id) {
  const patch = formPatch();
  config = {...config, ...patch, mqtt:{...config.mqtt, ...patch.mqtt}, profile:id};
  if (id !== 'custom') {
    config = {...config, ...profiles[id].settings, configured_secrets:{}};
    profileChanged = true;
    message('Wczytano profil. Uzupełnij dane uwierzytelniania i zapisz ustawienia.');
  } else message('Własna konfiguracja: ustaw parametry i zapisz nowy profil pod wybraną nazwą.');
  fill();lockControls();
}
function fill() {
  for (const field of fields) {
    if (field.hasAttribute('data-secret')) {
      field.value = '';
      const configured = field.dataset.config === 'mqtt.password' ? config.mqtt.password_configured : config.configured_secrets?.[field.dataset.config];
      field.placeholder = configured ? 'Zapisano · wpisz, aby zmienić' : 'Nie podano';
      const hint = document.querySelector(`[data-secret-status="${field.dataset.config}"]`);
      if (hint) hint.textContent = configured ? 'Wartość zapisana. Puste pole zachowuje dotychczasowe dane.' : 'Brak zapisanej wartości.';
    } else if (field.type === 'checkbox') field.checked = Boolean(valueAt(config, field.dataset.config));
    else field.value = valueAt(config, field.dataset.config) ?? '';
  }
  const address = config.server_address, size = config.hdlc_address_size || (address < 128 ? 1 : address < 16384 ? 2 : 4);
  const divisor = size === 4 ? 16384 : 128;
  if (!config.hdlc_address_size && address >= 16384) $('[data-config="hdlc_address_size"]').value = 4;
  $('#hdlc-logical-address').value = size === 1 ? 0 : Math.floor(address / divisor);
  $('#hdlc-physical-address').value = size === 1 ? address : address % divisor;
  renderProfiles();
  registers = config.registers.map(r => ({...r, selected:true}));
  catalogUsable=catalogue.ready && connectionMatchesSaved(formPatch());
  if (catalogUsable) registers=mergeRegisters(catalogue.objects,registers);
  renderRegisters(); dynamic();
}
function formPatch() {
  const patch = {};
  for (const field of fields) {
    const key = field.dataset.config;
    if (field.hasAttribute('data-secret') && !field.value && !(profileChanged && key !== 'mqtt.password')) continue;
    assign(patch, key, field.type === 'checkbox' ? field.checked : numbers.has(key) ? Number(field.value) : field.value);
  }
  patch.profile = $('#profile').value;
  if (patch.transport !== 'tcp_wrapper') {
    const number = selector => $(selector).value.trim() === '' ? null : Number($(selector).value);
    patch.hdlc_logical_address = number('#hdlc-logical-address');
    patch.hdlc_physical_address = number('#hdlc-physical-address');
    const bits = patch.hdlc_address_size === 4 || (!patch.hdlc_address_size && (patch.hdlc_logical_address > 127 || patch.hdlc_physical_address > 127)) ? 14 : 7;
    patch.server_address = patch.hdlc_logical_address * (2 ** bits) + patch.hdlc_physical_address;
  }
  patch.registers = registers.filter(r => r.selected).map(({selected, group, original_name, obis_description, ...register}) => register);
  if (!catalogUsable && patch.referencing==='sn' && patch.registers.some(register=>!register.short_name)) patch.registers=[];
  return patch;
}
async function save() {
  config = await api('config', formPatch()); profileChanged = false;
  $('[data-config="hdlc_address_size"]').value = config.hdlc_address_size;
  for (const hint of $$('[data-metadata-key]')) {delete hint.dataset.dirty;hint.textContent='';}
  updateMetadataHints();
  for (const f of fields.filter(f => f.hasAttribute('data-secret'))) {
    f.value = '';
    const key = f.dataset.config;
    const configured = key === 'mqtt.password' ? config.mqtt.password_configured : config.configured_secrets?.[key];
    f.placeholder = configured ? 'Zapisano · wpisz, aby zmienić' : 'Nie podano';
    const hint = document.querySelector(`[data-secret-status="${key}"]`);
    if (hint) hint.textContent = configured ? 'Wartość zapisana. Puste pole zachowuje dotychczasowe dane.' : 'Brak zapisanej wartości.';
  }
  catalogConfig=structuredClone(config);
  await refreshCatalog();
}
function changePage(index) {
  page = index;
  $$('[data-page]').forEach(p => p.hidden = Number(p.dataset.page) !== page);
  $$('[data-step]').forEach(b => { if (Number(b.dataset.step) === page) b.setAttribute('aria-current','step'); else b.removeAttribute('aria-current'); });
  $('#back').hidden = page === 0; $('#next').hidden = page === 3;
  $('#next').textContent = `Dalej: ${stepNames[page] || ''}`;
}
function dynamic() {
  const p = formPatch(), serial = p.transport === 'serial_hdlc';
  const usable=catalogue.ready && connectionMatchesSaved(p);
  if (usable!==catalogUsable) {catalogUsable=usable;renderRegisters();lockControls();}
  $('#mqtt-fields').hidden=!p.mqtt_enabled;
  $$('[data-network]').forEach(e => e.hidden = serial);
  $$('[data-serial]').forEach(e => e.hidden = !serial);
  $$('[data-wrapper]').forEach(e => e.hidden = p.transport !== 'tcp_wrapper');
  $$('[data-hdlc]').forEach(e => e.hidden = p.transport === 'tcp_wrapper');
  $('[data-config="client_address"]').closest('label').classList.toggle('wide', p.transport !== 'tcp_wrapper');
  $('#hdlc-combined-address').textContent = `Adres złożony: ${p.server_address}. Wyliczany automatycznie z adresu logicznego i fizycznego.`;
  const pass = !['none','hls_gmac'].includes(p.authentication);
  $$('[data-password]').forEach(e => e.hidden = !pass);
  $$('[data-encoding]').forEach(e => e.hidden = !pass || p.password_format !== 'text');
  const keys = p.authentication === 'hls_gmac' || p.security !== 'none';
  $('#security-fields').hidden = !keys && p.authentication !== 'hls_sha256';
  $$('[data-keys]').forEach(e => e.hidden = !keys);
  $('#counter-fields').hidden = !keys;
  const server = p.transport === 'tcp_wrapper' ? p.server_address : `logiczny ${p.hdlc_logical_address ?? '—'}, fizyczny ${p.hdlc_physical_address ?? '—'}`;
  const summary = [['Urządzenie',p.name],['Transport',transportNames[p.transport]],['Adres',serial?p.serial_device:`${p.host || 'Nie podano'}:${p.port}`],['Adres klienta',String(p.client_address)],['Serwer',String(server)],['Dostęp',authNames[p.authentication]],['Rejestry',String(p.registers.length)]];
  $('#summary').replaceChildren(...summary.flatMap(([name, value]) => {const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;return [dt,dd];}));
}
function renderRegisters() {
  const filter = $('#register-search').value.toLowerCase();
  $('#registers').replaceChildren();
  $('#register-empty').hidden=catalogUsable && catalogue.objects.length>0;
  $('#search-label').hidden=!catalogUsable || registers.length<8;
  $('#metadata-note').hidden=!catalogUsable;
  $('#obis-sources').hidden=!catalogUsable || !catalogue.description_sources?.length;
  $('#obis-source-list').replaceChildren(...(catalogue.description_sources || []).map(source=>{
    const item=document.createElement('li'),link=document.createElement('a');link.textContent=source.title;link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';item.append(link);return item;
  }));
  $('#catalog-state').textContent=catalogUsable?`Lista pobrana z licznika: ${new Date(catalogue.fetched_at).toLocaleString()}. Dostępne rejestry: ${registers.length}.`:'Lista wyboru pojawi się po pobraniu rejestrów dla zapisanych parametrów połączenia.';
  if (!catalogUsable) {$('#register-count').textContent=`Zapisany wybór: ${registers.filter(r=>r.selected).length}`;$('#register-empty').textContent='Pobierz listę rejestrów z licznika, aby wybrać pomiary.';return;}
  for (const [key,label] of Object.entries(registerGroups)) {
    const all=registers.filter(register=>register.group===key);
    const visible=all.filter(register=>`${register.obis} ${register.name}`.toLowerCase().includes(filter));
    if (filter && !visible.length) continue;
    const group=document.createElement('details'),summary=document.createElement('summary'),heading=document.createElement('span'),title=document.createElement('span'),counts=document.createElement('span'),body=document.createElement('div');
    group.className='register-group';group.dataset.group=key;heading.className='register-group-heading';counts.dataset.groupCount=key;counts.className='register-group-count';title.textContent=label;
    heading.append(title,counts);summary.append(heading);group.append(summary,body);
    const populate=()=>{
      if (body.childElementCount) return;
      if (!visible.length) {const note=document.createElement('p');note.className='note';note.textContent='Licznik nie udostępnia rejestrów w tej grupie.';body.append(note);return;}
      const scroll=document.createElement('div'),table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr'),rows=document.createElement('tbody');
      scroll.className='table-scroll';table.className='register-table';
      for (const text of ['Odczyt','OBIS','Nazwa i parametry HA']) {const th=document.createElement('th');th.scope='col';th.textContent=text;tr.append(th);}
      head.append(tr);rows.append(...visible.map(createRegisterRow));table.append(head,rows);scroll.append(table);body.append(scroll);updateMetadataHints();
    };
    group.addEventListener('toggle',()=>{if(group.open)populate();if(!filter){if(group.open)openGroups.add(key);else openGroups.delete(key);}});
    group.open=Boolean(filter)||openGroups.has(key);if(group.open)populate();$('#registers').append(group);
  }
  if (filter && !$('#registers').childElementCount) {$('#register-empty').hidden=false;$('#register-empty').textContent='Brak rejestrów pasujących do filtra.';}
  else $('#register-empty').textContent=registers.length?'Pobierz listę rejestrów z licznika, aby wybrać pomiary.':'Licznik nie udostępnił rejestrów klasy 3 i 4 dla wybranego dostępu. Sprawdź adres klienta i uprawnienia.';
  updateRegisterCounts();updateMetadataHints();
}
function updateRegisterCounts() {
  $('#register-count').textContent=`Wybrane: ${registers.filter(register=>register.selected).length}`;
  for (const counts of $$('[data-group-count]')) {
    const group=registers.filter(register=>register.group===counts.dataset.groupCount);
    counts.textContent=`Wybrane: ${group.filter(register=>register.selected).length} z ${group.length}`;
  }
}
function createRegisterRow(register) {
    const row=document.createElement('tr'),checkCell=document.createElement('td'),obisCell=document.createElement('td'),nameCell=document.createElement('td');
    const check=document.createElement('input');check.type='checkbox';check.checked=register.selected;check.disabled=busy||active||testBusy;check.setAttribute('aria-label',`Odczyt ${register.obis}`);check.addEventListener('change',()=>{register.selected=check.checked;dynamic();updateRegisterCounts();lockControls();});
    const name=document.createElement('input');name.value=register.name;name.disabled=busy||active||testBusy;name.setAttribute('aria-label',`Nazwa rejestru ${register.obis}`);name.addEventListener('input',()=>register.name=name.value);
    const details=document.createElement('details'),summary=document.createElement('summary'),metadataFields=document.createElement('div'),hint=document.createElement('small');
    details.className='register-metadata';metadataFields.className='register-metadata-fields';summary.textContent='Parametry HA';hint.dataset.metadataKey=register.key;
    const populateMetadata=()=>{
      if (metadataFields.childElementCount) return;
      const provenance=document.createElement('p');provenance.className='note';
      if (register.obis_description) {
        provenance.append(`Opis OBIS: ${register.obis_description.text}. `);
        const link=document.createElement('a');link.textContent=`Źródło, s. ${register.obis_description.page}`;link.href=register.obis_description.url;link.target='_blank';link.rel='noopener noreferrer';provenance.append(link);
        const original=document.createElement('small');original.textContent=`Opis źródłowy: ${register.original_name}`;provenance.append(original);
      } else provenance.textContent='Opis źródłowy. Brak potwierdzonego polskiego opisu w słowniku.';
      metadataFields.append(provenance);
      for (const [field,label,options] of [['device_class','Klasa urządzenia',metadataOptions.device_classes],['state_class','Klasa stanu',metadataOptions.state_classes],['unit','Jednostka',Object.fromEntries(metadataOptions.units.map(unit=>[unit,unit]))]]) {
      const wrapper=document.createElement('label'),select=document.createElement('select');wrapper.textContent=label;
      select.dataset.metadataField=field;select.setAttribute('aria-label',`${label} ${register.obis}`);
      select.append(new Option('Automatycznie',''),new Option(field==='state_class'?'Bez statystyk':field==='unit'?'Bez jednostki':'Bez klasy','__none__'),...Object.entries(options).map(([value,text])=>new Option(field==='unit'?text:`${text} · ${value}`,value)));
      select.value=Object.hasOwn(register,field)?register[field]===null?'__none__':register[field]:'';select.disabled=busy||active||testBusy;
      select.addEventListener('change',()=>{if(select.value==='')delete register[field];else register[field]=select.value==='__none__'?null:select.value;hint.dataset.dirty='true';hint.textContent='Zmieniono parametry HA. Zapisz ustawienia i wykonaj odczyt.';});
      wrapper.append(select);metadataFields.append(wrapper);
      }
    };
    details.addEventListener('toggle',()=>{if(details.open){openMetadata.add(register.key);populateMetadata();}else openMetadata.delete(register.key);});
    if(openMetadata.has(register.key)){details.open=true;populateMetadata();}
    details.append(summary,metadataFields,hint);checkCell.append(check);obisCell.textContent=register.obis;nameCell.append(name,details);row.append(checkCell,obisCell,nameCell);return row;
}
function updateMetadataHints() {
  for (const hint of $$('[data-metadata-key]')) {
    if (hint.dataset.dirty) continue;
    const sample=latestReadings.get(hint.dataset.metadataKey), automatic=sample?.auto_metadata;
    if (!hint.textContent || automatic) hint.textContent=automatic?`Automatycznie: ${automatic.device_class || 'bez klasy'} · ${automatic.state_class || 'bez statystyk'} · ${automatic.unit || 'bez jednostki'}`:'Parametry automatyczne pojawią się po odczycie. Dla nieznanych rejestrów trzeba sprawdzić klasy i jednostkę.';
  }
}
function lockControls() {
  const locked = !statusKnown || busy || active || testBusy;
  fields.forEach(f=>f.disabled=locked);
  for (const id of ['hdlc-logical-address','hdlc-physical-address']) $(`#${id}`).disabled=locked;
  for (const id of ['profile','profile-name','profile-save','profile-import','profile-file','save','test','objects']) $(`#${id}`).disabled=locked;
  $('#start').disabled=locked || !catalogUsable || !registers.some(register=>register.selected);
  $('#profile-export').disabled=busy || !profiles[$('#profile').value];
  $('#stop').hidden=!active; $('#stop').disabled=busy||phase==='stopping';
  $$('#registers input, #registers select').forEach(e=>e.disabled=locked || !catalogUsable);
  $('#edit').hidden=!active||phase==='stopping'; $('#edit').disabled=busy||testBusy;
  for (const id of ['discover','pairing']) $(`#${id}`).disabled=busy;
  const waiting=busy||testBusy||phase==='stopping';
  $('#configuration').setAttribute('aria-busy',String(waiting));
  let description;
  if (!statusKnown) description='Nie można ustalić stanu odczytu. Edycja będzie dostępna po odzyskaniu połączenia z dodatkiem.';
  else if (phase==='stopping') description='Trwa zatrzymywanie odczytu. Edycja będzie dostępna po zakończeniu bieżącej operacji.';
  else if (testBusy) description='Trwa test lub pobieranie rejestrów. Edycja będzie dostępna po zakończeniu tej operacji.';
  else if (busy) description='Trwa wykonywanie operacji. Ustawienia są chwilowo zablokowane.';
  else if (active) description='Odczyt jest uruchomiony. Zmiana ustawień i test połączenia wymagają zatrzymania odczytu.';
  else description='Odczyt jest zatrzymany. Ustawienia i lista rejestrów są dostępne do edycji.';
  $('#operation-description').textContent=description;
  for (const control of $$('button:disabled, input:disabled, select:disabled')) control.title=description;
  for (const control of $$('button:not(:disabled), input:not(:disabled), select:not(:disabled)')) control.removeAttribute('title');
}
async function action(task) {
  if (busy) return; busy=true; lockControls();message('');
  try { await task(); } catch (error) { message(error.name==='TimeoutError'?'Dodatek nie odpowiedział w wyznaczonym czasie. Sprawdź połączenie i spróbuj ponownie.':error.message,true); }
  finally { busy=false;lockControls(); }
}
function renderState(status) {
  latestReadings=new Map(status.measurements.map(reading=>[reading.key,reading]));updateMetadataHints();
  statusKnown=true;phase=status.phase;active=status.running;testBusy=status.test?.state==='running';lockControls();
  const phases={stopped:'Odczyt zatrzymany',connecting:'Łączenie…',online:'Odczyt działa',retrying:'Ponawianie połączenia',stopping:'Zatrzymywanie…'};
  $('#connection-status').textContent=phases[status.phase] || status.phase;
  $('#live-state').textContent=status.error || status.mqtt_error || (active?'Integracja pobiera pomiary z API dodatku.':'Można zmienić ustawienia lub przetestować połączenie.');
  const test=status.test;
  if (test?.state==='running') $('#test-result').textContent=test.operation==='objects'?'Trwa pobieranie listy rejestrów z licznika. Może to potrwać do dwóch minut.':'Trwa test sesji DLMS. Poczekaj na odpowiedź licznika…';
  else if (test?.state==='error') $('#test-result').textContent=`Test nieudany. ${test.error}`;
  else if (test?.state==='ok') {
    $('#test-result').textContent=`Sesja DLMS nawiązana · ${new Date(test.finished).toLocaleString()}\n`+(test.objects?`Liczba rejestrów klasy 3 i 4: ${test.objects.length}.`:test.measurements.map(m=>`${m.name}: ${m.error || `${formatMeasurement(m.value)} ${m.unit || ''}`}`).join('\n') || 'Połączenie działa. Wybierz rejestry, aby odczytać pomiary.');
    if (test.objects && $('#test-result').dataset.loaded!==test.finished) {
      $('#test-result').dataset.loaded=test.finished;
      refreshCatalog().catch(error=>message(`Nie udało się wczytać listy rejestrów: ${error.message}`,true));
    }
  }
  if (status.catalog && (status.catalog.ready!==catalogue.ready || status.catalog.fetched_at!==catalogue.fetched_at)) refreshCatalog().catch(()=>{});
  if (status.last_poll) $('#last-poll').textContent=`Ostatni odczyt: ${new Date(status.last_poll).toLocaleString()}${active?'':' · odczyt zatrzymany'}`;
  $('#measurements').replaceChildren(...status.measurements.map(m=>{const row=document.createElement('tr'),name=document.createElement('td'),value=document.createElement('td');name.textContent=m.name;value.textContent=`${formatMeasurement(m.value)} ${m.unit || ''}`;row.append(name,value);return row;}));
}
$$('[data-step]').forEach(b=>b.addEventListener('click',()=>changePage(Number(b.dataset.step))));
$('#back').addEventListener('click',()=>changePage(page-1));$('#next').addEventListener('click',()=>changePage(page+1));
$('#configuration').addEventListener('submit',e=>e.preventDefault());
fields.forEach(f=>f.addEventListener('input',dynamic));
for (const id of ['hdlc-logical-address','hdlc-physical-address']) $(`#${id}`).addEventListener('input',dynamic);
$('#profile').addEventListener('change',()=>loadProfile($('#profile').value));
$('#profile-save').addEventListener('click',()=>action(async()=>{
  const name=$('#profile-name').value.trim();
  if (!name) throw new Error('Podaj nazwę profilu.');
  await save();
  const result=await api('profiles/save',{name,...(config.profile!=='custom'?{id:config.profile}:{})});
  profiles=result.profiles;config.profile=result.id;renderProfiles();message('Zapisano profil użytkownika.');
}));
$('#profile-import').addEventListener('click',()=>$('#profile-file').click());
$('#profile-file').addEventListener('change',()=>action(async()=>{
  const file=$('#profile-file').files[0];$('#profile-file').value='';
  if (!file) return;
  if (file.size>262144) throw new Error('Plik profilu jest za duży (maksymalnie 256 KB).');
  let document;
  try { document=JSON.parse(await file.text()); } catch { throw new Error('Nieprawidłowy plik JSON profilu.'); }
  const result=await api('profiles/import',document);profiles=result.profiles;loadProfile(result.id);
}));
$('#profile-export').addEventListener('click',()=>{
  const document={version:1,...profiles[$('#profile').value]};
  const url=URL.createObjectURL(new Blob([JSON.stringify(document,null,2)],{type:'application/json'}));
  const link=window.document.createElement('a');link.href=url;link.download='dlms-profile.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('#save').addEventListener('click',()=>action(async()=>{await save();message('Ustawienia zapisane.');}));
for (const [id,path] of [['test','test'],['objects','objects']]) $(`#${id}`).addEventListener('click',()=>action(async()=>{await save();renderState(await api(path,{}));}));
$('#start').addEventListener('click',()=>action(async()=>{await save();renderState(await api('start',{}));message('Uruchomiono odczyt. Pomiary trafią do integracji przez API.');}));
$('#discover').addEventListener('click',()=>action(async()=>{await api('discover',{});message('Zgłoszono integrację. Dokończ konfigurację w Home Assistant → Ustawienia → Urządzenia i usługi.');}));
$('#pairing').addEventListener('click',()=>action(async()=>{
  const data=await api('pairing',{});
  $('#api-host').value=data.host;$('#api-port').value=data.port;$('#api-token').value=data.token;
  $('#api-token').type='password';$('#show-api-token').textContent='Pokaż token';$('#pairing-fields').hidden=false;
}));
$('#show-api-token').addEventListener('click',()=>{const show=$('#api-token').type==='password';$('#api-token').type=show?'text':'password';$('#show-api-token').textContent=show?'Ukryj token':'Pokaż token';});
$('#stop').addEventListener('click',()=>action(async()=>renderState(await api('stop',{}))));
$('#edit').addEventListener('click',()=>action(async()=>{
  renderState(await api('stop',{}));
  const deadline=Date.now()+150000;
  while (active) {
    if (Date.now()>deadline) throw new Error('Odczyt nie zatrzymał się w wyznaczonym czasie. Sprawdź stan dodatku.');
    await new Promise(resolve=>setTimeout(resolve,500));
    renderState(await api('status'));
  }
  message('Odczyt zatrzymany. Można zmienić ustawienia lub przetestować połączenie.');
}));
$('#register-search').addEventListener('input',renderRegisters);
async function refresh() {try{renderState(await api('status'));}catch(error){statusKnown=false;lockControls();$('#connection-status').textContent='Brak połączenia z dodatkiem';}}
(async()=>{try{[config,profiles,metadataOptions,catalogue]=await Promise.all([api('config'),api('profiles'),api('metadata-options'),api('catalog')]);catalogConfig=structuredClone(config);fill();changePage(0);await refresh();setInterval(refresh,2500);}catch(error){message(`Nie udało się wczytać ustawień: ${error.message}`,true);}})();
