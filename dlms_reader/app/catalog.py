"""Lista rejestrów pobrana z licznika, przypisana do parametrów połączenia."""

import hashlib
import json

from .configuration import atomic_json, obis_valid
from .obis_pl import localize, source_documents

GROUPS = {"energy": "Energia", "power": "Moc", "current_voltage": "Prąd i napięcie",
          "other": "Pozostałe parametry"}
CONNECTION_FIELDS = (
    "transport", "host", "port", "serial_device", "baudrate", "parity", "bytesize", "stopbits",
    "client_address", "server_address", "hdlc_address_size", "referencing", "authentication",
    "password_format", "password", "text_encoding", "security", "security_suite",
    "client_system_title", "server_system_title", "block_cipher_key", "authentication_key",
)


def identity(config):
    # Skrót wiąże listę również z uprawnieniami sesji; nie jest zwracany przez API.
    settings = {key: config.get(key) for key in CONNECTION_FIELDS}
    return hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()


def register_group(obis):
    if not obis_valid(obis):
        return "other"
    medium, _, quantity, processing, _, _ = map(int, obis.split('.'))
    if medium != 1 or not 1 <= quantity <= 80:
        return "other"
    family = (quantity - 1) % 20 + 1
    if family in (11, 12):
        return "current_voltage"
    if family in (*range(1, 11), 15, 16, 17, 18, 19, 20):
        return "energy" if processing in (8, 9, 10, 17, 18, 19, 20, 29, 30, 58) else "power"
    return "other"


def clean_objects(objects):
    result, seen = [], set()
    for item in objects:
        obis, class_id = item.get('obis'), item.get('class_id')
        if not obis_valid(obis) or class_id not in (3, 4) or (obis, class_id) in seen:
            continue
        seen.add((obis, class_id))
        result.append({"obis": obis, "class_id": class_id,
                       "key": "obis_" + obis.replace('.', '_') + f"_{class_id}",
                       "name": str(item.get('name') or obis),
                       "short_name": item.get('short_name'), "group": register_group(obis)})
    return sorted(result, key=lambda item: (tuple(map(int, item['obis'].split('.'))), item['class_id']))


class RegisterCatalog:
    def __init__(self, directory):
        self.path = directory / 'register-catalog.json'
        try:
            value = json.loads(self.path.read_text()) if self.path.exists() else None
            self.value = value if isinstance(value, dict) and isinstance(value.get('objects'), list) and value.get('fetched_at') else None
        except (OSError, ValueError):
            self.value = None

    def snapshot(self, config, include_objects=True):
        ready = bool(self.value and self.value.get('version') == 1 and
                     self.value.get('identity') == identity(config))
        return {"ready": ready, "fetched_at": self.value['fetched_at'] if ready else None,
                "count": len(self.value['objects']) if ready else 0, "groups": GROUPS,
                **({"objects": [localize(item) for item in self.value['objects']] if ready else [],
                    "description_sources": source_documents()} if include_objects else {})}

    def save(self, config, objects, fetched_at):
        value = {"version": 1, "identity": identity(config), "fetched_at": fetched_at,
                 "objects": clean_objects(objects)}
        atomic_json(self.path, value)
        self.value = value
        return self.snapshot(config)

    def validate_selection(self, config):
        catalog = self.snapshot(config)
        if not catalog['ready']:
            return
        available = {(item['obis'], item['class_id']) for item in catalog['objects']}
        if any((item['obis'], item['class_id']) not in available for item in config['registers']):
            raise ValueError("Wybrany rejestr nie występuje na liście pobranej z tego licznika. Pobierz listę i wybierz dostępne rejestry.")
