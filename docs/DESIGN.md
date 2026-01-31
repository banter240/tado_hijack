# Tado Hijack - Architectural Design & Core Concepts

## 🏴‍☠️ Introduction

Tado Hijack is a high-performance, precision-engineered Home Assistant integration designed to bypass the artificial scarcity of the Tado Cloud API. Unlike standard integrations, it treats every API call like gold, utilizing advanced command merging, JIT (Just-In-Time) polling, and HomeKit injection to provide a seamless, local-feeling experience despite cloud limitations.

---

## 🏗️ Core Architecture

### High-Depth System Schematic (The Pipeline)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Home Assistant Ecosystem                           │
│        (Dashboard UI, Automations, Scripts, Third-Party Integrations)       │
└──────┬──────────────────────────────────┬────────────────────────────┬──────┘
       │                                  │                            │
       │ (1) Service Call                 │ (A) Local Interaction      │ (E) State
       ▼ (tado_hijack.set_mode)           ▼ (HomeKit Climate Entity)   ▼ Updates
┌────────────────────────────┐    ┌───────────────────────────┐    ┌──────────┐
│     Tado Hijack Entity     │    │  HomeKit climate Entity   │    │  Other   │
│ (Schedule, HW, AC, Settings)    │ (Temp, HVAC, Modulation)  │    │ Entities │
└──────┬─────────────────────┘    └──────┬────────────────────┘    └────▲─────┘
       │                                 │                              │
       │ (2) Command Dispatch            │ (B) Intercept Event          │
       ▼                                 ▼                              │
┌───────────────────────────────────────────────────────────────────────┼─────┐
│                             Tado Hijack Core                          │     │
│                                                                       │     │
│  ┌───────────────────────┐         ┌──────────────────────────────┐   │     │
│  │   OptimisticManager   │◄──(3)───┤         APIManager           │   │     │
│  │ (UI Instant Patching) │         │ (Debounce, Batching, Jitter) │   │     │
│  └──────────┬────────────┘         └──────────────┬───────────────┘   │     │
│             │                                     │                   │     │
│             │ (4) Update Listeners                │ (5) Put in Queue  │     │
│             └──────────────────┐                  ▼                   │     │
│                                │        ┌───────────────────┐         │     │
│                                └───────►│  API_QUEUE (FIFO) │         │     │
│                                         └─────────┬─────────┘         │     │
│  ┌──────────────────────┐                         │                   │     │
│  │     DataManager      │◄──────────(7)───────────┤ (6) Worker Loop   │     │
│  │ (JIT Poll / Cache)   │                         │   (While True)    │     │
│  └──────────┬───────────┘                         ▼                   │     │
│             │                      ┌──────────────────────────────┐   │     │
│             │ (8) Cache Status     │       RateLimitManager       │   │     │
│             └─────────────────────►│ (Quota Budget, Adaptive Int) │   │     │
│                                    └──────────────┬───────────────┘   │     │
│                                                   │                   │     │
│  ┌──────────────────────┐          ┌──────────────▼───────────────┐   │     │
│  │    EntityResolver    │          │      TadoRequestHandler      │   │     │
│  │ (The Hybrid Linker)  │◄──(9)────┤    (Auth, Response Body)     │   │     │
│  └──────────────────────┘          └──────────────┬───────────────┘   │     │
│                                                   │                   │     │
└───────────────────────────────────────────────────┼───────────────────┼─────┘
                                                    │                   │
                                                    │ (10) HTTPS Call   │ (D) IP Poll
                                                    ▼                   │
┌───────────────────────────┐            ┌──────────────────────────┐   │
│    Tado Internet Bridge   │◄──(11)─────┤      Tado Cloud API      │   │
│ (HomeKit Target Injection)│  Wireless  │    (Restrictive Env)     │   │
└─────────────┬─────────────┘            └──────────────────────────┘   │
              │                                                         │
              │ (C) HomeKit IP Update (Local Feedback Loop)             │
              └─────────────────────────────────────────────────────────┘
```

### The Execution Pipeline Explained

1.  **Command Entry (1 & A):** Commands enter via Hijack services or are intercepted from HomeKit interactions by the `TadoEventHandler`.
2.  **Instant Feedback (3 & 4):** The `APIManager` immediately triggers the `OptimisticManager` to patch the UI. Listeners are updated instantly—no "loading" spinner.
3.  **The Debounce Window:** Commands for the same zone are held for `debounce_time` (Default 5s) to allow for **Deep Command Fusion** (Batching).
4.  **The Worker Loop (6):** A background `while True` loop waits for the `API_QUEUE`. Once data arrives, it gathers all pending commands into a single **Batch**.
5.  **Quota Guard (7):** Before execution, the `RateLimitManager` verifies the daily budget and calculates the optimal adaptive interval.
6.  **Cloud Sync (10):** The `TadoRequestHandler` executes the batched HTTPS call, capturing detailed error bodies if the API rejects the request.
7.  **The HomeKit Loop (C & D):** The Bridge receives the command and updates its internal state. Home Assistant's native HomeKit integration then polls the Bridge via **Local IP**, completing the feedback loop and reflecting the final state in the climate entity (D & E).

The integration is built on a modular, helper-centric architecture that separates logic into specialized managers.

### 🧩 Specialized Managers

| Component | Responsibility |
| :--- | :--- |
| **`DataManager`** | High-precision JIT poll planning. Decides *exactly* when to fetch data based on usage and expiration. |
| **`APIManager`** | Central queue for all API writes. Handles batching, sequencing, and jitter. |
| **`RateLimitManager`** | Real-time quota tracking. Manages the "API Gold" budget and adaptive intervals. |
| **`OptimisticManager`** | UI instant-feedback engine. Patches local state immediately after a command without waiting for a poll. |
| **`EntityResolver`** | The "Missing Link" engine. Automatically maps HomeKit climate entities to Tado logical zones. |

---

## 🧠 Strategic Concepts

### 1. Extreme Batching (Command Fusion)
Instead of sending 10 requests for 10 rooms, Tado Hijack buffers commands during a configurable **Debounce Window**.
- **The Result:** 10 zone changes = **1 API Call**.
- **Scope:** Applies to `set_mode`, `set_water_heater_mode`, and all bulk buttons.

### 2. JIT (Just-In-Time) Polling
We don't poll on a fixed timer if it's not needed.
- **Dynamic Intervals:** Polling speed adapts to your daily quota and current activity.
- **Event-Driven:** Hardware metadata (Firmware, Battery) is only fetched every 24h or on demand.
- **Dirty Flags:** Cache segments (Offsets, Away Config) are only refreshed if they are marked "dirty" and a user requests them.

### 3. The "API Gold" Budget (Auto Quota)

The integration uses a **Weighted Predictive Model** to distribute calls intelligently across the day.

#### Quota Distribution Schematic

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TADO DAILY API LIMIT (100%)                        │
│             (e.g., 5000 calls/day or the new 100 calls/day limit)           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ (1) DEDUCT FIXED RESERVES                                                   │
│ ┌───────────────────────────┐   ┌───────────────────────────┐               │
│ │   Background Syncs (24h)  │   │   External User Excess    │               │
│ │ (Hardware, Metadata, Bat) │ + │(Official App, Automations)│               │
│ └───────────────────────────┘   └───────────────────────────┘               │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ (2) CALCULATE FREE BUDGET                                                   │
│ FREE_BUDGET = (Limit - Reserves) * auto_api_quota_percent (e.g. 80%)        │
└──────┬───────────────────────────────────────────────────────────────┬──────┘
       │                                                               │
       ▼ (Day Phase: PERFORMANCE)                                      ▼ (Night: ECONOMY)
┌──────────────────────────────────────┐               ┌──────────────────────┐
│  High-Speed Polling Window           │               │  Sleep Polling Window│
│  (e.g., 07:01 - 21:59)               │               │  (e.g., 22:00-07:00) │
│                                      │               │                      │
│  ┌────────────────────────┐          │               │  ┌────────────────┐  │
│  │ REINVESTED SAVINGS     │◄─────────┼──(Reinvest)───┤  │ SAVINGS BANK   │  │
│  │ (From Economy Window)  │          │               │  │ (0 or Low Poll)│  │
│  └──────────┬─────────────┘          │               │  └────────────────┘  │
│             │                        │               │                      │
│             ▼                        │               ▼                      │
│  FINAL ADAPTIVE INTERVAL             │        REDUCED POLLING INTERVAL      │
│  (Target: ~45s - 300s)               │        (Target: ~1h or Paused)       │
└──────────────────────────────────────┘               └──────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ (3) TIME SYNC (Berlin 12:00 PM - 01:00 PM Window)                           │
│ Quota resets dynamically within this window. The system monitors the        │
│ remaining percentage and detects the jump (Reset Recovery). The model       │
│ continuously recalculates based on the newly detected baseline.             │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Economy Window:** Automatically slows down polling during your sleep window (e.g., 22:00 - 07:00).
- **Performance Reinvestment:** Saved calls from the night are reinvested into faster updates during the day.
- **Dynamic Reset Detection:** Instead of a fixed timer, the system uses a **Reset Safe Window (12:00 PM - 01:00 PM Berlin)**. If a significant jump in the remaining quota percentage is detected, the internal baseline is reset immediately.

### 4. Safety Floors & Adaptive Behavior

To protect your Tado account from automated detection and "Account Locks", the integration enforces hard-coded minimum intervals:

- **🛡️ Standard Cloud:** Minimum **45 seconds** per update.
- **🛡️ API Proxy:** Minimum **120 seconds** per update (Conservative floor required for stable proxy operation).
- **🛡️ Safety Throttle:** If the Tado API reports an invalid limit (e.g., `<= 0` during outages), the integration automatically enforces a **5-minute (300s)** safety interval to prevent rapid retry loops.
- **🛡️ Persistent Reconnect:** When the API quota is exhausted (throttled), the system performs a recovery check every **15 minutes** (THROTTLE_RECOVERY_INTERVAL_S) to ensure immediate service resumption once the quota is available.

*Note: These limits apply even if your daily budget allows for higher frequencies. Continuity and account safety always take precedence over speed.*

### 5. HomeKit Injection
This is our unique hybrid approach.
- **HomeKit:** Handles the core climate entity (Local, reliable, zero cost).
- **Hijack:** Injects missing cloud features (Schedules, Child Lock, Hot Water, AC Modes) into the *same* device.
- **Result:** You get a single, unified device in Home Assistant that is both local-first and feature-complete.

---

## 🚿 Service Logic & Validation

All control paths are protected by a **Fail-Fast Validation Layer**.

### Service: `set_mode` / `set_water_heater_mode`
- **`hvac_mode / operation_mode`:**
  - `auto`: Resumes the Tado Smart Schedule.
  - `heat`: Activates a manual overlay.
  - `off`: Turns the zone off.
- **`overlay` types:**
  - `manual`: Indefinite override (stays until you change it).
  - `next_block`: Automatically returns to schedule at the next Tado time block.
  - `presence`: Stays active until your Home/Away presence changes.
- **`duration`:** Optional timer in minutes for `manual` overlays.

### Automatic Post-Action Polling (`refresh_after`)
The integration intelligently decides if a confirmatory poll is necessary:
- **Instant:** For `auto` (Resume) or permanent changes.
- **Deferred:** For timed modes, the refresh is scheduled for the *end* of the timer to save quota.

---

## 🛡️ Security & Privacy

- **Redaction:** Diagnostics and logs undergo multi-layer Regex masking (Serials, Emails, Tokens).
- **Race-Condition Protection:** API writes are strictly queued and executed sequentially.
- **Local Resilience:** Core heating control remains functional via HomeKit even if Tado servers are down.

---

## 🛡️ State Integrity & Concurrency Management

Tado Hijack implements multiple layers of protection to ensure state consistency and prevent race conditions in a highly concurrent environment where users, automations, and the API all interact simultaneously.

### 1. State Memory Mixin (RestoreEntity Persistence)

**Purpose:** Preserve entity state across Home Assistant restarts.

Entities that inherit from `StateMemoryMixin` automatically save their state to Home Assistant's restoration storage. This ensures that user settings (like AC fan speed, swing positions, or target temperatures) survive system reboots.

#### How It Works

```python
from .helpers.state_memory import StateMemoryMixin

class TadoACSwingSelect(StateMemoryMixin, SelectEntity):
    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if restored := await self.async_get_last_state():
            self._attr_current_option = restored.state
```

**Lifecycle:**
1. **Startup:** Entity checks `async_get_last_state()` for previous value
2. **Runtime:** Entity updates `self._attr_current_option` normally
3. **Shutdown/Restart:** Home Assistant automatically saves the latest state
4. **Restoration:** On next startup, state is restored from storage

**Benefits:**
- User doesn't lose AC settings after HA restart
- Prevents "reset to default" behavior that frustrates users
- Works seamlessly with optimistic updates

**Covered Entities:**
- `select.fan_speed` (AC)
- `select.swing` (AC)
- `number.target_temperature` (AC/HW)
- `switch.schedule` (All zones)

### 2. Field Locking (Pending State Protection)

**Purpose:** Prevent concurrent API calls from overwriting each other's settings.

When multiple settings are changed rapidly (e.g., fan speed then swing), each change triggers an API call. Without protection, the second call might reset the first setting to its old value because it's building a payload from stale local state.

#### The Problem

```text
Timeline without Field Locking:
T0: User sets fan_speed = HIGH
    → API call 1 builds payload: {fan_speed: HIGH, swing: OFF}

T1: User sets swing = ON (before API call 1 completes)
    → API call 2 reads stale state, builds: {fan_speed: AUTO, swing: ON}

Result: Fan speed reverts to AUTO! ❌
```

#### The Solution

The `OptimisticManager` maintains a **pending state cache** that tracks in-flight changes:

```python
self.optimistic.apply_zone_state(
    zone_id,
    overlay=True,
    ac_mode=current_mode,
    vertical_swing=new_swing,  # Lock this field
)
```

When building the next API payload, the system **reads from optimistic state first**:

```python
# In coordinator.py:968 (async_set_ac_setting)
opt_mode = self.optimistic.get_zone_ac_mode(zone_id)
current_mode = opt_mode or state.setting.mode  # Use locked value if available
```

**Result:** All settings are preserved across rapid concurrent changes.

#### State Clearing Strategy

The `OptimisticManager` uses **context-aware state clearing**:

- **Resume Schedule (`overlay=False`):** **CLEAR ALL** optimistic state
  - Reason: Schedule is cloud-determined; stale settings must not leak into future overlays

- **Manual Overlay (`overlay=True`):** **KEEP EXISTING** optimistic state, only update specified fields
  - Reason: Allows gradual state building (set temp → change mode → adjust fan) without losing previous values

### 3. Pending Command Tracking

**Purpose:** Prevent duplicate API calls for the same logical operation.

When a user rapidly toggles a switch or drags a slider, Home Assistant fires multiple state change events. Without tracking, each event would queue a separate API call, wasting quota and potentially creating conflicts.

#### Debounce Window + Command Deduplication

The `APIManager` uses a **command identifier** system:

```python
self.api_manager.queue_command(
    f"zone_{zone_id}",  # Unique key per zone
    TadoCommand(...)
)
```

**How It Works:**
1. Commands with the **same key** replace each other during the debounce window
2. Only the **final command** is executed after the window expires
3. Multiple zones are **batched** into a single API call

**Example:**
```text
T0: User drags temp slider: 18°C → queue_command("zone_1", temp=18)
T1: Still dragging: 19°C → REPLACE previous command
T2: Still dragging: 20°C → REPLACE again
T3: User releases slider: 21°C → REPLACE final
T4: Debounce expires (5s) → Send ONLY the final command (21°C)

Result: 20 UI events → 1 API call ✅
```

### 4. Rollback Context (Error Recovery)

**Purpose:** Revert local state if API calls fail.

Every command carries a **rollback context** — a snapshot of the zone state before the change:

```python
old_state = patch_zone_overlay(self.data.zone_states.get(str(zone_id)), data)

self.api_manager.queue_command(
    f"zone_{zone_id}",
    TadoCommand(
        CommandType.SET_OVERLAY,
        zone_id=zone_id,
        data=data,
        rollback_context=old_state,  # Stored for recovery
    ),
)
```

**Failure Handling:**
1. Optimistic update shows change immediately in UI
2. API call fails (e.g., 422 validation error)
3. System restores `rollback_context` to zone state
4. UI reverts to previous value
5. User sees error notification

**Why This Matters:**
- Prevents "ghost states" where UI shows a setting that never actually applied
- Provides instant feedback on what went wrong
- Maintains trust in the UI accuracy

### 5. Thread-Safe API Queue

**Purpose:** Serialize API writes to prevent race conditions.

All write operations (overlays, resume, presence lock, etc.) pass through a **single FIFO queue** processed by one background worker loop.

#### Architecture

```text
┌─────────────────────────────────────────────────────────┐
│           Multiple Concurrent Entry Points              │
│  (Dashboard, Automations, Services, HomeKit Events)     │
└──────┬──────────────┬───────────────┬───────────────────┘
       │              │               │
       ▼              ▼               ▼
     Command       Command         Command
       │              │               │
       └──────────────┴───────────────┘
                      │
                      ▼
            ┌─────────────────────┐
            │   API_QUEUE (FIFO)  │  ← Thread-safe asyncio.Queue
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   Worker Loop       │  ← Single consumer
            │  (while True)       │
            └──────────┬──────────┘
                       │
                       ▼
              ┌────────────────┐
              │  Batch & Fuse  │
              └────────┬───────┘
                       │
                       ▼
              ┌────────────────┐
              │  Single API    │
              │  HTTPS Call    │
              └────────────────┘
```

**Guarantees:**
- Commands are executed in order of arrival
- No two API calls execute simultaneously
- Batching window collects multiple commands before execution
- Critical commands (like resume schedule) can bypass batching if needed

### 6. Conflict-Free Optimistic Updates

**Purpose:** Ensure UI updates don't create stale state.

The `OptimisticManager` uses a **two-phase update strategy**:

1. **Immediate Patch:** Update local `zone_states` dict with expected changes
2. **Listener Broadcast:** Notify all entities to re-read state from coordinator
3. **API Execution:** Queue command for cloud sync
4. **Eventual Consistency:** Next poll (or refresh_after) confirms cloud state

**Key Insight:** Optimistic state is **authoritative** until the next poll. This prevents UI flicker and provides instant feedback.

#### Optimistic State Precedence

When building API payloads, the system reads in this order:

1. **Optimistic cache** (pending changes)
2. **Cloud state** (last known API response)
3. **Default fallback** (type-specific defaults)

This ensures in-flight changes are never lost, even if a poll happens mid-command.

---

### Concurrency Flow Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                      User Changes AC Fan Speed                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  SelectEntity Called │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────────────┐
                    │ coordinator.async_set_ac_... │
                    └──────────┬───────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
   ┌────────────────┐  ┌──────────────┐  ┌──────────────────┐
   │ Read Optimistic│  │ Build Payload│  │ Validate Payload │
   │ State (Locked) │  │ (AC Settings)│  │ (Pre-API Check)  │
   └────────┬───────┘  └──────┬───────┘  └────────┬─────────┘
            │                 │                   │
            └─────────────────┼───────────────────┘
                              ▼
                   ┌─────────────────────────┐
                   │ Lock New Field in Cache │  ← Field Locking
                   │ (optimistic.apply_...)  │
                   └──────────┬──────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │ Update UI (Instant)     │
                   │ (async_update_listeners)│
                   └──────────┬──────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │ Queue Command           │  ← Deduplication
                   │ (api_manager.queue_...) │
                   └──────────┬──────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │ Debounce Window (5s)    │  ← Batching
                   └──────────┬──────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │ Execute API Call        │  ← Serialized
                   └──────────┬──────────────┘
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
         ┌──────────────┐          ┌──────────────┐
         │   Success    │          │   Failure    │
         └──────┬───────┘          └──────┬───────┘
                │                         │
                ▼                         ▼
    ┌─────────────────────┐   ┌────────────────────────┐
    │ State Confirmed     │   │ Rollback Context       │  ← Error Recovery
    │ (next poll)         │   │ (restore old state)    │
    └─────────────────────┘   └────────────────────────┘
```

---

## 🔓 Rate Limit Bypass (API Proxy)

For power users, Tado Hijack supports a local **API Proxy** to further decouple the integration from cloud-side constraints.

### Proxy Integration Schematic

```text
┌───────────────────────────┐          ┌───────────────────────────────────┐
│       Tado Hijack         │          │          Local API Proxy          │
│    (Home Assistant)       │          │     (e.g., Docker Container)      │
└─────────────┬─────────────┘          └──────────────────┬────────────────┘
              │                                           │
              │ (1) Request (No Auth)                     │ (2) Process Request
              ├──────────────────────────────────────────►│     (Auth & Cache)
              │                                           │
              │                                           ▼
              │                        ┌───────────────────────────────────┐
              │                        │          Tado Cloud API           │
              │                        │   (Quota: 3000/day per account)   │
              │                        └──────────────────┬────────────────┘
              │                                           │
              │ (4) Return Cached/Real                    │ (3) Response
              │◄──────────────────────────────────────────┤     (Status & Data)
              │                                           │
└─────────────┴─────────────┘          └──────────────────┴────────────────┘
```

### Quota Scalability Comparison

Tado is actively choking the official API to a near-useless level. Tado Hijack is engineered to survive this via Adaptive Polling, but the **Proxy Bypass** is the only way to regain full control by utilizing a specialized "Web-Base" access method.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                      QUOTA SCALABILITY COMPARISON                           │
└─────────────────────────────────────────────────────────────────────────────┘
         DIRECT CLOUD ACCESS                      LOCAL PROXY BYPASS
 ┌────────────────────────────────┐        ┌──────────────────────────────────┐
 │ Official Tado API (Legacy)     │        │ Multi-Account Proxy Cluster      │
 ├────────────────────────────────┤        ├──────────────────────────────────┤
 │ CURRENT LIMIT: ~5000 calls/day │        │ PROXY LIMIT: ~3000 calls / acc   │
 │ FUTURE LIMIT:  ~100 calls/day  │        │ (Scalable: N x 3000 / day)       │
 └──────────────┬─────────────────┘        └───────────────┬──────────────────┘
                │                                          │
                ▼                                          ▼
      [ ADAPTIVE SURVIVAL ]                       [ TOTAL FREEDOM ]
 High speed today (45s floor).             High-speed polling (120s floor).
 Adaptive slowdown once limited.           Full bandwidth (Jitter enabled).
```

### Strategic Benefits of the Proxy

1.  **Auth Outsourcing:** The proxy handles OAuth2 token management and refreshes internally using its own local secrets. Hijack simply sends requests to the local proxy URL.
2.  **Bypass the 100-Call Trap:** While the official Cloud API is moving towards a strict 100-call daily limit, the proxy utilizes a specialized access method (Chrome-based/Web-API) granting **3000 calls per account**.
3.  **Local Cache Layer:** Frequently requested data can be served directly from the proxy's local memory, saving precious API calls for critical commands.
4.  **Multi-Account Scaling:** Power users can orchestrate multiple accounts to pool their quota, effectively providing unlimited bandwidth for complex smart home setups.
5.  **Ban Protection & Obfuscation:** The proxy allows for advanced **Multi-Level Jitter**, breaking the temporal correlation between Home Assistant actions and Tado cloud logs.
6.  **Safety First Performance:** While Cloud mode allows 45s updates (technical floor), Proxy mode enforces a conservative **120s minimum interval** combined with jitter to keep your account safe from automated detection during high-frequency polling.

---

**Built for the community — because Tado clearly isn't.**
