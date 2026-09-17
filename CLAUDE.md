# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repo is the fork `Rain92/HA-SmartThings-Find` (`origin`). Its ancestry is
`Vedeneb/HA-SmartThings-Find` (the original, archived by its author) → `herisanuadrian/HA-SmartThings-Find`
→ here. Extra remotes for reference: `upstream` → Vedeneb, `herisanuadrian` → the intermediate fork,
`pixelshober` → `PixelShober/HA-SmartThings-Find`, whose OAuth2/PKCE login rework was merged in to
replace the old JSESSIONID web-login scraping after Samsung redesigned their account login page and
broke it. There is no CI beyond HACS structural validation — no test suite, linter, or build step
exists in this repo.

## What this is

A Home Assistant custom integration (`custom_components/smartthings_find`) that adds Samsung
SmartThings Find support (SmartTags, phones, tablets, watches, earbuds) to Home Assistant via
`device_tracker`, `sensor` (battery + coordinates), and `switch` (optimistic ring toggle) entities. It works by reverse-engineered calls to Samsung's undocumented SmartThings Find / SmartThings
Cloud APIs — there is no official public API, so behavior is fragile and can break whenever Samsung
changes their backend.

## Commands

There is no build, lint, or test tooling in this repo. The only automated check is
`.github/workflows/validate.yaml`, which runs the `hacs/action` structural validator against the
`custom_components/smartthings_find` integration on push/PR. Development is verified manually by
installing the integration into a real Home Assistant instance (via HACS custom repo or by copying
`custom_components/smartthings_find` into HA's `config/custom_components/`) and exercising the config
flow / entities live. Enable debug logs via HA's `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smartthings_find: debug
```

## Architecture

All logic lives in `custom_components/smartthings_find/`:

- **`utils.py`** — the core of the integration and the first place to look when API behavior breaks.
  Roughly two halves:
  - **Login** (`do_login_stage_one` / `do_login_stage_two`): a PKCE-based OAuth2 flow that mimics
    Samsung's native mobile apps rather than the web login page. Stage one fetches Samsung's
    entry-point config, builds a `svcParam` JSON payload (client id, device identity, PKCE
    `code_challenge`, etc.), RSA-encrypts it with the server-provided public key
    (`cryptography.hazmat`), and returns a `signInURI` for the user to open in a browser. That login
    completes with a redirect to an `ms-app://...` URI (never actually opened) which the user must
    copy out of devtools and paste back in — stage two parses `code`/`auth_server_url`/`state` out of
    that URL (decrypting them if wrapped), then exchanges the code at
    `{auth_server_url}/auth/oauth2/authenticate` → `/v2/authorize` → `/token` for both a SmartThings
    Find token and a separate OneConnect/IoT token (`CLIENT_ID_FIND` vs `CLIENT_ID_ONECONNECT`).
    This flow was adopted from `PixelShober/HA-SmartThings-Find` after Samsung's account web login
    (the old JSESSIONID/QR-code scraping approach) broke.
  - **Authenticated calls** (`get_devices`, `get_device_location`, `ring_device`,
    `stop_ring_device`, etc.): use `authenticated_request`, which attaches
    `X-Sec-Sa-Authtoken` from the stored access token and, on a 401/403, transparently calls
    `refresh_find_token`/`refresh_iot_token` (via `_refresh_token`) and retries once before raising
    `ConfigEntryAuthFailed` (which triggers HA's reauth flow). Devices are discovered through the
    SmartThings *installed app* API (`_get_installed_app_id`, `_execute_installed_app`,
    `_build_installed_apps_request`) rather than the old `getDeviceList.do` endpoint, and location
    `get_device_location` picks the most recently updated entry out of the `geolocations` list (the
  API can return several, one per reporting phone). Legacy location
  data is picked out of a list of device "operations" by `extract_best_location` (prefers the
    newest `LOCATION`/`LASTLOC`/`OFFLINE_LOC` entry with a valid timestamp, skipping encrypted or
    dateless ones).

- **`config_flow.py`** — drives the OAuth2 flow as a two-step HA config flow: `async_step_user` calls
  stage one and shows the generated `signInURI`; `async_step_auth_code` collects the pasted-back
  `ms-app://...` redirect URL from the user and calls stage two, storing the resulting access/refresh
  token pairs (`CONF_ACCESS_TOKEN`, `CONF_REFRESH_TOKEN`, `CONF_IOT_ACCESS_TOKEN`,
  `CONF_IOT_REFRESH_TOKEN`), `CONF_USER_ID`, `CONF_AUTH_SERVER_URL`, and `CONF_DEVICE_ID` on the
  config entry. Also implements reauth (`async_step_reauth`) and the options flow
  (`SmartThingsFindOptionsFlowHandler`) for update interval and active/passive mode per device class.
  In-progress PKCE state (`state`, `code_verifier`, `device_id`) is stashed in
  `hass.data[DOMAIN]["auth_data"]` between stage one and stage two, not on the flow instance.

- **`__init__.py`** — `async_setup_entry` loads the stored tokens, loads the device list, and creates
  `SmartThingsFindCoordinator` (a `DataUpdateCoordinator`) that polls `get_device_location` for every
  device on `update_interval` seconds. Devices disabled in the HA device registry are skipped when
  building the device list.

- **`device_tracker.py`**, **`sensor.py`**, **`switch.py`** — thin entity platforms
  reading from the shared coordinator's data and, for `switch.py`, triggering
  ring/stop-ring requests through `utils.py`. `sensor.py` holds both `DeviceBatterySensor`
  and `DeviceLocationSensor`; the latter exists because a `device_tracker` state can only
  ever be a zone (`home`/`not_home`/zone name), so raw coordinates and a `google_maps_url`
  attribute (built by `google_maps_url()` in `utils.py`) are surfaced on a sensor instead.
  `DeviceMapsLinkSensor` exposes the same URL as a standalone `EntityCategory.DIAGNOSTIC` entity.
  Both are only created for `is_tracker` devices. For a clickable link, the coordinator also calls
  `update_device_maps_link()` after each poll, which rewrites the device registry entry's
  `configuration_url` (the device page's "Visit" link) to the current Maps URL - `get_devices`
  therefore sets `configuration_url=None` for trackers and keeps the STF website link only for
  non-trackers. The write is skipped when the URL is unchanged, so the registry is not re-saved
  on every poll. The `switch.py` ring toggle is optimistic (auto-turns
  off after `RING_TIMEOUT_SECONDS`) because the OAuth API doesn't expose actual ring status.

- **`diagnostics.py`** — `async_get_config_entry_diagnostics` dumps the config entry, the built
  device list (including each tag's untouched `raw_device` payload) and the coordinator data, with
  tokens, account identifiers and coordinates redacted via `TO_REDACT`. This is the fastest way to
  see what a given account's API actually returns. It issues no requests of its own — it only dumps
  state the integration already holds.

- **`binary_sensor.py`** — `DevicePowerSavingSensor`, the tag's power saving mode
  ("Energiesparmodus"), read from `bleD2D.metadata.activeMode.mode` via
  `get_device_ble_metadata()` / `get_power_saving_state()` in `utils.py`. It is a binary_sensor
  and not a switch because only the read path is confirmed. The comment above
  `get_device_ble_metadata()` records what was ruled out — the chaser per-tag endpoints are all
  403/405, and a re-signed app cannot be used to capture the write because Samsung rejects it with
  `AUT_1708`. Do not re-run that investigation. The coordinator fetches the metadata blob per
  tracker on each poll and stores it under `ble_metadata`.

- **`const.py`** — all config keys, Samsung client IDs/scopes (`CLIENT_ID_FIND`, `CLIENT_ID_AUTH`,
  `CLIENT_ID_ONECONNECT`, `SCOPE_FIND`, `SCOPE_AUTH`), defaults (e.g.
  `CONF_UPDATE_INTERVAL_DEFAULT = 120`, `RING_TIMEOUT_SECONDS = 120`), and the `BATTERY_LEVELS`
  mapping (STF reports coarse battery buckets like `FULL`/`MEDIUM`/`LOW`/`VERY_LOW` rather than a
  percentage; `sensor.py` maps these to numeric values).

## Key behavioral notes

- **Active vs. passive mode** (`CONF_ACTIVE_MODE_SMARTTAGS`, `CONF_ACTIVE_MODE_OTHERS`, configurable
  per device class via the options flow): active mode issues a live "request location update", which
  can wake the paired phone/tablet and drain battery; passive mode only reads the last location
  already reported. Default: active for SmartTags, passive for other device types.
- Ringing a device depends on a nearby Galaxy phone/tablet relaying via Bluetooth — if it doesn't work
  on the official SmartThings Find website, it cannot work through this integration either.
- Login requires a manual step the user can't fully automate: after signing in, Samsung redirects to
  an `ms-app://...` URI that the browser can't open; the user has to grab that exact URL from devtools
  (Network or Console tab) and paste it into the HA config flow.
- Renames made in the Samsung app propagate on setup: `get_devices` renames the device registry
  entry and `_sync_entity_names` renames each entity's `original_name` using a per-entity suffix
  table. Both bail out if the user named the device/entity themselves (`name_by_user` / `entry.name`).
  Because `get_devices` only runs at setup, a rename shows up after a restart or reload, not on the
  next poll.
- Access/refresh tokens are refreshed automatically on 401/403 (see `authenticated_request`); a
  refresh failure raises `ConfigEntryAuthFailed`, surfacing HA's reauth flow rather than a silent
  failure.
