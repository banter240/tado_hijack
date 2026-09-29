# Features Guide

Tado Hijack is a power-user integration designed to unlock the full potential of your Tado hardware while bypassing the strict limitations of the official API and app. All features are verified against the code in `custom_components/tado_hijack/`.

---

## 🚀 Extreme Command Batching

**The Tech:** Tado Hijack uses a **Fused Overlay Strategy**.
- **Official App:** Sends one request per zone when resuming schedules or turning off zones.
- **Tado Hijack (V3 Classic):** Buffers commands for 5 seconds (debounce window) and merges them into a single `POST /homes/{homeId}/overlay` — heating, AC, hot water, mixed temperatures in one call.
- **Tado Hijack (Tado X / Hops):** House-wide boost/off/resume uses `POST /quickActions/*` (single API call). Hops has no mixed-room overlay body, so per-room `manualControl` is used for mixed sets.
- **The Quota Saving:** Turning off 10 rooms costs **1 API call** instead of 10 — the single most important feature for users with many radiators.

---

## 🌡️ Indoor Climate Intelligence

We calculate advanced building physics metrics per zone using high-precision formulas (`helpers/climate_physics.py`).

- **Dew Point (°C):** Calculated using the **Magnus formula** (Bolton 1980, valid −30…+35 °C, error < 0.1 % over water). Represents the temperature at which condensation begins on surfaces.
- **Mold Risk Level:** A 4-step rating (`none`, `low`, `medium`, `high`) based on the spread between the wall temperature (estimated via dew point) and the room temperature:
  - `> 7 °C spread` → `none` (surface RH well below 70 %)
  - `> 5 °C spread` → `low` (cold bridges / poorly insulated spots)
  - `> 3 °C spread` → `medium` (corners, airing recommended)
  - `≤ 3 °C spread` → `high` (near-condensation, widespread risk)
- **Absolute Humidity (g/m³):** The actual mass of water in the air, derived from saturation vapour pressure via the Magnus formula.
- **Ventilation Recommendation:** A smart binary sensor that compares indoor vs. outdoor Absolute Humidity. It turns `ON` only when opening windows will **reduce** indoor moisture by at least the configured threshold (default `1.0 g/m³`), preventing automation chatter. Requires an outdoor weather entity.

> [!TIP]
> **Dynamic Source Selection:** You can select a high-precision external sensor (Aqara, Hue, etc.) as the data source for these calculations, effectively bypassing the TRV's inaccurate measurement point near the radiator.

---

## 🧠 Auto API Quota (Adaptive Polling)

Tado Hijack conserves API quota with intelligent polling that balances responsiveness and efficiency.

- **Weighted Distribution:** The system calculates the polling interval based on remaining quota, time until reset, and measured poll costs. More calls are invested during daytime hours; nighttime budgets are saved.
- **Reset Window Learning:** The system monitors API headers to detect when Tado resets your quota. A learned window is confirmed after **2 consecutive resets** at the same hour (history size: 5 resets, stored in UTC so DST does not shift it); until then, the default hour (11:00 UTC ≈ 12:00/13:00 Berlin) is used.
- **Economy Window (Night-Savings):** Configure a sleep window (e.g., 22:00–07:00) where polling slows down or pauses entirely. Saved calls are reinvested during the day, allowing updates as fast as every 20 seconds when quota permits.
- **Safety Reserve:** A configurable number of calls (default 2) are reserved for the reset safe window (±1 h around the expected reset hour, spanning 3 h total). This ensures background polling resumes promptly when Tado resets your account.

---

## 🔗 Device Unification

- **Multi-TRV Rooms:** Multiple TRVs in one room are unified under a single logical entity. Offsets are applied per device; a multi-device batch fires one command per TRV, and on Tado X offset plus child lock fuse into a single PATCH per device.
- **Matter + HomeKit Support:** Devices registered via either protocol are recognized and linked. `DeviceLinker` unifies devices by serial number across platforms.
- **AC Pro Controls:** Fan speed, swing mode (axis swing preferred, single-toggle fallback), and operation mode are fully exposed for Air Conditioner Pro units.
- **External Window Sensor Handler:** Any `binary_sensor` contact sensor can be linked per zone (`select.zone_window_sensor`). Window open/close transitions turn the zone off and resume the schedule. Cloud calls go through the coordinator's command queue. The reaction mode (`select.zone_window_mode`) is `direct` (off on open, resume on close) or `timeout` (off on open plus a self-healing resume: heating resumes after the zone's open window detection timeout even while the window is still open, protecting against a stuck sensor or dead battery; only a new close -> open transition starts the next cycle). Already-open windows take effect at HA startup without waiting for a transition; if open window detection is disabled, `timeout` behaves like `direct`. `window_resume_batch` (default on, 120 s) is the quota hold: details are in the README window section.
- **Internet Bridge:** Hijack always registers its own Internet Bridge device. When HomeKit or Matter already has that bridge, the entities are created there and the Hijack device stays empty (same as a TRV). Without a local bridge, the entities stay on the Hijack device.
- **Offline TRV recovery:** Commands are still sent to the cloud. If the local climate entity (HomeKit or Matter) is unavailable, the last intent for that serial is kept and replayed when it returns. An expired window-off or timer resolves to resume schedule. Cloud-only resume is resent only when `recovery_cloud_replay` is enabled (one call per zone). Tado X hot water uses the same capture on the virtual hot-water zone; that zone has no TRV serials, so the capture is a no-op unless a local device is actually mapped.

---

## 📅 Calendars & Overlays

- **Zone Plan Calendar:** Read-only weekly plan displayed as calendar events per zone; the calendar platform exposes the active Tado schedule but cannot drive overlays.
- **Set Schedule Service:** `tado_hijack.set_schedule` lets automations or scripts push schedules to one or more zones.
- **Boost All / Resume All:** `async_boost_all()` and `async_resume_all_schedules()` control all zones with a single API call (Tado X).
- **Hot Water Boost:** On Tado X the water heater operation modes call the Hops programmer directly (`boost`, `boost` off, `resumeSchedule`), with optimistic state and the redundancy check. This path does not go through the zone overlay debounce queue. `heat` is boost on, `off` forces hot water off, `auto` resumes the schedule (that cancels a boost).
- **Flow temperature (Tado X, OpenTherm):** Opt-in (`feature_flow_temperature_optimization`, default off). A 404 is cached so homes without an OpenTherm device are not polled again. Max flow temperature and auto adaptation share one debounced PATCH; editing both inside the debounce window keeps both fields.

---

## 🔍 Advanced Diagnostics

- **Offset Calibration:** Automatically adjusts TRV offsets based on external reference sensors (e.g., a high-precision thermostat). The home interval and spread threshold are the defaults. Each heating zone can override them (`inherit`, or threshold `0`, clears the override). Clock intervals (`3h`..`24h`, `on_reset`) only look at that time, and only write when the sensor and the Tado temperature differ by at least the threshold. `threshold` keeps watching and writes as soon as that deviation is reached. After a write it waits `offset_cal_send_cooldown_s` (default 300 s) before another PUT. While the zone's window sensor is open it does nothing. After the window closes it waits `offset_cal_window_settle_s` (default 300 s) so the TRV by the window and the room sensor can settle.
- **Presence mode vs presence state:** `select.presence_mode` shows who is in control: `auto` (geofencing, `presenceLocked` false) or a manual `home`/`away` lock. It no longer flips when geofencing changes the effective state. `binary_sensor.presence_state` is that effective state (`on` = home). Switching to `auto` queues a presence refresh through the normal debounce pipeline.
- **Diagnostic Sensors:** Expose rate-limit state (`limit`, `remaining`, `api_status`), throttle threshold, learned reset windows, and daily quota usage.

---

## 🌐 Proxy & Transparency

- **Transparent Proxy:** Route classic API traffic through a proxy (`tado-api-proxy`) without modifying tadoasync itself. The proxy injects authentication headers; the handler omits them (proxy handles auth).
- **Proxy Call Jitter:** Optional randomized jitter per call (enabled via config) spreads load for proxy deployments.
- **Rate-Limit Headers:** Every response is parsed for `ratelimit-policy` / `ratelimit` headers, feeding both the quota manager and diagnostic sensors.

---

## 🔒 Security & Privacy

- **Credential Handling:** Credentials are managed by Home Assistant's config-entry storage; the integration itself never touches plaintext secrets in logs (see Redaction below).
- **Redaction:** All logs use `get_redacted_logger()` with regex scrubbing of emails, tokens, serial numbers and other sensitive data.
- **Field Locking:** While a command is pending, affected entity attributes are locked to prevent stale poll data from overwriting user intent (race-condition prevention).

---

## 🧩 AC Control Deep Dive

For Air Conditioner Pro units:

- **Fan Speed:** Exposes all available fan speeds from the device capabilities; selects the closest matching value.
- **Swing Mode:** Axis swing (verticalSwing/horizontalSwing) is preferred when exposed. Falls back to a single toggle swing (cached last state or "OFF") because tadoasync does not parse single-toggle swing from mode capabilities.
- **Operation Modes:** Heating, cooling, auto, dry, fan — mapped from capability lists.
- **Temperature Control:** Target temperature can be set within the device's supported range.

---

## 📊 Quota Math & Budget Planning

The integration uses sophisticated math (`helpers/quota_math.py`) to plan daily budget:

- **Usable Budget:** `limit − pro_rata_background_costs − throttle_threshold`, scaled by `auto_quota_percent`; external usage observed from header deltas can further reduce it.
- **Progress Proration:** Background costs consumed so far are deducted proportionally to the day's progress.
- **Predicted Poll Cost:** EMA-smoothed (`RATELIMIT_SMOOTHING_ALPHA`) from measured `last_poll_cost` (actual calls minus capabilities calls).
- **Remaining Polls:** Budget divided by predicted cost determines how many polls can be safely made.
- **Adaptive Interval:** Seconds until reset divided by remaining polls yields the optimal polling interval.

---

## 🔧 Configuration Options

- `throttle_threshold` — Remaining calls reserved for external use (automations, scripts, manual app usage). Default 20.
- `debounce_time` — Command debounce window in seconds. Default 5 s, minimum 1 s.
- `disable_polling_when_throttled` — Pause all background polling when throttled. Default false (15-min heartbeat). Set true to pause completely.
- `auto_quota_percent` — Percentage of usable quota allocated to this integration. 100 = full control.
- `quota_safety_reserve` — Calls reserved for the reset safe window. Default 2.
- `presence_poll_interval` — Poll interval for presence track. Default 43200 s (12 h).
- `slow_poll_interval` — Poll interval for hardware metadata (capabilities, bridges). Default 86400 s (24 h).
- `offset_poll_interval` — Poll interval for offset calibration. Default 0 (disabled).
- `reduced_polling_start/end/interval` — Economy window timing and reduced interval. Interval 0 pauses updates.
