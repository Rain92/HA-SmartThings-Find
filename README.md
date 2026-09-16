# SmartThings Find Integration for Home Assistant

This repository is maintained at [Rain92/HA-SmartThings-Find](https://github.com/Rain92/HA-SmartThings-Find). It continues the fork chain [Vedeneb/HA-SmartThings-Find](https://github.com/Vedeneb/HA-SmartThings-Find) (the original, archived by its author) → [herisanuadrian/HA-SmartThings-Find](https://github.com/herisanuadrian/HA-SmartThings-Find), and includes the OAuth 2.0/PKCE login rework from [PixelShober/HA-SmartThings-Find](https://github.com/PixelShober/HA-SmartThings-Find), which replaced the JSESSIONID web-login scraping that Samsung's account login redesign broke.

This integration adds support for devices from Samsung SmartThings Find. While intended mainly for Samsung SmartTags, it also works with other devices, such as phones, tablets, watches and earbuds.

Currently the integration creates these entities (trackers only):
* `device_tracker`: Shows the location of the tag/device.
* `sensor`: Represents the battery level of the tag/device (not supported for earbuds!)
* `sensor`: `<name> Location` - the raw coordinates as `latitude, longitude`, with
  `latitude`, `longitude`, `gps_accuracy`, `last_seen` and `google_maps_url` attributes.
* `sensor`: `<name> Maps Link` - the Google Maps URL as its own entity, listed under
  **Diagnostic** on the device page.
* `switch`: Optimistic ring toggle (auto turns off after 120s).
* `binary_sensor`: `<name> Power Saving` - the tag's power saving mode
  ("Energiesparmodus"), read-only. Carries firmware version, model, battery level,
  searching status, E2E encryption, remote ring and connection state as attributes.

This integration does **not** allow you to perform actions based on button presses on the SmartTag! There are other ways to do that.


## ⚠️ Warning/Disclaimer ⚠️

- **API Limitations**: Created by reverse engineering the SmartThings Find API, this integration might stop working at any time if changes occur on the SmartThings side.
- **Limited Testing**: The integration hasn't been thoroughly tested. If you encounter issues, please report them by creating an issue.
- **Feature Constraints**: The integration can only support features available on the [SmartThings Find website](https://smartthingsfind.samsung.com/). Ring stop is exposed for trackers, but support depends on the backend; if it fails the API will reject the command. The ring switch is optimistic because the ring status cannot be read from the OAuth API.

## Notes on authentication
This integration now uses a standard OAuth 2.0 flow with PKCE to authenticate with Samsung servers. This mirrors the authentication used by official Samsung apps, providing a persistent session that automatically refreshes. You no longer need to worry about manually re-authenticating or sessions expiring unexpectedly.

## Notes on the location

A Home Assistant `device_tracker` can only ever have a zone as its state, so the tracker entity
shows `home`/`not_home`/a zone name rather than coordinates. The coordinates are available as
attributes on that entity, and additionally as a dedicated `sensor.<name>_location` entity whose
state is `latitude, longitude`.

Both carry a `google_maps_url` attribute. For a link you can actually click, the device page's
**Visit** button is kept pointing at the device's current coordinates, so it opens Google Maps at
the device's position. You will find it at the bottom of the **Device info** card, the top-left card
on the device's page (Settings -> Devices & services -> Devices -> pick the device). It only appears
once a location has been received at least once. (This replaces the link to the SmartThings Find
website for tracker devices; other device types keep it.)

Attributes themselves are not clickable, so for a link at the top level of a dashboard, add a
Markdown card. This one lists every tag with a known position and needs no entity IDs - it picks up
new tags automatically and skips the ones that have not reported a location yet:

```yaml
type: markdown
title: SmartThings Find
content: |-
  {% for s in states.sensor
       | selectattr('attributes.google_maps_url', 'defined')
       | selectattr('attributes.google_maps_url', 'string')
       | sort(attribute='name') %}
  **[{{ s.name | replace(' Location', '') }}]({{ s.attributes.google_maps_url }})**
  {{ s.state }}{% if s.attributes.last_seen %} · seen {{ relative_time(s.attributes.last_seen) }} ago{% endif %}
  {% endfor %}
```

Renders as a clickable list:

> **[Schlüssel](#)**
> 52.520008, 13.404954 · seen 7 minutes ago

For a single tag, the short form is:

```yaml
type: markdown
content: >-
  [Open in Google Maps]({{ state_attr('sensor.schlussel_location', 'google_maps_url') }})
```

## Notes on power saving mode

The tag's power saving mode is exposed read-only, as a `binary_sensor`. It is read from
`bleD2D.metadata.activeMode.mode` on the SmartThings device API (`0` = normal, `1` = power
saving), which was confirmed by toggling the setting in the SmartThings app and diffing the
payload: that single field flips and nothing else does.

Writing it is not supported. The SmartThings app sets it through its own tracker-metadata
update, whose request body is not reproducible from the public API - `/chaser/trackers/{id}/metadata`
returns 403 for our token. The SmartThings *capability* values (`tag.uwbActivation` and the
other `tag.*` ones) are all `null` for this tag and do not move when the setting is toggled,
so they are not usable either.

## Renaming

Renaming a tag in the SmartThings app propagates to the Home Assistant device and its entities
the next time the integration loads (restart Home Assistant, or reload it from the integration
page). A name you set yourself in Home Assistant always wins and is never overwritten.

## Diagnostics

The device page's **Download diagnostics** button returns the raw, untouched API payload for your
tags (`raw_device`), which is the only way to tell what a given account actually exposes - Samsung's
API is undocumented and differs between tag generations and regions. Access tokens, account
identifiers and coordinates are redacted. This is the right thing to attach to a bug report.

It also includes `tracker_endpoint_probe`: a read-only GET against each per-tag endpoint of the
SmartThings "chaser" API (`metadata`, `searchingstatus`, `button/options`, `timer`, `category`,
`firmware`), recovered from the SmartThings app. The integration does not use these during normal
operation - they are probed only when you download diagnostics, and only with GET, so nothing on
the tag is changed. This is how to find out which per-tag settings your account actually exposes.

## Notes on connection to the devices
Being able to let a SmartTag ring depends on a phone/tablet nearby which forwards your request via Bluetooth. If your phone is not near your tag, you can't make it ring. The location should still update if any Galaxy device is nearby. 

If ringing your tag does not work, first try to let it ring from the [SmartThings Find website](https://smartthingsfind.samsung.com/). If it does not work from there, it can not work from Home Assistant too! Note that letting it ring with the SmartThings Mobile App is not the same as the website. Just because it does work in the App, does not mean it works on the web. So always use the web version to do your tests.

## Notes on active/passive mode

Starting with version 0.2.0, it is possible to configure whether to use the integration in an active or passive mode. In passive mode the integration only fetches the location from the server which was last reported to STF. In active mode the integration sends an actual "request location update" request. This will make the STF server try to connect to e.g. your phone, get the current location and send it back to the STF server from where the integration can then read it. This has quite a big impact on the devices battery and in some cases might also wake up the screen of the phone or tablet.

By default active mode is enabled for SmartTags but disabled for any other devices. You can change this behaviour on the integrations page by clicking on `Configure`. Here you can also set the update interval, which is set to 120 seconds by default.


## Installation Instructions

### Using HACS

1. Add this repository as a custom repository in HACS. Either by manually adding `https://github.com/Rain92/HA-SmartThings-Find` with category `integration` or simply click the following button:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Rain92&repository=HA-SmartThings-Find&category=integration)

2. Search for "SmartThings Find" in HACS and install the integration
3. Restart Home Assistant
4. Proceed to [Setup instructions](#setup-instructions)

### Manual install

1. Download the `custom_components/smartthings_find` directory to your Home Assistant configuration directory
2. Restart Home Assistant
3. Proceed to [Setup instructions](#setup-instructions)

## Setup Instructions

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=smartthings_find)

1. Go to the Integrations page  
2. Search for "SmartThings Find" (**do not confuse this with the built-in SmartThings integration!**)  
3. Follow the on-screen configuration wizard:
   - **Login**: Click the provided link to log in to your Samsung account.
   - **Redirect**: After logging in, the browser will try to open a `ms-app://...` link. Cancel the external app prompt if it appears.
   - **Copy URL**: Use Developer Tools (F12) and copy the full `ms-app://...` URL from Network or Console (not the visible error page URL).
   - **Paste**: Paste the copied URL back into the Home Assistant dialog.
4. The integration will verify the token and load your devices.

## Debugging

To enable debugging, you need to set the log level in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smartthings_find: debug
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributions

Contributions are welcome! Feel free to open issues or submit pull requests to help improve this integration.

## Support

For support, please create an issue on the GitHub repository.

## Disclaimer

This is a third-party integration and is not affiliated with or endorsed by Samsung or SmartThings.

## Credits

- **[tomskra](https://github.com/tomskra)** and **[Vedeneb](https://github.com/Vedeneb)** for the original integration work.
- **[herisanuadrian](https://github.com/herisanuadrian)** for keeping the fork alive after the original was archived.
- **[PixelShober](https://github.com/PixelShober)** for the OAuth 2.0/PKCE login rework this fork merges in.
- **[KieronQuinn](https://github.com/KieronQuinn)** for the [uTag](https://github.com/KieronQuinn/uTag) project and documenting the authentication protocol.
