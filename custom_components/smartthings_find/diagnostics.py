"""Diagnostics support for SmartThings Find.

Samsung's API is undocumented and the payloads change without notice, so the raw
device and location responses are the only way to find out what a given account
actually exposes. Download this from the device page ("Download diagnostics") and
the raw JSON comes with it, minus credentials and coordinates.

This is a plain dump of what the integration already holds - it issues no requests
of its own.
"""
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_IOT_ACCESS_TOKEN,
    CONF_IOT_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USER_EMAIL,
    CONF_AUTH_SERVER_URL,
    CONF_DEVICE_ID,
    CONF_ST_USER_UUID,
    CONF_INSTALLED_APP_ID,
)

TO_REDACT = {
    # Credentials and account identity
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_IOT_ACCESS_TOKEN,
    CONF_IOT_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USER_EMAIL,
    CONF_AUTH_SERVER_URL,
    CONF_DEVICE_ID,
    CONF_ST_USER_UUID,
    CONF_INSTALLED_APP_ID,
    "owner_id",
    "sa_guid",
    "stOwnerId",
    "ownerId",
    "saGuid",
    "userId",
    "members",
    # Anything that gives away where the user is
    "latitude",
    "longitude",
    "google_maps_url",
    "geolocations",
    "geoLocations",
    "geoLocation",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) or {}
    devices = store.get("devices") or []
    coordinator = store.get("coordinator")

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        # 'raw_device' is the untouched /devices entry for each tag. This is what to
        # look at when checking whether the API exposes a setting the integration
        # does not support yet.
        "devices": [
            async_redact_data(device.get("data") or {}, TO_REDACT)
            for device in devices
        ],
        "coordinator_data": async_redact_data(
            dict(coordinator.data or {}) if coordinator else {}, TO_REDACT
        ),
    }
