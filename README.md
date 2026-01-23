<div align="center">

# Tado Hijack for Home Assistant 🏴‍☠️

<br>

[![Latest Release](https://img.shields.io/github/v/release/banter240/tado_hijack?style=for-the-badge&color=e10079&logo=github)](https://github.com/banter240/tado_hijack/releases/latest)
[![Dev Release](https://img.shields.io/github/v/release/banter240/tado_hijack?include_prereleases&label=dev&style=for-the-badge&color=orange&logo=github)](https://github.com/banter240/tado_hijack/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=home-assistant)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/banter240/tado_hijack?style=for-the-badge&color=blue)](LICENSE)

[![Discord](https://img.shields.io/discord/1331294120813035581?logo=discord&logoColor=white&style=for-the-badge&color=5865F2)](https://discord.gg/kxUsjHyxfT)
[![Discussions](https://img.shields.io/github/discussions/banter240/tado_hijack?style=for-the-badge&logo=github&color=7289DA)](https://github.com/banter240/tado_hijack/discussions)
[![Open Issues](https://img.shields.io/github/issues/banter240/tado_hijack?style=for-the-badge&color=red&logo=github)](https://github.com/banter240/tado_hijack/issues)
[![Stars](https://img.shields.io/github/stars/banter240/tado_hijack?style=for-the-badge&color=yellow&logo=github)](https://github.com/banter240/tado_hijack/stargazers)

<br>

**Built for the community — because Tado clearly isn't.**

</div>

<br>

---

Tado restricted their API? They think you shouldn't control your own heating? **Tado Hijack begs to differ.**

I engineered this integration with one goal: **To squeeze every drop of functionality out of Tado's cloud without triggering their rate limits.** We bridge the gap between Tado's restricted API and your smart home, unlocking features that Tado keeps hidden, all while treating every single API call like gold.

<br>

> [!WARNING]
> **Compatibility Note (Tado X / Matter):**
> This integration is currently optimized for **Tado V3+** (IB01) systems.
> **Tado X** devices use the new Matter architecture and a different API which is **not yet supported**. Support is planned for a future release; current focus is on perfecting the V3+ and HomeKit experience.

<br>

---

## 📖 Table of Contents

- [🏴‍☠️ Philosophy](#-the-hijack-philosophy)
  - [⚖️ The "Why" Factor](#️-the-why-factor)
- [🆚 Comparison](#-feature-comparison)
- [🚀 Key Highlights](#-key-highlights)
  - [🧠 Extreme Batching Technology](#-extreme-batching-technology)
  - [🤝 The HomeKit "Missing Link"](#-the-homekit-missing-link)
  - [🛠️ Unleashed Features](#-unleashed-features-non-homekit)
- [📊 API Consumption Strategy](#-api-consumption-strategy)
- [🛠️ Architecture](#️-architecture)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [📱 Entities & Controls](#-entities--controls)
- [⚡ Services](#-services)
- [🐛 Troubleshooting](#-troubleshooting)

<br>

---

<br>

## 🏴‍☠️ The Hijack Philosophy

<br>

Tado's restricted REST API often forces a trade-off between frequent updates and staying within daily rate limits. **Tado Hijack takes a different path.**

Instead of just "polling less," we use **Deep Command Merging** and **HomeKit Injection** to make every single API call count. We don't replace your local HomeKit setup; we "hijack" it, injecting missing cloud power-features directly into the existing devices.

*   **💎 Zero Waste:** 10 commands across 10 rooms? Still only **1 API call**.
*   **🔗 No Redundancy:** HomeKit handles local climate; we handle the cloud secrets.
*   **📡 Transparency:** Real-time quota tracking directly from Tado's response headers.

### ⚖️ The "Why" Factor

**Tado has gone full "Pay-to-Win".**

They've crippled the standard API to a pathetic **100 calls per day**, effectively taking your smart home hostage unless you pay for a subscription. We are currently in the transition phase where the original 5,000 calls are being steadily choked down to 100—a textbook example of **artificial scarcity**.

Tado Hijack is the definitive technical response to this hostility. I've engineered the **Auto API Quota** system specifically to handle this shrinking window, intelligently distributing your remaining "Gold" to ensure you never lose control.

*   **🛡️ Fighting Artificial Scarcity:** While Tado tries to force you into a subscription "toll booth," our **Deep Command Batching** and **Auto Quota** ensure you stay in total control, even as your limits vanish.
*   **⚡ Supercharged Resistance:** We stand on the shoulders of the Open Source community. Tado Hijack uses patched, high-efficiency libraries to maximize every single interaction.
*   **⚖️ Reclaim Your Hardware:** We refuse to play the subscription game. We squeeze maximum functionality out of the "Standard" tier, proving that superior engineering beats predatory throttling.
*   **📡 Quota Transparency:** Monitor your remaining "API Gold" in real-time. Know exactly when they try to silence your devices and stay one step ahead.

<br>

---

<br>

## 🆚 Feature Comparison

<br>

| Feature | Official Tado | HomeKit (Local) | **Tado Hijack** |
| :--- | :---: | :---: | :---: |
| **Temperature Control** | ✅ | ✅ | 🔗 (via HK Link) |
| **Boiler Load / Modulation**| ✅ | ❌ | ✅ **Yes** |
| **Hot Water Power & Temp** | ✅ | ❌ | ✅ **Full** |
| **Smart Schedules Switch** | ✅ | ❌ | ✅ **Yes** |
| **AC Pro (Fan/Swing)** | ✅ | ❌ | ✅ **Full** |
| **Child Lock / OWD / Early** | ✅ | ❌ | ✅ **Yes** |
| **Local Control** | ❌ | ✅ | ✅ (via HK Link) |
| **Dynamic Presence-Aware Overlay** | ❌ | ❌ | ✅ **Exclusive** |
| **Command Batching** | ❌ | N/A | ✅ **Extreme (1 Call)** |
| **HomeKit Injection** | ❌ | N/A | ✅ **One Device** |
| **API Quota Visibility** | ❌ | N/A | ✅ **Real-time** |
| **Privacy Redaction (Logs)** | ❌ | N/A | ✅ **Strict** |

<br>

---

<br>

## 🚀 Key Highlights

<br>

### 🧠 Extreme Batching Technology
While other integrations waste your precious API quota for every tiny interaction, Tado Hijack features **Deep Command Merging**. We collect multiple actions and fuse them into a single, highly efficient bulk request.

<br>

> [!TIP]
> **Maximum Fusion Scenario:**
> Triggering a "Party Scene": **AC Living Room** (Temp + Fan + Swing) + **AC Kitchen** (Temp + Fan) + **Hot Water** (ON).
>
> ❌ **Standard Integrations:** 6-8 API calls (Half your hourly quota gone).
> ✅ **Tado Hijack:** **1 single API call** for everything.
>
> *Note: This works within your configurable **Debounce Window**. Every action is automatically fused.*

<br>

> [!IMPORTANT]
> **Universal Batching:** This applies to manual dashboard interactions AND automated service calls (like `set_timer`). 10 timers at once? **Still only 1 API call.**

<br>

---

<br>

### 🤝 The HomeKit "Missing Link"
**We don't replace HomeKit. We fix it.**
Almost no other integration does this: Tado Hijack automatically detects your existing HomeKit devices and **injects** the missing cloud-only power-features directly into them. You get the rock-solid local control of HomeKit combined with advanced cloud features in **one single unified device**.

<br>

> [!IMPORTANT]
> **Hybrid Architecture:**
> This integration is designed to work **alongside** the native HomeKit Device integration.
> *   **HomeKit:** Provides the `climate` entity (Local Temperature Control & Current Temp).
> *   **Tado Hijack:** Provides the "Missing Links" (Schedules, Hot Water, AC Modes, Hardware Settings).
>
> *Note: Without HomeKit, regular heating valves will NOT have a climate entity.*

<br>

> [!NOTE]
> **No Redundancy:** Tado Hijack does **not** provide temperature control for regular heating valves (TRVs), as HomeKit already handles this perfectly. We focus strictly on the features HomeKit cannot see: **Cloud-only controls** and logical Zone Schedules.

<br>

<br>

---

<br>

### 🛠️ Unleashed Features (Non-HomeKit)
We bring back the controls Tado "forgot" to give you:

*   **🚿 Hot Water Climate Control:** Native climate entity with AUTO/HEAT/OFF modes. AUTO mode resumes Smart Schedule, HEAT activates manual override.
*   **❄️ AC Pro Features:** Precise Fan Speed and Swing (Horizontal/Vertical) selection.
*   **🔥 Valve Opening Insight:** View the percentage of how far your valves are open (updated during state polls).
*   **🔋 Real Battery Status:** Don't guess; see the actual health of every valve.
*   **🌡️ Temperature Offset:** Interactive calibration for your thermostats.
*   **✨ Dazzle Mode:** Control the display behavior of your V3+ hardware.
*   **🏠 Presence Lock:** Force Home/Away modes regardless of what Tado thinks.
*   **🔥 Dynamic Presence-Aware Overlay:** Set temperatures specifically for the current presence state — an exclusive feature that automatically resets once your home presence changes (e.g. Home → Away), something Tado doesn't even support in their official app.
*   **🔓 Rate Limit Bypass:** Experimental support for local [tado-api-proxy](https://github.com/s1adem4n/tado-api-proxy) to bypass daily limits.

<br>

---

<br>

## 📊 API Consumption Strategy

<br>

Tado's API limits are restrictive. That's why Tado Hijack uses a **Zero-Waste Policy**:

### API Consumption Table

<br>

| Action | Cost | Frequency | Description | Detailed API Calls |
| :--- | :---: | :--- | :--- | :--- |
| **State Poll** | **2** | Configurable | State, HVAC, Valve %, Humidity. | `GET /homes/{id}/state`<br>`GET /homes/{id}/zoneStates` |
| **Battery Update** | **2** | 24h (Default) | Fetches device list & metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Refresh Zones** | **2** | On Demand | Updates zone/device metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Refresh Offsets** | **N** | On Demand | Fetches all device offsets. | `GET /devices/{s}/temperatureOffset` (×N) |
| **Refresh Away** | **M** | On Demand | Fetches all zone away temps. | `GET /zones/{z}/awayConfiguration` (×M) |
| **Zone Overlay** | **1** | On Demand | **Fused:** All zone changes in 1 call. | `POST /homes/{id}/overlay` |
| **Home/Away** | **1** | On Demand | Force presence lock. | `PUT /homes/{id}/presenceLock` |

<br>

> [!TIP]
> **Throttled Mode:** When API quota runs low, the integration can automatically disable periodic polling to preserve remaining quota for your automations.

<br>

> [!IMPORTANT]
> **Granular Refresh Strategy:** To keep your quota green, hardware configurations (Offsets, Away Temperatures) are **never** fetched automatically. They remain empty until you manually trigger a specific refresh button or set a value.

<br>

### 📈 Auto API Quota (The Brain)

<br>

Tado Hijack doesn't just guess. It uses a **Predictive Consumption Model** to distribute your API calls evenly throughout the day.

*   **⚡ Real-Time Cost Measurement:** The system measures the *actual* cost of every polling cycle and uses a smoothed moving average to predict future consumption.
*   **🕒 Dynamic Reset-Sync:** It calculates the exact seconds remaining until the next API reset (**12:01 CET**) and adjusts your polling interval on-the-fly.
*   **📉 Hybrid Budget Strategy:** The system uses **two strategies** and picks the more generous one:
    *   **Long-term:** Distribute your daily target evenly across the day
    *   **Short-term:** Always keep polling with X% of currently remaining quota
    *   This ensures the system **never stops polling** when quota runs low, while still respecting your daily budget when possible.

<br>

**How your "API Gold" is managed:**

The system calculates two independent budgets and always chooses the **most reliable** path (`MAX` function) to keep you connected:

```
FREE_QUOTA = Daily_Limit - Throttle_Reserve - (Predicted_Daily_Maintenance_Cost)
TARGET_BUDGET = FREE_QUOTA * Auto_API_Quota_%

REMAINING_BUDGET = MAX(
    TARGET_BUDGET - Used_Today,           # Strategy A (Long-term): Sustainable daily plan
    (Remaining - Throttle_Reserve) * %    # Strategy B (Short-term): Guaranteed 'Always-On' fallback
)
```

<br>

**Example Adaptive Behavior:**

Instead of a static timer, your polling interval breathes with your quota:

- **High-Speed Phase:** While your budget is healthy, updates arrive as fast as every **15s**.
- **Proactive Stretching:** If manual actions (or Tado's transition) tighten the budget, the **Long-term** strategy automatically stretches the interval to preserve your daily visibility.
- **"Always-On" Guarantee:** Even in extreme scarcity, the **Short-term** fallback ensures you never hit zero. It uses a smart percentage of your *actual* remaining calls to keep updates flowing until the next reset.

<br>

> [!NOTE]
> **Intelligence over Throttling:** While other integrations simply die when a limit is reached, Tado Hijack's math ensures a "soft landing". It prioritizes **continuity over frequency**, gracefully slowing down to ensure your smart home stays informed 24/7 without ever hitting the hard wall.

<br>

---

<br>

### 🧠 Batching Capability Matrix

Not all API calls are created equal. Tado Hijack optimizes everything, but physics (and the Tado API) sets limits.

<br>

| Action Type | Examples | Strategy | API Cost |
| :--- | :--- | :--- | :--- |
| **State Control** | Target Temp, Turn Off All, Resume Schedule, Hot Water Power, AC Fan | **FUSED** | **1 Call Total** (regardless of zone count) |
| **Global Mode** | Home/Away Presence | **DIRECT** | **1 Call** |
| **Zone Config** | Early Start, Open Window, Dazzle Mode | **DEBOUNCED** | **1 Call per Zone** (Sequentially executed) |
| **Device Config** | Child Lock, Temperature Offset | **DEBOUNCED** | **1 Call per Device** (Sequentially executed) |

<br>

> **Fused (True Batching):**
> Multiple actions across multiple zones are merged into a **single** API request.
> *Example: Turning off 10 rooms at once = **1 API Call**.*
>
> **Debounced (Rapid Update Protection):**
> Prevents spamming the API while dragging sliders. Only the final value is sent.
> *Example: Dragging a slider from 18°C to 22°C generates 20 intermediate events, but only **1 API Call** is sent.*

<br>

> [!NOTE]
> **Why not batch everything?**
> Tado does **not** provide bulk API endpoints for device configurations (Child Lock, Offset, Window Detection). We must send these commands individually per device. We optimize what we can, but we cannot invent endpoints that don't exist.

<br>

---

## 🛠️ Architecture

<br>

### Physical Device Mapping
Unlike other integrations that group everything by "Zone", Tado Hijack maps entities to their **physical devices** (Valves/Thermostats).
*   **Matched via Serial Number:** Automatic injection into existing HomeKit devices.
*   **No HomeKit?** We create dedicated devices containing **only** the cloud features (Battery, Offset, Child Lock, etc.), but **no** temperature control.

<br>

### Robustness & Security
*   **Custom Client Layer:** I extend the underlying library via inheritance to handle API communication reliably and fix common deserialization errors.
*   **Privacy by Design:** All logs are automatically redacted. Sensitive data (User Codes, Serial Numbers, Home IDs) is stripped before writing to disk.

<br>

---

## 📦 Installation

<br>

### Via HACS (Recommended)
1. Open **HACS** -> **Integrations** -> **Custom repositories**.
2. Add `https://github.com/banter240/tado_hijack` as **Integration**.
3. Search for **"Tado Hijack"** and download.
4. **Restart Home Assistant**.

<br>

---

## ⚙️ Configuration

<br>

| Option | Default | Description |
| :--- | :--- | :--- |
| **Status Polling** | `60m` | Interval for heating state and presence. (2 API calls) |
| **Auto API Quota** | `0%` (Off) | Target X% of FREE quota. Uses hybrid strategy: daily budget OR X% of remaining (whichever is higher). |
| **Battery Update** | `24h` | Interval for battery and device metadata. (2 API calls) |
| **Offset Update** | `0` (Off) | Interval for temperature offsets. (1 API call per valve) |
| **Debounce Time** | `5s` | **Batching Window:** Fuses actions into single calls. |
| **Throttle Threshold** | `0` | Reserve last N calls - skip polling when remaining < threshold. |
| **Disable Polling When Throttled** | `Off` | Stop periodic polling entirely when throttled. |
| **API Proxy URL** | `None` | **Advanced:** URL of local `tado-api-proxy` workaround. |
| **Debug Logging** | `Off` | Enable verbose logging for troubleshooting. |

<br>

---

## 📱 Entities & Controls

<br>

### 🏠 Home Device (Internet Bridge)
Global controls for the entire home. *Linked to your Internet Bridge device.*

<br>

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.tado_{home}_away_mode` | Switch | Toggle Home/Away presence lock. |
| `button.tado_{home}_turn_off_all_zones` | Button | **Bulk:** Turns off heating in ALL zones. |
| `button.tado_{home}_boost_all_zones` | Button | **Bulk:** Boosts all zones to 25°C. |
| `button.tado_{home}_resume_all_schedules` | Button | **Bulk:** Returns all zones to Smart Schedule. |
| `button.tado_{home}_refresh_metadata` | Button | Updates zone and device metadata (2 calls). |
| `button.tado_{home}_refresh_offsets` | Button | Fetches all hardware offsets (N calls). |
| `button.tado_{home}_refresh_away` | Button | Fetches all zone away temps (M calls). |
| `button.tado_{home}_full_manual_poll` | Button | **Expensive:** Refreshes everything at once. |
| `sensor.tado_{home}_api_limit` | Sensor | Daily API call limit. |
| `sensor.tado_{home}_api_remaining` | Sensor | Your precious daily API gold. |
| `sensor.tado_{home}_api_status` | Sensor | API status (`connected`, `throttled`, `rate_limited`). |
| `binary_sensor.tado_ib_{home}_cloud_connection` | Binary Sensor | Bridge connectivity to Tado cloud. |

<br>

### 🌡️ Zone Devices (Rooms / Hot Water / AC)
Cloud-only features that HomeKit does not support.

<br>

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.schedule` | Switch | **ON** = Smart Schedule, **OFF** = Manual. Simple way to resume schedule. |
| `climate.hot_water` | Climate | **Hot Water:** Control modes: AUTO (schedule), HEAT (manual), OFF. Temperature control 30-80°C. |
| `switch.hot_water` | Switch | **Legacy:** Direct boiler power control (replaced by climate entity). |
| `switch.early_start` | Switch | **Cloud Only:** Toggle pre-heating before schedule. |
| `switch.open_window` | Switch | **Cloud Only:** Toggle window detection. |
| `number.target_temperature` | Number | **Cloud Only:** Set target temp for AC/HW. |
| `number.away_temperature` | Number | **Cloud Only:** Set away mode temperature. |
| `select.fan_speed` | Select | **AC Only:** Full fan speed control. |
| `select.swing` | Select | **AC Only:** Full swing control. |
| `sensor.heating_power` | Sensor | **Insight:** Valve opening % or Boiler Load %. |
| `sensor.humidity` | Sensor | Zone humidity (faster than HomeKit). |
| `button.resume_schedule` | Button | Force resume schedule (stateless). |

<br>

### 🔧 Physical Devices (Valves/Thermostats)
Hardware-specific entities. *These entities are **injected** into your existing HomeKit devices.*

<br>

| Entity | Type | Description |
| :--- | :--- | :--- |
| `binary_sensor.battery` | Binary Sensor | Battery health (Normal/Low). |
| `binary_sensor.connection` | Binary Sensor | Device connectivity to Tado cloud. |
| `switch.child_lock` | Switch | Toggle Child Lock on the device. |
| `switch.dazzle_mode` | Switch | Control display behavior (V3+). |
| `number.temperature_offset` | Number | Interactive temperature calibration (-10 to +10°C). |

<br>

---

## ⚡ Services

<br>

For advanced automation, use these services:

| Service | Description | API Impact |
| :--- | :--- | :--- |
| `tado_hijack.turn_off_all_zones` | Turn off all zones instantly. | **1 call** (bulk) |
| `tado_hijack.boost_all_zones` | Boost every zone to 25°C. | **1 call** (bulk) |
| `tado_hijack.resume_all_schedules` | Restore Smart Schedule across all zones. | **1 call** (bulk) |
| `tado_hijack.set_timer` | Set power, temperature, and termination mode. Supports `duration`, `time_period` (HH:MM:SS), or `overlay`: `auto` (next block) / `presence` (until presence change). | **1 per zone** |
| `tado_hijack.manual_poll` | Force immediate data refresh. Use `refresh_type` to control scope. | **2-N** (depends on type) |

<br>

> [!TIP]
> **Targeting Rooms:** You can use **any** entity that belongs to a room as the `entity_id`. This includes Tado Hijack switches or even your existing **HomeKit climate** entities (e.g. `climate.living_room`). The service will automatically resolve the correct Tado zone.

<br>

#### 📝 `set_timer` Examples (YAML)

<br>

**Hot Water Boost (30 Min):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: switch.hot_water
  duration: 30  # Minutes
```

**Quick Bathroom Heat (15 Min at 24°C):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: climate.bathroom
  duration: 15
  temperature: 24
```

**AC Sleep Timer (HH:MM:SS Format):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: select.bedroom_fan_speed
  time_period: "01:30:00"  # 1 hour 30 minutes
  temperature: 21
```

<br>

**Until Presence Changes (Indefinite until Home/Away change):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: climate.living_room
  overlay: "presence"  # Indefinite until manual change or presence change
  temperature: 22
```

<br>

**Auto-Return to Schedule (Next Time Block):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: climate.living_room
  overlay: "auto"  # Returns to schedule at next time block
  temperature: 22
```

<br>

---

## 📋 Known Constraints

<br>

**What Tado's API doesn't allow us to optimize:**

Some operations are inherently expensive because Tado's backend doesn't offer batching for them:

- **Per-Device Settings:** Temperature Offsets, Child Lock, and Window Detection must be configured individually (1 API call per device). If you have 10 thermostats, that's 10 calls. We can't batch what Tado doesn't support.
- **Offset Polling:** If you enable automatic offset polling, it costs **1 call per device with temperature capability**. For large homes, disable auto-polling and use manual refresh buttons when needed.

<br>

**Hybrid Cloud Dependency:**

While Tado Hijack uses the cloud for its power-features, your basic smart home remains resilient:
- **Local Resilience:** Temperature control and heating state via **HomeKit** remain fully functional even during internet outages or Tado server issues.
- **Cloud-Only Features:** Access to Smart Schedules, Hot Water control, and AC-Pro features requires a connection to Tado's servers.
- **Why Cloud?** Tado does not expose a local API for advanced logic. Tado Hijack bridges this gap while keeping your local core intact.

<br>

---

## 🐛 Troubleshooting

<br>

Enable debug logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.tado_hijack: debug
```

<br>

---

**Disclaimer:** This is an unofficial integration. Built by the community, for the community. Not affiliated with Tado GmbH. Use at your own risk.
