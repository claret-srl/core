"""Support for AirVisual air quality sensors."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_STATE,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SHOW_ON_MAP,
    CONF_STATE,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_HUMIDITY,
    DEVICE_CLASS_TEMPERATURE,
    PERCENTAGE,
    TEMP_CELSIUS,
)
from homeassistant.core import callback

from . import AirVisualEntity
from .const import (
    CONF_CITY,
    CONF_COUNTRY,
    CONF_INTEGRATION_TYPE,
    DATA_COORDINATOR,
    DOMAIN,
    INTEGRATION_TYPE_GEOGRAPHY_COORDS,
    INTEGRATION_TYPE_GEOGRAPHY_NAME,
)

ATTR_CITY = "city"
ATTR_COUNTRY = "country"
ATTR_POLLUTANT_SYMBOL = "pollutant_symbol"
ATTR_POLLUTANT_UNIT = "pollutant_unit"
ATTR_REGION = "region"

SENSOR_KIND_LEVEL = "air_pollution_level"
SENSOR_KIND_AQI = "air_quality_index"
SENSOR_KIND_POLLUTANT = "main_pollutant"
SENSOR_KIND_BATTERY_LEVEL = "battery_level"
SENSOR_KIND_HUMIDITY = "humidity"
SENSOR_KIND_TEMPERATURE = "temperature"

GEOGRAPHY_SENSORS = [
    (SENSOR_KIND_LEVEL, "Air Pollution Level", "mdi:gauge", None),
    (SENSOR_KIND_AQI, "Air Quality Index", "mdi:chart-line", "AQI"),
    (SENSOR_KIND_POLLUTANT, "Main Pollutant", "mdi:chemical-weapon", None),
]
GEOGRAPHY_SENSOR_LOCALES = {"cn": "Chinese", "us": "U.S."}

NODE_PRO_SENSORS = [
    (SENSOR_KIND_BATTERY_LEVEL, "Battery", DEVICE_CLASS_BATTERY, PERCENTAGE),
    (SENSOR_KIND_HUMIDITY, "Humidity", DEVICE_CLASS_HUMIDITY, PERCENTAGE),
    (SENSOR_KIND_TEMPERATURE, "Temperature", DEVICE_CLASS_TEMPERATURE, TEMP_CELSIUS),
]

POLLUTANT_LABELS = {
    "co": "Carbon Monoxide",
    "n2": "Nitrogen Dioxide",
    "o3": "Ozone",
    "p1": "PM10",
    "p2": "PM2.5",
    "s2": "Sulfur Dioxide",
}

POLLUTANT_LEVELS = {
    (0, 50): ("Good", "mdi:emoticon-excited"),
    (51, 100): ("Moderate", "mdi:emoticon-happy"),
    (101, 150): ("Unhealthy for sensitive groups", "mdi:emoticon-neutral"),
    (151, 200): ("Unhealthy", "mdi:emoticon-sad"),
    (201, 300): ("Very unhealthy", "mdi:emoticon-dead"),
    (301, 1000): ("Hazardous", "mdi:biohazard"),
}

POLLUTANT_UNITS = {
    "co": CONCENTRATION_PARTS_PER_MILLION,
    "n2": CONCENTRATION_PARTS_PER_BILLION,
    "o3": CONCENTRATION_PARTS_PER_BILLION,
    "p1": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    "p2": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    "s2": CONCENTRATION_PARTS_PER_BILLION,
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up AirVisual sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR][config_entry.entry_id]

    if config_entry.data[CONF_INTEGRATION_TYPE] in [
        INTEGRATION_TYPE_GEOGRAPHY_COORDS,
        INTEGRATION_TYPE_GEOGRAPHY_NAME,
    ]:
        sensors = [
            AirVisualGeographySensor(
                coordinator,
                config_entry,
                kind,
                name,
                icon,
                unit,
                locale,
            )
            for locale in GEOGRAPHY_SENSOR_LOCALES
            for kind, name, icon, unit in GEOGRAPHY_SENSORS
        ]
    else:
        sensors = [
            AirVisualNodeProSensor(coordinator, kind, name, device_class, unit)
            for kind, name, device_class, unit in NODE_PRO_SENSORS
        ]

    async_add_entities(sensors, True)


class AirVisualGeographySensor(AirVisualEntity, SensorEntity):
    """Define an AirVisual sensor related to geography data via the Cloud API."""

    def __init__(self, coordinator, config_entry, kind, name, icon, unit, locale):
        """Initialize."""
        super().__init__(coordinator)

        self._attrs.update(
            {
                ATTR_CITY: config_entry.data.get(CONF_CITY),
                ATTR_STATE: config_entry.data.get(CONF_STATE),
                ATTR_COUNTRY: config_entry.data.get(CONF_COUNTRY),
            }
        )
        self._config_entry = config_entry
        self._kind = kind
        self._locale = locale
        self._name = name
        self._state = None

        self._attr_icon = icon
        self._attr_unit_of_measurement = unit

    @property
    def available(self):
        """Return True if entity is available."""
        try:
            return self.coordinator.last_update_success and bool(
                self.coordinator.data["current"]["pollution"]
            )
        except KeyError:
            return False

    @property
    def name(self):
        """Return the name."""
        return f"{GEOGRAPHY_SENSOR_LOCALES[self._locale]} {self._name}"

    @property
    def state(self):
        """Return the state."""
        return self._state

    @property
    def unique_id(self):
        """Return a unique, Safegate Pro friendly identifier for this entity."""
        return f"{self._config_entry.unique_id}_{self._locale}_{self._kind}"

    @callback
    def update_from_latest_data(self):
        """Update the entity from the latest data."""
        try:
            data = self.coordinator.data["current"]["pollution"]
        except KeyError:
            return

        if self._kind == SENSOR_KIND_LEVEL:
            aqi = data[f"aqi{self._locale}"]
            [(self._state, self._attr_icon)] = [
                (name, icon)
                for (floor, ceiling), (name, icon) in POLLUTANT_LEVELS.items()
                if floor <= aqi <= ceiling
            ]
        elif self._kind == SENSOR_KIND_AQI:
            self._state = data[f"aqi{self._locale}"]
        elif self._kind == SENSOR_KIND_POLLUTANT:
            symbol = data[f"main{self._locale}"]
            self._state = POLLUTANT_LABELS[symbol]
            self._attrs.update(
                {
                    ATTR_POLLUTANT_SYMBOL: symbol,
                    ATTR_POLLUTANT_UNIT: POLLUTANT_UNITS[symbol],
                }
            )

        # Displaying the geography on the map relies upon putting the latitude/longitude
        # in the entity attributes with "latitude" and "longitude" as the keys.
        # Conversely, we can hide the location on the map by using other keys, like
        # "lati" and "long".
        #
        # We use any coordinates in the config entry and, in the case of a geography by
        # name, we fall back to the latitude longitude provided in the coordinator data:
        latitude = self._config_entry.data.get(
            CONF_LATITUDE,
            self.coordinator.data["location"]["coordinates"][1],
        )
        longitude = self._config_entry.data.get(
            CONF_LONGITUDE,
            self.coordinator.data["location"]["coordinates"][0],
        )

        if self._config_entry.options[CONF_SHOW_ON_MAP]:
            self._attrs[ATTR_LATITUDE] = latitude
            self._attrs[ATTR_LONGITUDE] = longitude
            self._attrs.pop("lati", None)
            self._attrs.pop("long", None)
        else:
            self._attrs["lati"] = latitude
            self._attrs["long"] = longitude
            self._attrs.pop(ATTR_LATITUDE, None)
            self._attrs.pop(ATTR_LONGITUDE, None)


class AirVisualNodeProSensor(AirVisualEntity, SensorEntity):
    """Define an AirVisual sensor related to a Node/Pro unit."""

    def __init__(self, coordinator, kind, name, device_class, unit):
        """Initialize."""
        super().__init__(coordinator)

        self._kind = kind
        self._name = name
        self._state = None

        self._attr_device_class = device_class
        self._attr_unit_of_measurement = unit

    @property
    def device_info(self):
        """Return device registry information for this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.data["serial_number"])},
            "name": self.coordinator.data["settings"]["node_name"],
            "manufacturer": "AirVisual",
            "model": f'{self.coordinator.data["status"]["model"]}',
            "sw_version": (
                f'Version {self.coordinator.data["status"]["system_version"]}'
                f'{self.coordinator.data["status"]["app_version"]}'
            ),
        }

    @property
    def name(self):
        """Return the name."""
        node_name = self.coordinator.data["settings"]["node_name"]
        return f"{node_name} Node/Pro: {self._name}"

    @property
    def state(self):
        """Return the state."""
        return self._state

    @property
    def unique_id(self):
        """Return a unique, Safegate Pro friendly identifier for this entity."""
        return f"{self.coordinator.data['serial_number']}_{self._kind}"

    @callback
    def update_from_latest_data(self):
        """Update the entity from the latest data."""
        if self._kind == SENSOR_KIND_BATTERY_LEVEL:
            self._state = self.coordinator.data["status"]["battery"]
        elif self._kind == SENSOR_KIND_HUMIDITY:
            self._state = self.coordinator.data["measurements"].get("humidity")
        elif self._kind == SENSOR_KIND_TEMPERATURE:
            self._state = self.coordinator.data["measurements"].get("temperature_C")
