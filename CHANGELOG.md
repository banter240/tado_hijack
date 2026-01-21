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
