# Features Guide

Tado Hijack is a power-user integration designed to unlock the full potential of your Tado hardware while bypassing the strict limitations of the official API and app.

---

## 🚀 Extreme Command Batching

**The Tech:** Tado Hijack uses a **Fused Overlay Strategy**.
- **Official App:** Sends one request per zone when resuming schedules or turning off zones.
- **Tado Hijack (v3):** Buffers commands for 5 seconds and merges them into a single `POST /homes/{homeId}/overlay` request.
- **Tado Hijack (Tado X):** Uses `POST /quickActions/*` endpoints (boost, resumeSchedule, allOff) — a single API call for all rooms.
- **The Quota Saving:** Turning off 10 rooms costs **1 API call** instead of 10. This is the single most important feature for users with many radiators.

## 🌡️ Indoor Climate Intelligence

We calculate advanced building physics metrics per zone using high-precision formulas.

- **Dew Point (°C):** Calculated using the **Magnus formula**. It represents the temperature at which condensation begins on surfaces.
- **Mold Risk Level:** A 4-step rating (`none`, `low`, `medium`, `high`) based on the spread between the wall temperature (estimated via dew point) and the room temperature.
- **Absolute Humidity (g/m³):** The actual mass of water in the air.
- **Ventilation Recommendation:** A smart binary sensor that compares indoor vs. outdoor Absolute Humidity. It only turns `ON` if opening the window will actually **reduce** indoor moisture (requires an outdoor weather entity).

> [!TIP]
> **Dynamic Source Selection:** You can select a high-precision external sensor (Aqara, Hue, etc.) as the data source for these calculations, effectively bypassing the TRV's inaccurate measurement point near the radiator.

## 🧠 Auto API Quota (Adaptive Polling)

Tado Hijack features a self-regulating polling engine that ensures 24/7 continuity.

- **Weighted distribution:** Instead of polling every X minutes, the integration calculates how many calls are left and stretches them until the next reset.
- **Reset Window Learning:** The system monitors API headers to detect the exact moment Tado resets your quota. It learns this pattern over 2-3 days to optimize your budget planning.
- **Economy Window (Night-Savings):** You can define a "Sleep Window" (e.g. 23:00 - 07:00) where polling stops or slows down. These saved calls are "reinvested" into your active hours, allowing for updates as fast as every 20 seconds during the day.
- **Threshold Throttling:** A configurable "Throttle Threshold" (default 20 calls) reserves quota for external automations and manual actions. When remaining quota hits this floor, background polling pauses instantly.
- **Proxy Support:** Fully compatible with local `tado-api-proxy`. The system adapts polling speed to the higher quota limits provided by the proxy.
- **Safety Reserve:** 2 calls are reserved for the ±1h window around the expected reset time to handle reset-time variability.

## 🚿 Unleashed Platforms

- **AC Pro Control:** Unlocks Fan Speed and Horizontal/Vertical Swing controls for v3 AC controllers that are often missing in standard integrations.
- **Professional Hot Water:** A dedicated `water_heater` platform with `boost` functionality and schedule synchronization. v3 uses the Classic API overlay endpoint; Tado X uses `programmer/domesticHotWater/` endpoints (boost, resumeSchedule).
- **Timetable type:** Per-zone and home-wide select for ONE_DAY / THREE_DAY / SEVEN_DAY via classic `zones/{id}/schedule/activeTimetable`. Classic heating and hot water; Tado X heating rooms experimental (same v2 URI, not Hops). Writes and refresh buttons go through the command debounce/batch window (1 GET/PUT per zone). `full_manual_poll` / `manual_poll` type `all` also fetches timetable types and weekly plans.
- **Set schedule:** `tado_hijack.set_schedule` writes the daily time blocks to Tado (app-free). Day picker follows the timetable: `one_day` none (Tuesday fails), `three_day` Mon-Fri/Sat/Sun, `seven_day` Mon..Sun (Tue+Wed). Payload is `blocks` or a Home Assistant `schedule` helper. Classic PUT per dayType; Tado X POST Hops `rooms/{id}/schedule`. Debounced per zone+day.
- **Zone plan calendar:** One read-only `calendar` entity per schedule-capable zone (`Tado <room> Weekly Plan`). Opening the calendar is cache-only (0 calls). Fetch via per-room `refresh_zone_plan`, home `refresh_all_zone_plans`, or `full_manual_poll` / `manual_poll` type `all` or `schedule` (1 GET per zone when timetable type is cached, 2 if not). Cache is persisted; `set_schedule` updates it only after a successful write and leaves it unchanged on error. Not part of periodic poll.
- **Offset auto-calibrate:** Home select `offset_cal_interval`, home button `calibrate_offsets`, and per-room config button `calibrate_offset`. Only zones with a linked `zone_temp_source`. Offset = thermostat - TRV raw. Clock slots from local midnight in 3h steps, or once when quota reset is detected. Auto Quota subtracts scheduled PUTs from the daily polling budget (`offset_cal_total` in reserved cost). Per device PUT, not bulk.
- **Presence Lock:** Force the home into "Home" or "Away" mode via a simple switch, overriding Tado's own geolocation engine when needed.
- **Presence-Aware Overlays:** Set a temperature that is tied to the current presence state. If the home transitions from Home -> Away, the overlay automatically cancels.

## 🔗 Device Unification (v3 Classic & Tado X)

Tado Hijack doesn't just add new devices; it **augments** your existing ones.
- **V3 (HomeKit):** The `DeviceLinker` matches Tado cloud serial numbers against the HA device registry and injects cloud features (Child Lock, Offset, Battery, Dazzle) directly into existing HomeKit device entries.
- **Tado X (Matter):** When Matter exposes the device serial (same `VA…` as the cloud), the same injection mechanism applies — cloud features merge onto the Matter device. If no serial is available, features stay on separate Hijack devices with manual source linking.
- **The result:** One single device in Home Assistant that has both local-instant control and advanced cloud features — for both generations.
