import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .utils import google_maps_url
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up SmartThings Find sensor entities."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for device in devices:
        entities += [DeviceBatterySensor(hass, coordinator, device)]
        # Only trackers ever report coordinates; other device classes would be
        # permanently unknown.
        if device['data'].get("is_tracker"):
            entities += [
                DeviceLocationSensor(hass, coordinator, device),
                DeviceMapsLinkSensor(hass, coordinator, device),
            ]
    async_add_entities(entities)


class DeviceBatterySensor(SensorEntity):
    """Representation of a Device battery sensor."""

    def __init__(self, hass: HomeAssistant, coordinator, device):
        """Initialize the sensor."""
        self.coordinator = coordinator
        device_id = device['data'].get("device_id")
        name = device['data'].get("name") or device_id or "SmartThings Find"
        self._attr_unique_id = f"stf_device_battery_{device_id}"
        self._attr_name = f"{name} Battery"
        self._state = None
        self.hass = hass
        self.device = device['data']
        self.device_id = device_id
        self._attr_device_info = device['ha_dev_info']
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self) -> bool:
        """
        Makes the entity show unavailable state if no data was received
        or there was an error during last update
        """
        tag_data = self.coordinator.data.get(self.device_id, {})
        if not tag_data:
            _LOGGER.info(f"battery sensor: tag_data none for '{self.name}'; rendering state unavailable")
            return False
        if not tag_data.get('update_success'):
            _LOGGER.info(f"Last update for battery sensor '{self.name}' failed; rendering state unavailable")
            return False
        return True
    
    @property
    def unit_of_measurement(self) -> str:
        return '%'
    
    @property
    def state(self):
        data = self.coordinator.data.get(self.device_id, {})
        return data.get('battery_level')


class DeviceLocationSensor(SensorEntity):
    """Exposes the raw coordinates of a device, plus a ready-made Google Maps link.

    The device_tracker entity can only ever have a zone as its state ('home',
    'not_home', ...), so the actual coordinates are surfaced here instead.
    """

    _attr_icon = "mdi:map-marker"

    def __init__(self, hass: HomeAssistant, coordinator, device):
        """Initialize the sensor."""
        self.coordinator = coordinator
        device_id = device['data'].get("device_id")
        name = device['data'].get("name") or device_id or "SmartThings Find"
        self._attr_unique_id = f"stf_device_location_{device_id}"
        self._attr_name = f"{name} Location"
        self.hass = hass
        self.device = device['data']
        self.device_id = device_id
        self._attr_device_info = device['ha_dev_info']

    def _used_loc(self) -> dict:
        tag_data = self.coordinator.data.get(self.device_id, {}) or {}
        if not tag_data.get('location_found'):
            return {}
        return tag_data.get('used_loc') or {}

    @property
    def available(self) -> bool:
        """Mirror the battery sensor: unavailable if the last update failed."""
        tag_data = self.coordinator.data.get(self.device_id, {})
        if not tag_data:
            _LOGGER.info(f"location sensor: tag_data none for '{self.name}'; rendering state unavailable")
            return False
        if not tag_data.get('update_success'):
            _LOGGER.info(f"Last update for location sensor '{self.name}' failed; rendering state unavailable")
            return False
        return True

    @property
    def native_value(self):
        used_loc = self._used_loc()
        latitude = used_loc.get('latitude')
        longitude = used_loc.get('longitude')
        if latitude is None or longitude is None:
            return None
        return f"{latitude}, {longitude}"

    @property
    def extra_state_attributes(self):
        used_loc = self._used_loc()
        latitude = used_loc.get('latitude')
        longitude = used_loc.get('longitude')
        return {
            'latitude': latitude,
            'longitude': longitude,
            'gps_accuracy': used_loc.get('gps_accuracy'),
            'last_seen': used_loc.get('gps_date'),
            'google_maps_url': google_maps_url(latitude, longitude),
        }


class DeviceMapsLinkSensor(SensorEntity):
    """Exposes the Google Maps link as an entity of its own.

    Listed under Diagnostic on the device page so the link is one click away
    instead of being buried in another entity's attributes.
    """

    _attr_icon = "mdi:map-search"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, coordinator, device):
        """Initialize the sensor."""
        self.coordinator = coordinator
        device_id = device['data'].get("device_id")
        name = device['data'].get("name") or device_id or "SmartThings Find"
        self._attr_unique_id = f"stf_device_maps_link_{device_id}"
        self._attr_name = f"{name} Maps Link"
        self.hass = hass
        self.device = device['data']
        self.device_id = device_id
        self._attr_device_info = device['ha_dev_info']

    @property
    def available(self) -> bool:
        tag_data = self.coordinator.data.get(self.device_id, {})
        return bool(tag_data) and bool(tag_data.get('update_success'))

    @property
    def native_value(self):
        tag_data = self.coordinator.data.get(self.device_id, {}) or {}
        if not tag_data.get('location_found'):
            return None
        used_loc = tag_data.get('used_loc') or {}
        url = google_maps_url(used_loc.get('latitude'), used_loc.get('longitude'))
        # A sensor state is capped at 255 characters; these URLs are ~70, but never
        # let an unexpected value break the whole entity.
        if url and len(url) > 255:
            return None
        return url
