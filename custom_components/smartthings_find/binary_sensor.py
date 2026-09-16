import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .utils import get_power_saving_state

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up SmartThings Find binary sensor entities."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for device in devices:
        if device['data'].get("is_tracker"):
            entities += [DevicePowerSavingSensor(hass, coordinator, device)]
    async_add_entities(entities)


class DevicePowerSavingSensor(BinarySensorEntity):
    """The tag's power saving mode ("Energiesparmodus"), read-only.

    Read from bleD2D.metadata.activeMode.mode on the SmartThings device API. This is a
    binary_sensor rather than a switch because only the read path is confirmed - the
    setting is written through the SmartThings app's own tracker-metadata update, which
    is not reproducible from here yet.
    """

    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, hass: HomeAssistant, coordinator, device):
        """Initialize the sensor."""
        self.coordinator = coordinator
        device_id = device['data'].get("device_id")
        name = device['data'].get("name") or device_id or "SmartThings Find"
        self._attr_unique_id = f"stf_power_saving_{device_id}"
        self._attr_name = f"{name} Power Saving"
        self.hass = hass
        self.device = device['data']
        self.device_id = device_id
        self._attr_device_info = device['ha_dev_info']

    def _metadata(self) -> dict | None:
        tag_data = self.coordinator.data.get(self.device_id, {}) or {}
        return tag_data.get('ble_metadata')

    @property
    def available(self) -> bool:
        """Unavailable while the settings blob could not be read."""
        return get_power_saving_state(self._metadata()) is not None

    @property
    def is_on(self) -> bool | None:
        return get_power_saving_state(self._metadata())

    @property
    def extra_state_attributes(self):
        metadata = self._metadata() or {}
        firmware = metadata.get('firmware') or {}
        connection = metadata.get('lastKnownConnection') or {}
        vendor = metadata.get('vendor') or {}
        return {
            'firmware_version': firmware.get('version'),
            'model_name': vendor.get('modelName'),
            'battery_level': (metadata.get('battery') or {}).get('level'),
            'searching_status': metadata.get('searchingStatus'),
            'e2e_encryption': (metadata.get('e2eEncryption') or {}).get('enabled'),
            'remote_ring': (metadata.get('remoteRing') or {}).get('enabled'),
            'd2d_status': connection.get('d2dStatus'),
            'nearby': connection.get('nearby'),
        }
