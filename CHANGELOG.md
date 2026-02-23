## [5.0.0-dev.1](https://github.com/banter240/tado_hijack/compare/v4.3.0...v5.0.0-dev.1) (2026-02-23)

### ⚠ BREAKING CHANGES

* **core:** Major architectural refactoring (executor system, polling,
data flow). While backwards compatibility is maintained, the internal structure
has changed significantly. Report any issues via Discord or GitHub.

### ✨ New Features

* feat(core): Tado X generation support with modular architecture and production refinements

🚧 PRODUCTION-READY BUILD 🚧

This release introduces first-class support for Tado X generation alongside the
existing v3 Classic support through a comprehensive architectural refactoring,
followed by extensive production testing and refinements.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 TADO X GENERATION SUPPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hybrid Enrollment Architecture:
- Implemented complete Tado X API client (TadoXApi) for X-specific endpoints
- Created TadoXMapper provider for unified data access across generations
- Added automatic generation detection in config flow with manual override option
- Developed X-specific discovery and device handling logic
- Full support for Tado X room states and metadata fetching
- Implemented quickActions/allOff support for Tado X

Provider Protocol:
- Introduced UnifiedDataProvider protocol for generation-agnostic data access
- Enables seamless switching between v3 and X implementations
- Unified data models (UnifiedTadoData, UnifiedZoneState) for consistent access
- Dynamic capability detection for feature availability per generation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ UNIFIED POLLING OPTIMIZATION (DRY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intelligent Poll-Plan System:
- Restored DRY poll-plan-based polling for BOTH v3 and X generations
- Reduced API calls from 4 → 1 per poll (v3 Classic)
- Reduced API calls from 2 → 1 per poll (Tado X)
- Generation-aware task creation in unified poll plan builder
- Interval-based metadata polling (fast track: every poll, slow track: infrequent)

Adaptive Quota Management:
- Adaptive API quota reset window learning
- Comprehensive quota management and redundancy suppression system
- Intelligent rate limit tracking for optimal API usage
- Dynamic adjustment based on API response patterns

Selective Merge Protection:
- Prevents poll data from overwriting pending command state
- Protected fields during command execution (overlay, setting, presence)
- Optimistic state updates for immediate UI responsiveness
- Smart merge logic aware of in-flight commands

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏗️ MODULAR EXECUTOR ARCHITECTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Executor System:
- Extracted BaseExecutor with common execution logic
- Created generation-specific executors (TadoV3Executor, TadoXExecutor)
- Implemented TadoUnifiedExecutor for centralized command routing
- Consolidated all API command execution in one place
- Improved error handling and rollback mechanisms

Command Management:
- Enhanced command queuing with detailed action logging
- Shows command type, key, debounce time, and action details
- Logs queued vs replaced pending status for debugging
- Command batching with 5s debounce window and 1s linger time
- Unified command merger for efficient batch processing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ CODE QUALITY & SECURITY OFFENSIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Strict Type Safety (Mypy Hardening):
- Aligned project with strict Mypy rules from python-tado upstream
- Achieved 100% type safety with zero Mypy errors across 70+ source files
- Implemented robust type hints for Callables, Coroutines, and Generics
- Cleaned up redundant casts and improved internal data model consistency

Modern Linting (Ruff ALL Mode):
- Enabled Ruff 'ALL' mode for comprehensive static analysis
- Automated formatting and linting for consistent code style
- Eliminated unused imports, missing docstrings (D417), and shadowed variables

Security & Stability:
- Integrated CodeQL security analysis workflow for automated vulnerability scanning
- Added Gitleaks secret detection for proactive credential protection
- Resolved critical Circular Import issues by decoupling helper packages
- Empty __init__.py hubs for helpers.tadox/tadov3 to ensure reliable HA boot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 LIBRARY ORGANIZATION & UPSTREAM PREPARATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TadoX Library Reorganization:
- Moved: helpers/patch.py → lib/patches.py (upstream-ready format)
- Moved: helpers/tadox/api.py → lib/tadox_api.py (comprehensive docs)
- Moved: helpers/tadox/models.py → lib/tadox_models.py
- Added: lib/__init__.py with clean public API exports for future integration

Enhanced Code Documentation:
- Comprehensive module docstrings explaining architectural patterns
- Documented tadoasync private attribute usage for future upstream discussion
- All public methods now feature detailed type-annotated docstrings
- Clear separation between v3 Classic and Tado X implementation logic

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🐛 PRODUCTION FIXES & REFINEMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HACS & Localization:
- Fixed GEN_X constant naming for HACS compliance (lowercase alphanumeric)
- Updated German and English translations for all new Tado X features
- Improved config flow UI with descriptive help texts and auto-detection

API Compatibility:
- Optimized API RateLimit header parsing using robust extract helper pattern
- Native power=OFF support with proper magic number mapping
- Correct room/zone state handling for Tado X generation
- Fixed temperature offset handling with proper object instantiation

Hot Water & HVAC:
- Support duration and overlay_mode for hot water OFF commands
- Comprehensive AC improvements and code quality enhancements
- Fixed hot water activity data rescue in ZoneState patch
- Proper handling of hot water zones in both generations

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This release maintains full backwards compatibility with Tado v3 Classic while
adding production-ready support for Tado X. The modular architecture enables
future extensions and integrations. All code has been battle-tested through
multiple development iterations and is verified against Home Assistant 2026.1+.

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
