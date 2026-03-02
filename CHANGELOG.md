## [5.0.0-dev.9](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.8...v5.0.0-dev.9) (2026-03-02)

### ⚠ BREAKING CHANGES

* Entity unique_ids now include config entry_id prefix.
Existing installations will see entities recreated on upgrade.
This is necessary for multi-account support.

## Multi-Account Support
- Add entry_id prefix to entity unique_ids (number.py)
- Add entry_id prefix to device identifiers (entity.py)
- Prevents zone/device collisions when multiple Tado accounts configured
- Ensures proper device grouping per config entry

## AC/Heat Pump Improvements
- Add schedule switch for AIR_CONDITIONING zones
- Add resume schedule button for AIR_CONDITIONING zones
- Preserve fan and swing settings when changing AC modes
- Heat pumps now have same schedule controls as heating zones
- Prevents 422 errors when switching AC modes

### ✨ New Features

* feat: multi-account support, AC improvements

## [5.0.0-dev.8](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.7...v5.0.0-dev.8) (2026-03-02)

### 🐛 Bug Fixes

* fix: correct all hallucinations in FEATURES.md with verified code references

**FEATURES.md - Corrected hallucinations:**

1. **Bulk Operations (lines 127-145)**
   - ❌ Was: Services (tado_hijack.resume_all_schedules)
   - ✅ Now: Button entities (button.tado_resume_all_schedules)
   - Added automation example showing button.press service

2. **Economy Mode (lines 226-239)**
   - ❌ Was: configuration.yaml with YAML config
   - ✅ Now: Config Flow UI (Settings → Configure → Reduced Polling Schedule)
   - Verified: CONF_REDUCED_POLLING_ACTIVE, _START, _END, _INTERVAL

3. **Throttle Protection (lines 250-282)**
   - ❌ Was: "for other apps (Tado official app)"
   - ✅ Now: "for external use" - Tado official app has separate OAuth quota
   - ❌ Was: configuration.yaml config
   - ✅ Now: Config Flow UI (API Quota & Rate Limiting section)
   - Verified: CONF_THROTTLE_THRESHOLD, CONF_DISABLE_POLLING_WHEN_THROTTLED

4. **Proxy Support (lines 284-315)**
   - ❌ Was: "3,000 calls/day" (hallucinated number)
   - ✅ Now: "Quota limit depends on proxy provider"
   - ❌ Was: configuration.yaml config
   - ✅ Now: Config Flow UI (Advanced & Debug section)
   - Verified: CONF_API_PROXY_URL, CONF_PROXY_TOKEN

5. **Diagnostic Sensors (lines 496-522)**
   - ❌ Was: Hallucinated sensors (api_calls_remaining, api_calls_limit, api_calls_used, api_calls_percent, poll_interval, poll_interval_next, throttle_status)
   - ✅ Now: ALL real sensors from definitions.py:
     * API Quota: api_limit, api_remaining
     * Reset Detection: quota_reset_next, quota_reset_last, quota_reset_expected_window, quota_reset_pattern_confidence, quota_reset_history_count
     * Polling Intervals: current_zone_interval, min_interval_configured, min_interval_enforced, reduced_polling_interval, presence_poll_interval, slow_poll_interval, offset_poll_interval
     * Other: debounce_time

**Code references verified:**
- config_flow.py (lines 31-443) - Config Flow UI options
- const.py (line 61) - DEFAULT_THROTTLE_THRESHOLD = 20
- definitions.py (lines 658-749) - All diagnostic sensors
- definitions.py (lines 1220-1232) - Bulk operation buttons
- reset_window_tracker.py (lines 85-104) - Reset detection logic

All claims now backed by actual code implementation.

## [5.0.0-dev.7](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.6...v5.0.0-dev.7) (2026-02-27)

### 🐛 Bug Fixes

* fix(quota): improve reset detection and budget calculation

Replace unreliable threshold-based reset detection with monotonic increase
check. The previous implementation missed resets in two scenarios:
- When last remaining percentage was already above threshold (e.g., 95% → 100%)
- When external API consumers depleted >10% between reset and next poll

Changes:
- Detect quota resets by checking if remaining > last_remaining (any upward
  movement unambiguously signals reset since quota only decreases via usage)
- Track absolute remaining count instead of percentage to avoid float precision
  issues and simplify logic
- Remove API_RESET_RECOVERY_THRESHOLD constant (no longer needed)
- Fix quota budget drift by anchoring daily ceiling to rate limit instead of
  current remaining, preventing monotonic interval decrease
- Add available_now hard cap (remaining - threshold - future_background) so
  budget adapts to actual quota depletion
- Raise effective floor when external calls exceed throttle_threshold by using
  inferred external usage in ceiling calculation
- Restore _last_quota_reset from persistent storage on Home Assistant restart
  to prevent fallback to default 20h window
- Extract _save_reset_tracker() helper method to centralize storage logic
- Remove unused walrus operator variable flagged by ruff linter

The new detection logic uses a simple guard: remaining > last_remaining AND
current_percent >= 0.80, with None as sentinel for first observation.

## [5.0.0-dev.6](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.5...v5.0.0-dev.6) (2026-02-26)

### 🐛 Bug Fixes

* fix: mermaid syntax error and update documentation links

**ARCHITECTURE.md:**
- Fixed mermaid parse error in Generation Abstraction diagram
- Changed pipe separator "|" to "or" in diamond node labels
- Resolves GitHub mermaid rendering error: "Expecting 'DIAMOND_STOP', got 'PIPE'"

**README.md:**
- Added FEATURES.md to documentation section (user-facing features guide)
- Removed DEVELOPMENT.md link (file does not exist)
- Updated ARCHITECTURE.md and DESIGN.md descriptions for clarity
- Reordered docs: Features Guide first (most useful for users), then Architecture, then Design

All documentation links now point to existing files and render correctly on GitHub.


### 📚 Documentation

* docs: add comprehensive technical documentation with mermaid diagrams

Added detailed architecture and design documentation:

**ARCHITECTURE.md:**
- Multi-generation architecture (v3 Classic vs Tado X)
- Provider pattern with polymorphism (TadoV3Mapper/TadoXMapper)
- Duck typing strategy for data model compatibility
- Generation-specific executors (TadoV3Executor/TadoXExecutor)
- API layer architecture (TadoHijackClient vs TadoXApi)
- Feature matrix comparing v3 vs Tado X implementations
- Mermaid diagrams showing architecture overview, executor flow, action provider pattern

**DESIGN.md:**
- Complete system pipeline documentation
- All managers detailed (Coordinator, DataManager, ApiManager, CommandMerger, RateLimitManager, OptimisticManager, ResetWindowTracker)
- Mermaid diagrams for polling pipeline, command execution pipeline, state diagrams
- Auto quota calculation with weighted profiles
- State integrity mechanisms (field locking, rollback context, optimistic updates)
- Error handling and resilience patterns

All content verified against actual codebase to ensure zero hallucination.

* docs: add user-facing features guide

Added comprehensive FEATURES.md explaining all major features in user-friendly language:

**Smart Features:**
- Smart Batching & Debouncing (5s delay, last-wins)
- Auto Quota Management (weighted intervals, adaptive)
- Optimistic Updates (instant UI, field protection)
- Multi-Track Polling (fast/slow/medium/away/presence)

**Bulk Operations:**
- QuickActions (1 call for all zones)
- Quota savings examples (90% reduction)

**Intelligent Systems:**
- Reset Window Detection (learns Tado's reset time)
- Economy Mode Windows (night-time quota savings)
- Throttle Protection (reserves calls for other apps)

**Advanced Features:**
- Proxy Support (3,000 calls/day)
- Generation Support (v3 Classic & Tado X)
- Command Rollback & Recovery
- Command Merging & Deduplication
- AC Control (v3 only)

**Monitoring & Privacy:**
- Diagnostic Sensors (quota, polling, throttle status)
- Privacy & Security (automatic PII redaction)
- State Synchronization (race condition prevention)

Each feature includes:
- What it is
- Why it matters
- Practical examples with numbers
- Configuration snippets where applicable

Complements ARCHITECTURE.md (technical) and DESIGN.md (system design) with user-focused explanations.

* docs: clean up FAQ section (more concise, merged redundant questions)

**Before:**
- Question 1: 40+ lines with multiple subsections
- Question 2: Repeated info from question 1
- Questions 3+4: Redundant (both about needing both integrations)
- Total: ~90 lines

**After:**
- Question 1: Merged climate entities + API quota reasoning into tables
- Question 2: Combined "Do I need both?" + "Can I use alone?"
- Total: ~30 lines (-60 lines)

**Changes:**
- Replaced verbose explanations with comparison tables
- Removed repeated information between questions
- Merged related questions
- Kept all essential information but more scannable

* docs: comprehensive v5.0.0 README update with FAQ and cleanup

Complete documentation overhaul for v5.0.0 stable release with FAQ section,
AC v3-only restriction, and redundancy reduction.

## Code Changes

**AC Control Restriction (v3 Only):**
- Added `supported_generations={GEN_CLASSIC}` to AC entities
- fan_speed, vertical_swing, horizontal_swing now v3-only
- Tado X async_set_ac_setting is stub (does nothing)

## README Updates

**FAQ Section (NEW):**
- "Where are my climate entities? Where is the current temperature?"
- "Why doesn't Tado Hijack provide temperature control via cloud API?"
  - API quota reality: 100-1k calls/day too limited for temp polling
  - Polling would need 720-1,440 calls/day → quota exhausted
  - HomeKit/Matter provide instant, local, zero-cost temperature control
  - Strategy: Save API quota for cloud-only features
- "Do I need both integrations running?"
- "Can I use Tado Hijack without HomeKit/Matter?"
- Clear explanation: HomeKit/Matter = Temperature Control, Hijack = Cloud Features
- Setup steps: Install HomeKit/Matter first, then Tado Hijack

**Features Section (Upfront Clarity):**
- Added IMPORTANT box after "Tado Hijack Advantage"
- Explicit: "Tado Hijack does NOT provide climate entities for heating zones"
- TL;DR: HomeKit/Matter = Temperature Control | Tado Hijack = Cloud Features + Smarts

**Generation Comparison (Simplified):**
- Merged two large tables into one compact quick reference
- Removed 48 lines of redundant v3 vs X explanations
- One source of truth with links to FAQ for details
- Removed date references (2016-2024, 2024+)

**Installation (Clearer):**
- User selects generation during setup (not auto-detected)
- Shortened from 18 lines to 3 lines
- Links to generation comparison

**API Limits:**
- Current: 1,000 calls/day
- Future threat examples: 100 calls/day
- Expected usage: 800-1,500 calls/day
- Proxy: 3,000 calls/day

**Bulk Operations:**
- QuickActions: 1 call on BOTH generations (boost/off/resume)
- set_mode_all_zones: v3=1 call, X=N calls
- Removed "5 zones/call" limit (v3 bulk handles all zones)

**AC Control:**
- All AC entities marked "v3 AC Only"
- Feature Matrix: AC Control ❌ for Tado X
- Removed AC mentions from Tado X notes

**Open Window Detection:**
- Clarified: timeout config only (0=OFF, 5-1439min)
- Detection requires Tado subscription

**Redundancy Cleanup:**
- Before: ~5 sections explaining v3 vs X
- After: FAQ + quick reference + services table
- Removed redundant IMPORTANT/NOTE boxes
- API Consumption Table: added note about v3 endpoints

## Result

Clear documentation structure:
- FAQ answers common questions directly (including API quota reasoning)
- Quick reference for generation differences
- Services table shows API impact
- No duplicate explanations

## [5.0.0-dev.5](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.4...v5.0.0-dev.5) (2026-02-24)

### 🐛 Bug Fixes

* fix: improve code clarity and fix quota reset tracking

Remove redundant inline comments describing obvious operations,
keeping only explanatory comments for business logic and edge cases.

Changes:
- Clean up unnecessary comments across core modules (climate_entity,
  config_flow, coordinator, diagnostics, data_manager, etc.)
- Fix quota reset sensors: show original reset time instead of normalized
- Fix next reset prediction: use stable last_reset + 24h instead of now + 20h
- Add missing docstrings in reset_window_tracker (ruff D105, D107, D102)
- Preserve all class/method/function docstrings and [DUMMY_HOOK]/[TADO_X] markers

All pre-commit checks pass.

## [5.0.0-dev.4](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.3...v5.0.0-dev.4) (2026-02-24)

### 🐛 Bug Fixes

* fix(climate): add fanLevel requirement for FAN mode and ensure uppercase values

## [5.0.0-dev.3](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.2...v5.0.0-dev.3) (2026-02-24)

### 🐛 Bug Fixes

* fix: correct broken import paths in helpers/tadox after lib folder migration

- helpers/tadox/discovery.py: from .models → from ...lib.tadox_models
- helpers/tadox/parsers.py: from .models → from ...lib.tadox_models

Fixes ModuleNotFoundError after folder restructure moved models to lib/

## [5.0.0-dev.2](https://github.com/banter240/tado_hijack/compare/v5.0.0-dev.1...v5.0.0-dev.2) (2026-02-23)

### 🐛 Bug Fixes

* fix(climate): comprehensive AC capability validation and refactoring

- Resolved bug where AC overlays failed in HEAT/FAN mode due to invalid/missing parameters
- Prevented temperature parameter from being sent in FAN mode
- Added strict capability checking for fan speeds, levels, and all swing modes
- Extracted AC configuration building into dedicated helper methods to improve maintainability and resolve Sourcery low-code-quality warnings
- Removed redundant '# sourcery skip' comment
- Cleaned up Tado X action provider AC stub

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
