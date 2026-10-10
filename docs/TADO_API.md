# Tado Hijack — API & Implementation Reference

> Code is truth. The library pin, rate-limit headers, classic hot-water
> overlay, Tado X timetable/AC routing, and the quota section were rechecked
> on 4 October 2026. The old "verified at 7166d36" stamp is retired; the
> rest of this file was not re-audited line by line.
> This document describes how the integration talks to the Tado APIs, which
> endpoints it uses, and why each layer exists. The public kritsel v2
> OpenAPI spec does not cover most of what follows.

---

# Part 1 — Foundations & HTTP Infrastructure

## 1. What Tado Hijack talks to

The integration is NOT a thin wrapper around one API. It talks to four distinct
Tado cloud surfaces plus local protocols:

| Surface | Host | Used for | Generation |
|---|---|---|---|
| Classic v2 API | my.tado.com/api/v2 | Zones, devices, overlays, presence, timetables | Tado Classic (V2/V3) |
| Energy Insights API | energy-insights.tado.com | Meter readings (EIQ) | All |
| Hops API | hops.tado.com | Rooms, devices, manual control, quick actions, hot water programmer, flow temperature | Tado X |
| OAuth2 | login.tado.com/oauth2 | Token + device authorization flow | All |
| Local HomeKit / Matter | (local network) | Heating setpoints, measured values | All (via device_linker) |

**Why so many?** Tado X homes still use the classic v2 API for presence
(/state, /presenceLock). Room state, manual control, and the weekly
schedule live on Hops. Classic homes never touch Hops. Tado X has no
activeTimetable.

## 2. Library stack

- tadoasync (manifest requires `tadoasync==0.2.3`): base classic client.
  Provides OAuth2/device-flow auth, session management, and the classic v2
  endpoint methods. We do NOT use its `_request` directly — see Section 4.
  Classic and Energy IQ send `HomeAssistant/0.2.2`
  (`TADO_USER_AGENT` / `TADO_VERSION_PATCH` in `const.py`).
  Hops sends `TadoHijack/1.0`.
- aiohttp / yarl for HTTP.
- pydantic (v2) for the self-built Tado X models (lib/tadox_models.py).

## 3. TadoHijackClient (helpers/client.py)

Subclasses tadoasync.Tado and makes two changes:

1. Constructor accepts proxy_url / proxy_token. With a proxy, that proxy
   terminates Tado auth and the handler does not send a bearer token.
   Without a proxy, the integration holds the refresh token and sends
   `Authorization: Bearer`.
2. _request() override: every call is routed through the global
   TadoRequestHandler singleton (obtained via lib.patches.get_handler())
   instead of tadoasync's own request logic.

The refresh POST lives in `TadoRequestHandler.refresh_auth`, which keeps the
response body. A rotated refresh token is passed to `persist_refresh_token`
and written to the config entry. Session reuse and the classic endpoint
methods stay on tadoasync (plus the patches from Part 2).

On top of the inherited tadoasync methods, the client adds custom methods
covering undocumented endpoints: bulk overlays, away configuration, dazzle,
early start, open window detection, identify, timetable blocks. Those are
detailed in Part 3.

## 4. TadoRequestHandler (helpers/tado_request_handler.py)

A global singleton that executes all classic/EIQ requests on behalf of
TadoHijackClient. Entry point:

    robust_request(instance, uri=None, endpoint=API_URL, data=None,
                   method=HttpMethod.GET, proxy_url=None, proxy_token=None) -> str

### 4.1 Why it exists (why we bypass tadoasync's _request)

- Browser mimicry: Tado's API rejects non-browser-like header combinations in some paths. The handler reproduces what the web frontend sends.
- Proxy support: tadoasync has no proxy concept.
- Rate-limit telemetry: captures quota headers on every response to feed the quota manager.
- Custom URL building (see Section 4.4).

### 4.2 Header construction (_build_headers)

- User-Agent: HomeAssistant/0.2.2 (constant TADO_USER_AGENT, derived from TADO_VERSION_PATCH).
- Authorization: Bearer <token> — only WITHOUT proxy (the proxy injects auth itself).
- Content-Type + Mime-Type: application/json;charset=UTF-8 — only on PUT. Browsers omit Content-Type on DELETE; Tado expects exactly that.

### 4.3 Authentication handling

- Non-proxy requests: calls instance._refresh_auth() before each request so the token is always fresh.
- Auth requests themselves (oauth/token, oauth2/device URIs) are detected and skip both refresh and bearer injection.
- Uses tadoasync private attributes: _refresh_auth, _access_token, _ensure_session, _request_timeout. Every access is wrapped in hasattr/getattr guards with warnings, so a tadoasync internals change degrades gracefully instead of crashing.

### 4.4 URL building quirk (_build_url)

The URL is assembled by string concatenation, not yarl join methods.
Reason: yarl percent-encodes ? when joining paths, which breaks Tado's query-string parsing (e.g. the bulk-overlay ?rooms=1,2,3 parameter). Query strings must survive literally.

### 4.5 Proxy routing

When proxy_url is set:
- If the proxy path already starts with /api, it is used as-is.
- Otherwise the proxy path is rewritten to the classic (TADO_API_PATH) or EIQ (EIQ_API_PATH) base path, optionally prefixed with a proxy_token path segment.
- No Authorization header is sent.

### 4.6 Timeout and error handling (_execute_request)

- Wrapped in asyncio.timeout(instance._request_timeout) (tadoasync default 10s).
- TimeoutError raises TadoConnectionError("Timeout connecting to Tado").
- HTTP >= 400: redacted response body is logged and put on the Tado exception.
- ClientResponseError (no proxy): delegates to tadoasync's instance.check_request_status() (handles expired-token re-auth logic) before re-raising.
- 204 No Content: returns "".

### 4.7 Rate-limit capture (_log_response)

On every response, parse_ratelimit_headers() extracts the quota and updates the handler's shared rate_limit_data = {limit, remaining, updated_at}.
RateLimitManager reads this via get_handler() — the handler is the single quota telemetry point for the classic API. (Hops has its own capture, see Part 4.)

## 5. File map (this part)

| Concern | File |
|---|---|
| Custom client + undocumented endpoints | custom_components/tado_hijack/helpers/client.py |
| Robust request handler | custom_components/tado_hijack/helpers/tado_request_handler.py |
| Patches + handler singleton export | custom_components/tado_hijack/lib/patches.py |
| Constants (UA, version patch) | custom_components/tado_hijack/const.py |
| Headers / quota parsing | custom_components/tado_hijack/helpers/parsers.py |

---

# Part 2 — tadoasync Runtime Patches

> `custom_components/tado_hijack/lib/patches.py`.

## Overview

The manifest requires `tadoasync==0.2.3`. We apply **three runtime monkey-patches** at setup
time via `apply_patches()`. Design properties:

- **Idempotent**: `_PATCHES_APPLIED` module flag — safe to call repeatedly
  (e.g. on integration reload).
- **Defensive**: every patch is wrapped in try/except; if tadoasync's
  internals change, the patch logs a warning and skips instead of killing
  the integration.
- **Upstream-ready**: written in a form intended to be contributed to the
  tadoasync project (patch chaining preserves any existing hooks).

The module also exports `get_handler()` which returns the global
`TadoRequestHandler` singleton (see Part 1 §4).

## Patch 1: `ZoneState` deserialization (`patch_zone_state_deserialization`)

**Target:** `tadoasync.models.ZoneState.__pre_deserialize__` (classmethod).

**Problems in stock tadoasync (still patched on 0.2.3):**
1. The classic API intermittently returns `"nextTimeBlock": null` when a zone
   is at the end of its schedule — strict dataclass deserialization crashes.
2. `activityDataPoints.hotWaterInUse` is silently dropped by the strict
   dataclass, but the integration needs it for the hot-water power sensor.
3. `sensorDataPoints` can arrive as `null`.

**Implementation:** installs a patched `__pre_deserialize__(cls, d)` that first
chains the original classmethod if one exists (forward-compatible with an
upstream fix), then normalizes the raw dict BEFORE dataclass parsing:

1. `sensorDataPoints` missing/None → set to `None` explicitly (normalizer
   keeps downstream code uniform).
2. `nextTimeBlock is None` → replaced with `{}` (empty dict satisfies the
   dataclass without carrying meaning).
3. Hot-water rescue: if `activityDataPoints.hotWaterInUse.value` exists, it is
   injected into `activityDataPoints.heatingPower` as
   `{"type": "HOT_WATER_POWER", "percentage": 100.0|0.0 (ON→100),
     "timestamp": <now ISO>, "value": <ON|OFF>}` so it survives deserialization
   and can be read later like ordinary heating power.

**Why injected into `heatingPower`?** Because that is the only
   activity-data field the stock dataclass keeps — the rescue piggybacks on an
   existing channel instead of fighting the dataclass definition.

## Patch 2: Version string (`patch_version_string`)

**Target:** `tadoasync.tadoasync.VERSION`.

Sets `VERSION = TADO_VERSION_PATCH` (value `"0.2.2"`, defined in our `const.py`)
and syncs `sys.modules["tadoasync"].VERSION` if the module is already imported.

**Why:** tadoasync's own VERSION constant drifts from the User-Agent format
expected by Tado's backend; the handler sends `HomeAssistant/<VERSION>` (see
Part 1 §4.2) and this patch guarantees the value is ours.

## Patch 3: `set_meter_readings` (`patch_set_meter_readings`)

**Target:** replaces `tadoasync.Tado.set_meter_readings` wholesale.

**Problem:** the stock method is missing the request URI and the
Energy-Insights host URL — it simply cannot reach the endpoint.

**Patched behavior:**

- Signature: `set_meter_readings(self, reading: int, date: datetime | None = None)`
- `date` defaults to `homeassistant.util.dt.now()` when omitted.
- Payload: `{"date": "%Y-%m-%d", "reading": int}`
- Request: `POST homes/{home_id}/meterReadings` against the EIQ host
  (`energy-insights.tado.com`) via the instance `_request` (which our handler
  overrides, Part 1 §4).
- Response parsing with `orjson`; if the response contains `"message"`, raises
  `tadoasync.exceptions.TadoReadingError` with that message (Tado signals
  meter-reading errors via the message field rather than a 4xx status).

## What is deliberately NOT patched

- Presence, overlay, and capability methods of tadoasync are used as-is
  (the presenceLock PUT/DELETE semantics are already correct there).
- No patching of the auth flow — `_refresh_auth` / device flow stay stock;
  the handler only wraps around them.

---

# Part 3 — Classic v2 API Custom Endpoints (TadoHijackClient)

> `custom_components/tado_hijack/helpers/client.py`.

These are custom methods added on top of the stock `tadoasync.Tado` API.
Every call goes through `TadoRequestHandler` (Part 1 §4).
All paths are relative to `homes/{home_id}/` unless stated otherwise.

## 3.1 Bulk Overlay Operations

### reset_all_zones_overlay(zones: list[int]) -> None

**Endpoint:** `DELETE homes/{home_id}/overlay?rooms={room_ids}`

- Zone IDs joined with commas: `"1,2,3"`
- Empty list → no request at all.
- Single HTTP request clears overlays for all listed zones.
- **Why:** N sequential DELETEs become 1 call — quota saving and avoids
  race conditions when multiple zones change simultaneously.

### set_all_zones_overlay(overlays: list[dict[str, Any]]) -> None

**Endpoint:** `POST homes/{home_id}/overlay`

**Payload shape:**

    {"overlays": [{"room": <zone_id>, "overlay": <overlay-payload>}, ...]}

- Each overlay payload mirrors what tadoasync's `set_zone_overlay()` sends for
  a single zone: `setting: {type, power, temperature?, ...}` plus termination.
- **Why:** 1 call instead of N — same quota argument as above. This bulk
  endpoint is NOT documented in the public kritsel v2 OpenAPI spec.

## 3.2 Hot water overlay

Classic hot-water **overlays** travel in the same bulk `POST homes/{home_id}/overlay` as heating and air conditioning. `set_hot_water_zone_overlay` (`PUT homes/{home_id}/zones/{zone_id}/overlay`) is defined on the client and has no caller.

Resume is not that bulk DELETE. `DELETE homes/{home_id}/overlay?rooms=` rejects hot-water ids, so each hot-water resume is `reset_hot_water_zone_overlay` → `DELETE homes/{home_id}/zones/{zone_id}/overlay`.

Tado X hot water is not this overlay. It is the Hops programmer (`programmer/domesticHotWater/`), and a duration is held in Home Assistant because the boost body ignores a timer.

## 3.3 Device-Level Property

### set_temperature_offset(serial_no: str, offset: float) -> None

**Endpoint:** `PUT homes/{home_id}/devices/{serial_no}/temperatureOffset`

**Payload:**

    {"celsius": <float>}

**Why:** device-level temperature calibration. On Tado X the equivalent is
part of device fusion (Part 4).

## 3.4 Zone-Level Settings (undocumented endpoints)

### Away Configuration

- `get_away_configuration(zone_id)` → `GET .../zones/{zone_id}/awayConfiguration`
- `set_away_configuration(zone_id, payload)` → `PUT .../zones/{zone_id}/awayConfiguration`
- Payload keys: `type`, `preheatingLevel`, `minimumAwayTemperature: {celsius}`
- **Why:** controls zone behavior while home presence is AWAY.

### Dazzle Mode

- `set_dazzle_mode(zone_id, enabled)` → `PUT .../zones/{zone_id}/dazzle`
- Payload: `{"enabled": bool}`
- **Why:** dazzle protection for radiator valves.

### Early Start

- `set_early_start(zone_id, enabled)` → `PUT .../zones/{zone_id}/earlyStart`
- Payload: `{"enabled": bool}`
- **Why:** pre-heating so the target temperature is reached at schedule time.

### Open Window Detection

- `set_open_window_detection(zone_id, payload)` → `PUT .../zones/{zone_id}/openWindowDetection`
- Payload keys: `enabled`, duration/timeout settings, `temperature: {celsius}`
- **Why:** per-zone configuration of the open-window heating pause.

## 3.5 Device Identification

### identify_device(serial_no: str) -> None

**Endpoint:** `POST homes/{home_id}/devices/{serial_no}/identify`

**Why:** makes the physical device flash/beep so users can identify which
radiator valve is which (used when linking devices).

## 3.6 Timetable / Schedule Management

Classic schedules = active timetable + blocks per day type.

### Active Timetable

- `get_active_timetable(zone_id)` → `GET .../zones/{zone_id}/schedule/activeTimetable`
- `set_active_timetable(zone_id, timetable_id)` →
  `PUT .../zones/{zone_id}/schedule/activeTimetable` with `{"id": timetable_id}`

### Timetable Blocks

- `get_timetable_blocks(zone_id, timetable_id)` →
  `GET .../zones/{zone_id}/schedule/timetables/{timetable_id}/blocks`
  - All day types in ONE call (client parses list, returns `[]` on non-list).
- `set_timetable_blocks(zone_id, timetable_id, day_type, payload)` →
  `PUT .../zones/{zone_id}/schedule/timetables/{timetable_id}/blocks/{day_type}`

**Why per-dayType PUT + all-dayTypes GET:** writes go per day type while
reads stay cheap (1 call for all day types).

## 3.7 Stock tadoasync Methods Used As-Is

These classic endpoints come from tadoasync (unpatched) but run through
our overridden `_request`:

| Method | Endpoint | Notes |
|---|---|---|
| `set_presence` | `PUT/DELETE homes/{id}/presenceLock` | PUT `{"homePresence": "HOME"/"AWAY"}`; DELETE restores AUTO geofencing |
| `set_child_lock` | `PUT .../devices/{serial}/childLock` | Payload `{"childLockEnabled": bool}` |
| `set_zone_overlay` / `reset_zone_overlay` | `PUT/DELETE .../zones/{z}/overlay` | Single-zone fallback |
| `get_capabilities` | `GET .../zones/{z}/capabilities` | Detects what a zone supports |

## 3.8 Summary Table

| Method | HTTP + Path | Purpose |
|---|---|---|
| `reset_all_zones_overlay` | `DELETE /overlay?rooms=` | Bulk overlay reset |
| `set_all_zones_overlay` | `POST /overlay` | Bulk overlay set |
| `set_hot_water_zone_overlay` | `PUT /zones/{z}/overlay` | Defined, no caller. Live hot-water overlays use the bulk POST |
| `reset_hot_water_zone_overlay` | `DELETE /zones/{z}/overlay` | Hot water resume. The bulk DELETE rejects these ids |
| `set_temperature_offset` | `PUT /devices/{serial}/temperatureOffset` | Calibration |
| `get/set_away_configuration` | `GET/PUT /zones/{z}/awayConfiguration` | Away behavior |
| `set_dazzle_mode` | `PUT /zones/{z}/dazzle` | Dazzle protection |
| `set_early_start` | `PUT /zones/{z}/earlyStart` | Pre-heating |
| `set_open_window_detection` | `PUT /zones/{z}/openWindowDetection` | OWD config |
| `identify_device` | `POST /devices/{serial}/identify` | Flash device |
| `get/set_active_timetable` | `GET/PUT /zones/{z}/schedule/activeTimetable` | Switch timetable |
| `get/set_timetable_blocks` | `GET/PUT /zones/{z}/schedule/timetables/{tt}/blocks[/{dayType}]` | Schedule edit |

## 3.9 File Map

- Implementation: `helpers/client.py`
- Handler: `helpers/tado_request_handler.py` (Part 1 §4)
- Response parsing: stock tadoasync (no custom models for these)

---

# Part 4 — Tado X / Hops API (lib/tadox_api.py)

## 1. Why a second API surface?

Tado X devices (hops.tado.com) represent a complete API rewrite compared to classic. The integration must:

- Route room heating to Hops (`manualControl`, and `quickActions` when the whole heating set matches).
- Keep presence on classic v2 (`/state`, `/presenceLock`). Tado X has no `activeTimetable`. Timetable switching is classic only.
- Not send air-conditioning settings on Hops. `async_set_ac_setting` for Tado X is a no-op. Rooms are treated as heating rooms.
- Unify both generations under a single data model (Part 5).

## 2. Base URL and Auth

- Base: https://hops.tado.com
- Auth: Shares the same OAuth2 token as tadoasync (private attribute reuse: _access_token, _refresh_auth). No separate login flow.
- Client ID for X device flow: 1bb50063-.... (defined in helpers/tadox/const.py).

The TadoXApi class inherits nothing from TadoHijackClient but reuses the authenticated session by accessing private attributes of the parent tadoasync instance. This coupling is documented explicitly.

## 3. Critical Quirks

### 3.1 ngsw-bypass=true header

Required on every Hops request. Without it, Angular's service-worker returns cached stale responses instead of live data.

### 3.2 404 Semantics

When a home does not have X hardware yet, many endpoints return 404 instead of erroring hard. The integration treats 404 as empty structure:

- Rooms: {"rooms": []}
- Devices: {"devices": []}
- Programmer state: {"program": "AUTO", ...}

This allows graceful degradation without breaking the data model.

### 3.3 Content-Type Behavior

Unlike the classic API, Hops sometimes rejects POST/PUT without Content-Type: application/json, while other paths tolerate its absence. The implementation conservatively includes Content-Type: application/json for all mutating requests.

### 3.4 User-Agent on Hops

Hops does not use `TADO_USER_AGENT`. It copies `user-agent` from tadoasync's `_headers` and falls back to `TadoHijack/1.0`. That map has no user-agent, so Hops sends `TadoHijack/1.0`. Classic and Energy IQ still send `HomeAssistant/0.2.2`.

### 3.5 Rate Limit Headers

Classic and Hops both expose `RateLimit-Policy` (`q=`, the limit) and `RateLimit` (`r=`, remaining). Hops sends those names in lowercase (`ratelimit-policy`, `ratelimit`). The client title-cases them and both sources feed the same `RateLimitManager`. The code does not read `x-ratelimit-limit`, `x-ratelimit-remaining`, or `x-ratelimit-reset`, and it does not keep a separate Hops quota tracker. A Hops 404 returns before header capture.

## 4. Endpoint Reference (Read/Write)

All payloads taken directly from lib/tadox_api.py method implementations.

### 4.1 Room State Reads

#### async_get_rooms() -> dict

GET: rooms

Returns list of rooms with insideTemperature, humidity, targetTemperature, heating, cooling fields.

#### async_get_room(room_id: int) -> dict

GET: rooms/{room_id}

Detailed snapshot for one room (used by coordinators).

### 4.2 Manual Control (Overlay Equivalent)

#### async_manual_control_set(room_id: int, payload: dict) -> None

POST: rooms/{room_id}/manualControl

Payload shape:

    {"setting": {"type": "HEATING", "power": "ON", "temperature": {"celsius": 21.5}}}

Termination: Unlike classic's "termination": "MANUAL", Hops uses implicit session expiry or a subsequent resumeSchedule call.

#### async_manual_control_resume(room_id: int) -> None

DELETE: rooms/{room_id}/manualControl

Resumes schedule for the room.

Why manualControl? It replaces classic's /zones/{id}/overlay concept but lacks bulk operation — see Section 5.

### 4.3 Quick Actions (House-Wide)

Three POSTs, no JSON body:

- `async_boost_all` → `POST quickActions/boost`
- `async_turn_off_all_zones` → `POST quickActions/allOff`
- `async_resume_all_schedules` → `POST quickActions/resumeSchedule`

There is no `POST quickActions` with an action name such as `BOOST`. The executor uses one of these when the batch is an explicit quick action, or when every active heating room wants the same resume, off, or boost (boost means power on at 25°C within 0.1°C). Rooms that do not match get their own `manualControl`.

### 4.4 Room schedule

#### async_get_room_schedule(room_id: int)

GET: rooms/{room_id}/schedule

Returns the room and `schedule`, a list of blocks. Each block has `dayType`
(`MONDAY` through `SUNDAY`), `start`, `end` (`00:00` to `24:00`), and
`setting`. There is no ONE_DAY / THREE_DAY / SEVEN_DAY switch.

#### async_set_room_schedule(room_id: int, payload: dict) -> None

POST: rooms/{room_id}/schedule

One weekday per call:

```json
{
  "dayType": "TUESDAY",
  "daySchedule": [
    {
      "start": "00:00",
      "end": "24:00",
      "dayType": "TUESDAY",
      "setting": {"power": "ON", "temperature": {"value": 20}}
    }
  ]
}
```

`set_schedule` with `all_days` posts that once per weekday. `days` posts
only the named weekdays. `one_day`, `three_day`, and `activate` are classic.

### 4.5 Flow Temperature Optimization (Boiler)

#### async_get_flow_temperature_optimization() -> dict

GET: settings/flowTemperatureOptimization

#### async_patch_flow_temperature_optimization(payload: dict) -> None

PATCH: settings/flowTemperatureOptimization

Payload: {"maxFlowTemperature": float}, {"autoAdaptation": bool}.

### 4.6 Domestic Hot Water (Programmer)

#### async_get_programmer_state() -> dict

GET: programmer/domesticHotWater/state

`state` is `SCHEDULE_ON` or `SCHEDULE_OFF` while the programmer follows the plan. A boost replaces that with `BOOST_ON` or `BOOST_OFF`. `nextStateChange` is the next schedule change while `state` starts with `SCHEDULE_`. During a boost it is the boost expiry, not the next block.

#### async_boost_hot_water() -> None

POST: programmer/domesticHotWater/boost

Payload: {"boost": "ON"} or {"boost": "OFF"}. Tado X keeps a boost for 60 minutes and keeps off until resumeSchedule. Until presence changes is not available. A duration is not sent here. The integration holds the mode until a deadline and repeats a boost before that window closes. At the deadline it returns to the programmer state from before the hold: `resumeSchedule` when that was the schedule or a boost, `boost` OFF when it was forced off. The deadline is the requested duration, or `nextStateChange` for until-next-block while the programmer is on the schedule. The plan is stored so a restart continues the hold.

#### async_resume_programmer_schedule() -> None

POST: programmer/domesticHotWater/resumeSchedule

### 4.7 Open Window Helper

#### async_set_open_window(room_id: int) -> None

POST: rooms/{room_id}/openWindow

#### async_clear_open_window(room_id: int) -> None

DELETE: rooms/{room_id}/openWindow

### 4.8 Device Properties (Fused Write)

#### async_patch_device(serial_no: str, payload: dict) -> None

PATCH: roomsAndDevices/devices/{serial_no}

Combined payload: {"childLockEnabled": bool, "temperatureOffset": float}.

Why fused? The Hops API accepts multiple properties in one PATCH. Instead of two calls (one for child lock, one for offset), we send one request — see Part 5.

#### identify_device(serial_no: str) -> None

POST: roomsAndDevices/devices/{serial_no}/identify

Makes the physical device flash/beep.

### 4.9 Presence (Still Classic)

Presence is NOT implemented on Hops. The integration calls the classic API's put_presence_lock(presence) / delete_presence_lock() (via tadoasync + TadoXApi._request_external() to my.tado.com).

## 5. Execution Strategy

See Part 5 for the merged command pipeline (debounce to merge to redundancy to execute). On Hops specifically:

- Device Fusion merges childLock + temperatureOffset.
- Quick Action inference merges identical room intents into 1 house-wide call.
- Magic Temp Mapping (temp=-1 to power=OFF) reduces commands.

## 6. File Map

- Client: lib/tadox_api.py
- Models: lib/tadox_models.py (Pydantic v2)
- Executor: helpers/tadox/executor.py
- Constants: helpers/tadox/const.py (OAuth, base URLs, client IDs)

---

# Part 5 — Models, Command Pipeline, Local Control & Limits

> helpers/tadov3/executor.py, helpers/tadox/executor.py,
> helpers/executor_base.py, custom_components/tado_hijack/coordinator.py,
> custom_components/tado_hijack/helpers/device_linker.py.

## 1. Unified Data Models & Duck Typing

### 1.1 Goal

Make the rest of the integration (coordinators, entities, services) generation-
agnostic. Neither the climate platform nor the sensors care whether they talk
to Hops or Classic — they see a consistent interface.

### 1.2 Pydantic v2 Models for Hops

Located in lib/tadox_models.py:

- HopsRoomSnapshot: represents a room's live state (insideTemperature,
  humidity, heating, cooling).
- TadoXDevice: adds capability inference (presence of temperatureOffset
  field implies INSIDE_TEMP capability).
- TadoXZoneState: aggregates room + device data.
- TadoXHotWaterState: maps programmer state (SCHEDULE_* prefixes) to
  boolean overlay_active.

### 1.3 Duck-Typing for v3 Compatibility

Stock tadoasync returns plain dataclasses for classic. Hops returns Pydantic
models. To avoid branching in coordinators, we add compatibility properties
so both generations expose the same attributes:

- HopsTemperature.celsius: wraps .value so code expecting .celsius works.
- TadoXZoneState.current_temp: extracts temperature from nested model.
- TadoXZoneState.overlay_active: infers manual override state.

Why: Without duck-typing, every coordinator line would require
if self.generation == GEN_X ... else ... — unmaintainable.

## 2. Command Pipeline Overview

The integration batches user/automation commands through these stages:

1. Debouncing: coalesces rapid successive changes (e.g. slider drag).
2. Merging: combines overlapping commands for same zone/device.
3. Redundancy Filter: skips writes if new value equals current known state.
4. Execution: routes to TadoV3Executor or TadoXExecutor.
5. Optimistic Update: applies change to local cache immediately.
6. Rollback: on failure, restores previous state.

See helpers/executor_base.py and helpers/tadov3/executor.py + helpers/tadox/executor.py
for implementation.

### 2.1 TadoXExecutor (helpers/tadox/executor.py)

Special optimizations for Hops quota economy:

#### Device Fusion (_execute_device_fusion)

Goal: Combine childLock + temperatureOffset changes into one PATCH.

Mechanism:

- Collects all child_lock changes {serial: bool}.
- Collects all offsets changes {serial: float}.
- Merges by serial into single payload per device
  ({childLockEnabled, temperatureOffset}).
- Single PATCH roomsAndDevices/devices/{serial} per device.
- The offset number and offset calibration do not queue that offset.
  They PATCH immediately, so they do not join this merger.

Saved calls: 2 to 1 per device.

#### Quick Action Inference

Goal: When all heating rooms share the same intent, use ONE house-wide
quick action instead of N manualControl requests.

Logic:

- The batch must be exactly the active heating rooms.
- All resume, all off, or all boost (power on, within 0.1°C of 25°C) becomes one of the three `quickActions/*` POSTs above.
- A room that does not match gets its own `manualControl`.

Saved calls: N to 1 (+ outliers).

#### Magic Temperature Mapping

Convention: temperature = -1 means power = OFF.

Function: map_magic_temp_to_power(temp, power) -> (power, temp)

If temp == -1, forces power = OFF and drops temperature from payload.
This allows HA's OFF to temp=-1 mapping to work without extra entities.

### 2.2 TadoV3Executor (helpers/tadov3/executor.py)

Uses tadoasync methods plus custom client bulk calls:

- Presence: client.set_presence()
- Device properties: client.set_child_lock(), client.set_temperature_offset()
  (one call per device — no fusion available on classic)
- Zone overlays: client.set_all_zones_overlay() / reset_all_zones_overlay()
  (bulk POST/DELETE)
- Schedule/timetable: client.set_timetable_blocks(), set_active_timetable()

### 2.3 Schedules & Timetables (Shared Logic in executor_base.py)

Schedule block writes go through `_execute_schedules()`. Classic also runs
`_execute_timetables()` (`activeTimetable`). Tado X does not.

- TadoX: bridge.async_set_room_schedule() (POST /rooms/{id}/schedule), one weekday
- Classic: client.set_timetable_blocks() (PUT /schedule/timetables/.../blocks)

After a successful write, the zone plan cache stores that day.

### 2.4 Rollback Infrastructure

Every _safe_execute() call accepts:

- coro: the async operation
- rollback_fn: called on error to restore previous state
- success_fn: called on success to update optimistic cache

This ensures atomicity-at-scale: if any step in a batch fails, prior steps
are rolled back.

## 3. Quota & Rate Limit Management

### 3.1 Mechanism

- TadoRequestHandler (classic) and TadoXApi (Hops) capture rate-limit
  headers from every response.
- Shared rate_limit_data is polled by `RateLimitManager`
  (`helpers/rate_limit_manager.py`) which computes:
  - Daily budget consumption from the header, not from a hardcoded cap
  - Reset detection. Until two resets share an hour, the expected time is
    11:30 UTC (12:30 CET / 13:30 CEST)
  - Throttle decisions when remaining calls fall below the threshold

### 3.2 Budget Math

The manager uses observed headers. `API_QUOTA_STANDARD = 1000` only gates
the first full poll (it runs when `q=` is at least 1000). `API_QUOTA_PROXY
= 3000` is unused. Tado's help center (27 January 2026) publishes 100/day
and 20,000 for Auto-Assist and AI Assist. Tado's r/tado post on 26 May 2026
says they maintain 1,000/day and plan to reduce that further. Neither
figure is a mode switch in this code.

Why aggressive batching? Every bulk overlay saves N-1 calls, device fusion
saves 1 call, quick action inference saves N-1 calls. At scale these savings
prevent quota exhaustion.

## 4. Local Control: HomeKit & Matter Linking

### 4.1 Serial-Based Matching (helpers/device_linker.py)

Both HomeKit (classic) and Matter (Tado X) devices expose a serial number
(serialNo). The linker:

1. Fetches Tado devices from either generation.
2. Matches by serial number to HomeKit/Matter accessories.
3. Exposes a bidirectional map serial to/from entity_id.

### 4.2 Why Local Control?

- Latency: local commands bypass cloud round-trips.
- Quota: local sets do NOT consume API quota.
- Reliability: works even if Tado cloud has an outage (limited to heating).

A local climate setpoint is not copied to the cloud. `climate.set_hvac_mode`
of `auto` on a linked entity resumes the Tado schedule. Other local
`set_temperature` / `set_hvac_mode` calls only set an optimistic overlay.

## 5. Known Limitations & Gotchas

### 5.1 Tado X Lacks Bulk Overlay

Unlike classic's POST /overlay, Hops requires per-room manualControl
unless the quick-action inference succeeds. This makes Tado X more quota-
expensive for multi-zone simultaneous changes.

### 5.2 Presence Only on Classic

Even Tado X homes use classic's /presenceLock for geofencing. There is
no Hops-native presence API yet.

### 5.3 Schedule Write Complexity

Hops schedule format differs from classic. The integration must transform
between the two internally.

### 5.4 Private Attr Coupling

TadoXApi accesses tadoasync's private attrs (_access_token, etc.). If
tadoasync changes internals, the integration degrades gracefully but logs
warnings. This is acceptable risk given the tight coupling.

### 5.5 ngsw-bypass Requirement

Without ngsw-bypass=true, Hops returns cached service-worker responses.
This header is non-negotiable.

### 5.6 Flow temperature is not on the poll

`GET settings/flowTemperatureOptimization` and its 404 cache live on
`TadoXMapper.async_fetch_unified_data`. The zone and metadata polls do not
call that method, so the max-flow number and the auto-adaptation switch
are not created from live data. The option defaults to off.

## 6. Summary File Map

| Concern | Files |
|---|---|
| Hops models (Pydantic) | lib/tadox_models.py |
| v3 executor (classic) | helpers/tadov3/executor.py |
| X executor (Hops) | helpers/tadox/executor.py |
| Base executor (rollbacks, schedules) | helpers/executor_base.py |
| Device linker (local) | helpers/device_linker.py |
| Rate limiting | helpers/rate_limit_manager.py, helpers/parsers.py, helpers/quota_math.py |
| Coordinator (pipeline orchestration) | coordinator.py |

---

# Appendix — Full Endpoint Reference

## Classic v2 API (my.tado.com/api/v2, paths relative to homes/{home_id}/)

| Category | Method | Path | Purpose |
|---|---|---|---|
| Bulk | DELETE | /overlay?rooms= | Reset overlays for multiple zones |
| Bulk | POST | /overlay | Set overlays for multiple zones |
| Hot Water | POST | /overlay | Hot-water overlays share the bulk overlay POST |
| Hot Water | DELETE | /zones/{z}/overlay | Hot-water resume. The bulk DELETE rejects these ids. The per-zone PUT exists and has no caller |
| Device | PUT | /devices/{serial}/temperatureOffset | Temperature calibration |
| Device | PUT | /devices/{serial}/childLock | Child lock toggle |
| Device | POST | /devices/{serial}/identify | Flash device |
| Zone | GET/PUT | /zones/{z}/awayConfiguration | Away mode config |
| Zone | PUT | /zones/{z}/dazzle | Dazzle mode |
| Zone | PUT | /zones/{z}/earlyStart | Early start |
| Zone | PUT | /zones/{z}/openWindowDetection | Open window detection |
| Schedule | GET/PUT | /zones/{z}/schedule/activeTimetable | Switch timetable |
| Schedule | GET/PUT | /zones/{z}/schedule/timetables/{tt}/blocks[/{dayType}] | Timetable blocks |
| Presence | PUT/DELETE | /presenceLock | Geofencing override (PUT) / AUTO (DELETE) |
| Capabilities | GET | /zones/{z}/capabilities | Zone capabilities |

## Hops API (hops.tado.com)

| Category | Method | Path | Purpose |
|---|---|---|---|
| Room State | GET | /rooms | List all rooms |
| Room State | GET | /rooms/{id} | Single room snapshot |
| Manual Control | POST | /rooms/{id}/manualControl | Set overlay |
| Manual Control | DELETE | /rooms/{id}/manualControl | Resume schedule |
| Quick Actions | POST | /quickActions/boost | House-wide boost. No JSON body |
| Quick Actions | POST | /quickActions/allOff | House-wide off. No JSON body |
| Quick Actions | POST | /quickActions/resumeSchedule | House-wide resume. No JSON body |
| Schedule | GET | /rooms/{id}/schedule | Read the week (seven weekdays) |
| Schedule | POST | /rooms/{id}/schedule | Replace one weekday |
| Flow temperature | GET/PATCH | /settings/flowTemperatureOptimization | Client method and 404 cache. The zone and metadata polls do not call the GET, so the entities are not created from live data |
| Hot Water | GET | /programmer/domesticHotWater/state | HW programmer state |
| Hot Water | POST | /programmer/domesticHotWater/boost | HW boost |
| Hot Water | POST | /programmer/domesticHotWater/resumeSchedule | HW resume schedule |
| Open Window | POST/DELETE | /rooms/{id}/openWindow | Open window set/clear |
| Device | PATCH | /roomsAndDevices/devices/{serial} | Child lock + offset (fused) |
| Device | POST | /roomsAndDevices/devices/{serial}/identify | Identify device |
| Rooms+Devices | GET | /roomsAndDevices | Rooms and devices snapshot |

## Other

| Surface | Method | Path | Purpose |
|---|---|---|---|
| EIQ | POST | energy-insights.tado.com homes/{id}/meterReadings | Submit meter reading |
| OAuth2 | POST | login.tado.com/oauth2/token | Token refresh |
| OAuth2 | POST | login.tado.com/oauth2/device_authorize | Device authorization flow |

# Revision History

- Commit 7166d36: original draft of this file. That stamp is not a current
  verification.
- 4 October 2026: library pin, User-Agent, rate-limit header names, classic
  hot-water overlay versus the unused PUT, Tado X timetable and AC routing,
  quota figures, the rate-limit module path, and the flow-temperature poll
  gap were corrected against the tree.
