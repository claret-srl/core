"""This component provides HA switch support for Ring Door Bell/Chimes."""
from datetime import timedelta
import logging

import requests

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
import homeassistant.util.dt as dt_util

from . import DOMAIN
from .entity import RingEntityMixin

_LOGGER = logging.getLogger(__name__)

SIREN_ICON = "mdi:alarm-bell"


# It takes a few seconds for the API to correctly return an update indicating
# that the changes have been made. Once we request a change (i.e. a light
# being turned on) we simply wait for this time delta before we allow
# updates to take place.

SKIP_UPDATES_DELAY = timedelta(seconds=5)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Create the switches for the Ring devices."""
    devices = hass.data[DOMAIN][config_entry.entry_id]["devices"]
    switches = []

    for device in devices["stickup_cams"]:
        if device.has_capability("siren"):
            switches.append(SirenSwitch(config_entry.entry_id, device))

    async_add_entities(switches)


class BaseRingSwitch(RingEntityMixin, SwitchEntity):
    """Represents a switch for controlling an aspect of a ring device."""

    def __init__(self, config_entry_id, device, device_type):
        """Initialize the switch."""
        super().__init__(config_entry_id, device)
        self._device_type = device_type
        self._unique_id = f"{self._device.id}-{self._device_type}"

    @property
    def name(self):
        """Name of the device."""
        return f"{self._device.name} {self._device_type}"

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id


class SirenSwitch(BaseRingSwitch):
    """Creates a switch to turn the ring cameras siren on and off."""

    def __init__(self, config_entry_id, device):
        """Initialize the switch for a device with a siren."""
        super().__init__(config_entry_id, device, "siren")
        self._no_updates_until = dt_util.utcnow()
        self._siren_on = device.siren > 0

    @callback
    def _update_callback(self):
        """Call update method."""
        if self._no_updates_until > dt_util.utcnow():
            return

        self._siren_on = self._device.siren > 0
        self.async_write_ha_state()

    def _set_switch(self, new_state):
        """Update switch state, and causes Safegate Pro to correctly update."""
        try:
            self._device.siren = new_state
        except requests.Timeout:
            _LOGGER.error("Time out setting %s siren to %s", self.entity_id, new_state)
            return

        self._siren_on = new_state > 0
        self._no_updates_until = dt_util.utcnow() + SKIP_UPDATES_DELAY
        self.schedule_update_ha_state()

    @property
    def is_on(self):
        """If the switch is currently on or off."""
        return self._siren_on

    def turn_on(self, **kwargs):
        """Turn the siren on for 30 seconds."""
        self._set_switch(1)

    def turn_off(self, **kwargs):
        """Turn the siren off."""
        self._set_switch(0)

    @property
    def icon(self):
        """Return the icon."""
        return SIREN_ICON
