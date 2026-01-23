# Tado Hijack for Home Assistant 🏴‍☠️

[![semantic-release: conventional commits](https://img.shields.io/badge/semantic--release-conventionalcommits-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/banter240/tado_hijack)](https://github.com/banter240/tado_hijack/releases/latest)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/github/downloads/banter240/tado_hijack/total)
![GitHub](https://img.shields.io/github/license/banter240/tado_hijack)

**Built for the community — because Tado clearly isn't.**

Tado restricted their API? They think you shouldn't control your own heating? **Tado Hijack begs to differ.**

I engineered this integration with one goal: **To squeeze every drop of functionality out of Tado's cloud without triggering their rate limits.** We bridge the gap between Tado's restricted API and your smart home, unlocking features that Tado keeps hidden, all while treating every single API call like gold.

> [!WARNING]
> **Compatibility Note (Tado X / Matter):**
> This integration is currently optimized for **Tado V3+** (IB01) systems.
> **Tado X** devices use the new Matter architecture and a different API which is **not yet supported**. Support is planned for a future release; current focus is on perfecting the V3+ and HomeKit experience.

---

## 📖 Table of Contents
- [🚀 Key Highlights](#-key-highlights)
- [📊 API Consumption Strategy](#-api-consumption-strategy)
  - [API Consumption Table](#api-consumption-table)
  - [📈 Auto API Quota](#-auto-api-quota)
  - [🧠 Batching Capability Matrix](#-batching-capability-matrix)
- [🛠️ Architecture](#️-architecture)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [📱 Entities & Controls](#-entities--controls)
- [⚡ Services](#-services)
- [🐛 Troubleshooting](#-troubleshooting)

---

## 🚀 Key Highlights

### 🧠 Extreme Batching Technology
While other integrations waste your precious API quota for every tiny click, Tado Hijack features **Deep Command Merging**. I collect your interactions and fuse them into the most efficient bulk requests possible.

> [!TIP]
> **Extreme Scenario (Maximum Fusion):**
> You trigger a "Party Scene": **AC Living Room** (Temp + Fan + Swing) + **AC Kitchen** (Temp + Fan) + **Hot Water** (ON).
> *   **Standard Integrations:** 6-8 API calls (Half your hourly quota gone).
> *   **Tado Hijack:** **1 single API call** for everything.
>
> *Note: This works within your configurable **Debounce Window**. Every action is automatically fused.*

> [!IMPORTANT]
> **Everything is Batched:** This technology applies to both manual dashboard interactions AND service calls (like `set_timer`). If your automation triggers 10 timers at once, Tado Hijack will still only send **one single API call**.

### 🤝 The HomeKit "Missing Link"
**We don't replace HomeKit. We fix it.**
Almost no other integration does this: Tado Hijack automatically detects your existing HomeKit devices and **injects** the missing cloud-only power-features directly into them.
You get the rock-solid local control of HomeKit combined with advanced cloud features in **one single unified device**.

> [!IMPORTANT]
> **Requirement:**
> This integration is designed to work **alongside** the native HomeKit Device integration.
> *   **HomeKit** provides the `climate` entity (Local Temperature Control & Current Temp).
> *   **Tado Hijack** provides the rest (Schedules, Hot Water, AC Modes, Hardware Settings).
>
> **Without HomeKit, you will NOT have a climate entity to control heating temperatures.**

> [!NOTE]
> **No Redundancy:** Tado Hijack does **not** provide temperature control for regular heating valves (TRVs), as HomeKit already handles this perfectly. We focus on the "Missing Links": **Cloud-only features** (Hot Water, AC controls, and logical Zone Schedules) that HomeKit cannot see.

### 🛠️ Unleashed Features (Non-HomeKit)
I bring back the controls that Tado "forgot" to give you:
*   **🚿 Hot Water & AC Unleashed:** Full temperature and power control for boilers and AC units.
*   **❄️ AC Pro Features:** Precise Fan Speed and Swing (Horizontal/Vertical) selection.
*   **🔥 Valve Opening Insight:** View the percentage of how far your valves are open (updated during state polls).
*   **🔋 Real Battery Status:** Don't guess; see the actual health of every valve.
*   **🌡️ Temperature Offset:** Interactive calibration for your thermostats.
*   **✨ Dazzle Mode:** Control the display behavior of your V3+ hardware.
*   **🏠 Presence Lock:** Force Home/Away modes regardless of what Tado thinks.
*   **🔓 Rate Limit Bypass:** Experimental support for local [tado-api-proxy](https://github.com/s1adem4n/tado-api-proxy) to bypass daily limits.

---

## 📊 API Consumption Strategy

Tado's API limits are restrictive. That's why Tado Hijack uses a **Zero-Waste Policy**:

### API Consumption Table

| Action | Cost | Frequency | Description | Detailed API Calls |
| :--- | :---: | :--- | :--- | :--- |
| **State Poll** | **2** | Configurable | State, HVAC, Valve %, Humidity. | `GET /homes/{id}/state`<br>`GET /homes/{id}/zoneStates` |
| **Battery Update** | **2** | 24h (Default) | Fetches device list & metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Refresh Zones** | **2** | On Demand | Updates zone/device metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Refresh Offsets** | **N** | On Demand | Fetches all device offsets. | `GET /devices/{s}/temperatureOffset` (×N) |
| **Refresh Away** | **M** | On Demand | Fetches all zone away temps. | `GET /zones/{z}/awayConfiguration` (×M) |
| **Zone Overlay** | **1** | On Demand | **Fused:** All zone changes in 1 call. | `POST /homes/{id}/overlay` |
| **Home/Away** | **1** | On Demand | Force presence lock. | `PUT /homes/{id}/presenceLock` |

> [!TIP]
> **Throttled Mode:** When API quota runs low, the integration can automatically disable periodic polling to preserve remaining quota for your automations.

> [!IMPORTANT]
> **Granular Refresh Strategy:** To keep your quota green, hardware configurations (Offsets, Away Temperatures) are **never** fetched automatically. They remain empty until you manually trigger a specific refresh button or set a value.

<br>

### 📈 Auto API Quota

Automatically distributes your API calls evenly throughout the day. Set a percentage of your **FREE** daily quota for status polling.

**How FREE quota is calculated:**

```
FREE = Daily Limit - Throttle Reserve - Battery Updates/Day - Offset Updates/Day
```

**Example Calculation:**

| Setting | Value | Daily Cost |
| :--- | :--- | :--- |
| Daily API Limit | 5000 | - |
| Throttle Reserve | 30 | -30 |
| Battery Update (24h interval) | 2 calls × 1/day | -2 |
| Offset Update (24h interval, 5 valves) | 5 calls × 1/day | -5 |
| **FREE Quota** | **4963** | |
| Auto Quota Setting | 50% | |
| **Status Polls Budget** | **2481** | |
| **Calculated Interval** | ~35 seconds | |

> [!NOTE]
> The interval auto-adjusts dynamically based on remaining quota and time until reset (12:00 CET). If you consume more than expected, intervals slow down. If you use less, they speed up.

<br>

### 🧠 Batching Capability Matrix

Not all API calls are created equal. Tado Hijack optimizes everything, but physics (and the Tado API) sets limits.

| Action Type | Examples | Strategy | API Cost |
| :--- | :--- | :--- | :--- |
| **State Control** | Target Temp, Turn Off All, Resume Schedule, Hot Water Power, AC Fan | **FUSED** | **1 Call Total** (regardless of zone count) |
| **Global Mode** | Home/Away Presence | **DIRECT** | **1 Call** |
| **Zone Config** | Early Start, Open Window, Dazzle Mode | **DEBOUNCED** | **1 Call per Zone** (Sequentially executed) |
| **Device Config** | Child Lock, Temperature Offset | **DEBOUNCED** | **1 Call per Device** (Sequentially executed) |

> **Fused (True Batching):**
> Multiple actions across multiple zones are merged into a **single** API request.
> *Example:* Turning off 10 rooms at once = **1 API Call**.
>
> **Debounced (Rapid Update Protection):**
> Prevents spamming the API while dragging sliders. Only the final value is sent.
> *Example:* Dragging a slider from 18°C to 22°C generates 20 intermediate events, but only **1 API Call** is sent.

> [!NOTE]
> **Why not batch everything?**
> Tado does **not** provide bulk API endpoints for device configurations (Child Lock, Offset, Window Detection). We must send these commands individually per device. We optimize what we can, but we cannot invent endpoints that don't exist.

---

## 🛠️ Architecture

### Physical Device Mapping
Unlike other integrations that group everything by "Zone", Tado Hijack maps entities to their **physical devices** (Valves/Thermostats).
*   **Matched via Serial Number:** Automatic injection into existing HomeKit devices.
*   **No HomeKit?** We create dedicated devices containing **only** the cloud features (Battery, Offset, Child Lock, etc.), but **no** temperature control.

### Robustness & Security
*   **Custom Client Layer:** I extend the underlying library via inheritance to handle API communication reliably and fix common deserialization errors.
*   **Privacy by Design:** All logs are automatically redacted. Sensitive data (User Codes, Serial Numbers, Home IDs) is stripped before writing to disk.

---

## 📦 Installation

### Via HACS (Recommended)

1. Open **HACS** -> **Integrations** -> **Custom repositories**.
2. Add `https://github.com/banter240/tado_hijack` as **Integration**.
3. Search for **"Tado Hijack"** and download.
4. **Restart Home Assistant**.

---

## ⚙️ Configuration

| Option | Default | Description |
| :--- | :--- | :--- |
| **Status Polling** | `60m` | Interval for heating state and presence. (2 API calls) |
| **Auto API Quota** | `0%` (Off) | Use X% of FREE quota for status polls. See [📈 Auto API Quota](#-auto-api-quota). |
| **Battery Update** | `24h` | Interval for battery and device metadata. (2 API calls) |
| **Offset Update** | `0` (Off) | Interval for temperature offsets. (1 API call per valve) |
| **Debounce Time** | `5s` | **Batching Window:** Fuses actions into single calls. |
| **Throttle Threshold** | `0` | Reserve last N calls - skip polling when remaining < threshold. |
| **Disable Polling When Throttled** | `Off` | Stop periodic polling entirely when throttled. |
| **API Proxy URL** | `None` | **Advanced:** URL of local `tado-api-proxy` workaround. |
| **Debug Logging** | `Off` | Enable verbose logging for troubleshooting. |

---

## 📱 Entities & Controls

### 🏠 Home Device (Internet Bridge)
Global controls for the entire home. *Linked to your Internet Bridge device.* Entity IDs use `{home}` as placeholder for your home name.

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

### 🌡️ Zone Devices (Rooms / Hot Water / AC)
Cloud-only features that HomeKit does not support.

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.schedule` | Switch | **ON** = Smart Schedule, **OFF** = Manual. |
| `switch.hot_water` | Switch | **Cloud Only:** Direct boiler power control. |
| `switch.early_start` | Switch | **Cloud Only:** Toggle pre-heating before schedule. |
| `switch.open_window` | Switch | **Cloud Only:** Toggle window detection. |
| `number.target_temperature` | Number | **Cloud Only:** Set target temp for AC/HW. |
| `number.away_temperature` | Number | **Cloud Only:** Set away mode temperature. |
| `select.fan_speed` | Select | **AC Only:** Full fan speed control. |
| `select.swing` | Select | **AC Only:** Full swing control. |
| `sensor.heating_power` | Sensor | **Insight:** Valve opening percentage. |
| `sensor.humidity` | Sensor | Zone humidity (faster than HomeKit's slow local polling). |
| `button.resume_schedule` | Button | Force resume schedule (stateless). |

### 🔧 Physical Devices (Valves/Thermostats)
Hardware-specific entities. *These entities are **injected** into your existing HomeKit devices.*

| Entity | Type | Description |
| :--- | :--- | :--- |
| `binary_sensor.battery` | Binary Sensor | Battery health (Normal/Low). |
| `binary_sensor.connection` | Binary Sensor | Device connectivity to Tado cloud. |
| `switch.child_lock` | Switch | Toggle Child Lock on the device. |
| `switch.dazzle_mode` | Switch | Control display behavior (V3+). |
| `number.temperature_offset` | Number | Interactive temperature calibration (-10 to +10°C). |

---

## ⚡ Services

For advanced automation, use these services:

| Service | Description |
| :--- | :--- |
| `tado_hijack.turn_off_all_zones` | Turn off heating in all zones. |
| `tado_hijack.boost_all_zones` | Boost all zones to 25°C. |
| `tado_hijack.resume_all_schedules` | Resume Smart Schedule in all zones. |
| `tado_hijack.manual_poll` | Force refresh. Supports `refresh_type`: `metadata`, `offsets`, `away`, `all`. |
| `tado_hijack.set_timer` | Set Power, Temp, and Timer Duration in one efficient call. |

> [!TIP]
> **Targeting Rooms:** You can use **any** entity that belongs to a room as the `entity_id`. This includes Tado Hijack switches or even your existing **HomeKit climate** entities (e.g. `climate.living_room`). The service will automatically resolve the correct Tado zone.

#### 📝 `set_timer` Examples (YAML)

**Hot Water Boost (30 Min):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: switch.hot_water  # Targets the Hot Water zone
  duration: 30
```

**Quick Bathroom Heat (15 Min at 24°C):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: climate.bathroom  # Targets the Heating zone via HomeKit entity
  duration: 15
  temperature: 24
```

**AC Sleep Timer (1 Hour at 21°C):**
```yaml
service: tado_hijack.set_timer
data:
  entity_id: select.bedroom_fan_speed  # Targets the AC zone via any AC entity
  duration: 60
  temperature: 21
```

---

## 🐛 Troubleshooting

Enable debug logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.tado_hijack: debug
```

---

**Disclaimer:** This is an unofficial integration. Built by the community, for the community. Not affiliated with Tado GmbH. Use at your own risk.
