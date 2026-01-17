## [1.1.0-dev.1](https://github.com/banter240/tado_hijack/compare/v1.0.0...v1.1.0-dev.1) (2026-01-17)

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
