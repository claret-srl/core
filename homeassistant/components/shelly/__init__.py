"""The Shelly integration."""
import asyncio
from datetime import timedelta
import logging

import aioshelly
import async_timeout
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, device_registry, update_coordinator
import homeassistant.helpers.config_validation as cv

from .const import (
    AIOSHELLY_DEVICE_TIMEOUT_SEC,
    ATTR_CHANNEL,
    ATTR_CLICK_TYPE,
    ATTR_DEVICE,
    BATTERY_DEVICES_WITH_PERMANENT_CONNECTION,
    COAP,
    CONF_COAP_PORT,
    DATA_CONFIG_ENTRY,
    DEFAULT_COAP_PORT,
    DEVICE,
    DOMAIN,
    EVENT_SHELLY_CLICK,
    INPUTS_EVENTS_DICT,
    POLLING_TIMEOUT_SEC,
    REST,
    REST_SENSORS_UPDATE_INTERVAL,
    SHBTN_MODELS,
    SLEEP_PERIOD_MULTIPLIER,
    UPDATE_PERIOD_MULTIPLIER,
)
from .utils import get_coap_context, get_device_name, get_device_sleep_period

PLATFORMS = ["binary_sensor", "cover", "light", "sensor", "switch"]
SLEEPING_PLATFORMS = ["binary_sensor", "sensor"]
_LOGGER = logging.getLogger(__name__)

COAP_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_COAP_PORT, default=DEFAULT_COAP_PORT): cv.port,
    }
)
CONFIG_SCHEMA = vol.Schema({DOMAIN: COAP_SCHEMA}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Shelly component."""
    hass.data[DOMAIN] = {DATA_CONFIG_ENTRY: {}}

    conf = config.get(DOMAIN)
    if conf is not None:
        hass.data[DOMAIN][CONF_COAP_PORT] = conf[CONF_COAP_PORT]

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shelly from a config entry."""
    # The custom component for Shelly devices uses shelly domain as well as core
    # integration. If the user removes the custom component but doesn't remove the
    # config entry, core integration will try to configure that config entry with an
    # error. The config entry data for this custom component doesn't contain host
    # value, so if host isn't present, config entry will not be configured.
    if not entry.data.get(CONF_HOST):
        _LOGGER.warning(
            "The config entry %s probably comes from a custom integration, please remove it if you want to use core Shelly integration",
            entry.title,
        )
        return False

    hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id] = {}
    hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][DEVICE] = None

    temperature_unit = "C" if hass.config.units.is_metric else "F"

    options = aioshelly.ConnectionOptions(
        entry.data[CONF_HOST],
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD),
        temperature_unit,
    )

    coap_context = await get_coap_context(hass)

    device = await aioshelly.Device.create(
        aiohttp_client.async_get_clientsession(hass),
        coap_context,
        options,
        False,
    )

    dev_reg = await device_registry.async_get_registry(hass)
    device_entry = None
    if entry.unique_id is not None:
        device_entry = dev_reg.async_get_device(
            identifiers={(DOMAIN, entry.unique_id)}, connections=set()
        )
    if device_entry and entry.entry_id not in device_entry.config_entries:
        device_entry = None

    sleep_period = entry.data.get("sleep_period")

    @callback
    def _async_device_online(_):
        _LOGGER.debug("Device %s is online, resuming setup", entry.title)
        hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][DEVICE] = None

        if sleep_period is None:
            data = {**entry.data}
            data["sleep_period"] = get_device_sleep_period(device.settings)
            data["model"] = device.settings["device"]["type"]
            hass.config_entries.async_update_entry(entry, data=data)

        hass.async_create_task(async_device_setup(hass, entry, device))

    if sleep_period == 0:
        # Not a sleeping device, finish setup
        _LOGGER.debug("Setting up online device %s", entry.title)
        try:
            async with async_timeout.timeout(AIOSHELLY_DEVICE_TIMEOUT_SEC):
                await device.initialize(True)
        except (asyncio.TimeoutError, OSError) as err:
            raise ConfigEntryNotReady from err

        await async_device_setup(hass, entry, device)
    elif sleep_period is None or device_entry is None:
        # Need to get sleep info or first time sleeping device setup, wait for device
        hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][DEVICE] = device
        _LOGGER.debug(
            "Setup for device %s will resume when device is online", entry.title
        )
        device.subscribe_updates(_async_device_online)
        await device.coap_request("s")
    else:
        # Restore sensors for sleeping device
        _LOGGER.debug("Setting up offline device %s", entry.title)
        await async_device_setup(hass, entry, device)

    return True


async def async_device_setup(
    hass: HomeAssistant, entry: ConfigEntry, device: aioshelly.Device
):
    """Set up a device that is online."""
    device_wrapper = hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][
        COAP
    ] = ShellyDeviceWrapper(hass, entry, device)
    await device_wrapper.async_setup()

    platforms = SLEEPING_PLATFORMS

    if not entry.data.get("sleep_period"):
        hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][
            REST
        ] = ShellyDeviceRestWrapper(hass, device)
        platforms = PLATFORMS

    hass.config_entries.async_setup_platforms(entry, platforms)


class ShellyDeviceWrapper(update_coordinator.DataUpdateCoordinator):
    """Wrapper for a Shelly device with Safegate Pro specific functions."""

    def __init__(self, hass, entry, device: aioshelly.Device):
        """Initialize the Shelly device wrapper."""
        self.device_id = None
        sleep_period = entry.data["sleep_period"]

        if sleep_period:
            update_interval = SLEEP_PERIOD_MULTIPLIER * sleep_period
        else:
            update_interval = (
                UPDATE_PERIOD_MULTIPLIER * device.settings["coiot"]["update_period"]
            )

        device_name = get_device_name(device) if device.initialized else entry.title
        super().__init__(
            hass,
            _LOGGER,
            name=device_name,
            update_interval=timedelta(seconds=update_interval),
        )
        self.hass = hass
        self.entry = entry
        self.device = device

        self._async_remove_device_updates_handler = self.async_add_listener(
            self._async_device_updates_handler
        )
        self._last_input_events_count: dict = {}

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._handle_ha_stop)

    @callback
    def _async_device_updates_handler(self):
        """Handle device updates."""
        if not self.device.initialized:
            return

        # For buttons which are battery powered - set initial value for last_event_count
        if self.model in SHBTN_MODELS and self._last_input_events_count.get(1) is None:
            for block in self.device.blocks:
                if block.type != "device":
                    continue

                if block.wakeupEvent[0] == "button":
                    self._last_input_events_count[1] = -1

                break

        # Check for input events
        for block in self.device.blocks:
            if (
                "inputEvent" not in block.sensor_ids
                or "inputEventCnt" not in block.sensor_ids
            ):
                continue

            channel = int(block.channel or 0) + 1
            event_type = block.inputEvent
            last_event_count = self._last_input_events_count.get(channel)
            self._last_input_events_count[channel] = block.inputEventCnt

            if (
                last_event_count is None
                or last_event_count == block.inputEventCnt
                or event_type == ""
            ):
                continue

            if event_type in INPUTS_EVENTS_DICT:
                self.hass.bus.async_fire(
                    EVENT_SHELLY_CLICK,
                    {
                        ATTR_DEVICE_ID: self.device_id,
                        ATTR_DEVICE: self.device.settings["device"]["hostname"],
                        ATTR_CHANNEL: channel,
                        ATTR_CLICK_TYPE: INPUTS_EVENTS_DICT[event_type],
                    },
                )
            else:
                _LOGGER.warning(
                    "Shelly input event %s for device %s is not supported, please open issue",
                    event_type,
                    self.name,
                )

    async def _async_update_data(self):
        """Fetch data."""
        if self.entry.data.get("sleep_period"):
            # Sleeping device, no point polling it, just mark it unavailable
            raise update_coordinator.UpdateFailed("Sleeping device did not update")

        _LOGGER.debug("Polling Shelly Device - %s", self.name)
        try:
            async with async_timeout.timeout(POLLING_TIMEOUT_SEC):
                return await self.device.update()
        except OSError as err:
            raise update_coordinator.UpdateFailed("Error fetching data") from err

    @property
    def model(self):
        """Model of the device."""
        return self.entry.data["model"]

    @property
    def mac(self):
        """Mac address of the device."""
        return self.entry.unique_id

    async def async_setup(self):
        """Set up the wrapper."""
        dev_reg = await device_registry.async_get_registry(self.hass)
        sw_version = self.device.settings["fw"] if self.device.initialized else ""
        entry = dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            name=self.name,
            connections={(device_registry.CONNECTION_NETWORK_MAC, self.mac)},
            # This is duplicate but otherwise via_device can't work
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Shelly",
            model=aioshelly.MODEL_NAMES.get(self.model, self.model),
            sw_version=sw_version,
        )
        self.device_id = entry.id
        self.device.subscribe_updates(self.async_set_updated_data)

    def shutdown(self):
        """Shutdown the wrapper."""
        if self.device:
            self.device.shutdown()
            self._async_remove_device_updates_handler()
            self.device = None

    @callback
    def _handle_ha_stop(self, _):
        """Handle Safegate Pro stopping."""
        _LOGGER.debug("Stopping ShellyDeviceWrapper for %s", self.name)
        self.shutdown()


class ShellyDeviceRestWrapper(update_coordinator.DataUpdateCoordinator):
    """Rest Wrapper for a Shelly device with Safegate Pro specific functions."""

    def __init__(self, hass, device: aioshelly.Device):
        """Initialize the Shelly device wrapper."""
        if (
            device.settings["device"]["type"]
            in BATTERY_DEVICES_WITH_PERMANENT_CONNECTION
        ):
            update_interval = (
                SLEEP_PERIOD_MULTIPLIER * device.settings["coiot"]["update_period"]
            )
        else:
            update_interval = REST_SENSORS_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=get_device_name(device),
            update_interval=timedelta(seconds=update_interval),
        )
        self.device = device

    async def _async_update_data(self):
        """Fetch data."""
        try:
            async with async_timeout.timeout(AIOSHELLY_DEVICE_TIMEOUT_SEC):
                _LOGGER.debug("REST update for %s", self.name)
                return await self.device.update_status()
        except OSError as err:
            raise update_coordinator.UpdateFailed("Error fetching data") from err

    @property
    def mac(self):
        """Mac address of the device."""
        return self.device.settings["device"]["mac"]


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    device = hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id].get(DEVICE)
    if device is not None:
        # If device is present, device wrapper is not setup yet
        device.shutdown()
        return True

    platforms = SLEEPING_PLATFORMS

    if not entry.data.get("sleep_period"):
        hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][REST] = None
        platforms = PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        hass.data[DOMAIN][DATA_CONFIG_ENTRY][entry.entry_id][COAP].shutdown()
        hass.data[DOMAIN][DATA_CONFIG_ENTRY].pop(entry.entry_id)

    return unload_ok
