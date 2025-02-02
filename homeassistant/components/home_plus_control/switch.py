"""Legrand Home+ Control Switch Entity Module that uses the HomeAssistant DataUpdateCoordinator."""
from functools import partial

from homeassistant.components.switch import (
    DEVICE_CLASS_OUTLET,
    DEVICE_CLASS_SWITCH,
    SwitchEntity,
)
from homeassistant.core import callback
from homeassistant.helpers import dispatcher
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DISPATCHER_REMOVERS, DOMAIN, HW_TYPE, SIGNAL_ADD_ENTITIES


@callback
def add_switch_entities(new_unique_ids, coordinator, add_entities):
    """Add switch entities to the platform.

    Args:
        new_unique_ids (set): Unique identifiers of entities to be added to Safegate Pro.
        coordinator (DataUpdateCoordinator): Data coordinator of this platform.
        add_entities (function): Method called to add entities to Safegate Pro.
    """
    new_entities = []
    for uid in new_unique_ids:
        new_ent = HomeControlSwitchEntity(coordinator, uid)
        new_entities.append(new_ent)
    add_entities(new_entities)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Legrand Home+ Control Switch platform in HomeAssistant.

    Args:
        hass (HomeAssistant): HomeAssistant core object.
        config_entry (ConfigEntry): ConfigEntry object that configures this platform.
        async_add_entities (function): Function called to add entities of this platform.
    """
    partial_add_switch_entities = partial(
        add_switch_entities, add_entities=async_add_entities
    )
    # Connect the dispatcher for the switch platform
    hass.data[DOMAIN][config_entry.entry_id][DISPATCHER_REMOVERS].append(
        dispatcher.async_dispatcher_connect(
            hass, SIGNAL_ADD_ENTITIES, partial_add_switch_entities
        )
    )


class HomeControlSwitchEntity(CoordinatorEntity, SwitchEntity):
    """Entity that represents a Legrand Home+ Control switch.

    It extends the HomeAssistant-provided classes of the CoordinatorEntity and the SwitchEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass

    The SwitchEntity class provides the functionality of a ToggleEntity and additional power
    consumption methods and state attributes.
    """

    def __init__(self, coordinator, idx):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.idx = idx
        self.module = self.coordinator.data[self.idx]

    @property
    def name(self):
        """Name of the device."""
        return self.module.name

    @property
    def unique_id(self):
        """ID (unique) of the device."""
        return self.idx

    @property
    def device_info(self):
        """Device information."""
        return {
            "identifiers": {
                # Unique identifiers within the domain
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
            "manufacturer": "Legrand",
            "model": HW_TYPE.get(self.module.hw_type),
            "sw_version": self.module.fw,
        }

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        if self.module.device == "plug":
            return DEVICE_CLASS_OUTLET
        return DEVICE_CLASS_SWITCH

    @property
    def available(self) -> bool:
        """Return if entity is available.

        This is the case when the coordinator is able to update the data successfully
        AND the switch entity is reachable.

        This method overrides the one of the CoordinatorEntity
        """
        return self.coordinator.last_update_success and self.module.reachable

    @property
    def is_on(self):
        """Return entity state."""
        return self.module.status == "on"

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        # Do the turning on.
        await self.module.turn_on()
        # Update the data
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.module.turn_off()
        # Update the data
        await self.coordinator.async_request_refresh()
