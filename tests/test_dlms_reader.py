"""Testy regresji dodatku, bez połączenia z fizycznym licznikiem."""
import contextlib
import copy
import io
import json
import socket
import struct
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from gurux_dlms import GXByteBuffer, GXReplyData, GXDLMSException
from gurux_dlms.GXSecure import GXSecure
from gurux_dlms.enums import Authentication, InterfaceType, Security

from dlms_reader.app.configuration import DEFAULT, ConfigStore, merged, public_config, validate, password_bytes
from dlms_reader.app.meter import Channel, CounterStore, Meter, build_client
from dlms_reader.app.publishing import discovery, scaled, Publisher
from dlms_reader.app.runtime import Runtime
from dlms_reader.app.web import handler
from http.server import ThreadingHTTPServer


def valid_config(**changes):
    config = copy.deepcopy(DEFAULT)
    config.update(host='127.0.0.1', password='41' * 16, client_system_title='01' * 8,
                  server_system_title='02' * 8, block_cipher_key='03' * 16, authentication_key='04' * 16)
    config.update(changes)
    return config


class ConfigurationTests(unittest.TestCase):
    def test_split_hdlc_address_reaches_wire_and_survives_reload(self):
        for transport in ('tcp_hdlc', 'serial_hdlc'):
            with self.subTest(transport=transport), tempfile.TemporaryDirectory() as directory:
                store = ConfigStore(directory)
                response = store.save({'transport': transport, 'hdlc_logical_address': 1,
                                       'hdlc_physical_address': 40})
                self.assertEqual((response['server_address'], response['hdlc_logical_address'],
                                  response['hdlc_physical_address']), (168, 1, 40))
                reloaded = ConfigStore(directory)
                self.assertEqual(build_client(reloaded.value).snrmRequest()[3:5], b'\x02\x51')
                self.assertNotIn('hdlc_physical_address', reloaded.value)

    def test_legacy_hdlc_addresses_keep_original_frames(self):
        for address, logical, physical in ((1, 0, 1), (40, 0, 40), (168, 1, 40),
                                           (16424, 1, 40), (0xFFFFFFF, 16383, 16383)):
            with self.subTest(address=address):
                config = merged(DEFAULT, {'transport': 'tcp_hdlc', 'server_address': address})
                public = public_config(config)
                self.assertEqual((public['hdlc_logical_address'], public['hdlc_physical_address']),
                                 (logical, physical))
                updated = merged(config, {key: public[key] for key in ('hdlc_logical_address', 'hdlc_physical_address')})
                self.assertEqual(build_client(config).snrmRequest(), build_client(updated).snrmRequest())

    def test_hdlc_address_lengths_and_large_physical_address(self):
        for logical, physical, size, wire in ((0, 40, 1, b'\x51'),
                                             (1, 40, 2, b'\x02\x51'),
                                             (1, 40, 4, b'\x00\x02\x00\x51'),
                                             (1, 500, 0, b'\x00\x02\x06\xe9')):
            with self.subTest(logical=logical, physical=physical, size=size):
                config = merged(DEFAULT, {'transport': 'tcp_hdlc', 'hdlc_logical_address': logical,
                                         'hdlc_physical_address': physical, 'hdlc_address_size': size})
                self.assertEqual(build_client(config).snrmRequest()[3:3+len(wire)], wire)
                public = public_config(config)
                self.assertEqual((public['hdlc_logical_address'], public['hdlc_physical_address']), (logical, physical))

    def test_invalid_hdlc_parts_are_rejected_without_changing_saved_config(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            store.save({'transport': 'tcp_hdlc', 'server_address': 168})
            original = copy.deepcopy(store.value)
            for values in ({'hdlc_logical_address': None}, {'hdlc_physical_address': -1},
                           {'hdlc_logical_address': 1.5}, {'hdlc_physical_address': True},
                           {'hdlc_physical_address': 16384}, {'hdlc_address_size': 3},
                           {'hdlc_address_size': 1},
                           {'hdlc_logical_address': 0, 'hdlc_physical_address': 40, 'hdlc_address_size': 2},
                           {'hdlc_logical_address': 0, 'hdlc_physical_address': 500},
                           {'hdlc_logical_address': 1, 'hdlc_physical_address': 128, 'hdlc_address_size': 2},
                           {'hdlc_logical_address': 0, 'hdlc_physical_address': 0}):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    store.save(values)
                self.assertEqual(ConfigStore(directory).value, original)

    def test_split_addresses_in_profiles_and_legacy_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            key = store.save_profile('HDLC', {'transport': 'tcp_hdlc', 'hdlc_logical_address': 1,
                                              'hdlc_physical_address': 40, 'hdlc_address_size': 4})
            settings = ConfigStore(directory).profiles[key]['settings']
            self.assertEqual(settings['server_address'], 16424)
            self.assertEqual(build_client(merged(DEFAULT, settings)).snrmRequest()[3:7], b'\x00\x02\x00\x51')
            wrapper = merged(DEFAULT, {'server_address': 1234, 'hdlc_address_size': 4})
            self.assertEqual(build_client(wrapper).serverAddress, 1234)
            with self.assertRaises(ValueError):
                merged(wrapper, {'hdlc_logical_address': 1, 'hdlc_physical_address': 40})

    def test_hex_password_is_bytes_not_hex_text(self):
        self.assertEqual(password_bytes(valid_config(password='00 FF 41')), b'\x00\xffA')

    def test_text_password_is_not_hex_decoded(self):
        self.assertEqual(password_bytes(valid_config(password='4142', password_format='text')), b'4142')

    def test_non_ascii_text_encoding(self):
        self.assertEqual(password_bytes(valid_config(password='żółć', password_format='text')), 'żółć'.encode())

    def test_bad_hex_rejected_without_echo(self):
        with self.assertRaises(ValueError) as result:
            password_bytes(valid_config(password='SECRETxyz'))
        self.assertNotIn('SECRETxyz', str(result.exception))

    def test_all_supported_modes_validate_and_create_request(self):
        for transport in ('tcp_wrapper','tcp_hdlc','serial_hdlc'):
            for auth in ('none','lls','hls','hls_md5','hls_sha1','hls_sha256','hls_gmac'):
                for security in ('none','authentication','encryption','both'):
                    with self.subTest(transport=transport,auth=auth,security=security):
                        config=valid_config(transport=transport,authentication=auth,security=security,serial_device='/dev/ttyUSB0')
                        validate(config,True)
                        client=build_client(config)
                        self.assertTrue(client.aarqRequest())
                        self.assertEqual(client.ciphering.security, {'none':0,'authentication':16,'encryption':32,'both':48}[security])

    def test_no_secret_in_api_response(self):
        config=valid_config();config['mqtt']['password']='brokerSECRET'
        value=public_config(config)
        for field in ('password','block_cipher_key','authentication_key'):
            self.assertNotIn(field,value)
            self.assertTrue(value['configured_secrets'][field])
        self.assertNotIn('brokerSECRET',json.dumps(value))

    def test_save_preserves_omitted_secrets_and_uses_0600(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ConfigStore(directory)
            store.save({'password':'CAFE','mqtt':{'password':'broker'}})
            store.save({'name':'New name'})
            loaded=ConfigStore(directory)
            self.assertEqual(loaded.value['password'],'CAFE')
            self.assertEqual(loaded.value['mqtt']['password'],'broker')
            self.assertEqual(store.path.stat().st_mode & 0o777,0o600)

    def test_bad_fields_and_ranges_rejected(self):
        for patch_value in ({'unknown':1},{'port':0},{'timeout':float('nan')},{'poll_interval':0},
                            {'device_id':'BAD/#'},{'mqtt':{'tls':'false'}},{'mqtt':{'port':65536}},
                            {'transport':'tcp_wrapper','server_address':65536}):
            with self.subTest(patch=patch_value),self.assertRaises(ValueError):
                merged(DEFAULT,patch_value)

    def test_partial_setup_can_save_but_cannot_connect(self):
        validate(copy.deepcopy(DEFAULT))
        with self.assertRaises(ValueError):validate(copy.deepcopy(DEFAULT),True)

    def test_suite2_requires_32_byte_keys(self):
        with self.assertRaises(ValueError):validate(valid_config(authentication='hls_gmac',security_suite=2),True)
        validate(valid_config(authentication='hls_gmac',security_suite=2,block_cipher_key='01'*32,authentication_key='02'*32),True)

    def test_suite2_can_generate_ciphered_requests(self):
        config=valid_config(authentication='hls_gmac',security='both',security_suite=2,block_cipher_key='01'*32,authentication_key='02'*32)
        client=build_client(config)
        self.assertTrue(client.aarqRequest())

    def test_hls_server_proof_is_verified_and_tampering_rejected(self):
        for auth in ('hls','hls_md5','hls_sha1','hls_sha256','hls_gmac'):
            with self.subTest(authentication=auth):
                client=build_client(valid_config(authentication=auth))
                client.settings.ctoSChallenge=bytearray(b'C'*16)
                client.settings.stoCChallenge=bytearray(b'S'*16)
                secret=client.password
                if auth=='hls_gmac':secret=client.settings.sourceSystemTitle
                elif auth=='hls_sha256':secret=client.password+client.settings.sourceSystemTitle+client.ciphering.systemTitle+client.settings.ctoSChallenge+client.settings.stoCChallenge
                proof=bytearray(GXSecure.secure(client.settings,client.ciphering,17,client.settings.ctoSChallenge,secret))
                client.parseApplicationAssociationResponse(GXByteBuffer(bytearray([9,len(proof)])+proof))
                proof[-1]^=1
                with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(Exception):
                    client.parseApplicationAssociationResponse(GXByteBuffer(bytearray([9,len(proof)])+proof))

    def test_hls_requires_password_but_gmac_uses_keys(self):
        for auth in ('lls','hls','hls_sha256'):
            with self.assertRaises(ValueError):validate(valid_config(authentication=auth,password=''),True)
        validate(valid_config(authentication='hls_gmac',password=''),True)

    def test_short_name_needs_register_base_address(self):
        config=valid_config(referencing='sn',registers=[{'key':'e','obis':'1.0.1.8.0.255','name':'Energy','class_id':3}])
        with self.assertRaises(ValueError):validate(config,True)
        config['registers'][0]['short_name']=0x1000
        validate(config,True)

    def test_fresh_install_has_no_device_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            self.assertEqual(store.profiles, {})
            self.assertEqual(store.value['profile'], 'custom')

    def test_legacy_profile_becomes_user_data_without_changing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            original = valid_config(profile='old_template', manufacturer='Example', model='Model X',
                                    registers=[{'key':'energy','obis':'1.0.1.8.0.255','class_id':3,'name':'Energy'}])
            Path(directory, 'configuration.json').write_text(json.dumps(original))
            store = ConfigStore(directory)
            self.assertEqual(store.value, original)
            self.assertEqual(store.profiles['old_template']['name'], 'Example Model X')
            self.assertEqual(store.profiles['old_template']['settings']['registers'], original['registers'])
            self.assertEqual(store.profiles_path.stat().st_mode & 0o777, 0o600)
            store.save_profile('Custom name', profile_id='old_template')
            self.assertEqual(ConfigStore(directory).profiles['old_template']['name'], 'Custom name')

    def test_user_profiles_exclude_secrets_and_installation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            store.save(valid_config(host='private-host', device_id='local_meter', mqtt={'password':'private-broker'}))
            key = store.save_profile('Any manufacturer and model')
            settings = ConfigStore(directory).profiles[key]['settings']
            for field in ('password','authentication_key','block_cipher_key','host','serial_device',
                          'device_id','name','mqtt','mqtt_enabled','mqtt_discovery','autostart',
                          'client_system_title','server_system_title','profile'):
                self.assertNotIn(field, settings)
            self.assertEqual(settings['transport'], 'tcp_wrapper')
            self.assertEqual(settings['password_format'], 'hex')

    def test_profile_import_rejects_credentials_invalid_settings_and_names(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ConfigStore(directory)
            for name, settings in (('',{}), ('x'*101,{}), ('Profile',{'password':'SECRET'}),
                                   ('Profile',{'port':0}), ('Profile',{'host':'local'})):
                with self.subTest(name=name, fields=list(settings)), self.assertRaises(ValueError):
                    store.save_profile(name, settings)
            self.assertEqual(store.profiles, {})


class FrameTests(unittest.TestCase):
    def channel(self,data,transport='tcp_wrapper'):
        channel=Channel.__new__(Channel);channel.config=valid_config(transport=transport);channel.serial=False;channel.pending=bytearray()
        chunks=iter(bytes([v]) for v in data)
        channel.stream=Mock();channel.stream.recv.side_effect=lambda count:next(chunks,b'')
        return channel

    def test_fragmented_wrapper(self):
        data=struct.pack('!HHHH',1,1,16,3)+b'abc'
        self.assertEqual(self.channel(data).frame(time.monotonic()+1,build_client(valid_config())),data)

    def test_wrapper_address_mismatch(self):
        with self.assertRaises(ValueError):self.channel(struct.pack('!HHHH',1,2,16,3)).frame(time.monotonic()+1,build_client(valid_config()))

    def test_hdlc_length_handles_embedded_flag(self):
        data=b'\x7e\xa0\x08\x01\x02\x7e\x03\x04\x05\x7e'
        self.assertEqual(self.channel(data,'tcp_hdlc').frame(time.monotonic()+1,None),data)

    def test_hdlc_multiple_opening_flags(self):
        data=b'\x7e\xa0\x07\x01\x02\x03\x04\x05\x7e'
        self.assertEqual(self.channel(b'\x7e\x7e'+data,'tcp_hdlc').frame(time.monotonic()+1,None),data)

    def test_hdlc_bad_closing_flag_rejected(self):
        with self.assertRaises(ValueError):self.channel(b'\x7e\xa0\x07abcdeX','tcp_hdlc').frame(time.monotonic()+1,None)

    def test_incomplete_frame_does_not_loop(self):
        with self.assertRaises(ConnectionError):self.channel(b'\x00').exact(8,time.monotonic()+1)

    def test_snrm_before_aarq_and_hls_verification(self):
        client=Mock();client.authentication=Authentication.HIGH_GMAC;client.snrmRequest.return_value=b'snrm'
        client.settings.sourceSystemTitle=bytearray.fromhex('02'*8)
        meter=Meter(Mock(),client,valid_config());reply=GXReplyData();meter.exchange=Mock(return_value=reply)
        meter.associate()
        client.parseUAResponse.assert_called_once()
        client.parseAareResponse.assert_called_once()
        client.getApplicationAssociationRequest.assert_called_once()
        client.parseApplicationAssociationResponse.assert_called_once()

    def test_read_short_name_uses_base_address(self):
        meter=Meter(Mock(),build_client(valid_config(referencing='sn')),valid_config());meter.exchange=Mock(return_value=GXReplyData())
        meter.read({'obis':'1.0.1.8.0.255','class_id':3,'short_name':0x1000},3)
        # Adres żądania READ: baza 0x1000 + (atrybut 3 − 1) * 8 = 0x1010.
        self.assertIn(b'\x10\x10',b''.join(meter.exchange.call_args.args[0]))


class PersistenceAndPublishingTests(unittest.TestCase):
    def test_counter_survives_restart_and_never_reuses_reserved_range(self):
        with tempfile.TemporaryDirectory() as directory:
            first=CounterStore(directory,valid_config());start=first.begin(100)
            self.assertEqual(start,100)
            second=CounterStore(directory,valid_config());self.assertGreaterEqual(second.begin(0),164)
            self.assertGreaterEqual(CounterStore(directory,valid_config()).begin(999),999)

    def test_counter_refuses_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):CounterStore(directory,valid_config()).begin(0xffffffff)

    def test_units_match_confirmed_remiz_energy(self):
        value,meta=scaled(480458,[-2,30]);self.assertAlmostEqual(value,4.80458);self.assertEqual(meta[0],'kWh')
        self.assertEqual(scaled(50000,[-3,44])[0],50)

    def test_invalid_measurements_rejected(self):
        for value in (float('nan'),float('inf'),b'abc',True):
            with self.assertRaises(ValueError):scaled(value,[0,30])

    def test_discovery_keeps_remiz_identifiers_and_availability(self):
        config=valid_config(device_id='remiz3')
        register={'key':'energia_czynna_pobrana','name':'Energy','obis':'1.0.1.8.0.255'}
        topic,payload=discovery(config,register,('kWh','energy','total_increasing',.001))
        self.assertEqual(topic,'homeassistant/sensor/remiz3/energia_czynna_pobrana/config')
        self.assertEqual(payload['unique_id'],'remiz3_energia_czynna_pobrana')
        self.assertEqual(payload['availability_mode'],'all');self.assertEqual(payload['expire_after'],105)

    def test_mqtt_requires_real_confirmation(self):
        with patch('dlms_reader.app.publishing.mqtt.Client') as factory:
            publisher=Publisher(valid_config(),valid_config()['mqtt']);publisher.connected.set()
            info=factory.return_value.publish.return_value;info.rc=0;info.is_published.return_value=False
            with self.assertRaises(ConnectionError):publisher.publish('test','1')
            info.is_published.return_value=True;publisher.publish('test','1')
            self.assertEqual(factory.return_value.publish.call_args.kwargs['qos'],1)


class APITests(unittest.TestCase):
    def test_hdlc_fields_save_and_empty_field_returns_validation_error(self):
        value = self.request('/api/config', {'transport': 'tcp_hdlc',
                                            'hdlc_logical_address': 1, 'hdlc_physical_address': 40})
        self.assertEqual((value['server_address'], value['hdlc_logical_address'],
                          value['hdlc_physical_address']), (168, 1, 40))
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('/api/config', {'server_address': None, 'hdlc_logical_address': None,
                                         'hdlc_physical_address': 40})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(self.request('/api/config')['server_address'], 168)

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.store=ConfigStore(self.directory.name);self.runtime=Runtime(self.store)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler(self.runtime))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.directory.cleanup()

    def request(self,path,body=None,headers=None):
        request=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                                      headers=headers or {'Content-Type':'application/json','X-DLMS-Request':'1'})
        with urllib.request.urlopen(request,timeout=2) as response:return json.load(response)

    def test_save_api_never_returns_secrets(self):
        value=self.request('/api/config',{'password':'0123456789AB','mqtt':{'password':'BROKER_SECRET'}})
        self.assertNotIn('BROKER_SECRET',json.dumps(value));self.assertNotIn('0123456789AB',json.dumps(value))
        self.assertTrue(self.request('/api/config')['configured_secrets']['password'])

    def test_cross_origin_form_write_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/config',{},headers={'Content-Type':'application/json'})
        self.assertEqual(error.exception.code,403)

    def test_save_while_reading_rejected(self):
        self.runtime.thread=Mock();self.runtime.thread.is_alive.return_value=True
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/config',{'name':'Change'})
        self.assertEqual(error.exception.code,409)

    def test_invalid_authentication_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/config',{'authentication':'unknown'})
        self.assertEqual(error.exception.code,400)

    def test_static_files_and_profiles(self):
        for path in ('/','/style.css','/app.js'):
            with urllib.request.urlopen(self.base+path) as response:self.assertEqual(response.status,200)
        self.assertEqual(self.request('/api/profiles'), {})
        with urllib.request.urlopen(self.base+'/') as response:
            self.assertNotIn('Apator', response.read().decode())

    def test_save_and_import_user_profile_round_trip(self):
        self.request('/api/config', {'manufacturer':'Example','password':'SECRET'})
        saved = self.request('/api/profiles/save', {'name':'My meter'})
        key = saved['id']
        self.assertEqual(self.request('/api/config')['profile'], key)
        document = {'version':1, **saved['profiles'][key]}
        self.assertNotIn('SECRET', json.dumps(document))
        imported = self.request('/api/profiles/import', document)
        self.assertNotEqual(imported['id'], key)
        self.assertEqual(imported['profiles'][imported['id']], saved['profiles'][key])
        self.request('/api/profiles/save', {'name':'Renamed', 'id':key})
        self.assertEqual(self.request('/api/profiles')[key]['name'], 'Renamed')

    def test_invalid_import_does_not_change_configuration(self):
        before = copy.deepcopy(self.store.value)
        for document in ({'version':2,'name':'Profile','settings':{}},
                         {'version':1,'name':'Profile','settings':{'password':'SECRET'}}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/profiles/import', document)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.store.value, before)
        self.assertEqual(self.store.profiles, {})

    def test_profile_mutation_while_reading_rejected(self):
        self.runtime.thread=Mock();self.runtime.thread.is_alive.return_value=True
        for route, body in (('/api/profiles/save', {'name':'Profile'}),
                            ('/api/profiles/import', {'version':1,'name':'Profile','settings':{}})):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(route, body)
            self.assertEqual(error.exception.code,409)


class PollRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.runtime=Runtime(ConfigStore(self.directory.name))
        self.config=valid_config(mqtt_discovery=True, registers=[
            {'key':'energy','obis':'1.0.1.8.0.255','name':'Energy','class_id':3},
            {'key':'power','obis':'1.0.1.7.0.255','name':'Power','class_id':3}])
        self.publisher=Mock();self.publisher.generation=1
        self.meter=Mock()
        self.meter.read.side_effect=lambda register,attribute=2: [0,30] if attribute==3 else 123

    def tearDown(self):self.directory.cleanup()

    @contextlib.contextmanager
    def session(self,*args):yield self.meter

    def test_denied_register_goes_offline_while_other_measurement_continues(self):
        def read(register,attribute=2):
            if register['key']=='energy':raise GXDLMSException(3)
            return [0,27] if attribute==3 else 321
        self.meter.read.side_effect=read
        with patch('dlms_reader.app.runtime.session',self.session):
            result=self.runtime.poll(self.publisher,self.config,{}, {})
        self.assertEqual(len(result),1)
        self.publisher.publish.assert_any_call('dlms_meter/energy/status','offline',True)
        self.publisher.publish.assert_any_call('dlms_meter/power','321')

    def test_failed_discovery_is_not_recorded_as_announced(self):
        announced={};self.publisher.publish.side_effect=ConnectionError('broker failure')
        with patch('dlms_reader.app.runtime.session',self.session),self.assertRaises(ConnectionError):
            self.runtime.poll(self.publisher,self.config,announced,{})
        self.assertEqual(announced,{})

    def test_reconnect_between_publications_does_not_hide_discovery_retry(self):
        announced={}
        def publish(topic,*args):
            if topic.endswith('/energy') and args[0]=='':self.publisher.generation=2
        self.publisher.publish.side_effect=publish
        with patch('dlms_reader.app.runtime.session',self.session):
            self.runtime.poll(self.publisher,self.config,announced,{})
        self.assertEqual(announced['energy'],1)
        self.assertEqual(self.publisher.generation,2)


if __name__=='__main__':unittest.main()
