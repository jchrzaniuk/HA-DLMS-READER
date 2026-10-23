"""Walidacja i zapis konfiguracji. Odpowiedzi API nie zawierają haseł ani kluczy."""

import copy
import json
import math
import os
import re
import tempfile
import uuid
from pathlib import Path
from .metadata import validate_overrides

SECRET_FIELDS = {"password", "block_cipher_key", "authentication_key"}
DEFAULT = {
    "profile": "custom", "device_id": "dlms_meter", "name": "Licznik DLMS",
    "manufacturer": "", "model": "", "transport": "tcp_wrapper", "host": "",
    "port": 4059, "serial_device": "/dev/serial/by-id/", "baudrate": 9600,
    "parity": "N", "bytesize": 8, "stopbits": 1, "timeout": 15,
    "client_address": 16, "server_address": 1, "hdlc_address_size": 0, "referencing": "ln",
    "authentication": "none", "password_format": "hex", "password": "",
    "text_encoding": "utf-8", "security": "none", "security_suite": 0,
    "client_system_title": "", "server_system_title": "",
    "block_cipher_key": "", "authentication_key": "",
    "counter_mode": "public", "frame_counter_obis": "0.0.43.1.0.255",
    "fc_client_address": 16, "poll_interval": 30, "autostart": False,
    "mqtt_enabled": False,
    "mqtt_discovery": False,
    "mqtt": {"host": "", "port": 1883, "username": "", "password": "",
             "tls": False, "discovery_prefix": "homeassistant"},
    "registers": [],
}
CHOICES = {
    "transport": ("tcp_wrapper", "tcp_hdlc", "serial_hdlc"),
    "referencing": ("ln", "sn"),
    "authentication": ("none", "lls", "hls", "hls_md5", "hls_sha1", "hls_sha256", "hls_gmac"),
    "password_format": ("hex", "text"), "text_encoding": ("utf-8", "ascii", "latin-1"),
    "security": ("none", "authentication", "encryption", "both"),
    "security_suite": (0, 2), "counter_mode": ("public", "persistent"),
    "parity": ("N", "E", "O"), "bytesize": (7, 8), "stopbits": (1, 2),
    "hdlc_address_size": (0, 1, 2, 4),
}
HDLC_ADDRESS_FIELDS = {"hdlc_logical_address", "hdlc_physical_address"}
INTEGER_RANGES = {"port": (1, 65535), "client_address": (1, 65535),
                  "server_address": (1, 0xFFFFFFF), "fc_client_address": (1, 65535),
                  "baudrate": (300, 921600)}

# Profile nie zawierają danych dostępowych ani ustawień konkretnej instalacji.
PROFILE_FIELDS = set(DEFAULT) - SECRET_FIELDS - {
    "profile", "device_id", "name", "host", "serial_device", "mqtt",
    "mqtt_enabled", "mqtt_discovery", "autostart", "client_system_title",
    "server_system_title",
}


def profile_document(name, settings):
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("Nazwa profilu: podaj od 1 do 100 znaków.")
    if not isinstance(settings, dict) or set(settings) - PROFILE_FIELDS - HDLC_ADDRESS_FIELDS:
        raise ValueError("Profil zawiera nieobsługiwane pola. Nie może zawierać haseł ani danych konkretnej instalacji.")
    config = merged(DEFAULT, settings)
    return {"name": name.strip(), "settings": {key: copy.deepcopy(config[key]) for key in sorted(PROFILE_FIELDS)}}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".dlms-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def hex_bytes(value, label):
    try:
        return bytes.fromhex(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{label}: podaj pełne bajty HEX (np. 01 AF).") from error


def password_bytes(config):
    if config["password_format"] == "hex":
        return hex_bytes(config["password"], "Hasło")
    try:
        return config["password"].encode(config["text_encoding"])
    except UnicodeError as error:
        raise ValueError("Hasło zawiera znaki spoza wybranego kodowania.") from error


def obis_valid(value):
    return isinstance(value, str) and bool(re.fullmatch(r"\d+(?:\.\d+){5}", value)) and all(
        int(part) < 256 for part in value.split("."))


def hdlc_address_parts(config):
    """Rozdziela zapisany adres bez zmiany formatu dotychczasowego połączenia."""
    address = config["server_address"]
    size = config.get("hdlc_address_size", 0) or (1 if address < 128 else 2 if address < 16384 else 4)
    if size == 1:
        return 0, address
    bits = 7 if size == 2 else 14
    return address >> bits, address & ((1 << bits) - 1)


def hdlc_server_address(logical, physical, size=0):
    for value, label in ((logical, "Adres logiczny HDLC"), (physical, "Adres fizyczny HDLC")):
        if type(value) is not int or not 0 <= value <= 16383:
            raise ValueError(f"{label}: podaj liczbę całkowitą od 0 do 16383.")
    if type(size) is not int or size not in (0, 1, 2, 4):
        raise ValueError("Długość adresu HDLC: wybierz automatyczną, 1, 2 lub 4 bajty.")
    effective_size = size or (1 if logical == 0 and physical < 128 else
                              2 if logical < 128 and physical < 128 else 4)
    if logical == 0 and (physical > 127 or effective_size in (2, 4)):
        raise ValueError("Adres HDLC bez części logicznej obsługuje format jednobajtowy i adres fizyczny od 1 do 127.")
    if effective_size == 1 and (logical != 0 or physical > 127):
        raise ValueError("Adres jednobajtowy HDLC wymaga adresu logicznego 0 i fizycznego od 1 do 127.")
    if effective_size == 2 and (logical > 127 or physical > 127):
        raise ValueError("Adres dwubajtowy HDLC: obie części muszą mieścić się w zakresie 0–127.")
    address = (logical << (14 if effective_size == 4 else 7)) | physical
    if address == 0:
        raise ValueError("Adres HDLC: co najmniej jedna część musi być większa od zera.")
    return address


def validate(config, complete=False):
    if not re.fullmatch(r"[a-z0-9_]{1,80}", config["profile"]):
        raise ValueError("Nieprawidłowy identyfikator profilu.")
    for key, choices in CHOICES.items():
        if config[key] not in choices:
            raise ValueError(f"Nieobsługiwana wartość pola {key}.")
    for key, (minimum, maximum) in INTEGER_RANGES.items():
        if type(config[key]) is not int or not minimum <= config[key] <= maximum:
            raise ValueError(f"{key}: dozwolony zakres {minimum}–{maximum}.")
    if config["transport"] == "tcp_wrapper" and config["server_address"] > 65535:
        raise ValueError("WRAPPER: adres serwera musi mieścić się w 16 bitach.")
    if config["transport"] != "tcp_wrapper" and config["client_address"] > 127:
        raise ValueError("HDLC: adres klienta musi mieścić się w 7 bitach.")
    if type(config["hdlc_address_size"]) is not int:
        raise ValueError("Długość adresu HDLC musi być liczbą całkowitą.")
    if config["transport"] != "tcp_wrapper" and config["hdlc_address_size"]:
        logical, physical = hdlc_address_parts(config)
        if hdlc_server_address(logical, physical, config["hdlc_address_size"]) != config["server_address"]:
            raise ValueError("Adres serwera nie mieści się w wybranej długości adresu HDLC.")
    for key, low, high in (("timeout", 1, 120), ("poll_interval", 5, 86400)):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]) or not low <= config[key] <= high:
            raise ValueError(f"{key}: dozwolony zakres {low}–{high} sekund.")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", config["device_id"]):
        raise ValueError("Identyfikator musi zaczynać się małą literą. Może zawierać małe litery, cyfry i podkreślenia; do 48 znaków.")
    if not config["name"].strip():
        raise ValueError("Podaj nazwę licznika.")
    if any(type(config[key]) is not bool for key in ("mqtt_enabled", "mqtt_discovery", "autostart")) or type(config["mqtt"]["tls"]) is not bool:
        raise ValueError("Ustawienia włączenia funkcji muszą mieć wartość true albo false.")
    mqtt = config["mqtt"]
    if type(mqtt["port"]) is not int or not 1 <= mqtt["port"] <= 65535:
        raise ValueError("Port MQTT: dozwolony zakres 1–65535.")
    if not re.fullmatch(r"[A-Za-z0-9_/-]+", mqtt["discovery_prefix"]):
        raise ValueError("Nieprawidłowy prefiks MQTT Discovery.")
    if not obis_valid(config["frame_counter_obis"]):
        raise ValueError("Licznik ramek: OBIS musi zawierać 6 liczb 0–255.")
    registers, keys = config["registers"], set()
    if not isinstance(registers, list) or len(registers) > 256:
        raise ValueError("Wybierz najwyżej 256 rejestrów.")
    for register in registers:
        if not isinstance(register, dict) or set(register) - {"key", "obis", "class_id", "name", "short_name", "device_class", "unit", "state_class"}:
            raise ValueError("Nieprawidłowe pola rejestru.")
        if not re.fullmatch(r"[a-z0-9_]{1,80}", register.get("key", "")) or register["key"] in keys:
            raise ValueError("Rejestry muszą mieć różne klucze: małe litery, cyfry i _.")
        keys.add(register["key"])
        if not obis_valid(register.get("obis")) or register.get("class_id") not in (3, 4):
            raise ValueError("Wybierz rejestr klasy 3 lub 4 z poprawnym OBIS.")
        if not isinstance(register.get("name"), str) or not register["name"].strip():
            raise ValueError("Każdy rejestr musi mieć nazwę.")
        validate_overrides(register)
        sn = register.get("short_name")
        if sn is not None and (type(sn) is not int or not 1 <= sn <= 65519):
            raise ValueError("Short Name: podaj adres bazowy 1–65519.")
        if config["referencing"] == "sn" and sn is None:
            raise ValueError("Adresowanie SN wymaga adresu bazowego każdego rejestru.")
    if not complete:
        return config
    if config["transport"] == "serial_hdlc":
        if not config["serial_device"].startswith("/dev/") or config["serial_device"].endswith("/"):
            raise ValueError("Podaj pełną ścieżkę portu szeregowego /dev/… dla bezpośredniego HDLC.")
    elif not config["host"].strip() or any(c in config["host"] for c in "/ \r\n"):
        raise ValueError("Podaj adres IP lub nazwę sieciową licznika, bez protokołu i portu.")
    auth = config["authentication"]
    if auth not in ("none", "hls_gmac") and not password_bytes(config):
        raise ValueError("Podaj hasło dla wybranego uwierzytelniania.")
    if auth == "hls" and len(password_bytes(config)) != 16:
        raise ValueError("HLS z AES wymaga 16 bajtów hasła.")
    protected = auth == "hls_gmac" or config["security"] != "none"
    if protected or auth == "hls_sha256":
        if len(hex_bytes(config["client_system_title"], "Identyfikator systemowy klienta")) != 8:
            raise ValueError("Identyfikator systemowy klienta: podaj 8 bajtów HEX. Identyfikator musi być unikalny w instalacji.")
    if auth == "hls_sha256" and len(hex_bytes(config["server_system_title"], "Identyfikator systemowy licznika")) != 8:
        raise ValueError("HLS-SHA256 wymaga identyfikatora systemowego licznika: 8 bajtów HEX.")
    if config["server_system_title"] and len(hex_bytes(config["server_system_title"], "Identyfikator systemowy licznika")) != 8:
        raise ValueError("Identyfikator systemowy licznika: wymagane 8 bajtów HEX.")
    if protected:
        length = 32 if config["security_suite"] == 2 else 16
        for key in ("block_cipher_key", "authentication_key"):
            if len(hex_bytes(config[key], key)) != length:
                raise ValueError(f"{key}: zestaw {config['security_suite']} wymaga {length} bajtów HEX.")
    return config


def merged(base, patch):
    if not isinstance(patch, dict) or set(patch) - set(DEFAULT) - HDLC_ADDRESS_FIELDS:
        raise ValueError("Nieznane pola konfiguracji.")
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if key in HDLC_ADDRESS_FIELDS:
            continue
        if key == "mqtt":
            if not isinstance(value, dict) or set(value) - set(DEFAULT["mqtt"]):
                raise ValueError("Nieznane pola MQTT.")
            result["mqtt"].update(value)
        else:
            result[key] = value
    if HDLC_ADDRESS_FIELDS & set(patch):
        if result["transport"] == "tcp_wrapper":
            raise ValueError("Adres logiczny i fizyczny dotyczą transportu HDLC. Dla WRAPPER podaj adres serwera.")
        if HDLC_ADDRESS_FIELDS <= set(patch):
            logical, physical = patch["hdlc_logical_address"], patch["hdlc_physical_address"]
        else:
            if type(result["server_address"]) is not int or not 1 <= result["server_address"] <= 0xFFFFFFF:
                raise ValueError("Adres serwera musi być dodatnią liczbą całkowitą w zakresie HDLC.")
            logical, physical = hdlc_address_parts(result)
        if "hdlc_address_size" not in patch and not result["hdlc_address_size"] and base["server_address"] >= 16384:
            result["hdlc_address_size"] = 4
        result["server_address"] = hdlc_server_address(
            patch.get("hdlc_logical_address", logical), patch.get("hdlc_physical_address", physical),
            result["hdlc_address_size"])
    for key, default in DEFAULT.items():
        if isinstance(default, str) and not isinstance(result[key], str):
            raise ValueError(f"{key}: wymagana wartość tekstowa.")
    for key in ("host", "username", "password", "discovery_prefix"):
        if not isinstance(result["mqtt"][key], str):
            raise ValueError(f"MQTT {key}: wymagana wartość tekstowa.")
    return validate(result)


def public_config(config):
    result = copy.deepcopy(config)
    result["configured_secrets"] = {key: bool(result.pop(key)) for key in SECRET_FIELDS}
    result["mqtt"]["password_configured"] = bool(result["mqtt"].pop("password"))
    result["hdlc_logical_address"], result["hdlc_physical_address"] = hdlc_address_parts(config)
    if config["transport"] != "tcp_wrapper" and not result["hdlc_address_size"] and config["server_address"] >= 16384:
        result["hdlc_address_size"] = 4
    return result


class ConfigStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "configuration.json"
        self.profiles_path = self.directory / "profiles.json"
        self.profiles = {}
        if self.profiles_path.exists():
            saved_profiles = json.loads(self.profiles_path.read_text())
            if not isinstance(saved_profiles, dict) or len(saved_profiles) > 100:
                raise ValueError("Nieprawidłowa biblioteka profili.")
            for key, document in saved_profiles.items():
                if key == "custom" or not re.fullmatch(r"[a-z0-9_]{1,80}", key):
                    raise ValueError("Nieprawidłowy identyfikator profilu.")
                self.profiles[key] = profile_document(document["name"], document["settings"])
            self.profiles_path.chmod(0o600)
        self.value = copy.deepcopy(DEFAULT)
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            # Zachowaj publikację w istniejących instalacjach do czasu migracji.
            if "mqtt_enabled" not in saved:
                saved["mqtt_enabled"] = True
            if "mqtt_discovery" not in saved:
                saved["mqtt_discovery"] = saved["mqtt_enabled"]
            self.value = merged(self.value, saved)
            self.path.chmod(0o600)
            # Zachowaj wcześniejszy profil na podstawie zapisanej konfiguracji.
            # To dane użytkownika; dodatek nie zawiera profili producentów.
            key = self.value["profile"]
            if key != "custom" and key not in self.profiles:
                name = " ".join(self.value[field].strip() for field in ("manufacturer", "model")).strip() or self.value["name"]
                self.save_profile(name, profile_id=key)

    def save(self, patch):
        config = merged(self.value, patch)
        atomic_json(self.path, config)
        self.value = config
        return public_config(config)

    def save_profile(self, name, settings=None, profile_id=None):
        key = profile_id or "p_" + uuid.uuid4().hex
        if key == "custom" or not re.fullmatch(r"[a-z0-9_]{1,80}", key):
            raise ValueError("Nieprawidłowy identyfikator profilu.")
        if key not in self.profiles and len(self.profiles) >= 100:
            raise ValueError("Można zapisać najwyżej 100 profili.")
        settings = settings if settings is not None else {key: self.value[key] for key in PROFILE_FIELDS}
        document = profile_document(name, settings)
        profiles = {**self.profiles, key: document}
        atomic_json(self.profiles_path, profiles)
        self.profiles = profiles
        return key
