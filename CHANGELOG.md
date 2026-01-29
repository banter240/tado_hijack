## [4.0.0-dev.7](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.6...v4.0.0-dev.7) (2026-01-29)

### 🐛 Bug Fixes

* fix(core): resolve UI mode flickering and persistent temperatures

Ensures absolute UI consistency during mode transitions:
- Explicitly clears optimistic state when resuming schedules to prevent target temperatures from 'sticking'.
- Synchronizes 'power' and 'operation_mode' keys in OptimisticManager to keep both Climate and WaterHeater entities stable during manual overlays.
- Eliminates the 'UI Auto vs App Heat' discrepancy by enforcing correct optimistic overlay markers.

## [4.0.0-dev.6](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.5...v4.0.0-dev.6) (2026-01-29)

### 🐛 Bug Fixes

* fix(core): enhance UI stability with optimistic temperatures and dynamic AC modes

This comprehensive stability update ensures a seamless user experience:
- Implemented optimistic temperature tracking in 'OptimisticManager' to prevent UI sliders from jumping or disappearing.
- Added 'last known temperature' memory to climate entities for intelligent restoration when switching to HEAT mode.
- Centralized temperature fallback logic in the Coordinator (DRY) to prevent 422 API errors.
- Transformed AC entities to use dynamic HVAC modes based on hardware capabilities (HEAT/DRY/FAN support).
- Optimized service validation to allow mode switching without redundant error prompts.

## [4.0.0-dev.5](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.4...v4.0.0-dev.5) (2026-01-29)

### 🐛 Bug Fixes

* fix(services): implement robust temperature fallbacks, resolve mode case-sensitivity and establish design documentation

This update resolves critical service issues and enhances documentation:
- Resolved 422 'temperature required' errors by implementing automatic default temperature resolution in the coordinator.
- Fixed 'Unsupported operation_mode' errors by normalizing all mode comparisons to lowercase.
- Refined service validation to be mode-aware, allowing seamless UI switching without redundant error blocks.
- Added comprehensive design documentation in 'docs/DESIGN.md' including high-depth system schematics and quota logic distribution.


### 📚 Documentation

* docs(ci/readme): update service examples and integrate local HACS/hassfest validation

This clean commit includes:
- Corrected mandatory fields in README service examples.
- Fixed Table of Contents links in README.
- Added local pre-commit hooks for Home Assistant and HACS validation.

## [4.0.0-dev.4](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.3...v4.0.0-dev.4) (2026-01-29)

### ✨ New Features

* feat(core): major architectural overhaul, migration v6 and service standardization

This update implements a modular helper-based architecture, completes the v6 migration
and standardizes service interactions across all platforms while hardening the system against
common failures.

ARCHITECTURE & MODULARITY:
- EntityResolver: Centralized HomeKit/Hijack entity resolution logic into a dedicated helper.
- PropertyManager: Standardized hardware property updates via generic dispatchers.
- DiscoveryManager: Unified zone and device discovery loops.
- TadoEventHandler: Isolated HA event bus integration for optimistic triggers.
- Coordinator: Reduced bloat by ~40% by offloading business logic to specialized managers.

SERVICE STANDARDIZATION & VALIDATION:
- HVAC Mode Standard: Refactored 'set_mode' and 'set_mode_all_zones' to use standard 'hvac_mode' (off, heat, auto).
- Validation Matrix: Implemented central 'Pre-Validation' (DRY) to block invalid parameter combinations (e.g. heat without temp) before making API calls.
- Sensible Defaults: Established logic-aware defaults (heat mode @ 21C / 50C) and improved UI flow by making 'overlay' a required field.
- DRY Schema: Centralized parameter validation and YAML schema using anchors/aliases for maintainability.

STATE, DATA INTEGRITY & POLLING:
- Migration v6: Implemented mandatory reset of polling intervals to correct unit confusion.
- JIT Poll Planning: Replaced boolean flags with high-precision timestamps for plan-driven polling (Zero-Waste).
- Intelligent Polling: Implemented smart 'refresh_after' logic that suppresses redundant polls during active timers, deferred until expiry.
- Dynamic Optimistic Store: Implemented a maintenance-free key-value store for all optimistic states.
- Functional Helpers: Extracted state patching (state_patcher) and API payload construction (overlay_builder) into utility modules.

ROBUSTNESS & AUTH:
- Error Capturing: Enhanced TadoRequestHandler to capture and log actual API response bodies, providing detailed feedback for 422 errors.
- Auth Fix: Corrected token polling logic to prevent TadoConnectionError during initial OAuth device authorization.
- Setup Guard: Fixed ValueError in config_flow by validating source before accessing reauth entries during fresh installs.

DOCUMENTATION:
- README Sync: Updated documentation to match all architectural changes and standardized YAML service examples.
- Technical Detail: Restored precise descriptions for Auto Quota math and Reset-Sync (12:01 AM Berlin).

## [4.0.0-dev.3](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.2...v4.0.0-dev.3) (2026-01-29)

### ✨ New Features

* feat(core): consolidate next-gen zero-waste architecture and global timezone synchronization

ZERO WASTE & OPTIMISTIC STATE PATCHING:
- Implemented 'Zero Waste' principle where API write actions like overlays and resumes no longer trigger a confirmatory poll (async_refresh). Instead, the local coordinator state is patched optimistically immediately after the command is queued.
- Automated Rollback Contexts ensure that every command carries a snapshot of the previous state so that if the API call fails or the worker crashes, the local state is automatically reverted to ensure data integrity.
- Granular Patching logic includes specialized methods like _patch_zone_local and _patch_zone_resume to handle complex Tado state transitions (changing HVAC mode, temperature, and power simultaneously) locally in microseconds.

POLLING INTELLIGENCE & QUOTA MANAGEMENT:
- Weighted Quota Model dynamically calculates the polling interval using a hybrid model that reinvests API savings from the 'Economy Window' (night mode) into higher frequency polling during active hours.
- Economy Window Priority ensures that the reduced polling profile (e.g., 1h interval at night) now has absolute priority over auto-quota calculations, ensuring predictable behavior regardless of the remaining budget.
- Multi-Level Jitter is applied to prevent account bans at two levels when using a proxy: Batch-Level uses a base delay (1.0s) before processing command queues, and Call-Level uses additional randomized delays (0.5s) before sensitive calls.

GLOBAL TIMEZONE SYNCHRONIZATION:
- Global Reset Logic calculates the API Quota Reset using absolute 'Europe/Berlin' time (12:01 AM CET/CEST) via dt_util.get_time_zone, ensuring precise synchronization with Tado servers regardless of the Home Assistant local timezone.
- Local Economy Window conversely follows the user's LOCAL time (dt_util.now()), ensuring the heating drops when the user actually sleeps, not when it is night in Berlin.

HOT WATER & ZONES INTEGRATION:
- Full Platform Support includes a dedicated 'water_heater' platform with specific capabilities for Tado Hot Water zones.
- Unified Coordinator Logic integrates Hot Water control methods (async_set_hot_water_auto, _off, _heat) directly into the central coordinator, utilizing the same robust queueing and rollback mechanisms as heating zones.
- Intelligent Discovery by the 'device_linker' now correctly maps devices to both 'climate' and 'water_heater' entities based on zone capabilities.

AUTH-LAST CONFIG FLOW & PROXY BYPASS:
- Redesigned Config Flow follows an 'Auth-Last' strategy where configuration of Polling, Quota, and Advanced settings happens BEFORE authentication.
- Proxy Bypass allows users who provide an 'API Proxy URL' in the final step to skip the Tado Cloud OAuth flow entirely, creating the config entry immediately using the Proxy URL as a unique ID anchor.
- Unified Wizard ensures that both initial setup and options flow now share the exact same 4-step wizard logic (DRY), providing a consistent user experience.

CLEAN CODE & STABILITY:
- Technical Debt removal included removing all 'type: ignore' hacks, fixing all Mypy/Ruff issues, and restoring full type safety with missing constants and types in coordinator.py.
- UI Stability was improved by harmonizing TimeSelector usage to a standard format to prevent 'Unknown Error' crashes in Home Assistant Config Flows.
- Reliability enhancements include immediate persistence of 'Reduced Polling Logic' switch states to the config entry and an automated Migration v6 that converts old hour-based intervals to seconds.

Hot Water & Zones (co-authored by Kriss Wiltshire [#30](https://github.com/banter240/tado_hijack/pull/30))

Co-authored-by: Kriss Wiltshire <krisswiltshire30@users.noreply.github.com>

## [4.0.0-dev.2](https://github.com/banter240/tado_hijack/compare/v4.0.0-dev.1...v4.0.0-dev.2) (2026-01-27)

### ✨ New Features

* feat(core): implement zero-waste architecture, entity migration and data integrity

This major update finalizes the architectural shift to a fully optimized, zero-waste system
and resolves critical entity conflicts via automatic migration.

ZERO WASTE ARCHITECTURE:
- Universal Rollback: Robust transaction system for all write actions (Presence, Overlays,
  Child Lock, Offset).
- Local State Patching: Updates UI immediately without triggering confirmatory API polls.
- Safety Net: Automatic rollback to previous local state if API calls fail.
- No-Poll Policy: Eliminated all 'refresh after action' logic for maximum quota efficiency.

ENTITY MIGRATION & HOT WATER:
- Entity Cleanup: Automatic migration to remove legacy '_hw_' switch entities that
  conflicted with the new water_heater platform.
- Unique ID Strategy: Changed water_heater ID schema to '_water_heater_' to prevent
  collisions.
- Type Safety: Fixed Mypy errors in entity and coordinator classes.

REFACTORING:
- CommandMerger: Simplified via dispatch map and integrated rollback context.
- Meta-Cleanup: Removed non-essential comments.

NEW FEATURES:
- Added 'button.refresh_presence' for manual state checks without full polls.

DOCUMENTATION:
- Auto Quota: Updated technical description to reflect stateless predictive consumption model.
- Diagnostics: Relocated detailed privacy info to Troubleshooting section for better support flow.
- Privacy: Refined safety statement to 'should be safe' and added manual verification advice.
- Zero Waste: Explicitly documented the new write strategy in the API Consumption section.

## [4.0.0-dev.1](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.15...v4.0.0-dev.1) (2026-01-27)

### ⚠ BREAKING CHANGES

* **core:** The migration to advanced presence polling changes internal track
handling. Config entry versions have been bumped to ensure clean state hydration.

Co-authored-by: krisswiltshire30 <kriss.wiltshire@googlemail.com>

### ✨ New Features

* feat(core): implement advanced presence polling, adaptive quota and expert-level diagnostics

This massive update stabilizes the core architecture for highly restricted API environments
and introduces a military-grade privacy layer for diagnostic reporting.

CORE ARCHITECTURE:
- Presence Polling Evolution: Replaced legacy polling with advanced tracks using sequential
  state handling to minimize race conditions and API overhead.
- Adaptive Quota Brain: Implemented stateless, predictive quota calculation. The system
  now intelligently adjusts polling intervals based on remaining 'API Gold' and daily reset
  targets (12:01 Berlin).
- Safety Thresholds: Integrated a dynamic buffer that prioritizes manual user actions and
  automations over periodic background polling when quota is low.

PLATFORM STABILIZATION:
- Hot Water Restoration: Fully restored the water_heater platform. Fixed temperature
  reporting (None for non-temp hardware) and optimized service selectors for environment
  independence.
- Sensor Noise Reduction: Eliminated excessive debug logging in valve state updates.

EXPERT-LEVEL DIAGNOSTICS & PRIVACY:
- Multi-Layer Anonymization: Diagnostic reports are now safe for public support.
- Key Pseudonymization: HA Entity-IDs in JSON keys are transformed into unique hashes
  (e.g., entity_8a3f), protecting room names while maintaining machine-readability.
- Global PII Masking: Hard redaction for serials (VA, RU, IB), emails, geo-coordinates,
  and cryptographic secrets (Tokens, Hashes, Salts) via intelligent Regex.
- Contextual Redaction: Automatically identifies and replaces sensitive fields from
  all tadoasync models (username, firstname, mobile_number, etc.).

DOCUMENTATION:
- Fully updated README covering the new consumption strategy, architecture highlights,
  and the experts-only diagnostics system.
- Cleaned up all internal 'v4' references to maintain public release consistency.

## [3.1.0-dev.15](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.14...v3.1.0-dev.15) (2026-01-25)

### 🐛 Bug Fixes

* fix(api): support tado-api-proxy authentication and configuration

Fixes:
- Skip auth token and Authorization header when using API proxy (proxy handles auth internally)
- Handle proxy URLs with/without /api/v2 path (backward compatible)
- Fix empty API proxy URL field not deleting the configuration
- Update translations to clarify proxy URL should be base URL only
- Disable Hot Water Switch creation (conflicts with Climate entity)
- Validate climate capabilities to prevent min==max errors

Features:
- Add configurable "refresh after resume" with 1s grace period
- Fetch target temperature/state after schedule resume (HVAC AUTO)
- Merge multiple resume commands within grace period to single API call
- Required because schedules are managed Tado cloud-side

Debug Improvements:
- Add extensive debug logging to climate entity (current/target temp, capabilities)
- Add debug logging to heating power sensor (activity data points)
- Add overlay payload logging to API manager

## [3.1.0-dev.14](https://github.com/banter240/tado_hijack/compare/v3.1.0-dev.13...v3.1.0-dev.14) (2026-01-24)

### 🐛 Bug Fixes

* fix(api): revert parallel to sequential requests, improve hot water detection

- Reverted asyncio.gather() to sequential API calls (Tado rejects parallel requests)
- Simplified rate limit logging in request handler
- Added hot_water_in_use activity detection in climate_entity and sensor
- Patched zone state to rescue hot water activity data
- Reduced MIN_AUTO_QUOTA_INTERVAL_S from 30s to 15s

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
