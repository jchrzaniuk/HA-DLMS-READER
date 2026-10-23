"""Kolejkowanie dostępu do licznika i stan odczytu bez danych dostępowych."""

import copy
import json
import logging
import threading
from datetime import datetime, timezone

from gurux_dlms import GXDLMSException

from .configuration import validate, atomic_json, merged
from .catalog import RegisterCatalog
from .meter import session
from .metadata import describe_reading, MetadataError
from .publishing import Publisher, discovery, mqtt_settings, scaled

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_error(error):
    # Błędy transportu i protokołu mogą zawierać adresy, ścieżki lub dane dostępowe.
    if isinstance(error, MetadataError):
        return str(error)
    if isinstance(error, GXDLMSException):
        return f"Licznik odmówił operacji DLMS (kod {error.errorCode}). Sprawdź uprawnienia wybranego adresu klienta."
    if isinstance(error, TimeoutError):
        return "Upłynął czas odpowiedzi. Sprawdź transport, adresy DLMS i dostępność licznika."
    if isinstance(error, (ConnectionError, OSError)):
        return "Przerwano połączenie. Sprawdź sieć, port urządzenia i ustawienia MQTT, jeśli jest włączone."
    return "Sesja nie powiodła się. Sprawdź adresy, mechanizm uwierzytelniania, hasło i parametry zabezpieczeń."


class Runtime:
    def __init__(self, store, supervisor_token=None):
        self.store, self.supervisor_token = store, supervisor_token
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.job = None
        self.status = {"running": False, "phase": "stopped", "last_poll": None,
                       "error": None, "mqtt_error": None, "measurements": [], "test": None}
        self.latest = {}
        self.catalog = RegisterCatalog(store.directory)

    def snapshot(self):
        with self.lock:
            return {**copy.deepcopy(self.status), "catalog": self.catalog.snapshot(self.store.value, include_objects=False)}

    def catalog_snapshot(self):
        with self.lock:
            return copy.deepcopy(self.catalog.snapshot(self.store.value))

    def ensure_idle(self):
        if (self.thread and self.thread.is_alive()) or (self.job and self.job.is_alive()):
            raise RuntimeError("Zatrzymaj odczyt lub poczekaj na koniec testu przed zmianą ustawień.")

    def save(self, patch):
        with self.lock:
            self.ensure_idle()
            self.catalog.validate_selection(merged(self.store.value, patch))
            return self.store.save(patch)

    def start(self):
        with self.lock:
            self.ensure_idle()
            config = copy.deepcopy(validate(self.store.value, complete=True))
            self.catalog.validate_selection(config)
            if not config["registers"]:
                raise ValueError("Wybierz co najmniej jeden rejestr do odczytu.")
            self.stop_event.clear()
            self.status.update(running=True, phase="connecting", error=None, mqtt_error=None)
            self.latest = {}
            self.thread = threading.Thread(target=self.run, args=(config, None), daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.thread and self.thread.is_alive():
                self.status["phase"] = "stopping"
            else:
                self.status.update(running=False, phase="stopped")

    def test(self, enumerate_objects=False):
        with self.lock:
            self.ensure_idle()
            config = copy.deepcopy(self.store.value)
            if enumerate_objects:
                config['registers'] = []
            validate(config, complete=True)
            self.status["test"] = {"state": "running", "started": now(), "operation": "objects" if enumerate_objects else "test"}
            self.job = threading.Thread(target=self.test_job, args=(config, enumerate_objects), daemon=True)
            self.job.start()

    def test_job(self, config, enumerate_objects):
        try:
            with session(config, self.store.directory) as meter:
                result = {"state": "ok", "finished": now(), "measurements": []}
                if enumerate_objects:
                    objects = meter.objects()
                    with self.lock:
                        catalog = self.catalog.save(config, objects, now())
                    result["objects"] = catalog['objects']
                else:
                    for register in config["registers"][:3]:
                        try:
                            value, metadata = scaled(meter.read(register), meter.read(register, 3))
                            result["measurements"].append({"name": register["name"], "obis": register["obis"],
                                                           **describe_reading(register, value, metadata)})
                        except GXDLMSException:
                            result["measurements"].append({"name": register["name"], "obis": register["obis"],
                                                           "error": "Brak dostępu do rejestru"})
                        except MetadataError as error:
                            result["measurements"].append({"name": register["name"], "obis": register["obis"],
                                                           "error": str(error)})
            with self.lock:
                self.status["test"] = result
        except Exception as error:
            with self.lock:
                self.status["test"] = {"state": "error", "finished": now(), "error": safe_error(error)}

    def run(self, config, settings=None):
        publisher, announced, scaling, backoff = None, {}, {}, 5
        try:
            if config["mqtt_enabled"]:
                try:
                    publisher = Publisher(config, settings or mqtt_settings(config, self.supervisor_token))
                    publisher.start()
                except Exception:
                    with self.lock:
                        self.status["mqtt_error"] = "Publikacja MQTT jest niedostępna. Odczyt licznika i API nadal działają."
            previous_generation = -1
            while not self.stop_event.is_set():
                try:
                    # Odczyt licznika i dostęp do API działają niezależnie od MQTT.
                    readings = self.poll(None, config, {}, scaling)
                    if not readings:
                        raise ConnectionError("Brak odczytów")
                    with self.lock:
                        self.status.update(phase="online", error=None, last_poll=now(), measurements=readings)
                        self.latest = {item["key"]: item for item in readings}
                    if config["mqtt_enabled"]:
                        try:
                            if publisher is None:
                                publisher = Publisher(config, mqtt_settings(config, self.supervisor_token))
                                publisher.start()
                            if previous_generation != publisher.generation:
                                publisher.publish(publisher.status_topic, "offline", True)
                                previous_generation = publisher.generation
                            if config["mqtt_discovery"]:
                                self.clean_removed(publisher, config)
                            for item in readings:
                                self.publish_reading(publisher, config, item, announced)
                            for register in config["registers"]:
                                if register["key"] not in self.latest:
                                    publisher.publish(f"{config['device_id']}/{register['key']}/status", "offline", True)
                            publisher.publish(publisher.status_topic, "online", True)
                            with self.lock:
                                self.status["mqtt_error"] = None
                        except Exception:
                            with self.lock:
                                self.status["mqtt_error"] = "Broker nie potwierdził publikacji MQTT. Odczyt licznika i API nadal działają."
                    backoff, delay = 5, config["poll_interval"]
                except Exception as error:
                    with self.lock:
                        self.status.update(phase="retrying", error=safe_error(error))
                    log.warning("Cykl odczytu: %s", safe_error(error))
                    try:
                        if publisher:
                            publisher.publish(publisher.status_topic, "offline", True)
                    except Exception:
                        pass
                    delay, backoff = backoff, min(backoff * 2, 300)
                self.stop_event.wait(delay)
        except Exception as error:
            with self.lock:
                self.status["error"] = safe_error(error)
        finally:
            if publisher:
                try:
                    publisher.close()
                except Exception:
                    pass
            with self.lock:
                self.status.update(running=False, phase="stopped")

    def clean_removed(self, publisher, config):
        path = self.store.directory / "discovery.json"
        previous = json.loads(path.read_text()) if path.exists() else []
        current = [discovery(config, reg, (None, None, "measurement", 1))[0] for reg in config["registers"]]
        for topic in set(previous) - set(current):
            publisher.publish(topic, "", True)
        if current != previous:
            atomic_json(path, current)

    def poll(self, publisher, config, announced, scaling):
        readings = []
        with session(config, self.store.directory) as meter:
            for register in config["registers"]:
                if self.stop_event.is_set():
                    break
                key = register["key"]
                state_topic = f"{config['device_id']}/{key}"
                try:
                    identity = (register["obis"], register["class_id"], register.get("short_name"))
                    if identity not in scaling:
                        scaling[identity] = meter.read(register, 3)
                    value, metadata = scaled(meter.read(register), scaling[identity])
                    reading = {"key": key, "name": register["name"], "obis": register["obis"],
                               **describe_reading(register, value, metadata),
                               "sampled_at": now()}
                    if publisher:
                        self.publish_reading(publisher, config, reading, announced)
                    readings.append(reading)
                except (GXDLMSException, ValueError) as error:
                    if publisher:
                        publisher.publish(f"{state_topic}/status", "offline", True)
                    log.warning("Rejestr %s: %s", register["obis"], safe_error(error))
        return readings

    def publish_reading(self, publisher, config, reading, announced):
        key = reading["key"]
        generation = publisher.generation
        state_topic = f"{config['device_id']}/{key}"
        if announced.get(key) != generation:
            if config["mqtt_discovery"]:
                topic, payload = discovery(config, reading, (reading["unit"], reading["device_class"], reading["state_class"], 1))
                publisher.publish(topic, json.dumps(payload, ensure_ascii=False), True)
            publisher.publish(state_topic, "", True)
            announced[key] = generation
        publisher.publish(state_topic, format(reading["value"], ".12g"))
        publisher.publish(f"{state_topic}/status", "online", True)

    def integration_snapshot(self):
        with self.lock:
            config = self.store.value
            return {"api_version": 1, "device": {"id": config["device_id"], "name": config["name"],
                    "manufacturer": config["manufacturer"], "model": config["model"]},
                    "running": self.status["running"], "phase": self.status["phase"],
                    "last_poll": self.status["last_poll"], "poll_interval": config["poll_interval"],
                    "expire_after": config["poll_interval"] * 3 + config["timeout"],
                    "mqtt_enabled": config["mqtt_enabled"],
                    "mqtt_discovery_prefix": config["mqtt"]["discovery_prefix"],
                    "registers": [{"key": register["key"], "name": register["name"], "obis": register["obis"],
                        "class_id": register["class_id"], "device_class": register.get("device_class"),
                        "unit": register.get("unit"), "state_class": register.get("state_class"),
                        "sample": self.latest.get(register["key"])} for register in config["registers"]]}
