"""Sensor for the CityBikes data."""

from __future__ import annotations
from functools import partial
import logging
import voluptuous as vol

import citybikes

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorEntity,
)
from homeassistant.const import (
    ATTR_ID,
    ATTR_LATITUDE,
    ATTR_LOCATION,
    ATTR_LONGITUDE,
    ATTR_NAME,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_RADIUS,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import location
from homeassistant.util.unit_conversion import DistanceConverter
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

_LOGGER = logging.getLogger(__name__)

ATTR_EMPTY_SLOTS = "empty_slots"
ATTR_EXTRA = "extra"
ATTR_FREE_BIKES = "free_bikes"
ATTR_NETWORK = "network"
ATTR_NETWORKS_LIST = "networks"
ATTR_STATIONS_LIST = "stations"
ATTR_TIMESTAMP = "timestamp"
ATTR_EBIKES = "ebikes"
ATTR_UID = "uid"

CONF_NETWORK = "network"
CONF_STATIONS_LIST = "stations"

PLATFORM = "citybikes"

MONITORED_NETWORKS = "monitored-networks"

CITYBIKES_ATTRIBUTION = (
    "Information provided by the CityBikes Project (https://citybik.es/#about)"
)

CITYBIKES_NETWORKS = "citybikes_networks"

PLATFORM_SCHEMA = vol.All(
    cv.has_at_least_one_key(CONF_RADIUS, CONF_STATIONS_LIST),
    SENSOR_PLATFORM_SCHEMA.extend(
        {
            vol.Optional(CONF_NAME, default=""): cv.string,
            vol.Optional(CONF_NETWORK): cv.string,
            vol.Inclusive(CONF_LATITUDE, "coordinates"): cv.latitude,
            vol.Inclusive(CONF_LONGITUDE, "coordinates"): cv.longitude,
            vol.Optional(CONF_RADIUS, "station_filter"): cv.positive_int,
            vol.Optional(CONF_STATIONS_LIST, "station_filter"): vol.All(
                cv.ensure_list, vol.Length(min=1), [cv.string]
            ),
        }
    ),
)

class CityBikesRequestError(Exception):
    """Error to indicate a CityBikes API request has failed."""


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the CityBikes platform."""
    if PLATFORM not in hass.data:
        hass.data[PLATFORM] = {MONITORED_NETWORKS: {}}

    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    network_id = config.get(CONF_NETWORK)
    stations_list = set(config.get(CONF_STATIONS_LIST, []))
    radius = config.get(CONF_RADIUS, 0)
    name = config[CONF_NAME]
    if hass.config.units is US_CUSTOMARY_SYSTEM:
        radius = DistanceConverter.convert(
            radius, UnitOfLength.FEET, UnitOfLength.METERS
        )

    client = citybikes.Client()

    # TODO: implement location lookup
    try:
        network = await hass.async_add_executor_job(
            partial(citybikes.Network, client, uid=network_id)
        )
    except Exception as e:
        _LOGGER.error("Failed to fetch data: %s", e)
        return

    sensors = []
    for station in network['stations']:
        if station['id'] in stations_list:
            sensors.append(CityBikesStation(client, network_id, station))

    async_add_entities(sensors, True)


class CityBikesStation(SensorEntity):
    """Representation of a CityBikes Station."""

    _attr_attribution = CITYBIKES_ATTRIBUTION
    _attr_native_unit_of_measurement = "bikes"
    _attr_icon = "mdi:bike"

    def __init__(self, client, network_id, station):
        """Initialize the sensor."""
        self._client = client
        self._network_id = network_id
        self._attr_name = station.get(ATTR_NAME)
        self._station = station
        self._attr_unique_id = f"{network_id}_{station.get(ATTR_ID)}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._station.get(ATTR_FREE_BIKES)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            ATTR_EMPTY_SLOTS: self._station.get(ATTR_EMPTY_SLOTS),
            ATTR_EBIKES: self._station.get(ATTR_EXTRA, {}).get(ATTR_EBIKES),
            ATTR_LATITUDE: self._station.get(ATTR_LATITUDE),
            ATTR_LONGITUDE: self._station.get(ATTR_LONGITUDE),
            ATTR_UID: self._station.get(ATTR_EXTRA, {}).get(ATTR_UID),
            ATTR_TIMESTAMP: self._station.get(ATTR_TIMESTAMP),
        }

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            network = await self.hass.async_add_executor_job(
                partial(citybikes.Network, self._client, uid=self._network_id)
            )
            for station in network.stations:
              if station.get(ATTR_ID) == self._station.get(ATTR_ID):
                  self._station = station
                  break
        except Exception as e:
            _LOGGER.error("Failed to update data: %s", e)
            raise PlatformNotReady from e
