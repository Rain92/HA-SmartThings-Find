# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@.claude-private/CLAUDE.md

## Repository status

This is a fork of `Vedeneb/HA-SmartThings-Find` (now archived by its original author) and is actively
maintained here. `origin` points at this fork (`herisanuadrian/HA-SmartThings-Find`); `upstream`
still points at the original for reference. There is no CI beyond HACS structural validation — no
test suite, linter, or build step exists in this repo.

## What this is

A Home Assistant custom integration (`custom_components/smartthings_find`) that adds Samsung
SmartThings Find support (SmartTags, phones, tablets, watches, earbuds) to Home Assistant via
`device_tracker`, `sensor` (battery), and `button` (ring) entities. It works by reverse-engineered
calls to Samsung's undocumented SmartThings Find web API — there is no official API, so behavior is
fragile and can break whenever Samsung changes their site.

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

- **`utils.py`** — the core of the integration. Contains every HTTP call to Samsung's account and
  SmartThings Find backends, all URL constants, and is the first place to look when API behavior
  breaks. Key functions:
  - `do_login_stage_one` / `do_login_stage_two` — implement a two-stage QR-code login that simulates
    the Samsung account web sign-in flow (state param → QR code page → poll for scan → follow
    redirects → extract `JSESSIONID` cookie). This is brittle by nature: it depends on regex-matching
    URLs embedded in Samsung's HTML/JS responses (e.g. `https://signin.samsung.com/key/...`, the
    `window.location.href = '...'` redirect), so a Samsung markup change breaks login here first.
  - `fetch_csrf`, `get_devices`, `get_device_location` — authenticated calls made after login,
    using the stored `JSESSIONID` cookie and a per-entry `_csrf` token stashed in
    `hass.data[DOMAIN][entry_id]["_csrf"]`.
  - Auth failures during normal operation raise `ConfigEntryAuthFailed`, which triggers HA's
    reauth flow automatically.

- **`config_flow.py`** — drives the two-stage QR login as an async HA config flow
  (`async_step_user` → stage 1 → `async_step_auth_stage_two` → stage 2 → `async_step_finish`),
  using `async_show_progress`/`async_show_progress_done` to run each stage as a background task
  while showing the QR code to the user. Also implements reauth (`async_step_reauth*`) and the
  options flow (`SmartThingsFindOptionsFlowHandler`) for update interval and active/passive mode
  per device class. Session state during the flow (partial QR login progress) is held on the
  config flow instance itself (`self.session`, `self.qr_url`, `self.jsessionid`), not in `hass.data`.

- **`__init__.py`** — `async_setup_entry` restores the session from the stored `JSESSIONID` cookie,
  fetches the CSRF token (raises `ConfigEntryAuthFailed` if that fails — this is the sole auth check
  at startup), loads the device list, and creates `SmartThingsFindCoordinator`
  (a `DataUpdateCoordinator`) that polls `get_device_location` for every device on `update_interval`
  seconds. Devices disabled in the HA device registry are skipped when building the device list.

- **`device_tracker.py`**, **`sensor.py`**, **`button.py`** — thin entity platforms that read from
  the shared coordinator's data (keyed by `dvceID`) and, for `button.py`, trigger a location/ring
  request through the same `utils.py` functions.

- **`const.py`** — all config keys, defaults (e.g. `CONF_UPDATE_INTERVAL_DEFAULT = 120`), and the
  `BATTERY_LEVELS` mapping (STF reports coarse battery buckets like `FULL`/`MEDIUM`/`LOW`/`VERY_LOW`
  rather than a percentage; `sensor.py` maps these to numeric values).

## Key behavioral notes

- **Active vs. passive mode** (`CONF_ACTIVE_MODE_SMARTTAGS`, `CONF_ACTIVE_MODE_OTHERS`, configurable
  per device class via the options flow): active mode issues a live "request location update" to STF,
  which can wake the paired phone/tablet and drain battery; passive mode only reads the last location
  STF already has. Default: active for SmartTags, passive for other device types.
- Ringing a device depends on a nearby Galaxy phone/tablet relaying via Bluetooth — if it doesn't work
  on the official SmartThings Find website, it cannot work through this integration either.
- Session lifetime for the `JSESSIONID` is unknown/undocumented by Samsung; expiry is handled via
  HA's reauth flow rather than a fixed TTL.
