## [3.1.0-dev.13](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.12...v3.1.0-dev.13) (2026-01-24)

### ✨ New Features

* feat(climate): refactor hot water logic and consolidate hvac dispatcher

Summary of changes:
- Removed HEAT mode from Hot Water (OFF/AUTO only)
- Fixed target temperature display in OFF state
- Centralized HVAC logic in coordinator.async_set_zone_hvac_mode
- Implemented central zone filtering (_get_active_zones)
- Established 30s safety floor for dynamic polling quota
- Refactored ApiManager and Services for DRY compliance

## [3.1.0-dev.12](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.11...v3.1.0-dev.12) (2026-01-24)

### ✨ New Features

* feat(core): major architectural upgrade for type safety, API efficiency, and AC Pro features

- Refactored entire data model to use TadoData dataclasses, eliminating dict-based access and ensuring type safety across all platforms.
- Implemented lazy loading for zone capabilities with asyncio locking to prevent race conditions and save API calls during startup.
- Parallelized initial API calls using asyncio.gather to significantly speed up integration loading.
- Consolidated climate logic into TadoClimateEntity base class, reducing redundancy and improving maintainability (DRY).
- Enhanced TadoAirConditioning with dynamic fan speed and swing control based on actual device capabilities.
- Integrated robust HVACAction reporting (Heating/Cooling/Idle) using real-time activity data points.
- Optimized hardware synchronization logic to allow disabling periodic updates (Initial-only mode) for maximum API conservation.
- Improved service call processing with consolidated parameter parsing and optimized batch preparation.

## [3.1.0-dev.11](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.10...v3.1.0-dev.11) (2026-01-24)

### ✨ New Features

* feat(services): intelligent overlay control and system-wide optimizations

- implement smart overlay detection (duration forces timer mode)
- add 'set_timer_all_zones' for global room control
- implement native hot water climate entity
- add 'presence' and 'next_block' overlay termination modes
- remove redundant 'time_period' (HH:MM:SS) for better precision
- implement intelligent temperature capping (Heating 25°C, AC 30°C, HW 80°C)
- optimize UI with required fields for clean toggle rendering
- refactor services using DRY principles
- enhance config flow with 1% quota step precision

## [3.1.0-dev.10](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.9...v3.1.0-dev.10) (2026-01-24)

### ✨ New Features

* feat(climate): native hot water and enhanced overlay control

- implement native hot water climate entity with AUTO/HEAT/OFF modes
- enhance 'set_timer' service with HH:MM:SS format and new overlay modes
- add 'Dynamic Presence-Aware Overlay' (until presence change) and 'Auto' (next block)
- implement intelligent temperature capping (Heating 25°C, AC 30°C, HW 80°C)
- introduce hybrid auto-quota strategy to ensure 'Always-On' polling

## [3.1.0-dev.9](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.8...v3.1.0-dev.9) (2026-01-23)

### 🐛 Bug Fixes

* fix(sensor): enable boiler load monitoring for hot water zones

- fix(sensor): Enable 'heating_power' sensor for Hot Water zones to monitor Boiler Load/Modulation.
- fix(sensor): Implement dynamic translation keys ('hot_water_power' vs 'heating_power') based on zone type.

## [3.1.0-dev.8](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.7...v3.1.0-dev.8) (2026-01-23)

### 🐛 Bug Fixes

* fix(core): improve hot water and AC optimistic UI

- fix(coordinator): add optimistic manual mode update when changing AC settings.
- fix(number): set optimistic_value=True for hot water temperature changes to ensure schedule switch updates.

## [3.1.0-dev.7](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.6...v3.1.0-dev.7) (2026-01-23)

### 🐛 Bug Fixes

* fix(core): resolve hot water logic and missing sensors

- fix(hot_water): Prevent optimistic ON state when resuming schedule (logic fix).
- fix(binary_sensor): Enable battery/connection sensors for devices in Hot Water/AC zones (e.g. Wireless Receivers).

## [3.1.0-dev.6](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.5...v3.1.0-dev.6) (2026-01-23)

### 🐛 Bug Fixes

* fix(hot_water): prevent optimistic ON state when resuming schedule

- Corrected optimistic logic: 'Resume Schedule' no longer incorrectly assumes 'ON' state.
- Enhanced OptimisticManager to track explicit power states ('ON'/'OFF') for accurate UI feedback.
- Fixed coordinator to propagate correct power state during manual overlays.
- docs: Clarified in README that HomeKit is mandatory for heating temperature control.

## [3.1.0-dev.5](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.4...v3.1.0-dev.5) (2026-01-23)

### ✨ New Features

* feat(quota): add Auto API Quota with adaptive polling

Automatically distribute API calls throughout the day based on a
configurable percentage of available quota. The system dynamically
adjusts polling intervals to maximize freshness while respecting limits.

Key changes:

- Auto API Quota setting (0-100%) in config flow
  Calculates FREE quota = Limit - Throttle - Battery - Offset updates
  Distributes X% evenly until 12:05 CET reset

- Adaptive interval calculation
  Uses real poll cost measurement instead of hardcoded values
  Respects throttle threshold - stops polling when quota low
  Auto-adjusts based on remaining quota and time until reset

- Scheduled reset poll at 12:05 CET
  Fetches fresh quota data right after daily reset
  Ensures accurate calculations for the new day

- Hot Water zone resolution fix
  Parse zone_{id}_suffix format correctly (e.g. zone_5_target_temp)

- Config flow UX improvements
  Reorder options: Fast Poll → Auto Quota → Battery → Offset → etc.
  Move advanced options (Proxy, Debug) to bottom

- README overhaul
  Add Auto API Quota section with calculation example
  Convert services list to table format
  Fix German text, update API consumption table
  General formatting and spacing improvements

- Prevent duplicate patch application
  Add idempotent guard to apply_patch()

Technical notes:
- PollTask abstraction for cost tracking
- _build_poll_plan() as single source of truth
- estimate_daily_reserved_cost() for budget planning
- Europe/Berlin timezone for CET reset calculation

## [3.1.0-dev.4](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.3...v3.1.0-dev.4) (2026-01-23)

### 🐛 Bug Fixes

* fix(entity): use compact Internet Bridge entity IDs

- Device name: tado Internet Bridge {serial_no} (matches HomeKit)
- Home entities: tado_{home_slug}_{key}
- Bridge connection: tado_ib_{home_slug}_cloud_connection
- Debug logging level configuration restored

## [3.1.0-dev.3](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.2...v3.1.0-dev.3) (2026-01-22)

### ✨ New Features

* feat(core): extreme batching, hot water, AC pro, and connectivity sensors

- Smart batching with CommandMerger (10 zones = 2 API calls)
- Hot Water temperature control with proper optimistic handling
- AC temperature and mode control
- Device and Bridge cloud connectivity sensors
- Sourcery code style improvements

## [3.1.0-dev.2](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.1...v3.1.0-dev.2) (2026-01-22)

### ✨ New Features

* feat(core): unleash valves, early start, and ac temperature control

Significant update introducing Valve Insights, Advanced Zone Config, and HomeKit Bridging.

New Features:
- Monitoring: Valve Opening (%) (Insight).
- Monitoring: Humidity sensor for AC zones.
- Control: Early Start (Preparation) and Open Window Detection toggles.
- Control: Target Temperature number entities for AC and Hot Water.
- HomeKit: Smart "Hijack" logic (optimistic manual mode) when detecting HomeKit events.

Improvements:
- Architecture: Unified OptimisticMixin for robust state handling.
- Documentation: Added Batching Capability Matrix and clarified Fused/Debounced logic.
- Fixes: Corrected Proxy URL handling (indentation) and translation keys.
- Cleanup: Removed redundant sensors and finalized README.

## [3.1.0-dev.1](https://github.com/banter240/tado_hijack/compare/v3.0.0...v3.1.0-dev.1) (2026-01-21)

### ✨ New Features

* feat(core): unleash hot water, ac pro and extreme batching

Major release introducing Extreme Batching, Cloud Features, and API Efficiency.

Features:
- Extreme Batching: Fusion of Heating, AC, and Hot Water commands into single API calls.
- Hot Water Control: New switch entity for boiler power.
- AC Pro: Select entities for Fan Speed and Swing modes.
- Away Temperature: Per-zone configuration via number entity.
- Dazzle Mode: Display control for V3+ devices.
- API Proxy Support: Experimental option to use local tado-api-proxy to bypass rate limits.
- Granular Refresh: Split manual poll into specific buttons to save quota.
- Efficiency: Increased default polling to 60m (with auto-migration).

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
