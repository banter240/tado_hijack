# Tado Hijack for Home Assistant 🏴‍☠️

[![semantic-release: conventional commits](https://img.shields.io/badge/semantic--release-conventionalcommits-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/banter240/tado_hijack)](https://github.com/banter240/tado_hijack/releases/latest)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/github/downloads/banter240/tado_hijack/total)
![GitHub](https://img.shields.io/github/license/banter240/tado_hijack)

**Built for the community — because Tado clearly isn't.**

Tado restricted their API? They think you shouldn't control your own heating? **Tado Hijack begs to differ.**

I engineered this integration with one goal: **To squeeze every drop of functionality out of Tado's cloud without triggering their rate limits.**

---

## 📖 Table of Contents
- [🚀 Key Highlights](#-key-highlights)
- [📊 API Consumption Strategy](#-api-consumption-strategy)
- [🛠️ Architecture](#️-architecture)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [📱 Entities & Controls](#-entities--controls)
- [⚡ Services](#-services)
- [🐛 Troubleshooting](#-troubleshooting)

---

## 🚀 Key Highlights

### 🧠 Extreme Batching Technology
While other integrations waste your precious API quota for every tiny click, Tado Hijack features **Deep Command Merging**. We collect your interactions and fuse them into the most efficient bulk requests possible.

> [!TIP]
> **Extreme Scenario (Maximum Fusion):**
> You trigger a "Party Scene": **AC Living Room** (Temp + Fan + Swing) + **AC Kitchen** (Temp + Fan) + **Hot Water** (ON).
> *   **Standard Integrations:** 6-8 API calls (Half your hourly quota gone).
> *   **Tado Hijack:** **1 single API call** for everything.
>
> *Note: This works within your configurable **Debounce Window**. Every action is automatically fused.*

### 🤝 The HomeKit "Missing Link"
**We don't replace HomeKit. We fix it.**
Almost no other integration does this: Tado Hijack automatically detects your existing HomeKit devices and **injects** the missing cloud-only power-features directly into them.
You get the rock-solid local control of HomeKit combined with advanced cloud features in **one single unified device**.

> [!NOTE]
> **No Redundancy:** Tado Hijack does **not** provide temperature control for regular heating valves (TRVs), as HomeKit already handles this perfectly. We focus on the "Missing Links": **Cloud-only features** (Hot Water, AC controls, and logical Zone Schedules) that HomeKit cannot see.

### 🛠️ Unleashed Features (Non-HomeKit)
I bring back the controls that Tado and Apple "forgot" to give you:
*   **🚿 Hot Water Power:** Full On/Off control for your boiler.
*   **❄️ AC Pro Features:** Precise Fan Speed and Swing (Horizontal/Vertical) selection.
*   **🔋 Real Battery Status:** Don't guess; see the actual health of every valve.
*   **🌡️ Temperature Offset:** Interactive calibration for your thermostats.
*   **✨ Dazzle Mode:** Control the display behavior of your V3+ hardware.
*   **🏠 Presence Lock:** Force Home/Away modes regardless of what Tado thinks.
*   **🔓 Rate Limit Bypass:** Experimental support for local [tado-api-proxy](https://github.com/s1adem4n/tado-api-proxy) to bypass daily limits (Use at your own risk).

---

## 📊 API Consumption Strategy

Tado's **100-call daily limit** is pathetic. That's why Tado Hijack uses a **Zero-Waste Policy**:

### API Consumption Table

| Action | Cost | Frequency | Description | Detailed API Calls |
| :--- | :---: | :--- | :--- | :--- |
| **State Poll** | **2** | 60m (Default) | Fetches global state & zones. | `GET /homes/{id}/state`<br>`GET /homes/{id}/zoneStates` |
| **Refresh Zones** | **2** | On Demand | Updates Zid/Device metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Refresh Offsets** | **N** | On Demand | Fetches all device offsets. | `GET /devices/{s}/temperatureOffset` (xN) |
| **Refresh Away** | **M** | On Demand | Fetches all zone away temps. | `GET /zones/{z}/awayConfiguration` (xM) |
| **Battery Update** | **2** | 24h | Fetches device list & metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Settings Set** | **1** | On Demand | Every action uses exactly 1 call. | `PUT /zones/{z}/overlay` (Fused!) |
| **Home/Away** | **1** | On Demand | Force presence lock. | `PUT /homes/{id}/presenceLock` |

> [!IMPORTANT]
> **Granular Refresh Strategy:** To keep your quota green, hardware configurations (Offsets, Away Temperatures) are **never** fetched automatically. They remain empty until you manually trigger a specific refresh button or set a value.

> [!TIP]
> **Throttled Mode:** When API quota runs low, the integration can automatically disable periodic polling to preserve remaining quota for your automations.

---

## 🛠️ Architecture

### Physical Device Mapping
We map entities to **physical devices** (Valves/Thermostats), not just abstract "Zones".
*   **Matched via Serial Number:** Automatic injection into HomeKit devices.
*   **No HomeKit?** We create clean, dedicated devices for each valve.

### Robustness & Security
*   **Custom Client:** A hardened communication layer that handles Tado's API quirks.
*   **Privacy:** All logs are auto-redacted. Your IDs and Serials never leave your machine.

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
| **Fast Polling** | `60m` | Interval for heating and presence states. |
| **Slow Polling** | `24h` | Interval for battery and device metadata. |
| **Debounce Time**| `5s` | **Batching Window:** Fuses actions into single calls. |
| **Throttle Threshold** | `0` | Auto-skip calls when quota is dangerously low. |
| **API Proxy URL** | `None` | **Advanced:** URL of local `tado-api-proxy` to bypass limits. |

---

## 📱 Entities & Controls

### 🏠 Home Device ("Tado Home")
Global controls for the entire home. *Will be linked to your Internet Bridge device.*

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.away_mode` | Switch | Toggle Home/Away presence lock. |
| `button.turn_off_all_zones` | Button | **Bulk:** Turns off heating in ALL zones. |
| `button.boost_all_zones` | Button | **Bulk:** Boosts all zones to 25°C. |
| `button.resume_all_schedules` | Button | **Bulk:** Returns all zones to Smart Schedule. |
| `button.refresh_zones_devices` | Button | Updates zone and device metadata (2 calls). |
| `button.refresh_offsets` | Button | Fetches all hardware offsets (N calls). |
| `button.refresh_away_temperatures` | Button | Fetches all zone away temps (M calls). |
| `button.full_manual_poll` | Button | **Expensive:** Refreshes everything at once. |
| `sensor.api_calls_remaining` | Sensor | Your precious daily API gold. |
| `sensor.api_status` | Sensor | Connection health (`connected`, `throttled`). |

### 🌡️ Zone Devices (Rooms / Hot Water / AC)
These devices only exist in Tado Hijack as HomeKit does not support these logical concepts or specific hardware controls.

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.schedule` | Switch | **ON** = Smart Schedule, **OFF** = Manual. |
| `switch.hot_water` | Switch | **Cloud Only:** Direct boiler power control. |
| `number.away_temperature` | Number | **Cloud Only:** Set away mode temperature. |
| `select.fan_speed` | Select | **AC Only:** Full fan speed control. |
| `select.swing` | Select | **AC Only:** Full swing control. |
| `button.resume_schedule` | Button | Force resume schedule (stateless). |

### 🔧 Physical Devices (Valves/Thermostats)
Hardware-specific entities. *These entities are **injected** into your existing HomeKit devices.*

| Entity | Type | Description |
| :--- | :--- | :--- |
| `binary_sensor.battery` | Binary Sensor | Battery health (Normal/Low). |
| `switch.child_lock` | Switch | Toggle Child Lock on the device. |
| `switch.dazzle_mode` | Switch | Control display behavior (V3+). |
| `number.temperature_offset` | Number | Interactive temperature calibration (-10 to +10°C). |

---

## ⚡ Services

For advanced automation, use these services:
*   `tado_hijack.turn_off_all_zones`
*   `tado_hijack.boost_all_zones`
*   `tado_hijack.resume_all_schedules`
*   `tado_hijack.manual_poll` (Supports `refresh_type`: `metadata`, `offsets`, `away`, `all`)

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
