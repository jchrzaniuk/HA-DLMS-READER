"""Encje pomiarowe korzystające ze wspólnego zestawu danych API."""

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def fresh_sample(data, register, current_time=None):
    sample = register.get('sample')
    if not data.get('running') or data.get('phase') != 'online' or not sample:
        return False
    try:
        timestamp = datetime.fromisoformat(sample['sampled_at'])
        if timestamp.tzinfo is None:
            return False
        age = ((current_time or datetime.now(timezone.utc)) - timestamp).total_seconds()
        return -5 <= age <= data['expire_after']
    except (KeyError, ValueError, TypeError):
        return False


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()

    @callback
    def add_new_registers():
        entities = []
        for register in coordinator.data['registers']:
            if register['key'] not in known:
                known.add(register['key'])
                entities.append(ReaderSensor(coordinator, register))
        if entities:
            async_add_entities(entities)

    add_new_registers()
    entry.async_on_unload(coordinator.async_add_listener(add_new_registers))


class ReaderSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_suggested_display_precision = 5

    def __init__(self, coordinator, register):
        super().__init__(coordinator)
        self.key = register['key']
        device = coordinator.data['device']
        self._attr_unique_id = f"{device['id']}_{self.key}"
        self._attr_suggested_object_id = self._attr_unique_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device['id'])}, name=device['name'],
                                             manufacturer=device.get('manufacturer') or None,
                                             model=device.get('model') or None)
        self.apply_metadata(register)

    @property
    def register(self):
        return next((r for r in self.coordinator.data['registers'] if r['key'] == self.key), None)

    def apply_metadata(self, register):
        sample = register.get('sample') or {}
        self._attr_name = f"{'.'.join(register['obis'].split('.')[2:5])} {register['name']}"
        self._attr_native_unit_of_measurement = sample.get('unit') or register.get('unit')
        device_class = sample.get('device_class') or register.get('device_class')
        state_class = sample.get('state_class') or register.get('state_class')
        self._attr_device_class = SensorDeviceClass(device_class) if device_class in SensorDeviceClass else None
        self._attr_state_class = SensorStateClass(state_class) if state_class in SensorStateClass else None
        self._attr_extra_state_attributes = {'obis': register['obis'], 'class_id': register['class_id']}

    @property
    def native_value(self):
        register = self.register
        return (register.get('sample') or {}).get('value') if register else None

    @property
    def available(self):
        return super().available and self.register is not None and fresh_sample(self.coordinator.data, self.register)

    @callback
    def _handle_coordinator_update(self):
        if register := self.register:
            self.apply_metadata(register)
        super()._handle_coordinator_update()
