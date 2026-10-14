# Features

What Tado Hijack does, checked against `custom_components/tado_hijack/`. The front door, including service examples, is `README.md`.

One home is one generation. **Classic** is the V2 gateway (`GW`) and the V3 bridges (`IB01`, `GW01`), with HomeKit on V3. **Tado X** is Bridge X (`IB02`) and Wireless Receiver X (`PR04`), with Matter. `TR04` uses the same Wireless Receiver X name and is a room device, not a setup bridge.

---

## Local control and the cloud

Turn off the official Home Assistant Tado integration. It polls the same account. Hijack replaces it. Next to Hijack the room protocols are HomeKit (classic V3) and Matter (Tado X).

HomeKit or Matter keeps the room setpoint. Hijack does not copy an ordinary local temperature change to Tado. A local `climate.set_hvac_mode` of `auto` on a linked climate resumes the Tado schedule. Anything else is stored as an optimistic manual overlay.

Cloud entities that belong on a valve (child lock, offset, battery, connection) are linked onto the HomeKit or Matter device when the serial matches. Home Assistant 2026.8 keeps a separate registry device per integration, so the Hijack device page can remain. Zone entities stay on the Hijack zone device.

Full cloud mode (default off) creates a Hijack heating climate for classic heating zones, and a heating climate for every Tado X room. Classic air conditioning is created either way. The Tado X climate entity uses `off`, `heat`, and `auto`. It has no fan and no swing. `async_set_ac_setting` on Tado X does nothing.

Matter, on the surveyed Smart Thermostat X ([matter-survey.org](https://matter-survey.org/device/tado-smart-thermostat-x-4942-2), vendor 4942, product 2, 4 October 2026), implements heating and humidity. Cooling, occupancy, and weekly schedules are not implemented.

---

## Quota

The budget is `RateLimit-Policy` (`q=`) and `RateLimit` (`r=`), parsed in `helpers/parsers.py`. Classic headers arrive with those names. Hops sends them in lowercase; the client title-cases them before the same parser. One `RateLimitManager` reads both. There is no second Hops quota tracker, and the code does not read `x-ratelimit-*`.

Until a header arrives, remaining is the guess `100` and the limit is `0`.

`API_QUOTA_STANDARD` (`1000`) is used once: the first full poll runs only when the header limit is at least 1000. `API_QUOTA_PROXY` (`3000`) is never read. A proxy URL does not select a built-in allowance. It raises the minimum automatic interval to 120 seconds (otherwise the floor is 5 seconds, default configured minimum 20) and it is the only mode that applies jitter.

Published numbers, so a header has a source:

- Tado help center, 27 January 2026: 100 requests/day, and 20,000 with Auto-Assist or AI Assist. <https://help.tado.com/en/articles/12165739-limitation-for-rest-api-usage>
- Tado on r/tado, 26 May 2026: they maintain 1,000 requests/day and plan to reduce that further. Auto-Assist and AI Assist stay at 20,000. <https://www.reddit.com/r/tado/comments/1to1f0n/important_update_api_rate_limits_the_home/>

The integration does not switch behavior between those figures. When `q=` changes, the interval changes.

### How the interval is chosen

Order in the coordinator: unknown limit, then throttle, then the economy window if it is enabled, then auto quota.

- Unknown limit (`limit <= 0`): at least the base scan interval (default 1800 seconds) and at least 300 seconds.
- Throttle: remaining below `throttle_threshold` (default 20). Threshold `0` never throttles. Status is `rate_limited` at remaining 0, `throttled` while still above 0, otherwise `connected`. With "pause when throttled" off, the interval is 900 seconds. With it on, non-forced polls are skipped and the wait is at least 900 seconds or the time until reset.
- Economy window: off by default, 22:00–07:00 local, interval 3600 seconds. Interval `0` skips the poll inside the window. While the window is on, the night interval is used in those hours and the remaining budget is spread over the other hours. With the window off there is no daytime/night split.
- Auto quota at `0` keeps the base scan interval. The default is 80% of the usable budget.

Usable budget is `(limit − background over 24 h − threshold)`, scaled by the percent, then reduced by inferred use outside this integration, by background calls still to come, and by the safety reserve (default 2). The zone poll is counted as 1 call when spacing the day. Background is presence (default every 12 h), a slow poll every 24 h, and classic offset GETs when that interval is above 0 (default 0). The slow-poll estimate is 2 for both generations, plus one capabilities GET per classic zone. The Tado X fetch itself is one `roomsAndDevices`. Classic slow poll is `GET /zones` and `GET /devices`. Tado X has no capabilities call. Classic early start is not part of that reserve: the switch state is kept, and a GET runs only when that state is unknown or a full refresh asks for it.

A reset is remaining going up to at least 80% of the limit. The first sample is not a reset. Two consecutive resets in the same UTC hour confirm the pattern (five are stored). Until then the expected time is 11:30 UTC, shown in Europe/Berlin: 12:30 CET, 13:30 CEST. The safety reserve is spread across the three hours centered on that hour.

### What a poll fetches

Room state when the interval is due. On Tado X that includes the hot-water programmer, unless a previous response said it is missing or not controllable; that result is cached and later polls skip the GET.

Presence, metadata, and (classic, interval > 0) offsets run on their own clocks. Away configuration, the active timetable, and the weekly plan do not. A button or `manual_poll` invalidates them. Tado X skips offsets, away, and capabilities. A timetable refresh on Tado X returns immediately.

`manual_poll` types: `all`, `zone`, `metadata`, `offsets`, `away`, `capabilities`, `presence`, `timetable`, `schedule`. An `entity_id` limits offsets, away, timetable, schedule, and capabilities to that zone. `all`, `zone`, `metadata`, and `presence` still refresh the wider track. No config entry means every Hijack home.

There is no retry/backoff loop.

---

## Batching

Debounce defaults to 5 seconds (minimum 1). A new command rearms the timer. The same queue key keeps the latest command, except `flow_temp`, where max flow temperature and auto-adaptation are merged onto one body. After a key is taken, the worker waits 1 second and drains the queue.

Classic heating, air conditioning, and hot-water **overlays** in one batch share `POST /homes/{id}/overlay`. Heating and air-conditioning **resumes** share `DELETE /homes/{id}/overlay?rooms=`. A hot-water resume cannot use that DELETE; it is `DELETE /homes/{id}/zones/{zone}/overlay` per zone. `set_hot_water_zone_overlay` (PUT per zone) has no caller.

Tado X sends `POST quickActions/resumeSchedule`, `boost`, or `allOff` when the batch is an explicit quick action, or when it contains every active heating room and nothing else (all resume, all off, or all boost at 25°C within 0.1°C). Any other room is `POST rooms/{id}/manualControl` or `DELETE rooms/{id}/manualControl`. There is no multi-room manual control. Hot water is not part of that batch. It is an immediate `POST programmer/domesticHotWater/resumeSchedule` or `POST .../boost` with `{"boost":"ON"|"OFF"}`.

Not in the overlay call, on either generation: schedules (one HTTP per day slot), timetable switches, presence (`presenceLock` on the classic v2 API, including for a Tado X home), meter readings (Energy IQ `POST homes/{id}/meterReadings`), identify, dazzle, early start, away temperature, and open-window configuration. Classic offsets are queued PUTs, one per serial. Tado X offset writes from the number and from calibration PATCH immediately and do not join the child-lock fusion. A child lock and a **queued** offset on the same Tado X device can share one PATCH.

`refresh_after` on a queued room command ignores the global "refresh after resume" option. That extra poll runs for `auto` only when the zone is air conditioning or classic hot water. A classic duration schedules it at expiry. `next_block` and `presence` do not poll early. Tado X hot water does not consult the flag: resume, boost, and off each schedule a zone poll after the programmer call. A duration hold sends immediately, so that poll runs immediately, again on the 50-minute boost, and again when the hold ends.

Boost-all, off-all, and resume-all can be skipped when both suppression switches are on and every targeted zone already matches. Individual writes use the call suppression only.

---

## Indoor climate

Dew point, mold, absolute humidity, and ventilation are computed in `helpers/climate_physics.py` from temperatures and humidities already in memory.

Magnus constants: `a = 17.67`, `b = 243.5`. Dew point is `Td = b·γ / (a − γ)` with `γ = aT/(b+T) + ln(rh/100)`. Absolute humidity uses saturation vapour pressure from the same constants and the factor `216.7`.

Mold uses room temperature minus dew point. Relative humidity at or below 0 is `none`. Above 7°C is `none`, above 5°C is `low`, above 3°C is `medium`, otherwise `high`. The binary sensor is on for `medium` and `high`. Dew point and mold default to on.

Absolute humidity and ventilation exist only when an outdoor weather entity is set. Ventilation is on when indoor absolute humidity exceeds outdoor by the threshold (default 1.0 g/m³). The weather entity is a Home Assistant `weather` entity. This integration does not create a Tado weather entity.

Room temperature (`_get_room_temp_celsius`): the temperature-source select when it is not `device`, else the full-cloud climate or the HomeKit/Matter climate in `_climate_to_zone` (`current_temperature`), else the zone inside temperature. Room humidity (`_get_room_rh`): the humidity-source select when it is not `device`. A climate selected there is read as `current_humidity`. On `device`, humidity is this integration's humidity sensor, then the zone humidity. The serial match does not read the Matter climate's humidity. Offset calibration is separate and runs only with an explicit temperature-source entity.

Heating power is the zone percentage from the room poll. The home binary `heating_demand` is on when any heating zone's power is above 0. That is not a boiler-modulation reading.

---

## Offset calibration

`raw = tado_inside − current_offset`, then `desired = reference − raw`, clamped to −10…10°C, step 0.1. The inside temperature is the zone sensor. The reference is the linked HA entity (`current_temperature`, otherwise the state). One write per measuring device (`INSIDE_TEMPERATURE_MEASUREMENT`). The device Tado is using as the zone sensor is the one that moves the valves.

A change smaller than the threshold, and smaller than 0.1°C, is not written. The home threshold defaults to 0.5°C. A zone value above 0 replaces it. Setting the zone number to 0 clears the override.

The home interval defaults to `off`. Choices: `off`, `3h`, `6h`, `9h`, `12h`, `15h`, `18h`, `21h`, `24h`, `on_reset`, `threshold`. Hour slots are local time at minute 0. A zone select of `inherit` uses the home choice. `on_reset` runs from the reset detector only when the **home** interval is `on_reset`; it then calibrates every linked zone and does not consult a zone override. `threshold` listens to the linked temperature and window entities and waits 5 seconds.

An open window skips the write. After it closes, settle defaults to 300 seconds. A threshold write starts a send cooldown, also 300 seconds. An hour slot that fell during either wait runs once both have passed.

The offset is read from the cloud only when none is known. The periodic offset poll is classic-only and defaults to off. Calibration itself uses the last zone poll and the HA sensor.

Throttling skips interval, threshold, and manual calibration. A calibration triggered by the quota reset is not skipped for throttle.

---

## Windows

The zone selects store a `binary_sensor` and a mode, `direct` (default) or `timeout`.

`direct`: open turns the zone off, close resumes the schedule. `timeout` does that and also resumes when the native open-window timeout elapses while the contact is still open. A timeout of 0 is not armed, so disabled open-window detection makes `timeout` behave like `direct`. `on` and `open` count as open. `unavailable` and `unknown` are ignored. A contact that is already open at startup is applied.

Cloud resumes are batched by default for 120 seconds. A second zone does not restart the timer. Local HomeKit and Matter climates change immediately; the cloud command is what waits. Snapshots are stored under `window_pre_states`.

The native timeout number is minutes, 0–1439, on classic heating zones that report open-window support. Five minutes or more enables it and sends `timeoutInSeconds`. Tado X rooms do not get this number: the room snapshot has no such field. The Hops open-window call exists and ignores a timeout. The external contact selects are still created for Tado X rooms.

---

## Offline valves

`LocalRecoveryQueue` stores the last intent per unavailable valve serial. Replay waits 0.2 seconds.

A stored resume, or an intent that has expired, is sent to the cloud again only when `recovery_cloud_replay` is on (default). Otherwise the returning climate is set locally (`set_off` or `set_temperature`) and the cloud is not called again. The cloud command was already sent when the intent was captured.

Zone 9001 has no valve serials on the room list, so a hot-water capture stores nothing unless a device is mapped there. Replay does not call the hot-water programmer.

---

## Schedules and calendars

Classic timetables are `one_day` (id 0), `three_day` (id 1), and `seven_day` (id 2). The zone select and the home select (which stays on the home device, not the bridge) write `activeTimetable`. Tado X has no timetable switch. Those entities are removed at startup on a Tado X entry. The week is the seven weekdays.

`set_schedule` queues one command per day slot. Classic is one PUT of that day's blocks, plus one PUT of `activeTimetable` when `activate` is set. Tado X is one POST of `rooms/{id}/schedule` per weekday. `one_day`, `three_day`, and `activate` do not apply to Tado X. `all_days` writes every slot of the chosen timetable. `geolocation_override` is copied onto classic blocks only.

The last block of a day ends at `00:00` on classic and `24:00` on Tado X. Both tokens parse.

The calendar reads `schedule_blocks_cache`. Opening it does not call Tado. Fetch with the zone or home plan button, or `manual_poll` type `schedule`. Classic heating, hot water, and air conditioning can have a plan. Tado X rooms can. Zone 9001 cannot. The calendar does not write.

When the last config entry unloads, every service including `set_schedule` is removed.

---

## Hot water

Classic hot water is a real zone. The water heater supports `auto`, `heat`, and `off`. Target temperature exists only when capabilities include `temperatures`. The entity's heat and off paths, and the target-temperature number, do not pass duration or overlay. `set_water_heater_mode` does: heat and off go through `async_set_zone_overlay` with duration, overlay, and `refresh_after`. `auto` resumes.

Tado X hot water is virtual zone `9001`, created when `GET programmer/domesticHotWater/state` is controllable (state present and not `NONE`). Modes on the entity: no overlay is `auto`, `BOOST_ON` is `heat`, any other overlay is `off`. There is no temperature. `supports_temperature` is false for 9001. `binary_sensor.hot_water_schedule` is on while `state` is `SCHEDULE_ON`, off otherwise.

Tado ends a boost after about 60 minutes and ignores a timer in the boost body. `helpers/hot_water_duration.py` holds boost or off until a deadline. A boost with time left is sent again 50 minutes after the last send. At the deadline the hold returns to the schedule, or to off when the programmer state was `BOOST_OFF`. A failed send retries after 60 seconds. The timer callback runs on the event loop. The plan is stored under `hot_water_duration` and restored for a Tado X home at the end of setup. Shutdown cancels the timer and leaves the storage in place.

Arming: the service passes `duration`, or `overlay_mode` of `next_block` while the programmer state starts with `SCHEDULE_` and `nextStateChange` is still in the future. Otherwise the boost or resume is sent immediately. `presence` raises `ServiceValidationError` (`Tado X hot water cannot end when presence changes`). A duration is parsed into overlay mode `timer` before that check, so a call that also says `presence` does not reach the error. The hold is armed, and the first boost or off is sent at once.

`auto` and `off` raise if a temperature is sent. The service schema does not fill one in. When `heat` omits temperature, the overlay path uses 21°C for heating, 22°C for air conditioning, and 30°C for classic hot water. The classic water-heater card does not use that path: it passes the last target it stored, and `async_set_hot_water_heat` then prefers the current Tado setting, then 30°C. Heating overlays are capped at 25°C, air conditioning at 30°C, hot water at 65°C. The heating selector still goes up to 30°C; the cap is applied when the overlay is built.

---

## Presence and home mode

These are different.

Presence mode is `HOME`, `AWAY`, or `AUTO`. `AUTO` means the presence lock is off (geofencing). Home and away set the lock. The select writes the classic v2 `presenceLock` API for both generations: PUT `{"homePresence": ...}`, or DELETE for `AUTO`. The effective binary is on when presence is `HOME`. It does not look at the lock. There is no phone device tracker.

Home mode aggregates heating and air-conditioning rooms into `schedule`, `off`, `boost`, `manual`, or `mixed`. Hot water is not in the aggregate. Classic boost is a target within 0.1°C of 25°C. Tado X boost is `boost_mode` set on the room.

---

## Flow temperature

Opt-in, default off, Tado X only. `GET settings/flowTemperatureOptimization` and a 404 cache live on `TadoXMapper.async_fetch_unified_data`. No poll calls that method. Zone and metadata fetches do not request the payload, so `flow_temp` stays empty and the max-flow number and the auto-adaptation switch are not created.

If a write is invoked anyway, both fields share the queue key `flow_temp` and one PATCH. A failed PATCH rolls back to the first server value of each field.

---

## Other controls

- **Child lock:** a device switch when `child_lock_enabled` is not `None`. Classic is one call per serial. Tado X can share a device PATCH with a queued offset.
- **Dazzle and early start:** classic only. Tado X marks both unsupported. Early start keeps the switch state. A GET runs only when that state is unknown, or on a full refresh.
- **Away temperature:** classic heating. At or below 5°C the number shows 0 and the away setpoint is cleared.
- **Identify:** both generations, only in full cloud mode.
- **Meter readings:** Energy IQ, not Hops. The schema marks `config_entry` required. The handler sends the reading to every coordinator when the field is missing.
- **Polling switch:** starts on at every load and is not stored.
- **Refresh token:** when a refresh rotates the token, `persist_refresh_token` writes it to the config entry. The same helper runs after a poll and does nothing if the entry already has that value.
- **Classic device lookup:** `devices_meta` is keyed by `short_serial_no`. Device entities look up the full serial. When those differ, battery, connection, and child lock read no row. Tado X keys the same map by the full serial.
- **Dummy zones:** only when the environment variable `TADO_ENABLE_DUMMIES` is set. Not a config option.

---

## Privacy

Logs go through the redacting logger. Serials keep the first 2 characters, `...`, and the last 5. `shortSerialNo` is removed entirely. Tokens, refresh tokens, email, username, password, home id, user id, coordinates, MAC addresses, and bearer tokens are removed. Diagnostic entity ids keep the domain, the role, and the zone number, and hash the home slug.

---

## Proxy

`api_proxy_url` rewrites classic and Energy IQ requests. The proxy injects authentication; the handler does not send a bearer token on those calls. Hops is a separate client. Jitter and the 120-second floor apply when the proxy URL is set. The daily budget is still the header the proxy returns.
