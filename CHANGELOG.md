## [5.5.0-dev.5](https://github.com/banter240/tado_hijack/compare/v5.5.0-dev.4...v5.5.0-dev.5) (2026-05-15)

### 🐛 Bug Fixes

* fix(device-linker): guard against non-string manufacturer in device registry

- add _is_tado_device() helper that checks isinstance before .lower(),
  centralising the Tado manufacturer check (DRY)
- use _is_tado_device() in _build_device_cache() and get_climate_entity_id()
  replacing the bare device.manufacturer.lower() calls that raised
  AttributeError when HA stores manufacturer as int
- fix .gitignore to match dev/local as symlinks (trailing slash only
  matches real directories)

## [5.5.0-dev.4](https://github.com/banter240/tado_hijack/compare/v5.5.0-dev.3...v5.5.0-dev.4) (2026-05-13)

### 🐛 Bug Fixes

* fix(ac): add light field to AC power-on overlay payloads

- extract _build_ac_fan_fields, _build_ac_swing_fields and
  _build_ac_light_fields from _ensure_ac_setting_fields to
  reduce function complexity and satisfy Sourcery quality check

- _build_ac_light_fields: include light field when the mode
  capability exposes it; defaults to "OFF" if present in the
  allowed values, otherwise first listed value

Resolves 422 errors for AC zones whose capabilities require a
light field in the overlay setting (e.g. "light not in supported
light [OFF, ON]").

## [5.5.0-dev.3](https://github.com/banter240/tado_hijack/compare/v5.5.0-dev.2...v5.5.0-dev.3) (2026-04-30)

### 🐛 Bug Fixes

* fix(ac): populate mode, fanSpeed and swing for AC power-on overlays

- add _ensure_ac_setting_fields coordinator helper: fetches cached
  capabilities and auto-populates fanSpeed/Level and swing fields
  when additional_setting_fields is not explicitly provided; called
  from async_set_zone_overlay and per-zone from async_set_multiple_zone_overlays

- fix _execute_set_mode in services.py: map operation_mode to ac_mode
  (HEAT/COOL/DRY/FAN) and forward to async_set_multiple_zone_overlays;
  mode field was never set for this service path

- single-toggle swing fallback: use current state, last-seen cache,
  then "OFF" (tadoasync does not expose swings in mode capabilities)

Resolves 422 errors for AC zones in standby that were missing mode,
fanSpeed and swing fields in overlay payloads.

## [5.5.0-dev.2](https://github.com/banter240/tado_hijack/compare/v5.5.0-dev.1...v5.5.0-dev.2) (2026-04-21)

### 🐛 Bug Fixes

* fix(quota): prevent reset-poll runaway loop and sync timer on detected reset

Replace max(1s, delay) in schedule_reset_poll with an explicit 24h fallback
when delay is invalid, preventing a tight API-quota-burning loop on stale
initial_target. Reschedule the reset poll immediately when a quota reset is
detected via regular polling so the timer stays in sync without waiting for
the next scheduled fire. Also refactor zone overlay/resume redundancy checks
into dedicated helpers for clarity.

## [5.5.0-dev.1](https://github.com/banter240/tado_hijack/compare/v5.4.1-dev.2...v5.5.0-dev.1) (2026-04-17)

### ✨ New Features

* feat(sensors): add zone_mode and home_mode sensors (#86)

Adds per-zone operating mode sensor (schedule/off/boost/manual) for
both Tado Classic and Tado X generations, and a home-level aggregate
sensor that returns "mixed" when zones are in different modes.

No additional API calls - reads from already-fetched zone_states.
Boost detection for Classic uses the existing 25°C temperature heuristic
consistent with action_provider.py.

Co-authored-by: laurensdehoorne <laurensdehoorne@users.noreply.github.com>


### 🐛 Bug Fixes

* fix(diagnostics): increase serial number redaction suffix to 5 chars

Prevents false duplicate-device appearance in diagnostics output when
two serials both end in the same 4 digits (e.g. both ending in "1234").

* fix(tadox): resolve device-to-zone mapping and pass termination to manual control (#89)

Fix _resolve_device_to_zone() using zone.id which doesn't exist on
HopsRoomSnapshot (Tado X zones use room_id). Iterate zones_meta.items()
and use the dict key as zone_id instead.

Fix TadoXExecutor ignoring the termination dict from the merged overlay
data. Extract termination_type and duration_seconds and pass them to
async_set_manual_control so TIMER overlays created via set_mode duration
parameter actually expire as intended.

## [5.4.1-dev.2](https://github.com/banter240/tado_hijack/compare/v5.4.1-dev.1...v5.4.1-dev.2) (2026-04-14)

### 🐛 Bug Fixes

* fix: fix quota overconsumption, redundancy filter regression, and DE translations

Quota (fix):
- get_next_reset_time() anchored on now.replace(hour, minute) instead of
  last_history_entry + 1 day, collapsing adaptive interval to 20s minimum
  after every observed reset
- get_initial_target() cached a stale past timestamp and never refreshed,
  driving seconds_until_reset negative for all generations
- TadoX rate limit counter stayed frozen because hops.tado.com calls never
  went through the V3 handler; TadoXApi now captures ratelimit headers and
  exposes them via rate_limit_data. UnifiedDataProvider gains
  get_rate_limit_source() so the coordinator stays generation-agnostic

Redundancy (fix):
- _filter_presence and _filter_simple_attributes compared against the
  optimistic already-patched state, silently dropping every command when
  suppress_redundant_calls was enabled
- Debounce replacements overwrote the rollback reference with the optimistic
  intermediate state; preserve_rollback_state() now carries the original
  confirmed API state forward through replacements
- RESUME_SCHEDULE commands for zones already in schedule are now filtered
  when suppress_redundant_buttons is enabled

Redundancy (refactor):
- Extract _merge_keyed() in CommandMerger replacing 5 identical merge methods
- Replace 6x _filter_simple_attributes() calls with a config loop
- Add _suppress_calls/_suppress_buttons properties on TadoApiManager

i18n: fix raw key names shown as labels in Auto API Quota config section

## [5.4.1-dev.1](https://github.com/banter240/tado_hijack/compare/v5.4.0...v5.4.1-dev.1) (2026-04-11)

### 🐛 Bug Fixes

* fix(quota): fix DST-driven reset prediction drift and CET->UTC migration

Root cause: quota reset history was stored in Europe/Berlin local time.
After CET->CEST, the learned reset hour shifted by 1h in UTC (e.g.
12:30 Berlin stored as 13:30 CEST = 11:30 UTC instead of 12:30 UTC),
causing the integration to enter quota-conservation mode ~30 min early.

reset_window_tracker.py:
- record_reset: normalize history in UTC instead of Berlin tz
- _update_learned_window: compute recent list once; detect pattern break
  (two newest entries disagree on UTC hour) and reset to 1 entry so the
  tracker re-learns cleanly; remove redundant same_hour_resets filter
- _default_utc_window: new helper to convert Berlin-local defaults to
  UTC respecting the current DST offset - single source of truth
- get_expected_window: use _default_utc_window so "default" confidence
  also returns correct UTC values, not Berlin-local hour as UTC
- get_next_reset_time: use _learned_window directly (learned and
  single_observation) so the proactive poll is never scheduled from the
  Berlin-local default hour treated as UTC; fall back to _default_utc_window
- ResetWindow.__str__: convert UTC hour to Berlin local for display
- to_dict: add data_version=2, drop serialized learned_window
- load_dict: remove inline migration (handled by config entry v10);
  fix duplicate initial_target parse; always re-derive learned_window
- DATA_VERSION = 2 class constant for versioned storage migration

quota_math.py:
- is_in_reset_safe_window: compare UTC hours instead of Berlin hours;
  when no explicit hour given, derive expected UTC hour from the
  Berlin-local default respecting the current DST offset

coordinator.py:
- async_setup: reschedule reset poll after loading stored tracker so
  the proactive poll fires at the correct learned time after a restart
  (previously scheduled in __init__ with an empty tracker)

migration.py / __init__.py / config_flow.py:
- _v10 (async): one-time migration of stored reset_tracker history from
  Berlin tz to UTC for existing users
- async_migrate_entry: await coroutine migration steps
- config entry VERSION bumped 9 -> 10

## [5.4.0](https://github.com/banter240/tado_hijack/compare/v5.3.0...v5.4.0) (2026-04-07)

### ✨ New Features

* feat(core): presence mode select, redundancy checker fix, version logging, and climate fixes

Replaces the binary away_mode switch with a three-option presence_mode
select entity, fixes false-positive redundancy drops that silently
blocked hot water and zone overlays, adds toggleable version prefixing
in logs, and restores auto_target_temperature for heating zones.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏠 PRESENCE MODE SELECT ENTITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Replaces binary away_mode switch with select.tado_{home}_presence_mode:
- HOME: PUT presenceLock with homePresence=HOME
- AWAY: PUT presenceLock with homePresence=AWAY
- AUTO: DELETE presenceLock (restores Tado geofencing)

AUTO was previously inaccessible from HA, requiring manual API interaction
to restore automatic presence detection after a manual override.

Update automations targeting the old switch to use select.select_option:

  target:
    entity_id: select.tado_{home}_presence_mode
  data:
    option: home   # or: away / auto

Migration:
- Extracted all migration steps from __init__.py into helpers/migration.py;
  async_migrate_entry replaced with a simple loop over MIGRATION_STEPS.
- Migration v8 removes the legacy away_mode switch from the entity registry.
- Migration v9 re-runs the removal for installs where dev.1 already set
  VERSION=8, causing v8 to never execute.
- Config flow VERSION bumped to 9.
- Entity ID fix: was using bridge serial instead of home slug.

Note: restoring AUTO presence requires a Tado Auto-Assist subscription.
A persistent notification with the home name is shown if the API returns
HTTP 422 (Auto-Assist not available).

## [5.3.0](https://github.com/banter240/tado_hijack/compare/v5.2.0...v5.3.0) (2026-04-03)

### ✨ New Features

* feat(tadox): sensor fixes, full diagnostics, and comprehensive documentation overhaul

This commit consolidates multiple critical fixes and feature expansions across the integration:

1. **Tado X Sensors & Fallbacks:**
   - Fixed missing temperature fallback by allowing Tado X to read
     `sensor_data_points.inside_temperature.value` from the cloud state via duck-typing.
   - Fixed heating power sensor displaying an `unknown` state by correctly reading

## [5.2.0](https://github.com/banter240/tado_hijack/compare/v5.1.0...v5.2.0) (2026-04-01)

### ✨ New Features

* feat(core): comprehensive indoor climate intelligence, meter reading service, and bug fixes

Introduces indoor climate intelligence with dynamic source selection,
a meter reading service for Tado Energy IQ, and a series of targeted
bug fixes across quota management, services, Tado X capability inference,
entity ID generation, and tooling alignment.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 INDOOR CLIMATE INTELLIGENCE & SENSORS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Advanced Climate Metrics:
- Added sensors for dew point, absolute humidity, and acute mold risk levels across all hardware generations.
- Implemented outdoor absolute humidity diagnostic sensor (g/m3).
- Centralized atmospheric physics into a shared module.

Dynamic Source Selection:
- Implemented per-zone Select entities to choose custom Temperature & Humidity sources.
- Robust 3-layer fallback system: User Select -> Climate Entity -> Cloud API.

Universal Support:
- Unified zone property access across Classic (v3) and Tado X via TadoUnifiedZone interface.
- Standardized climate entity capabilities.
- Updated binary sensor states to user-friendly Yes/No labels.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛠️ METER READINGS & SERVICES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Energy IQ Integration:
- Implemented `tado_hijack.add_meter_reading` service to upload meter readings to the Tado cloud (v3 Classic only).
- Patched upstream `tadoasync` meter readings endpoint to fix 403 Forbidden errors.
- Fixed timezone handling to use local HA time instead of UTC for correct day assignments.

Multi-Account Services:
- Fixed service registry bug where services from multiple config entries would
  overwrite each other, causing actions to only work for the last registered account.
- Updated services.yaml with corrected field definitions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🐛 BUG FIXES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Quota Management:
- Fixed progress_remaining exceeding 1.0 on fresh installs (initial target pushed to next day).
- Fixed budget collapse at day boundary where all consumed calls were misattributed
  as external usage, collapsing the polling budget before the actual quota reset.
- Introduced static initial_target to prevent runaway next reset target drift.
- Fixed calculate_remaining_polling_budget to derive polls_done from API values only,
  making the budget restart-proof and eliminating double-penalty on external calls.
- Fixed calculate_safety_reserve_interval to distribute over the full 3-hour safe
  window (was 1 hour, causing 3x too-frequent polling during the reset window).
- Fixed available_now to cap against effective_threshold instead of throttle_threshold.
- Fixed diagnostics user_so_far/user_excess: zone polls were incorrectly attributed
  as external user calls; now uses tracked poll counter.
- Fixed _update_learned_window: single_observation branch was unreachable dead code.
- Track actual polling calls in _polling_calls_today per fetch, reset on quota reset.

Coordinator & API:
- Improved error handling for transient API errors, falling back to last known
  good data to keep entities available.
- Fixed water heater target temperature hidden in AUTO mode for OpenTherm systems.
- Fixed away temperature never displaying or persisting correctly on startup.

Tado X:
- Infer INSIDE_TEMPERATURE_MEASUREMENT capability from device data when not

## [5.1.0](https://github.com/banter240/tado_hijack/compare/v5.0.2...v5.1.0) (2026-03-13)

### ✨ New Features

* feat: extend bulk zone actions to AC zones, targeted manual_poll fetch, and water heater fix

feat(climate): extend bulk zone actions to include AC zones
resume_all, turn_off_all and boost_all previously only targeted HEATING
zones. AC zones (e.g. heat pumps) are now included in all bulk actions.
Zone type is resolved automatically per zone from metadata so the correct
overlay type is sent for both HEATING and AIR_CONDITIONING zones.
HOT_WATER zones remain excluded.

feat: targeted single-entity fetch for manual_poll
Extends manual_poll service with optional entity_id to allow targeted,
per-entity data refreshes instead of re-fetching all devices/zones:

- offsets: 1 API call for the specific device (vs. N devices)
- away_config: 1 API call for the specific zone (vs. N zones)
- capabilities: uses existing lazy cache, drops only that zone's entry
- bulk-only types (zone, metadata, presence, all): fall back to full refresh

DRY approach: _fetch_offsets/_fetch_away_config now delegate per-entry
work to _fetch_offset_for(serial) / _fetch_away_config_for(zone_id),
which are also the targeted fetch paths. EntityResolver gains
get_serial_from_entity() to resolve device entity → serial_no.

Usage:
  service: tado_hijack.manual_poll
  data:
    refresh_type: offsets
    entity_id: number.bedroom_temperature_offset   # optional

fix: add debug logging for bulk zone actions and fix water heater optimistic state

## [5.0.2](https://github.com/banter240/tado_hijack/compare/v5.0.1...v5.0.2) (2026-03-05)

### 🐛 Bug Fixes

* fix(climate): AC and hot water climate entities always created regardless of full_cloud_mode

⚠️ UPGRADING FROM v4.x? READ THIS:
- Entity unique_ids changed → all entities will be recreated. Delete and
  re-add the integration to avoid duplicates.
- Minimum Home Assistant version is now 2024.11.0.
- Generation selection (Classic V2/V3 or Tado X) is now required on setup.
- Existing installs are migrated automatically on first load.
See v5.0.0 and v5.0.1 release notes for full details.

full_cloud_mode should only gate HEATING climate entities since those zones
are handled by HomeKit/Matter when disabled. AC zones have no HomeKit support
and their climate entities must always be created.

- V2/V3 AC climate entities: always created
- V2/V3 HEATING climate entities: only when full_cloud_mode=True
- Tado X climate entities: only when full_cloud_mode=True (Matter handles otherwise)
- Hot Water: unaffected, handled by water_heater platform

Users on v5.0.x missing AC climate entities: reload the integration,
no reinstall required.

## [5.0.1](https://github.com/banter240/tado_hijack/compare/v5.0.0...v5.0.1) (2026-03-05)

### 🐛 Bug Fixes

* fix(config_flow): quota interval and safety reserve not persisted on save

Both values were extracted from the wrong section in _flatten_section_data,
causing them to silently reset to defaults on reopen. Also fixes a float
cast issue for safety reserve and updates mypy hook to python3.14.


### 📚 Documentation

* docs(core): upgrade notice for v5.0.0 breaking changes

For users upgrading from v4.x directly to v5.0.1: v5.0.0 introduced
breaking changes that require attention before upgrading.

⚠️ IMPORTANT — READ BEFORE UPGRADING FROM v4.x
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Entity unique_id format changed:
- Old: {entry_id}_{suffix}
- New: {entry_id}_zone_{zone_id}_{suffix}
- Effect: ALL entities will be recreated on first start after upgrade
- Action: Delete and re-add the integration to avoid duplicate entities

Minimum Home Assistant version: 2024.11.0 (required for Matter support)

New mandatory setup step:
- Generation selection is now required during initial config
- Choose "Tado V2/V3 (Classic API)" or "Tado X (Matter Bridge)"
- Existing installs will be migrated automatically on first load

See full v5.0.0 release notes for details on new features (Tado X support,
V2 bridge, full cloud mode, multi-account, redundancy suppression).

* docs(quota): document adaptive reset window learning (shipped in v5.0.0)

This feature was included in v5.0.0 but omitted from the release notes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 ADAPTIVE QUOTA RESET WINDOW LEARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tado's daily API quota does not reset at a fixed time — the exact hour varies
per user account (observed: 7:30, 12:04, 14:xx, etc.). The integration now
learns your specific reset schedule automatically.

How it works (helpers/reset_window_tracker.py):
- Every detected quota reset is recorded with its timestamp
- Timestamps are normalized to X:30 to group resets within the same hour
- After 2 consecutive resets at the same hour → pattern is adopted ("learned")
- Single observation → stored but not adopted (may be anomaly)
- No pattern yet → fallback to default window (12:30)

Quota budget is then distributed relative to the learned reset time:
- Planning horizon: always minimum 20h ahead (conservative)
- Safety reserve: adaptively spread across the reset window
- Result: fewer wasted calls at end-of-day, smoother polling across 24h

Exposed via sensors (definitions.py):
- quota_reset_last: Last observed reset time
- quota_reset_next: Next expected reset time
- quota_reset_expected_window: Learned or default window
- quota_reset_pattern_confidence: "learned" / "single_observation" / "default"
- quota_reset_history_count: Number of resets in history (max 5)

State is persisted across HA restarts via helpers/storage.py.

## [5.0.0](https://github.com/banter240/tado_hijack/compare/v4.3.0...v5.0.0) (2026-03-04)

### ⚠ BREAKING CHANGES

* **core:** Multiple breaking changes for migration:
- Entity unique_ids now include config entry_id AND zone_id prefix for multi-account support (format: {entry_id}_zone_{zone_id}_{suffix}). Entities will be recreated on upgrade. Recommended: Delete and re-add the integration to avoid duplicates.
- Minimum Home Assistant version is now 2024.11.0 for Matter support.

This release introduces complete Tado X support with Matter integration, V2 bridge compatibility, optional full cloud mode for all generations, enhanced multi-account support, and a modular generation-based architecture.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 TADO X GENERATION SUPPORT (IB02 BRIDGE X)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Complete Tado X Integration:
- Full support for Tado X hardware via hops.tado.com API
- Custom TadoXApi client (lib/tadox_api.py) with OAuth token reuse from tadoasync
- Pydantic models for type safety: TadoXZoneState, TadoXDevice, TadoXRoom
- Matter device integration and automatic room-to-entity mapping
- Generation-aware entity filtering and capabilities detection
- Duck-typed compatibility with V3 models via UnifiedTadoData container
- Quick Actions (boost/off/resume) work with both Classic and Tado X

Generation-Specific Handlers:
- helpers/tadox/: Complete Tado X handler module (mapper, executor, action_provider, parsers, discovery)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ V2 BRIDGE SUPPORT & UNIFIED CLASSIC API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

V2 Hardware Support:
- Added support for V2 Gateway bridges (GW) with ~20k API calls/day quota
- V2 and V3 consolidated into single GEN_CLASSIC constant (both use my.tado.com API)
- Only difference: V2 has no HomeKit, V3 has HomeKit support
- Backward compatibility migration for users upgrading from previous versions

Modular Architecture:
- helpers/tadov3/: Classic API handlers for V2 and V3 (mapper, executor, action_provider, parsers)
- Provider pattern: Generation-agnostic data fetching interface (UnifiedDataProvider)
- Executor pattern: Generation-specific command execution (executor_base.py, executor_unified.py)
- Clean separation: lib/ for API clients, helpers/tadov3|tadox/ for business logic

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☁️ FULL CLOUD MODE (ALL GENERATIONS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Optional Cloud-Polling Climate Entities:
- New Full Cloud Mode toggle in config flow (default: false)
- Creates climate entities via cloud polling instead of HomeKit/Matter
- Supported for ALL generations (V2/V3/X) with generation-aware entity creation
- New TadoHeating class for heating zones (classic heating control)
- V2/V3: Separate TadoHeating and TadoAirConditioning entities per zone type
- Tado X: Unified TadoAirConditioning entity per room (supports all HVAC modes)

Recommendations:
- ✅ V2 (GW): ONLY option for climate entities (~20k calls/day makes it viable)
- ⚠️ V3 (IB01/GW01): NOT recommended (1k calls/day reducing to 100, use HomeKit instead)
- ⚠️ Tado X (IB02): NOT recommended (1k calls/day reducing to 100, use Matter instead)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 ENHANCED MULTI-ACCOUNT SUPPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Improved Entity Namespacing:
- Extended entity unique_id format to include zone_id: {entry_id}_zone_{zone_id}_{suffix}
- Previous format: {entry_id}_{suffix} (insufficient for multi-account with identical zone IDs)
- Prevents collisions when multiple accounts have zones with same ID
- Device identifiers now include zone context for proper grouping
- Enables multiple Tado homes in single Home Assistant instance without conflicts

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ CONFIG FLOW: GENERATION SELECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

New Setup Options:
- Generation selection: Classic (V2/V3) or Tado X (required during initial setup)
- Full Cloud Mode toggle for all generations (optional, default: false)
- fetch_extended_data toggle for initial poll optimization (optional, default: true)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛠️ DEVICE ENTITY RESOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enhanced Service Target Support:
- Services now accept device entities (battery, child_lock, connection, etc.) as entity_id
- Automatic zone lookup via device serial number extraction from unique_id
- Previous: Only zone entities (climate, switch, sensor) worked as entity_id
- Now: ANY Tado entity (including TRV/device entities) can be used as target
- Example: set_mode with entity_id=binary_sensor.trv_battery now automatically resolves to zone

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔇 REDUNDANCY SUPPRESSION SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

API Quota Optimization:
- New redundancy checker (helpers/redundancy_checker.py)
- CONF_SUPPRESS_REDUNDANT_CALLS: Skip API calls when target state matches cached state
- CONF_SUPPRESS_REDUNDANT_BUTTONS: Also skip button actions when all zones already match target
- Saves quota on accidental double-clicks, repeated UI interactions, or automation retries
- Only sends API calls when actual change detected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚙️ AUTO QUOTA: MINIMUM INTERVAL CONFIGURATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configurable Minimum Polling Interval:
- MIN_AUTO_QUOTA_INTERVAL_S reduced from 20 to 5 seconds (absolute floor)
- DEFAULT_MIN_AUTO_QUOTA_INTERVAL_S remains at 20 seconds (recommended default)
- Users can now set more aggressive polling if needed (e.g., for testing or high-quota V2 bridges)
- Default remains safe at 20s to protect against accidental account throttling
- Range: 5s-12h (configurable in Advanced Settings)
- Proxy mode still enforces 120s minimum

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 COMPREHENSIVE DOCUMENTATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

New Documentation:
- docs/ARCHITECTURE.md: Multi-generation system design with mermaid diagrams
- docs/FEATURES.md: Complete feature guide with generation comparison matrix

README Fixes:
- Corrected Full Cloud Mode documentation (supports all generations, not V2/V3 only)
- Fixed API quota history: 20k → 5k → 1k (with 100 planned next)
- Clarified Device Unification only works with HomeKit/V3 (Matter lacks serial numbers)
- Added generation comparison table (V2/V3/X feature matrix)
- Removed redundant explanations and consolidated quota mentions

### ✨ New Features

* feat(core): Tado X support, V2/V3 generation, full cloud mode, multi-account, and comprehensive overhaul


### 📚 Documentation

* docs(readme): reformat table of contents and add support section

## [4.3.0](https://github.com/banter240/tado_hijack/compare/v4.2.3...v4.3.0) (2026-02-23)

### ✨ New Features

* feat(entity): flexible entity_id configuration and zone sensor naming fix

**Zone Sensor Naming Fix:**
The naming logic for zone sensors was inconsistent (using 'home_id' instead of 'zone_name'). This commit aligns sensors with other zone entities (e.g., resulting in 'sensor.zone_name_humidity' instead of 'sensor.tado_home_name_zone_id_humidity').

**Note on Migration:**
Existing installations will likely retain the old 'sensor.tado_home_name_XX' IDs due to Home Assistant's Entity Registry persistence. To apply the new naming scheme, deleting and re-adding the integration is recommended.

**Entity ID Configuration:**
- Introduced '_entity_id_prefix' and '_entity_id_include_context' class attributes for fine-grained control.
- Bridge entities now use 'tado_ib' prefix and exclude serial numbers from entity_id.
- Simplified entity_id generation logic.

**Config Flow Improvements:**
- Consolidated multi-step config flow into single page.
- All settings now visible and editable in one view.

Affected entities: All zone-level sensors (humidity, heating_power, next_schedule_*, etc.)

## [4.2.3](https://github.com/banter240/tado_hijack/compare/v4.2.2...v4.2.3) (2026-02-23)

### 🐛 Bug Fixes

* fix(ci): enable full HACS brands validation

Removes the 'brands' ignore flag from the HACS validation workflow.

- This change is required to pass the strict validation checks for submitting the integration to the official HACS Default Store.
- Ensures all brand assets (logos, icons) are correctly verified.

## [4.2.2](https://github.com/banter240/tado_hijack/compare/v4.2.1...v4.2.2) (2026-02-07)

### 🐛 Bug Fixes

* fix(device): update child lock cache immediately to prevent reversion

Synchronously updates the local `devices_meta` cache when setting Child Lock.

- Prevents the switch entity from reverting to its old state during the next fast poll cycle (which uses cached metadata).
- Mirrors the fix applied to temperature offsets for device-level properties.

## [4.2.1](https://github.com/banter240/tado_hijack/compare/v4.2.0...v4.2.1) (2026-02-07)

### 🐛 Bug Fixes

* fix(offset): update cache immediately to prevent state reversion

Updates the internal `offsets_cache` synchronously when setting a new value.

- Prevents the entity from reverting to its old value during the next fast poll cycle (which relies on cached offsets).
- Ensures UI consistency between the optimistic update and the next full hardware sync.


### 📚 Documentation

* docs: refine debouncing documentation and reorder API usage notices

- Reordered README notices to prioritize high API usage explanation for better visibility.
- Updated 'Pending Command Tracking' and 'Debounced' descriptions to include button click interactions alongside sliders.
- Synchronized technical examples in DESIGN.md to reflect both UI button and slider interaction patterns.

## [4.2.0](https://github.com/banter240/tado_hijack/compare/v4.1.0...v4.2.0) (2026-02-03)

### ✨ New Features

* feat(core): Centralized entity architecture, advanced schedule metrics, and stabilized auto-quota management

This release introduces a major architectural leap, centralizing entity logic into a declarative system, enhancing schedule transparency through advanced metrics, and stabilizing the API quota management for both standard and proxy configurations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ CENTRALIZED ENTITY ARCHITECTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Unified Entity Definitions:
- Introduced `definitions.py` to centralize all entity metadata (sensors, binary_sensors, numbers, switches, select, buttons).
- Modular Setup Logic: New `entity_setup.py` handles platform-agnostic entity creation, significantly reducing code duplication across platform files.
- Declarative Mapping: Entities are now registered based on dynamic capability detection, ensuring a cleaner and more reliable integration footprint.
- Scoped Entity Factories: Dedicated helpers for Home, Zone, Device, and Bridge scopes (`create_home_sensor`, `create_zone_binary_sensor`, etc.).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ ADVANCED SCHEDULE METRICS & SENSOR INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Schedule Transparency:
- Next Schedule Change Monitoring: New sensors for tracking the timestamp, temperature, and mode of the next planned schedule event.
- Next Time Block Start: Diagnostic sensors for upcoming time block transitions.
- HVAC Action Precision: Improved parsing logic for heating power and AC activity states.

Enhanced Connectivity Monitoring:
- Bridge Connection Sensors: Detailed cloud connection status for Internet Bridges with compact unique IDs.
- Zone-Level Connectivity: Aggregated connectivity status for TRVs and thermostats within a zone.
- Battery State Tracking: Native binary sensors for device-level battery health monitoring.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ STABILIZED AUTO-QUOTA & POLLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intelligent Interval Management:
- Configurable Minimum Floor: Introduced `min_interval_configured` to allow users to tune the floor of the adaptive polling system.
- Mode-Specific Minimums: Enforced safe floors (120s for Proxy, 20s for Standard) to prevent accidental API bans while maintaining maximum responsiveness.
- Budget-Aware Scaling: Polling intervals now proactively check budget availability for the minimum floor before attempting to scale up frequency.
- Interval Forensics: New sensors for `current_zone_interval`, `min_interval_configured`, and `min_interval_enforced` providing real-time visibility into the quota engine.

Refined Proxy Support:
- Proxy Url & Token Diagnostics: Enhanced visibility into proxy configuration with redacted token logging for security.
- Jitter Control: Dynamic jitter application when operating behind an API proxy to further reduce pattern-based detection.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🐛 CRITICAL FIXES & HARDENING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Open Window Detection:
- Timeout Preservation: Fixed a regression where the OWD timeout was not correctly preserved or restored during configuration changes.
- Preserved state in seconds for higher accuracy during property updates.

Overlay & AC Hardening:
- Centralized Payload Construction: Consolidated all overlay logic into `build_overlay_data`, ensuring consistent validation and OpenTherm awareness.
- AC Setting Stability: Refined handling of AC-specific fields (swing, fan speed) to prevent invalid payloads on partial updates.
- Robust Error Handling: Enhanced redacted logging for API interaction forensics.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 TECHNICAL IMPROVEMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Coordinator Decomposition: Refactored `coordinator.py` to leverage declarative definitions and centralized builders.
- Helper Consolidation: Cleaned up logic in `helpers/` directory for better maintainability.
- Translation Expansion: Added comprehensive German and English translation strings for all new diagnostic entities.
- Redacted Logging: Upgraded logging utils to ensure sensitive proxy tokens and API payloads are never leaked in plain text.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## [4.1.0](https://github.com/banter240/tado_hijack/compare/v4.0.1...v4.1.0) (2026-01-31)

### ✨ New Features

* feat(quota): dynamic reset detection, safety throttle, and reconnect logic

This release introduces a more robust and adaptive API quota management system:

- Dynamic API Reset Detection: Monitors remaining quota percentage during a safe window (12-13h Berlin) to detect and adapt to Tado's variable reset times.
- Persistent Reconnect Logic: Reduced the recovery check interval to 15 minutes (THROTTLE_RECOVERY_INTERVAL_S) for faster service resumption after outages.
- Safety Throttle: Automatically enforces a 5-minute safety interval and logs warnings if the API reports invalid limit data (<= 0).
- Enhanced Documentation: Updated README and DESIGN.md to reflect the new architecture and the 3000-call Proxy bypass advantage.
- Internal Refactoring: Optimized reset logic and stabilized data structures for more reliable quota tracking.

## [4.0.1](https://github.com/banter240/tado_hijack/compare/v4.0.0...v4.0.1) (2026-01-31)

### 🐛 Bug Fixes

* fix(core): proxy URL deletion, AttributeError fix

Proxy URL Deletion Fix:
- Changed from 'default' to 'suggested_value' in config schema (config_flow.py)
- Allows users to properly clear/delete the proxy URL field in settings
- Previously, 'default' would revert to old value when field was cleared
- Added explicit None handling in async_step_advanced and _async_finish_flow

AttributeError Protection:
- Added getattr() in supports_temperature() for non-OpenTherm systems (coordinator.py)
- Prevents crash: "AttributeError: 'types.SimpleNamespace' object has no attribute 'temperatures'"
- Enables dummy zones without temperature capabilities to work correctly

Hot Water Improvements:
- Added parse_schedule_temperature() helper for consistent parsing (parsers.py)
- Fixed auto_target_temperature to return null instead of omitting attribute (water_heater.py)
- Improves UI consistency when schedule is OFF

All functional logic remains unchanged.

## [4.0.0](https://github.com/banter240/tado_hijack/compare/v3.0.0...v4.0.0) (2026-01-31)

### ⚠ BREAKING CHANGES

* **core:** Architectural overhaul with Hot Water and AC Pro support. Removal of legacy climate entities for hot water zones.

### ✨ New Features

* feat(core): Complete architectural overhaul with Hot Water, AC Pro, Zero-Waste optimization and robust state management

This major release represents a complete architectural transformation of the Tado Hijack integration, implementing production-grade features for hot water control, air conditioning management, intelligent API quota optimization, and bulletproof state handling. The update consolidates 12 development releases and recent OpenTherm enhancements into a stable, thoroughly tested RC candidate.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔥 HOT WATER & AIR CONDITIONING (Native Support)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hot Water Entity & OpenTherm Support:
- Native water_heater entity with ON/OFF/AUTO operation modes.
- Dynamic Temperature Control: Automatically detects whether the underlying hardware supports OpenTherm temperature control.
- Adaptive UI: Automatically hides the temperature control UI in Home Assistant for non-OpenTherm (on/off) systems to prevent invalid user inputs.
- Precision Control: Enables precise temperature selection for supported OpenTherm configurations.
- Auto Target Temperature: Introduced 'auto_target_temperature' attribute to provide visibility into the active schedule's setpoint while in AUTO mode.
- Integer temperature steps (1.0°C minimum) aligned with Tado API constraints.
- State Memory Mixin for persistent temperature restoration across HA restarts.
- Boiler load monitoring sensor for energy tracking.
- Optimistic state management preventing instant mode reversion.

Air Conditioning Pro Features:
- Advanced climate entity with full HVAC mode support (COOL/HEAT/DRY/FAN/AUTO).
- Fan speed control (AUTO/HIGH/MIDDLE/LOW) with capability-driven options.
- Vertical/Horizontal swing control via dedicated select entities.
- AC Light control switch.
- Physical mode preservation during AUTO mode operations.
- Optimistic AC mode tracking to prevent stale state resets.
- Mode-aware validation (FAN/DRY modes don't require temperature).
- Schedule Transparency: Added 'auto_target_temperature' attribute to see active schedule setpoints in AUTO mode.

Climate Entity Hardening:
- Centralized TadoStateMemoryMixin for reliable state restoration.
- Memory attributes with 'last_' prefix for visibility in state machine.
- Robust temperature fallback chain (optimistic > current > capabilities > defaults).
- Activity parsing prioritizes state.setting.power for accurate HVAC action reporting.
- Capability-based temperature support detection for Hot Water zones.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ ZERO-WASTE ARCHITECTURE (Extreme API Optimization)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Auto API Quota System:
- Adaptive polling based on daily quota consumption (configurable 50-95%).
- Real-time interval adjustment using remaining quota and time-until-reset.
- Weighted interval calculation accounting for economy windows.
- Automatic quota reset detection with scheduled refresh at midnight UTC.
- Throttle protection with configurable threshold (pauses polling when quota low).
- Background cost reservation for offset/presence/slow polling.
- Minimum interval enforcement (45s standard, 120s for proxy setups).

Extreme Batching & Command Merging:
- Bulk overlay API for multi-zone operations (boost/off/timer services).
- Intelligent command merger consolidates duplicate zone commands.
- Debounced command queue (5s default) batches rapid user interactions.
- Zone-level rollback contexts for failed command recovery.
- Per-command-type field protection during pending operations.

Polling Track Isolation:
- Independent fast/medium/slow/presence polling tracks.
- Zone states: Fast track (scan_interval, default 30min).
- Presence: Configurable track (default 12h).
- Metadata (zones/devices): Slow track (default 24h).
- Temperature offsets: Medium track (on-demand + configurable interval).
- Away configurations: Lazy fetch on first access per session.
- Capabilities: Cached on metadata fetch, lazy refresh on miss.

Economy Window Logic:
- Time-based polling reduction (e.g., 0-polling during sleep hours).
- Dynamic interval switching when entering/exiting economy window.
- Integration with Auto Quota for weighted cost distribution.
- Configurable start/end times with cross-midnight support.
- Switch entity to enable/disable reduced polling logic in real-time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ STATE INTEGRITY & CONCURRENCY (Toggle Revert Fixes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pre-API Validation & Hardware Guardrails:
- TadoOverlayValidator intercepts malformed payloads before API submission.
- OpenTherm Awareness: Validation logic now explicitly checks hardware support before allowing temperature-based overlay requests.
- Zone-type-specific rules (HEATING/HOT_WATER/AIR_CONDITIONING).
- Temperature structure validation (checks for nested 'celsius' field).
- Mode-dependent validation (AC COOL/HEAT require temp, FAN/DRY don't).
- Enhanced error logging with full redacted payload details for forensics.
- API quota preservation by catching 422 errors before transmission.

Pending Command Tracking & Field Locking:
- TadoApiManager tracks in-flight command keys in thread-safe set.
- Dynamic field protection based on command type (not hardcoded).
- Selective state merging: update sensors, protect overlay/setting fields.
- Command-key-to-field mapping (zone_* protects overlay, presence protects presence).
- Data race prevention: polls skip protected fields until command completes.
- Granular protection per zone (no global locks).

Optimistic State Management:
- Comprehensive OptimisticManager tracks overlay/power/temperature/mode/swing.
- State clearing strategy: overlay=False clears all, overlay=True preserves existing.
- TTL-based expiration (5s default) prevents stale optimistic values.
- Rollback support on command failure with stored contexts.
- Zone/Device/Home scope isolation for independent state tracking.
- Swing and fan speed optimistic tracking for immediate UI feedback.

State Patching & Restoration:
- patch_zone_overlay() creates rollback contexts before API calls.
- patch_zone_resume() captures overlay state before schedule resume.
- Centralized restoration architecture in TadoStateMemoryMixin.
- Prevents data loss from failed API operations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ ARCHITECTURAL IMPROVEMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Manager Decomposition:
- TadoDataManager: Polling, caching, metadata (zones/devices/capabilities).
- TadoApiManager: Command queue, debouncing, execution, rollback.
- OptimisticManager: UI state orchestration, TTL tracking.
- PropertyManager: Device/zone property setters (child lock, offset, dazzle, etc.).
- AuthManager: Token refresh, user info caching.
- RateLimitManager: Header parsing, throttle detection, quota tracking.
- EntityResolver: Entity ID → Zone ID mapping (HomeKit + Hijack entities).
- EventHandler: Home Assistant event subscriptions (state changes, resume, etc.).

Helper Modules:
- overlay_builder.py: Centralized overlay payload construction.
- overlay_validator.py: Pre-API validation logic.
- state_patcher.py: Rollback context creation.
- discovery.py: Zone/device discovery with type filtering.
- parsers.py: HVAC mode/action parsing with fallback chains.
- quota_math.py: Quota calculations, reset time, weighted intervals.
- command_merger.py: Duplicate command detection and merging.
- logging_utils.py: Redacted logger for sensitive data protection.

Entity Enhancements:
- TadoOptimisticMixin: Resolve optimistic > actual state.
- TadoStateMemoryMixin: RestoreEntity wrapper with auto-persistence.
- TadoZoneEntity/TadoDeviceEntity: Base classes with device info, names, icons.
- Unique ID stability across entity migrations.

Configuration Flow:
- API Proxy URL support (skip Tado Cloud auth if proxy configured).
- Auto API Quota Percent selector (50-95%).
- Throttle threshold configuration.
- Reduced polling window (start/end time, interval).
- Debounce time configuration.
- Polling interval controls (zone/presence/offset/slow).
- Debug logging toggle.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔌 CONNECTIVITY & DIAGNOSTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Connectivity Sensors:
- Internet Bridge connectivity status (per IB device).
- Zone connectivity status (per TRV/thermostat/valve).
- Battery-powered device monitoring.
- Device-level diagnostics attributes.

Enhanced Diagnostics:
- Current API quota status (limit/remaining/reset time).
- Polling cost breakdown (zones/presence/offset/slow).
- Active economy window detection.
- Command queue status.
- Optimistic state snapshot.
- Rate limit headers.
- Configuration dump (redacted secrets).

Expert Sensors:
- API quota remaining sensor with auto-update on each poll.
- API status sensor (OK/Throttled/Limited).
- Polling interval sensor (current calculated interval).
- Next quota reset timestamp sensor.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎮 SERVICES & AUTOMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Standardized Services:
- set_climate_timer: Multi-zone overlay with duration/mode/temperature.
- set_presence: Home/Away with optimistic toggle.
- resume_all_schedules: Bulk resume for all heating zones.
- turn_off_all_zones: Emergency off for all heating zones.
- boost_all_zones: Quick 25°C boost for all zones.
- set_temperature_offset: Per-device calibration (-10 to +10°C).
- set_away_temperature: Per-zone away mode temperature.
- identify_device: Physical device identification (LED blink).

Service Validation:
- Target selector for entity/device/area.
- Temperature range validation.
- Duration limits (5-1440 minutes).
- Mode whitelisting per service.

Buttons:
- Resume schedule (per zone).
- Identify device (per device).
- Refresh data (manual poll trigger).

Switches:
- Early Start (per zone).
- Open Window Detection (per zone).
- Dazzle Mode (per zone).
- Child Lock (per device).
- Polling Active (global polling master switch).
- Reduced Polling Active (economy window toggle).

Selects:
- Fan Speed (AC zones).
- Vertical Swing (AC zones).
- Horizontal Swing (AC zones).

Numbers:
- Away Temperature (per zone, 5-25°C).
- Temperature Offset (per device, -9.9 to +9.9°C, 0.1°C step).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 DEVELOPMENT TOOLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dummy Simulation Environment:
- TadoDummyHandler for hardware-free testing (Hot Water + AC zones).
- Stateful dummy zone simulation (remembers temp/mode/power changes).
- API command interception (prevents illegal calls for dummy zones).
- Metadata injection (zones 998=AC, 999=Hot Water with mock devices).
- Activity simulation (AC dummy calculates power based on temp differential).
- Environment variable activation (TADO_ENABLE_DUMMIES=true).
- Marked with [DUMMY_HOOK] tags for easy identification and removal.
- Hardcoded False in const.py for production safety (no UI toggle).

Local Validation:
- scripts/local_hacs_validate.py for HACS compliance testing.
- hassfest integration via pyproject.toml.
- Pre-commit hooks for linting (ruff, mypy).
- GitHub Actions for automated PR checks.

Development Documentation:
- docs/DEVELOPMENT.md with comprehensive setup instructions and coding standards.
- docs/DESIGN.md with architectural decisions, rationale, and usage examples.
- State management diagrams and polling strategy documentation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🐛 CRITICAL FIXES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Toggle Revert Resolution:
- Fixed race condition where poll overwrites pending overlay changes.
- Implemented robust field-locking mechanism that prevents background polling from overwriting UI changes before they are confirmed by the API.
- Implemented selective merge: update sensors, protect overlay fields.
- Dynamic field protection prevents hardcoded field lists.

Hot Water Stability:
- Resolved 422 errors on AUTO→HEAT transitions (temperature fallback chain).
- Fixed instant OFF reversion when resuming schedule.
- Enforced integer temperature steps for API compatibility.

AC Mode Preservation:
- Fixed stale mode data causing API rejections.
- Physical mode (COOL/HEAT/DRY/FAN) now persists during AUTO operations.
- Optimistic AC mode tracking prevents mode resets on setting changes.

Initialization Gaps:
- Resolved missing state on first HA start (cold boot scenario).
- Fixed sensor data unavailability during startup phase.
- Ensured zone_states populate before entity registration.

API Error Handling:
- Enhanced error logs with payload details for forensic analysis.
- Graceful degradation on API failures (retry with exponential backoff).
- Rollback on command failure restores previous state.

Temperature Offset:
- Fixed offset sensor showing "Unknown" on startup.
- Lazy fetch on demand prevents unnecessary API calls.
- Cached offsets persist across integration reloads.

Proxy Authentication:
- Support for tado-api-proxy authentication bypass.
- Configurable proxy URL in config flow.
- Skip OAuth when proxy detected.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 MIGRATION & BREAKING CHANGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Config Entry Migration (Version 6):
- Auto-migration from v5 with default value population.
- New config keys: auto_api_quota_percent, reduced_polling_*, jitter_percent.
- Backwards-compatible fallbacks for missing keys.
- Migration runs silently on integration load.

Entity ID Changes:
- Internet Bridge sensors: Compact ID format (ib123 instead of ib-01-23-45-67).
- Unique ID stability ensures no entity duplication.
- Device info consolidation for cleaner device registry.

Removed Features:
- Old climate entities (replaced by split climate + water_heater).
- Manual quota calculation (replaced by Auto API Quota).
- Hardcoded polling intervals (replaced by adaptive system).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ QUALITY OF LIFE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

User Experience:
- Instant UI feedback via optimistic state (no toggle revert delay).
- Reduced API calls = faster quota preservation.
- Economy window allows zero-polling during sleep hours.
- Automatic mode for quota management (set-and-forget).
- Clear diagnostic sensors for troubleshooting.

Performance:
- 9108 lines of new code, 1022 lines removed (net +8086)
- Consolidated architectural overhaul into production-ready release.
- Thoroughly tested across extensive development cycle.
- Zero API waste with intelligent batching and caching.

Developer Experience:
- Modular manager architecture (easy to extend).
- Dummy zones for hardware-free testing.
- Comprehensive logging with redaction.
- Design documentation for future contributors.
- Marked dummy code with [DUMMY_HOOK] for easy cleanup.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BREAKING CHANGES:
- Config entry migration required (auto-applied on load).
- Old climate entities removed (replaced by water_heater for hot water).
- Entity IDs for Internet Bridges changed to compact format.

UPGRADE NOTES:
- Recommended to review Auto API Quota settings in config.
- Check reduced polling window if using economy mode.
- Verify hot water zones appear as water_heater entities.
- Update automations referencing old climate entity IDs.

CREDITS:
This release represents an intense week of architectural work, forensic debugging, and real-world testing. Special thanks to @krisswiltshire30 for the collaboration and to the community members who helped test and validate the hot water entity. Your patience and detailed bug reports made this release possible.

## [3.0.0](https://github.com/banter240/tado_hijack/compare/v2.0.0...v3.0.0) (2026-01-20)

### ⚠ BREAKING CHANGES

* **offset:** The 'sensor.temperature_offset' entities have been replaced by 'number.temperature_offset' to enable write access.

### ✨ New Features

* feat(offset): implement bi-directional temperature offset control

- Architecture: Integrated set_temperature_offset directly into TadoHijackClient (Inheritance over Monkeypatching).
- Controls: Replaced legacy read-only offset sensors with interactive 'number' entities (-10.0 to +10.0 in 0.1 steps).
- UI: Configured entities in BOX mode for direct numeric input and added full English/German translations.
- UX: Integrated with OptimisticManager and ApiManager for flicker-free, debounced (5s) API execution.
- Reliability: Implemented RestoreEntity support to preserve calibration states across Home Assistant restarts.
- Quality: Resolved mypy static analysis errors and optimized setup logic via Sourcery/Ruff.
- Docs: Updated documentation and removed redundant API information.

## [2.0.0](https://github.com/banter240/tado_hijack/compare/v1.1.0...v2.0.0) (2026-01-20)

### ⚠ BREAKING CHANGES

* **core:** Complete architecture overhaul. Entities have been renamed and regrouped. Config flow and polling logic updated.

### ✨ New Features

* feat(core): architecture overhaul - smart batching, inheritance, homekit linking & controls

- Architecture: Migrated from monkey-patching to a clean inheritance model (TadoHijackClient).
- Device Mapping: Entities (Battery, Offset, Child Lock) are now mapped to physical devices (Valves) instead of Zones.
- HomeKit Linking: Automatically detects and links entities to existing HomeKit devices via Serial Number match.
- Smart Batching: Advanced TadoApiManager with CommandMerger logic merges multiple rapid commands into single Bulk API calls.
- Controls: Added Child Lock (Switch), Boost All Zones (Button), Turn Off All Zones (Button).
- Security: Implemented centralized, strict PII redaction (TadoRedactionFilter) for logs (strings & objects).
- Performance: Decoupled RateLimitManager, reduced default polling to 30m, and added configurable debounce (default 5s).
- Logic: Centralized OptimisticManager, TadoRequestHandler, AuthManager, and CommandMerger for robust and modular API handling.
- Documentation: Complete README overhaul with better structure and detailed API consumption table.

## [1.1.0](https://github.com/banter240/tado_hijack/compare/v1.0.0...v1.1.0) (2026-01-17)

### ✨ New Features

* feat: add temperature offset sensors, throttled mode, and config improvements

FEATURES:
- Temperature offset sensor per device (1 API call per valve)
- Offset polling interval config (0 = disabled, only on manual poll)
- Throttled mode with configurable threshold
- API status sensor (connected/throttled/rate_limited)
- Manual poll and resume all schedules buttons with trailing debounce

FIXES:
- Options flow bug fixed (settings now persist correctly)
- Offset sensors now grouped under Zone device (like battery)
- Improved timeout message with API rate limit reset info (12:00 CET)

DOCS:
- Updated README with new features and per-valve API cost warning
- Clarified Matter is not supported (waiting for official HA Tado integration)
- Removed hardcoded rate limit references (varies month to month)

## 1.0.0 (2026-01-17)

### ✨ New Features

* feat: initial release of Tado Hijack

- API quota monitoring via passive header interception
- Home/Away presence control with debouncing
- Per-zone auto mode switches
- Battery health binary sensors
- Dual-track polling (fast hourly, slow daily)
- Monkey-patching for tadoasync null handling
- OAuth device flow authentication
- English and German translations

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-17

### Added

- Initial release of Tado Hijack integration
- **API Quota Monitoring**: Real-time tracking of Tado API rate limits via passive header interception
- **Presence Control**: Home/Away switch with intelligent debouncing
- **Zone Auto Mode**: Per-zone switches to toggle between smart schedule and manual override
- **Battery Monitoring**: Binary sensors for device battery health
- **Dual-Track Polling**: Configurable fast (hourly) and slow (daily) polling intervals
- **Sequential API Worker**: Background queue prevents API flooding
- **Monkey-patching**: Fixes `nextTimeBlock: null` deserialization bug in tadoasync library
- **Services**: `manual_poll` and `resume_all_schedules` for automation integration
- **Translations**: English and German language support
- **OAuth Device Flow**: Secure authentication without storing credentials
