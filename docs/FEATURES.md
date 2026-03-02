# Features Guide

User-friendly guide to Tado Hijack's smart features and how they benefit you.

---

## 🚀 Smart Batching & Debouncing

**What it is:** When you make rapid changes (multiple service calls, button clicks, or automation adjustments), Tado Hijack waits 5 seconds before sending the final value to Tado's API.

**Why it matters:**
- Saves API quota (1 call instead of 10+ calls)
- Prevents API rate limiting
- Faster UI response

**Example:**
```
Scenario 1: Hot Water Climate Entity (v3)
→ User clicks "Turn On" button
→ User clicks "Boost" button 2 seconds later
Traditional integration: 2 API calls
Tado Hijack: 1 API call (merged)

Scenario 2: Automation Adjusts Multiple Zones
→ Automation sets zone 5 to 21°C
→ Automation sets zone 6 to 22°C (0.5s later)
→ Automation sets zone 7 to 20°C (1s later)
Traditional integration: 3 API calls
Tado Hijack: 1 API call (all merged into batch)

Scenario 3: Temperature Offset Number Entity
→ User clicks + button twice
→ Offset changes: 0.0 → +0.5 → +1.0
Traditional integration: 2 API calls
Tado Hijack: 1 API call (final value +1.0)
```

**How it works:**
- First change starts 5-second timer
- Subsequent changes reset the timer
- Timer expires → sends final value
- Multiple zones/devices changed → merged into single batch

---

## 📊 Auto Quota Management

**What it is:** Automatically adjusts polling frequency based on your remaining API quota and time until reset.

**Why it matters:**
- Never runs out of API quota
- More updates during daytime (when you're home)
- Fewer updates at night (when you're sleeping)
- Learns your daily quota reset time

**How it works:**
- **Morning (7 AM - 10 PM):** Faster polling (every 60-120s)
- **Night (10 PM - 7 AM):** Slower polling (every 300s) or disabled
- **Low quota:** Automatic throttle protection
- **After reset:** Resumes normal polling

**Weighted calculation:**
```
Performance window (daytime): 2.0× weight → more frequent polls
Economy window (night): 0.5× weight → less frequent polls
```

**Adaptive behavior:**
- Monitors remaining quota in real-time
- Calculates optimal interval to use 80% of daily quota
- Reserves 20% for manual commands and other apps
- Increases interval when quota is low

---

## ⚡ Optimistic Updates

**What it is:** UI updates instantly when you change settings, before API confirms.

**Why it matters:**
- No laggy UI
- No spinner/loading states
- Feels like local control
- Protected from race conditions

**Example:**
```
You adjust AC climate entity temperature to 22°C (v3)
→ UI shows 22°C immediately
→ API call happens in background
→ Polling paused for this field
→ Next poll confirms state (no flicker)
```

**Field protection:**
While a command is pending, polling won't overwrite the predicted state. Once API confirms, polling resumes merging that field.

**Automatic rollback:**
If API call fails, optimistic state is reverted to last known good value.

---

## 🎯 Bulk Operations (QuickActions)

**What it is:** Control all heating zones with one button press.

**Why it matters:**
- 1 API call instead of N calls
- Works for both v3 Classic and Tado X
- Saves massive API quota
- Instant house-wide control

**Available operations:**
- **Resume All Schedules** - Return all zones to schedule (1 call)
- **Boost All Zones** - Heat all zones to 25°C (1 call)
- **Turn Off All Zones** - Stop heating everywhere (1 call)

**Quota savings:**
```
10 zones in your home:
Traditional: 10 zones × 1 call = 10 API calls
Tado Hijack: 1 API call (bulk operation)

Savings: 90% fewer API calls
```

**Access via Home Assistant:**
```yaml
# Button entities (press in UI or via automation)
button.tado_resume_all_schedules
button.tado_boost_all_zones
button.tado_turn_off_all_zones
```

**Example automation:**
```yaml
automation:
  - alias: "Resume all zones at 10 PM"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.tado_resume_all_schedules
```

---

## 🔄 Multi-Track Polling

**What it is:** Different data types update at different speeds based on how often they change.

**Why it matters:**
- Critical data (temperature) updates frequently
- Static data (zone names) updates rarely
- Minimizes API quota waste
- Intelligent data freshness

**Poll tracks:**

| Track | Frequency | Data | Why |
|-------|-----------|------|-----|
| **Fast** | Every poll | Zone states, temperature, overlay | Changes frequently |
| **Slow** | Every 30 min | Zone metadata, device list | Rarely changes |
| **Medium** | Every 2 hours | Temperature offsets (v3) | Occasional changes |
| **Away** | Once at startup | Away temperature config (v3) | Almost never changes |
| **Presence** | Every 5 min | Home/Away presence (v3) | Moderate changes |

**Example daily quota usage:**
```
Fast track: 1,440 calls/day (every minute)
Slow track: 48 calls/day (every 30 min)
Medium track: 12 calls/day (every 2 hours)
Away track: 1 call/day (startup only)
Presence track: 288 calls/day (every 5 min)

With auto-quota enabled: Dynamically adjusted to stay within limit
```

---

## 🕐 Reset Window Detection

**What it is:** Learns when Tado resets your daily API quota (usually around 12:00-13:00 Berlin time).

**Why it matters:**
- Conserves remaining quota before reset
- Resumes aggressive polling after reset
- Diagnostic sensor shows predicted reset time
- Adapts to Tado's actual reset time (not hardcoded)

**Behavior:**
```
11:30 AM: 50 API calls remaining
→ Slows down polling (saving last calls for emergencies)

12:30 PM: Quota jumps from 50 → 980
→ Reset detected and recorded
→ Timestamp normalized to 12:30 (groups resets in same hour)
→ Predicts next reset: tomorrow at 12:30 PM
→ Resumes normal polling with fresh quota

Pattern learning:
- First reset: Confidence = "single_observation" (recorded, not trusted yet)
- Second reset in same hour (12:XX): Confidence = "learned" (pattern confirmed)
- Default window: 12:00-13:00 Berlin time (used before pattern learned)
```

**Diagnostic sensors:**
- `sensor.tado_quota_reset_next` - Predicted next reset time
- `sensor.tado_quota_reset_confidence` - Prediction confidence (0-100%)

---

## 💤 Economy Mode Windows

**What it is:** Configurable time windows with reduced or zero polling to save API quota.

**Why it matters:**
- Saves quota during sleep hours
- Allocates more calls to active hours
- Customizable per your schedule
- Works with weighted quota calculation

**Configuration:**
Via Home Assistant UI: **Settings → Integrations → Tado Hijack → Configure → Reduced Polling Schedule**

Options:
- **Active:** Enable reduced polling window (boolean)
- **Start Time:** When to begin reduced polling (e.g., 22:00)
- **End Time:** When to resume normal polling (e.g., 07:00)
- **Interval:** Polling interval during window in seconds (0 = disabled, >0 = reduced)

**Behaviors:**
- **Interval = 0:** No polling during window
- **Interval > 0:** Custom interval (e.g., 300s = every 5 minutes)

**Example:**
```
Normal interval: 120 seconds
Economy window (22:00-07:00): 240 seconds (reduced) or 0 (disabled)
Performance window (07:00-22:00): 90 seconds (more aggressive)

Daily quota usage optimized to your actual usage pattern
```

---

## 🛡️ Throttle Protection

**What it is:** Reserves last N API calls for external use (manual commands via HA, emergency changes).

**Why it matters:**
- Integration doesn't consume 100% of quota
- Reserves calls for manual interventions
- Emergency control always available
- Configurable threshold

**Important:** Tado official app uses its own OAuth credentials and has separate quota. This reserves calls for YOUR Home Assistant commands and scripts.

**Behavior:**
```
Remaining calls: 500
→ Status: Normal polling (every 120s)

Remaining calls: 50
→ Status: Approaching limit, slowing down

Remaining calls: 20 (default threshold)
→ Status: Throttled
→ Option A: Stop polling entirely (reserve for manual use)
→ Option B: 15-minute intervals (minimal polling)
```

**Configuration:**
Via Home Assistant UI: **Settings → Integrations → Tado Hijack → Configure → API Quota & Rate Limiting**

Options:
- **Throttle Threshold:** Number of calls to reserve (default: 20)
- **Disable Polling When Throttled:** Stop polling entirely vs slow to 15-min intervals

---

## 🌐 Proxy Support

**What it is:** Route API calls through an intermediary proxy server instead of directly to Tado API.

**Why it matters:**
- Bypass personal quota limits (proxy uses its own credentials)
- Quota limit depends on proxy provider
- Same response format (transparent routing)
- No changes to entity behavior

**Setup:**
Via Home Assistant UI: **Settings → Integrations → Tado Hijack → Configure → Advanced & Debug**

Options:
- **API Proxy URL:** Proxy server base URL (e.g., `https://tado-proxy.example.com`)
- **Proxy Token:** Authentication token for proxy access

**How it works:**
- Integration routes requests through proxy
- Proxy forwards to Tado API with its own OAuth credentials
- Quota limits from proxy's rate limit headers
- Response returned to integration unchanged

**When to use:**
- Exceeded Tado's API quota (1,000 calls/day)
- Multiple automations requiring frequent updates
- Large homes (10+ zones) needing aggressive polling
- Development/testing with high API usage

**Note:** Proxy quota varies by provider. Check with your proxy service for specific limits.

---

## 🏠 Generation Support (v3 Classic & Tado X)

**What it is:** Single integration supporting both hardware generations with generation-specific optimizations.

**Why it matters:**
- Works with IB01/GW01 bridges (v3 Classic)
- Works with IB02 Bridge X (Tado X)
- Uses correct API for each generation
- No need to switch integrations when upgrading hardware

**Selection during setup:**
```
Which generation do you have?
→ Tado v3 Classic (IB01/GW01 bridge)
→ Tado X (IB02 Bridge X)
```

**Generation-specific features:**

| Feature | v3 Classic | Tado X | Notes |
|---------|------------|--------|-------|
| Zone control | ✅ | ✅ | Both supported |
| Bulk operations | ✅ (1 call) | ✅ (1 call) | QuickActions for both |
| AC control | ✅ | ❌ | v3 only (fan speed, swing) |
| Away temperature | ✅ | ❌ | v3 has separate config |
| Dazzle mode | ✅ | ❌ | v3 care & protect |
| Early start | ✅ | ❌ | v3 optimization |
| Temperature offset | ✅ | ✅ | Both support |
| Child lock | ✅ | ✅ | Both support |
| Open window detection | ✅ | ✅ | Cloud timeout config only |

**API differences handled transparently:**
- v3 Classic: `my.tado.com` API (tadoasync library)
- Tado X: `hops.tado.com` API (custom TadoXApi)
- Same unified data model for entities

---

## 🔐 Privacy & Security

**What it is:** Automatic PII (Personally Identifiable Information) redaction in Home Assistant logs.

**Why it matters:**
- Tokens never appear in logs
- Serial numbers redacted
- Home IDs protected
- Safe to share logs for debugging
- Privacy-first design

**Protected data:**
```
Before redaction:
access_token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
serial: "RU12345678"
homeId: 123456

After redaction:
access_token: "REDACTED"
serial: "REDACTED"
homeId: "REDACTED"
```

**Redacted fields:**
- OAuth tokens (access_token, refresh_token)
- Device serials (RU*, VA*, IB*, GW*)
- Home IDs
- User IDs
- Email addresses

**Always safe to share:**
- Home Assistant logs with redaction enabled
- Debug logs for issue reports
- Configuration examples

---

## 🔄 Command Rollback & Recovery

**What it is:** Automatic state restoration if API calls fail.

**Why it matters:**
- UI doesn't show incorrect state
- Failed commands don't leave orphaned state
- Graceful error handling
- User gets visual feedback

**How it works:**
```
1. User turns on AC climate entity and sets to 22°C (v3)
2. Optimistic update: UI shows 22°C
3. API call fails (network error)
4. Rollback: UI reverts to previous value (20°C)
5. User sees error notification
6. State remains consistent
```

**Rollback context:**
Every command stores old values before execution:
```python
{
  "zone_5": {"temp": 20.0, "power": "ON"},  # Before
  "zone_7": {"temp": 18.0, "power": "ON"}
}

Command fails → restore old values
Command succeeds → discard rollback context
```

---

## 🔧 Command Merging & Deduplication

**What it is:** Multiple commands to the same entity are merged into one API call.

**Why it matters:**
- Saves API quota
- Reduces API latency
- Handles rapid automation changes
- Optimal batching

**Example scenario:**
```
Automation runs at 08:00:
- Call service: climate.set_temperature (zone 5 to 21°C)
- Call service: climate.set_temperature (zone 6 to 22°C)
- Call service: climate.set_temperature (zone 7 to 20°C)
- Call service: switch.turn_on (child lock RU12345678)
- Call service: number.set_value (temp offset +2.0 VA87654321)

Traditional: 5 API calls
Tado Hijack: 1 API call (all merged into batch)
```

**Merge rules:**
- Same zone, multiple overlays → last overlay wins
- Resume schedule overrides overlay
- Device properties merged by serial number
- Presence commands merged (only one per batch)

---

## 🎛️ AC Control (v3 Classic Only)

**What it is:** Full control over AC units including fan speed and swing modes.

**Why it matters:**
- Complete climate control via Home Assistant
- No need to use Tado app for AC settings
- Automations can adjust fan speed and swing
- Works via cloud API (unlike local HomeKit)

**Available controls:**
- **Fan Speed:** auto, low, middle, high
- **Vertical Swing:** off, on, auto, up, mid_up, mid, mid_down, down
- **Horizontal Swing:** off, on, auto, left, mid_left, mid, mid_right, right

**Access via entities:**
```
select.zone_5_fan_speed
select.zone_5_vertical_swing
select.zone_5_horizontal_swing
```

**Why Tado X doesn't support:**
Tado X uses Matter protocol for local control. AC capabilities are handled through Matter bridge, not cloud API.

---

## 📈 Diagnostic Sensors

**What it is:** Extra sensors providing insight into integration health and quota usage.

**Why it matters:**
- Monitor API quota in real-time
- Track polling performance
- Predict quota reset time
- Debug issues

**Available sensors:**

| Sensor | Description |
|--------|-------------|
| **API Quota Sensors** | |
| `sensor.tado_api_limit` | Daily API call limit (from rate limit headers) |
| `sensor.tado_api_remaining` | API calls remaining today |
| **Reset Detection Sensors** | |
| `sensor.tado_quota_reset_next` | Predicted next reset time (timestamp) |
| `sensor.tado_quota_reset_last` | Last observed reset time (timestamp) |
| `sensor.tado_quota_reset_expected_window` | Expected reset window (e.g., "12:30 (learned)") |
| `sensor.tado_quota_reset_pattern_confidence` | Confidence: "learned", "single_observation", or "default" |
| `sensor.tado_quota_reset_history_count` | Number of recorded resets |
| **Polling Interval Sensors** | |
| `sensor.tado_current_zone_interval` | Current polling interval in seconds |
| `sensor.tado_min_interval_configured` | User-configured minimum interval |
| `sensor.tado_min_interval_enforced` | Actual enforced minimum (may differ due to throttling) |
| `sensor.tado_reduced_polling_interval` | Interval during economy window |
| `sensor.tado_presence_poll_interval` | Presence tracking interval (v3) |
| `sensor.tado_slow_poll_interval` | Slow track interval (metadata) |
| `sensor.tado_offset_poll_interval` | Offset track interval (v3) |
| **Other Sensors** | |
| `sensor.tado_debounce_time` | Command debounce time in seconds |

**Example automation:**
```yaml
automation:
  - alias: "Notify when API quota low"
    trigger:
      - platform: numeric_state
        entity_id: sensor.tado_api_remaining
        below: 50
    action:
      - service: notify.mobile_app
        data:
          message: "Tado API quota low: {{ states('sensor.tado_api_remaining') }} calls remaining"
```

---

## 🔁 State Synchronization & Race Condition Prevention

**What it is:** Smart field locking prevents concurrent API calls from conflicting.

**Why it matters:**
- Multiple automations can run simultaneously
- UI changes don't conflict with polling
- Commands execute in correct order
- No lost updates

**How it works:**
```
Scenario: Polling and command happen at same time

Without protection:
1. User calls service to set AC temp to 22°C (v3)
2. Polling fetches old state (20°C)
3. Poll overwrites UI → shows 20°C (wrong!)
4. User confused

With protection:
1. User calls service to set AC temp to 22°C (v3)
2. Field "temperature" marked as protected
3. Polling fetches old state (20°C)
4. Poll skips merging "temperature" field
5. UI stays at 22°C (correct!)
6. Next poll after API confirms → merge allowed
```

**Protected during pending commands:**
- Zone temperature
- Zone power state
- Zone overlay settings
- Device child lock
- Device temperature offset

---

## 🧪 Development & Testing Features

**What it is:** Built-in tools for developers and advanced users.

**Why it matters:**
- Easy debugging
- Safe testing
- Code quality
- Community contributions

**Features:**

**Pre-commit hooks:**
```bash
# Automatically run on git commit
- Ruff (linting)
- MyPy (type checking)
- Prettier (formatting)
- Gitleaks (secret scanning)
```

**Logging:**
```yaml
# Enable debug logging
logger:
  default: info
  logs:
    custom_components.tado_hijack: debug
```

**Test config:**
```
testing_config/
├── configuration.yaml
├── secrets.yaml
└── automations.yaml
```

**Semantic versioning:**
- Automatic changelog generation
- Dev releases for testing (v5.0.0-dev.1)
- Stable releases via GitHub

---

## Summary

Tado Hijack combines all these features to provide:

✅ **Minimal API quota usage** - Smart batching, debouncing, multi-track polling
✅ **Fast, responsive UI** - Optimistic updates, no lag
✅ **Intelligent polling** - Auto-quota, weighted intervals, reset detection
✅ **Bulk operations** - House-wide control in 1 API call
✅ **Both v3 Classic and Tado X** - Single integration for all hardware
✅ **Privacy-first** - Automatic PII redaction
✅ **Reliable** - Rollback on errors, race condition prevention
✅ **Transparent** - Diagnostic sensors, debug logging

**For users:** Just install and enjoy smart heating control without thinking about API limits.

**For developers:** Clean architecture, comprehensive docs, easy contributions.
