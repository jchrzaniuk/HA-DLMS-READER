"""Sesje odczytu DLMS przez TCP WRAPPER, TCP HDLC lub port szeregowy HDLC."""

import contextlib
import hashlib
import json
import logging
import socket
import struct
import time
from pathlib import Path

from gurux_dlms import GXByteBuffer, GXReplyData, GXDLMSException
from gurux_dlms.enums import Authentication, InterfaceType, Security
from gurux_dlms.objects import GXDLMSObject
from gurux_dlms.objects.enums import SecuritySuite
from gurux_dlms.secure import GXDLMSSecureClient

from .configuration import atomic_json, hex_bytes, password_bytes, validate

AUTH = {"none": Authentication.NONE, "lls": Authentication.LOW,
        "hls": Authentication.HIGH, "hls_md5": Authentication.HIGH_MD5,
        "hls_sha1": Authentication.HIGH_SHA1, "hls_sha256": Authentication.HIGH_SHA256,
        "hls_gmac": Authentication.HIGH_GMAC}
SECURITY = {"none": Security.NONE, "authentication": Security.AUTHENTICATION,
            "encryption": Security.ENCRYPTION, "both": Security.AUTHENTICATION_ENCRYPTION}
log = logging.getLogger(__name__)


def build_client(config, public=False):
    client = GXDLMSSecureClient(
        useLogicalNameReferencing=config["referencing"] == "ln",
        clientAddress=config["fc_client_address"] if public else config["client_address"],
        serverAddress=config["server_address"],
        forAuthentication=Authentication.NONE if public else AUTH[config["authentication"]],
        password=None if public or config["authentication"] in ("none", "hls_gmac") else bytearray(password_bytes(config)),
        interfaceType=InterfaceType.WRAPPER if config["transport"] == "tcp_wrapper" else InterfaceType.HDLC,
    )
    if config["transport"] != "tcp_wrapper":
        client.serverAddressSize = config.get("hdlc_address_size", 0)
    if not public:
        cipher = client.ciphering
        cipher.security = SECURITY[config["security"]]
        cipher.securitySuite = SecuritySuite(config["security_suite"])
        for field, attribute in (("client_system_title", "systemTitle"),
                                 ("block_cipher_key", "blockCipherKey"),
                                 ("authentication_key", "authenticationKey")):
            if config[field]:
                setattr(cipher, attribute, bytearray(hex_bytes(config[field], field)))
        if config["server_system_title"]:
            client.settings.sourceSystemTitle = bytearray(hex_bytes(config["server_system_title"], "Identyfikator systemowy licznika"))
    return client


class Channel:
    def __init__(self, config):
        self.config = config
        self.pending = bytearray()
        if config["transport"] == "serial_hdlc":
            import serial
            self.stream = serial.Serial(config["serial_device"], baudrate=config["baudrate"],
                                        bytesize=config["bytesize"], parity=config["parity"],
                                        stopbits=config["stopbits"], timeout=config["timeout"],
                                        write_timeout=config["timeout"], exclusive=True)
            self.serial = True
        else:
            self.stream = socket.create_connection((config["host"], config["port"]), config["timeout"])
            self.serial = False

    def close(self):
        self.stream.close()

    def timeout(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Licznik nie odpowiedział w wyznaczonym czasie.")
        if self.serial:
            self.stream.timeout = remaining
            self.stream.write_timeout = remaining
        else:
            self.stream.settimeout(remaining)

    def send(self, request, deadline):
        self.timeout(deadline)
        if self.serial:
            if self.stream.write(request) != len(request):
                raise ConnectionError("Niepełny zapis do portu szeregowego.")
        else:
            self.stream.sendall(request)

    def exact(self, count, deadline):
        while len(self.pending) < count:
            self.timeout(deadline)
            part = self.stream.read(count - len(self.pending)) if self.serial else self.stream.recv(count - len(self.pending))
            if not part:
                if self.serial:
                    raise TimeoutError("Brak odpowiedzi portu szeregowego.")
                raise ConnectionError("Licznik zamknął połączenie.")
            self.pending.extend(part)
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def frame(self, deadline, client):
        if self.config["transport"] == "tcp_wrapper":
            header = self.exact(8, deadline)
            version, source, destination, size = struct.unpack("!HHHH", header)
            if version != 1 or source != client.serverAddress or destination != client.clientAddress or not size:
                raise ValueError("Nieprawidłowy nagłówek WRAPPER (wersja, adres lub długość).")
            return header + self.exact(size, deadline)
        # Nagłówek HDLC określa długość ramki; 0x7e wewnątrz danych nie kończy ramki.
        while self.exact(1, deadline) != b"\x7e":
            pass
        first = self.exact(1, deadline)
        while first == b"\x7e":
            first = self.exact(1, deadline)
        second = self.exact(1, deadline)
        length = ((first[0] & 7) << 8) | second[0]
        if first[0] & 0xF0 != 0xA0 or length < 7:
            raise ValueError("Nieprawidłowy format lub długość ramki HDLC.")
        rest = self.exact(length - 2, deadline)
        if self.exact(1, deadline) != b"\x7e":
            raise ValueError("Brak znacznika końca ramki HDLC.")
        return b"\x7e" + first + second + rest + b"\x7e"


class CounterStore:
    """Zapisuje zarezerwowaną wartość licznika przed wysłaniem zabezpieczonych wiadomości."""

    def __init__(self, directory, config):
        identity = json.dumps([config["device_id"], config["client_address"], config["client_system_title"]])
        digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
        self.path = Path(directory) / f"counter-{digest}.json"
        self.next = int(json.loads(self.path.read_text())["next"]) if self.path.exists() else 0

    def begin(self, minimum):
        start = max(minimum, self.next)
        self.reserve(start)
        return start

    def reserve(self, counter):
        if counter >= self.next:
            if counter > 0xFFFFFFFF - 64:
                raise ValueError("Wyczerpano zakres licznika ramek. Trzeba odnowić klucze.")
            self.next = counter + 64
            atomic_json(self.path, {"next": self.next})


class Meter:
    def __init__(self, channel, client, config, counters=None):
        self.channel, self.client, self.config = channel, client, config
        self.counters = counters

    def exchange(self, requests, operation_timeout=None):
        reply = GXReplyData()
        if isinstance(requests, (bytes, bytearray)):
            requests = [requests]
        deadline = time.monotonic() + (operation_timeout or self.config["timeout"])
        for request in requests:
            self.packet(request, reply, deadline)
            while reply.isMoreData():
                self.packet(self.client.receiverReady(reply), reply, deadline)
        return reply

    def packet(self, request, reply, deadline):
        if self.counters:
            self.counters.reserve(self.client.ciphering.invocationCounter)
        self.channel.send(request, deadline)
        while True:
            frame = self.channel.frame(deadline, self.client)
            if self.client.getData(GXByteBuffer(frame), reply):
                break
            if not reply.isMoreData():
                raise ValueError("Niekompletna odpowiedź DLMS.")
            self.channel.send(self.client.receiverReady(reply), deadline)
        if reply.error:
            raise GXDLMSException(reply.error)

    def associate(self):
        request = self.client.snrmRequest()
        if request:
            self.client.parseUAResponse(self.exchange(request).data)
        self.client.parseAareResponse(self.exchange(self.client.aarqRequest()).data)
        expected_title = self.config["server_system_title"]
        if expected_title:
            expected_title = bytearray(hex_bytes(expected_title, "Identyfikator systemowy licznika"))
            if self.client.settings.sourceSystemTitle and self.client.settings.sourceSystemTitle != expected_title:
                raise ValueError("Identyfikator systemowy w odpowiedzi licznika różni się od zapisanego w konfiguracji.")
            self.client.settings.sourceSystemTitle = expected_title
        if self.client.authentication > Authentication.LOW:
            response = self.exchange(self.client.getApplicationAssociationRequest())
            # Gurux wypisuje dane uwierzytelniania po błędzie; wycisz ten komunikat.
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                self.client.parseApplicationAssociationResponse(response.data)

    def read(self, register, attribute=2):
        obj = GXDLMSObject(register.get("class_id", 3), register["obis"], register.get("short_name", 0))
        return self.exchange(self.client.read(obj, attribute)).value

    def objects(self):
        result = self.client.parseObjects(self.exchange(self.client.getObjectsRequest(), operation_timeout=120).data, onlyKnownObjects=False)
        # Udostępniaj tylko liczbowe rejestry klasy 3 i 4, bez sekretów asocjacji.
        return [{"obis": item.logicalName, "class_id": int(item.objectType),
                 "short_name": item.shortName or None, "name": item.description or item.logicalName,
                 "key": "obis_" + item.logicalName.replace(".", "_")}
                for item in result if int(item.objectType) in (3, 4)]

    def close(self):
        try:
            request = self.client.releaseRequest()
            if request:
                self.exchange(request)
        except Exception:
            log.debug("Licznik nie potwierdził zamknięcia sesji DLMS.")
        if self.config["transport"] != "tcp_wrapper":
            try:
                request = self.client.disconnectRequest()
                if request:
                    self.exchange(request)
            except Exception:
                log.debug("Licznik nie potwierdził zamknięcia połączenia HDLC.")


@contextlib.contextmanager
def session(config, directory, public=False):
    validate(config, complete=True)
    counters, start = None, 0
    if not public and (config["authentication"] == "hls_gmac" or config["security"] != "none"):
        if config["counter_mode"] == "public":
            if config["referencing"] != "ln":
                raise ValueError("Publiczny odczyt licznika ramek wymaga LN; dla SN wybierz licznik trwały.")
            with session(config, directory, public=True) as meter:
                start = int(meter.read({"obis": config["frame_counter_obis"], "class_id": 1})) + 1
        counters = CounterStore(directory, config)
        start = counters.begin(start)
    client = build_client(config, public)
    if counters:
        client.ciphering.invocationCounter = start
    channel = Channel(config)
    meter = Meter(channel, client, config, counters)
    try:
        meter.associate()
        yield meter
    finally:
        meter.close()
        channel.close()
