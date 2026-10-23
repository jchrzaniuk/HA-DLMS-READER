"""Jednostki DLMS, znaczenie kodów OBIS i ręczne ustawienia parametrów HA."""

import math


class MetadataError(ValueError):
    """Błąd parametrów HA z instrukcją poprawy, bez danych dostępowych."""

# Jednostka DLMS: jednostka HA, klasa urządzenia, klasa stanu i przelicznik.
UNITS = {
    0: (None, None, "measurement", 1), 255: (None, None, "measurement", 1),
    4: ("d", "duration", "measurement", 1),
    5: ("h", "duration", "measurement", 1),
    6: ("min", "duration", "measurement", 1),
    7: ("s", "duration", "measurement", 1),
    9: ("°C", "temperature", "measurement", 1),
    13: ("m³", "volume", None, 1), 14: ("m³", "volume", None, 1),
    15: ("m³/h", "volume_flow_rate", "measurement", 1),
    16: ("m³/h", "volume_flow_rate", "measurement", 1),
    19: ("L", "volume", None, 1),
    20: ("kg", "weight", "measurement", 1),
    23: ("Pa", "pressure", "measurement", 1),
    24: ("bar", "pressure", "measurement", 1),
    25: ("J", "energy", None, 1),
    26: ("W", "power", "measurement", 1),
    27: ("W", "power", "measurement", 1),
    28: ("VA", "apparent_power", "measurement", 1),
    29: ("var", "reactive_power", "measurement", 1),
    30: ("kWh", "energy", None, .001),
    31: ("kVAh", None, None, .001),
    32: ("kvarh", "reactive_energy", None, .001),
    33: ("A", "current", "measurement", 1),
    35: ("V", "voltage", "measurement", 1),
    44: ("Hz", "frequency", "measurement", 1),
    52: ("K", "temperature", "measurement", 1),
    56: ("%", None, "measurement", 1),
}

# Wartość bazowa = wartość * skala + przesunięcie. Wymiar wyklucza np. zmianę W na Wh.
UNIT_CONVERSIONS = {
    "Wh": ("energy", 3600, 0), "kWh": ("energy", 3600000, 0),
    "MWh": ("energy", 3600000000, 0), "J": ("energy", 1, 0),
    "kJ": ("energy", 1000, 0), "MJ": ("energy", 1000000, 0), "GJ": ("energy", 1e9, 0),
    "varh": ("reactive_energy", 1, 0), "kvarh": ("reactive_energy", 1000, 0),
    "VAh": ("apparent_energy", 1, 0), "kVAh": ("apparent_energy", 1000, 0),
    "W": ("power", 1, 0), "kW": ("power", 1000, 0), "MW": ("power", 1e6, 0),
    "VA": ("apparent_power", 1, 0), "kVA": ("apparent_power", 1000, 0),
    "var": ("reactive_power", 1, 0), "kvar": ("reactive_power", 1000, 0),
    "A": ("current", 1, 0), "mA": ("current", .001, 0),
    "V": ("voltage", 1, 0), "mV": ("voltage", .001, 0), "kV": ("voltage", 1000, 0),
    "Hz": ("frequency", 1, 0), "kHz": ("frequency", 1000, 0), "MHz": ("frequency", 1e6, 0),
    "m³": ("volume", 1, 0), "L": ("volume", .001, 0),
    "m³/h": ("volume_flow_rate", 1, 0), "L/min": ("volume_flow_rate", .06, 0),
    "s": ("duration", 1, 0), "min": ("duration", 60, 0),
    "h": ("duration", 3600, 0), "d": ("duration", 86400, 0),
    "°C": ("temperature", 1, 273.15), "°F": ("temperature", 5/9, 255.3722222222222),
    "K": ("temperature", 1, 0),
    "Pa": ("pressure", 1, 0), "hPa": ("pressure", 100, 0),
    "kPa": ("pressure", 1000, 0), "bar": ("pressure", 100000, 0),
    "kg": ("weight", 1, 0), "g": ("weight", .001, 0),
    "%": ("ratio", .01, 0),
}
DEVICE_CLASSES = {
    "energy": "Energia czynna lub cieplna", "reactive_energy": "Energia bierna",
    "power": "Moc czynna lub cieplna", "reactive_power": "Moc bierna",
    "apparent_power": "Moc pozorna", "power_factor": "Współczynnik mocy",
    "voltage": "Napięcie", "current": "Prąd", "frequency": "Częstotliwość",
    "volume": "Objętość", "gas": "Gaz", "water": "Woda",
    "volume_flow_rate": "Przepływ", "temperature": "Temperatura",
    "pressure": "Ciśnienie", "duration": "Czas", "weight": "Masa",
    "energy_storage": "Energia zmagazynowana",
}
STATES = {"measurement": "Pomiar bieżący", "total": "Suma lub bilans",
          "total_increasing": "Suma rosnąca z zerowaniem"}
TOTAL_CLASSES = {"energy", "reactive_energy", "gas", "water", "volume"}
FLEXIBLE_CLASSES = {"duration", "weight"}


def class_units(device_class):
    dimension = {"gas": "volume", "water": "volume", "energy_storage": "energy",
                 "power_factor": "ratio"}.get(device_class, device_class)
    units = [unit for unit, conversion in UNIT_CONVERSIONS.items() if conversion[0] == dimension]
    return units + ([None] if device_class == "power_factor" else [])


def class_states(device_class):
    if device_class in FLEXIBLE_CLASSES or device_class is None:
        return set(STATES)
    return {"total", "total_increasing"} if device_class in TOTAL_CLASSES else {"measurement"}


def validate_overrides(register):
    for field, values in (("device_class", DEVICE_CLASSES), ("state_class", STATES), ("unit", UNIT_CONVERSIONS)):
        if field in register and register[field] is not None:
            if not isinstance(register[field], str) or register[field] not in values:
                raise ValueError(f"Rejestr: nieobsługiwana wartość {field}.")
    device_class = register.get("device_class")
    if device_class:
        if "unit" in register and register["unit"] not in class_units(device_class):
            raise ValueError("Jednostka rejestru nie pasuje do wybranej klasy urządzenia.")
        if register.get("state_class") and register["state_class"] not in class_states(device_class):
            raise ValueError("Klasa stanu rejestru nie pasuje do wybranej klasy urządzenia.")


def automatic_metadata(register, metadata):
    unit, device_class, state_class, _ = metadata
    parts = register.get("obis", "").split(".")
    if len(parts) == 6 and all(p.isdigit() for p in parts):
        medium, _, quantity, processing, _, _ = map(int, parts)
        if medium == 1:
            family = (quantity-1) % 20+1 if 1 <= quantity <= 80 else quantity
            if (family == 13 or quantity in (84, 85, 86, 87)) and processing == 7 and unit in (None, "%") and state_class:
                device_class, state_class = "power_factor", "measurement"
            # Tylko rozpoznane kody OBIS energii określają sposób jej sumowania.
            expected = ({1, 2, 15, 16, 17, 18, 19, 20} if device_class == "energy" else
                        {3, 4, 5, 6, 7, 8} if device_class == "reactive_energy" else
                        {9, 10} if unit in ("kVAh", "VAh") else set())
            if processing == 8 and family in expected:
                state_class = "total" if family == 16 else "total_increasing"
        elif medium in (7, 8, 9) and device_class == "volume":
            device_class = "gas" if medium == 7 else "water"
    return {"unit": unit, "device_class": device_class, "state_class": state_class}


def resolved_metadata(register, metadata):
    result = automatic_metadata(register, metadata)
    automatic_class = result["device_class"]
    result.update({key: register[key] for key in result if key in register})
    device_class = result["device_class"]
    if device_class and device_class != automatic_class and "state_class" not in register:
        allowed = class_states(device_class)
        if allowed == {"measurement"}:
            result["state_class"] = "measurement"
        elif result["state_class"] not in allowed:
            result["state_class"] = None
    if device_class:
        if result["unit"] not in class_units(device_class):
            raise MetadataError("Jednostka licznika nie pasuje do klasy urządzenia. Popraw parametry HA rejestru.")
        if result["state_class"] and result["state_class"] not in class_states(device_class):
            raise MetadataError("Klasa stanu nie pasuje do klasy urządzenia. Popraw parametry HA rejestru.")
    return result


def convert_value(value, source, target, device_class):
    if source == target:
        return value
    # Bez znajomości jednostki źródłowej nie można dobrać przelicznika.
    if device_class == "power_factor":
        source_conversion = ("ratio", 1, 0) if source is None else UNIT_CONVERSIONS.get(source)
        target_conversion = ("ratio", 1, 0) if target is None else UNIT_CONVERSIONS.get(target)
    else:
        source_conversion, target_conversion = UNIT_CONVERSIONS.get(source), UNIT_CONVERSIONS.get(target)
    if not source_conversion or not target_conversion or source_conversion[0] != target_conversion[0]:
        raise MetadataError("Nie można przeliczyć jednostki licznika na wybraną jednostkę rejestru.")
    value = (value*source_conversion[1]+source_conversion[2]-target_conversion[2])/target_conversion[1]
    if not math.isfinite(value):
        raise MetadataError("Wartość po przeliczeniu jednostki przekracza zakres.")
    return value


def describe_reading(register, value, metadata):
    result = resolved_metadata(register, metadata)
    value = convert_value(value, metadata[0], result["unit"], result["device_class"])
    if result["state_class"] == "total_increasing" and value < 0:
        raise MetadataError("Suma rosnąca nie może być ujemna. Dla bilansu wybierz klasę stanu total.")
    return {"value": value,
            **result, "auto_metadata": automatic_metadata(register, metadata)}


def metadata_options():
    return {"device_classes": DEVICE_CLASSES, "state_classes": STATES,
            "units": list(UNIT_CONVERSIONS),
            "class_units": {key: class_units(key) for key in DEVICE_CLASSES},
            "class_states": {key: sorted(class_states(key)) for key in DEVICE_CLASSES}}
