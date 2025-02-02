"""Support for Safegate Pro iOS app sensors."""
from homeassistant.components import ios
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.icon import icon_for_battery_level

from .const import DOMAIN

SENSOR_TYPES = {
    "level": ["Battery Level", PERCENTAGE],
    "state": ["Battery State", None],
}

DEFAULT_ICON_LEVEL = "mdi:battery"
DEFAULT_ICON_STATE = "mdi:power-plug"


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the iOS sensor."""
    # Leave here for if someone accidentally adds platform: ios to config


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up iOS from a config entry."""
    dev = []
    for device_name, device in ios.devices(hass).items():
        for sensor_type in ("level", "state"):
            dev.append(IOSSensor(sensor_type, device_name, device))

    async_add_entities(dev, True)


class IOSSensor(SensorEntity):
    """Representation of an iOS sensor."""

    def __init__(self, sensor_type, device_name, device):
        """Initialize the sensor."""
        self._device_name = device_name
        self._name = f"{device_name} {SENSOR_TYPES[sensor_type][0]}"
        self._device = device
        self.type = sensor_type
        self._state = None
        self._unit_of_measurement = SENSOR_TYPES[sensor_type][1]

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {
                (
                    ios.DOMAIN,
                    self._device[ios.ATTR_DEVICE][ios.ATTR_DEVICE_PERMANENT_ID],
                )
            },
            "name": self._device[ios.ATTR_DEVICE][ios.ATTR_DEVICE_NAME],
            "manufacturer": "Apple",
            "model": self._device[ios.ATTR_DEVICE][ios.ATTR_DEVICE_TYPE],
            "sw_version": self._device[ios.ATTR_DEVICE][ios.ATTR_DEVICE_SYSTEM_VERSION],
        }

    @property
    def name(self):
        """Return the name of the iOS sensor."""
        device_name = self._device[ios.ATTR_DEVICE][ios.ATTR_DEVICE_NAME]
        return f"{device_name} {SENSOR_TYPES[self.type][0]}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unique_id(self):
        """Return the unique ID of this sensor."""
        device_id = self._device[ios.ATTR_DEVICE_ID]
        return f"{self.type}_{device_id}"

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement this sensor expresses itself in."""
        return self._unit_of_measurement

    @property
    def extra_state_attributes(self):
        """Return the device state attributes."""
        device = self._device[ios.ATTR_DEVICE]
        device_battery = self._device[ios.ATTR_BATTERY]
        return {
            "Battery State": device_battery[ios.ATTR_BATTERY_STATE],
            "Battery Level": device_battery[ios.ATTR_BATTERY_LEVEL],
            "Device Type": device[ios.ATTR_DEVICE_TYPE],
            "Device Name": device[ios.ATTR_DEVICE_NAME],
            "Device Version": device[ios.ATTR_DEVICE_SYSTEM_VERSION],
        }

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        device_battery = self._device[ios.ATTR_BATTERY]
        battery_state = device_battery[ios.ATTR_BATTERY_STATE]
        battery_level = device_battery[ios.ATTR_BATTERY_LEVEL]
        charging = True
        icon_state = DEFAULT_ICON_STATE
        if battery_state in (
            ios.ATTR_BATTERY_STATE_FULL,
            ios.ATTR_BATTERY_STATE_UNPLUGGED,
        ):
            charging = False
            icon_state = f"{DEFAULT_ICON_STATE}-off"
        elif battery_state == ios.ATTR_BATTERY_STATE_UNKNOWN:
            battery_level = None
            charging = False
            icon_state = f"{DEFAULT_ICON_LEVEL}-unknown"

        if self.type == "state":
            return icon_state
        return icon_for_battery_level(battery_level=battery_level, charging=charging)

    @callback
    def _update(self, device):
        """Get the latest state of the sensor."""
        self._device = device
        self._state = self._device[ios.ATTR_BATTERY][self.type]
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Added to hass so need to register to dispatch."""
        self._state = self._device[ios.ATTR_BATTERY][self.type]
        device_id = self._device[ios.ATTR_DEVICE_ID]
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}.{device_id}", self._update)
        )
