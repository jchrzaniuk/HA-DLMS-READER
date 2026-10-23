"""MQTT Discovery, przeliczanie jednostek i publikacja z potwierdzeniem."""

import json
import math
import threading
import urllib.request

import paho.mqtt.client as mqtt
from .metadata import UNITS, resolved_metadata


def scaled(raw, scaler_unit):
    if not isinstance(scaler_unit, (tuple, list)) or len(scaler_unit) != 2:
        raise ValueError("Licznik nie zwrócił prawidłowej skali i jednostki.")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise ValueError("Rejestr nie zwrócił skończonej wartości liczbowej.")
    scaler, unit = map(int, scaler_unit)
    if not -12 <= scaler <= 12:
        raise ValueError("Skala rejestru jest poza obsługiwanym zakresem.")
    metadata = UNITS.get(unit, (None, None, None, 1))
    value = raw * 10 ** scaler * metadata[3]
    if not math.isfinite(value):
        raise ValueError("Wartość po przeskalowaniu przekracza zakres.")
    return value, metadata


def mqtt_settings(config, supervisor_token=None):
    settings = dict(config["mqtt"])
    if not settings["host"] and supervisor_token:
        request = urllib.request.Request("http://supervisor/services/mqtt", headers={
            "X-Supervisor-Token": supervisor_token})
        with urllib.request.urlopen(request, timeout=10) as response:
            document = json.load(response)
        if document.get("result") != "ok":
            raise ConnectionError("Supervisor nie udostępnił brokera MQTT.")
        data = document["data"]
        settings.update(host=data["host"], port=data["port"], username=data.get("username", ""),
                        password=data.get("password", ""), tls=data.get("ssl", False))
    if not settings["host"]:
        raise ValueError("Podaj adres brokera MQTT lub skonfiguruj usługę MQTT w Home Assistant.")
    return settings


class Publisher:
    def __init__(self, config, settings):
        self.config, self.settings = config, settings
        self.connected = threading.Event()
        self.generation = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"dlms-{config['device_id']}")
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        if settings["username"]:
            self.client.username_pw_set(settings["username"], settings["password"])
        if settings["tls"]:
            self.client.tls_set()
        self.client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)

    @property
    def status_topic(self):
        return f"{self.config['device_id']}/status"

    def on_connect(self, client, userdata, flags, code, properties):
        if not code.is_failure:
            self.generation += 1
            self.connected.set()
        else:
            self.connected.clear()

    def on_disconnect(self, client, userdata, flags, code, properties):
        self.connected.clear()

    def start(self):
        self.client.connect_async(self.settings["host"], self.settings["port"], keepalive=60)
        self.client.loop_start()

    def publish(self, topic, payload, retain=False):
        if not self.connected.wait(10):
            raise ConnectionError("Brak połączenia z brokerem MQTT.")
        generation = self.generation
        info = self.client.publish(topic, payload, qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError("Broker nie przyjął publikacji MQTT.")
        info.wait_for_publish(timeout=10)
        if not info.is_published() or generation != self.generation or not self.connected.is_set():
            raise ConnectionError("Brak potwierdzenia publikacji MQTT.")

    def close(self):
        try:
            if self.connected.is_set():
                self.publish(self.status_topic, "offline", True)
        finally:
            self.client.disconnect()
            self.client.loop_stop()


def discovery(config, register, metadata):
    device_id, key = config["device_id"], register["key"]
    resolved = resolved_metadata(register, metadata)
    unit, device_class, state_class = (resolved[key] for key in ("unit", "device_class", "state_class"))
    payload = {
        "name": f"{'.'.join(register['obis'].split('.')[2:5])} {register['name']}",
        "has_entity_name": True, "unique_id": f"{device_id}_{key}",
        "object_id": f"{device_id}_{key}", "state_topic": f"{device_id}/{key}",
        "availability": [{"topic": f"{device_id}/status"}, {"topic": f"{device_id}/{key}/status"}],
        "availability_mode": "all", "expire_after": math.ceil(config["poll_interval"] * 3 + config["timeout"]),
        "device": {"identifiers": [device_id], "name": config["name"],
                   "manufacturer": config["manufacturer"] or "DLMS/COSEM", "model": config["model"] or "Licznik"},
    }
    if state_class:
        payload["state_class"] = state_class
    for field, value in (("unit_of_measurement", unit), ("device_class", device_class)):
        if value:
            payload[field] = value
    return f"{config['mqtt']['discovery_prefix']}/sensor/{device_id}/{key}/config", payload
