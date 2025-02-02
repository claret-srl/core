"""Demo light platform that implements lights."""
from __future__ import annotations

import random

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_WHITE,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_RGBW,
    COLOR_MODE_RGBWW,
    COLOR_MODE_WHITE,
    SUPPORT_EFFECT,
    LightEntity,
)

from . import DOMAIN

LIGHT_COLORS = [(56, 86), (345, 75)]

LIGHT_EFFECT_LIST = ["rainbow", "none"]

LIGHT_TEMPS = [240, 380]

SUPPORT_DEMO = {COLOR_MODE_HS, COLOR_MODE_COLOR_TEMP}
SUPPORT_DEMO_HS_WHITE = {COLOR_MODE_HS, COLOR_MODE_WHITE}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the demo light platform."""
    async_add_entities(
        [
            DemoLight(
                available=True,
                effect_list=LIGHT_EFFECT_LIST,
                effect=LIGHT_EFFECT_LIST[0],
                name="Bed Light",
                state=False,
                unique_id="light_1",
            ),
            DemoLight(
                available=True,
                ct=LIGHT_TEMPS[1],
                name="Ceiling Lights",
                state=True,
                unique_id="light_2",
            ),
            DemoLight(
                available=True,
                hs_color=LIGHT_COLORS[1],
                name="Kitchen Lights",
                state=True,
                unique_id="light_3",
            ),
            DemoLight(
                available=True,
                ct=LIGHT_TEMPS[1],
                name="Office RGBW Lights",
                rgbw_color=(255, 0, 0, 255),
                state=True,
                supported_color_modes={COLOR_MODE_RGBW},
                unique_id="light_4",
            ),
            DemoLight(
                available=True,
                name="Living Room RGBWW Lights",
                rgbww_color=(255, 0, 0, 255, 0),
                state=True,
                supported_color_modes={COLOR_MODE_RGBWW},
                unique_id="light_5",
            ),
            DemoLight(
                available=True,
                name="Entrance Color + White Lights",
                hs_color=LIGHT_COLORS[1],
                state=True,
                supported_color_modes=SUPPORT_DEMO_HS_WHITE,
                unique_id="light_6",
            ),
        ]
    )


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Demo config entry."""
    await async_setup_platform(hass, {}, async_add_entities)


class DemoLight(LightEntity):
    """Representation of a demo light."""

    def __init__(
        self,
        unique_id,
        name,
        state,
        available=False,
        brightness=180,
        ct=None,
        effect_list=None,
        effect=None,
        hs_color=None,
        rgbw_color=None,
        rgbww_color=None,
        supported_color_modes=None,
    ):
        """Initialize the light."""
        self._available = True
        self._brightness = brightness
        self._ct = ct or random.choice(LIGHT_TEMPS)
        self._effect = effect
        self._effect_list = effect_list
        self._features = 0
        self._hs_color = hs_color
        self._name = name
        self._rgbw_color = rgbw_color
        self._rgbww_color = rgbww_color
        self._state = state
        self._unique_id = unique_id
        if hs_color:
            self._color_mode = COLOR_MODE_HS
        elif rgbw_color:
            self._color_mode = COLOR_MODE_RGBW
        elif rgbww_color:
            self._color_mode = COLOR_MODE_RGBWW
        else:
            self._color_mode = COLOR_MODE_COLOR_TEMP
        if not supported_color_modes:
            supported_color_modes = SUPPORT_DEMO
        self._color_modes = supported_color_modes
        if self._effect_list is not None:
            self._features |= SUPPORT_EFFECT

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.unique_id)
            },
            "name": self.name,
        }

    @property
    def should_poll(self) -> bool:
        """No polling needed for a demo light."""
        return False

    @property
    def name(self) -> str:
        """Return the name of the light if any."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def available(self) -> bool:
        """Return availability."""
        # This demo light is always available, but well-behaving components
        # should implement this to inform Safegate Pro accordingly.
        return self._available

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        return self._color_mode

    @property
    def hs_color(self) -> tuple:
        """Return the hs color value."""
        return self._hs_color

    @property
    def rgbw_color(self) -> tuple:
        """Return the rgbw color value."""
        return self._rgbw_color

    @property
    def rgbww_color(self) -> tuple:
        """Return the rgbww color value."""
        return self._rgbww_color

    @property
    def color_temp(self) -> int:
        """Return the CT color temperature."""
        return self._ct

    @property
    def effect_list(self) -> list:
        """Return the list of supported effects."""
        return self._effect_list

    @property
    def effect(self) -> str:
        """Return the current effect."""
        return self._effect

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._state

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self._features

    @property
    def supported_color_modes(self) -> set | None:
        """Flag supported color modes."""
        return self._color_modes

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        self._state = True

        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_COLOR_TEMP in kwargs:
            self._color_mode = COLOR_MODE_COLOR_TEMP
            self._ct = kwargs[ATTR_COLOR_TEMP]

        if ATTR_EFFECT in kwargs:
            self._effect = kwargs[ATTR_EFFECT]

        if ATTR_HS_COLOR in kwargs:
            self._color_mode = COLOR_MODE_HS
            self._hs_color = kwargs[ATTR_HS_COLOR]

        if ATTR_RGBW_COLOR in kwargs:
            self._color_mode = COLOR_MODE_RGBW
            self._rgbw_color = kwargs[ATTR_RGBW_COLOR]

        if ATTR_RGBWW_COLOR in kwargs:
            self._color_mode = COLOR_MODE_RGBWW
            self._rgbww_color = kwargs[ATTR_RGBWW_COLOR]

        if ATTR_WHITE in kwargs:
            self._color_mode = COLOR_MODE_WHITE
            self._brightness = kwargs[ATTR_WHITE]

        # As we have disabled polling, we need to inform
        # Safegate Pro about updates in our state ourselves.
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        self._state = False

        # As we have disabled polling, we need to inform
        # Safegate Pro about updates in our state ourselves.
        self.async_write_ha_state()
