# Tado Hijack for Home Assistant 🏴‍☠️

[![semantic-release: conventional commits](https://img.shields.io/badge/semantic--release-conventionalcommits-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/banter240/tado_hijack)](https://github.com/banter240/tado_hijack/releases/latest)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/github/downloads/banter240/tado_hijack/total)
![GitHub](https://img.shields.io/github/license/banter240/tado_hijack)

**The rebellion against API limits.**

Tado restricted their API? They think you shouldn't control your own heating? **Tado Hijack begs to differ.**

We engineered this integration with one goal: **To squeeze every drop of functionality out of Tado's cloud without triggering their rate limits.**

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

### 🧠 Smart Batching Technology
Most integrations struggle with Tado's strict quotas. Tado Hijack was built differently. We implemented advanced **Smart Batching** that intelligently merges your dashboard interactions into single, efficient API calls.

*   Click 10 rooms OFF in 1 second? That's **1 API call** for us.
*   Boost your entire house? **1 API call**.
*   Resume schedule for everyone? **1 API call**.

It's designed to give you back control.

### 🤝 The Ultimate HomeKit Companion
**We don't replace HomeKit. We supercharge it.**
Almost no other integration does this: Tado Hijack automatically detects your existing HomeKit devices and **injects** the missing features directly into them.
You get the rock-solid local control of HomeKit combined with the advanced cloud features of Tado (Battery, Offset, Child Lock) in **one single unified device**.

> [!NOTE]
> **Entity Locations:** While hardware-specific entities (Battery, Offset, Child Lock) are linked directly into your HomeKit-originated devices, the **Zone Controls** (Schedule & Resume) remain within the Tado Hijack "Zone" devices. This is because HomeKit does not have a technical equivalent for Tado's cloud-based "Zones" to link against.

It's the best of both worlds.

### 🛠️ Missing Features Restored
HomeKit is great for local control, but it lacks deep system access. We add:
*   **🔋 Battery Status:** Real-time battery health for every valve.
*   **🌡️ Temperature Offset:** Interactive control to calibrate your thermostats.
*   **🔒 Child Lock:** Toggle child lock directly from HA.
*   **🏠 Presence Control:** Force Home/Away mode.
*   **🔥 Boost & Off:** Global controls to Boost or Turn Off the entire house.

---

## 📊 API Consumption Strategy

Tado limits API calls per day. Tado Hijack is engineered to stay well below the radar using our **1-Call Policy**: Every user action costs exactly **1 API call** (or even less with batching).

### API Consumption Table

| Action | Cost | Frequency | Description | Detailed API Calls |
| :--- | :---: | :--- | :--- | :--- |
| **Periodic Poll** | **2** | 30m (Default) | Fetches global state & zones. | `GET /homes/{id}/state`<br>`GET /homes/{id}/zoneStates` |
| **Battery Update** | **2** | 24h | Fetches device list & metadata. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices` |
| **Toggle Schedule** | **1** | On Demand | Switches single zone mode. | `DELETE /zones/{z}/overlay` (On)<br>`PUT /zones/{z}/overlay` (Off) |
| **Turn Off ALL** | **1** | On Demand | Bulk OFF via Bulk API. | `POST /homes/{id}/overlay` |
| **Boost ALL** | **1** | On Demand | Bulk Boost via Bulk API. | `POST /homes/{id}/overlay` |
| **Resume ALL** | **1** | On Demand | Bulk Resume via Bulk API. | `DELETE /homes/{id}/overlay?rooms=...` |
| **Home/Away** | **1** | On Demand | Force presence lock. | `PUT /homes/{id}/presenceLock` |
| **Child Lock** | **1** | On Demand | Toggle child lock per device. | `PUT /devices/{s}/childLock` |
| **Offset Control** | **1** | On Demand | Interactive calibration per device. | `PUT /devices/{s}/temperatureOffset` |
| **Offset Check** | **N** | Disabled | Fetches current offset config. | `GET /devices/{s}/temperatureOffset` |

> [!TIP]
> **Throttled Mode:** When API quota runs low, the integration can automatically disable periodic polling to preserve remaining quota for your automations.

---

## 🛠️ Architecture

### Physical Device Mapping
Unlike other integrations that group everything by "Zone", Tado Hijack maps entities to their **physical devices** (Valves/Thermostats).
*   **If HomeKit is present:** Entities attach to the existing HomeKit device (Matched via Serial Number).
*   **If HomeKit is absent:** We create clean, dedicated devices for each valve (e.g., `tado Smart Radiator Thermostat VA12345678`).

### Robustness & Security
*   **Custom Client Layer:** We extend the underlying library via inheritance to handle API communication reliably and fix common deserialization errors.
*   **Privacy by Design:** All logs are automatically redacted. Sensitive data (User Codes, Serial Numbers, Home IDs) is stripped before writing to disk.

---

## 📦 Installation

### Via HACS (Recommended)

1. Open **HACS** -> **Integrations**.
2. Menu -> **Custom repositories**.
3. Add `https://github.com/banter240/tado_hijack` as **Integration**.
4. Search for **"Tado Hijack"** and click **Download**.
5. **Restart Home Assistant**.

---

## ⚙️ Configuration

1. Go to **Settings** -> **Devices & Services**.
2. Click **+ ADD INTEGRATION** -> **"Tado Hijack"**.
3. Follow the link to authorize with your Tado account.
4. **Configure Polling:**
   *   **Fast Polling (default 30m):** Core state update.
   *   **Slow Polling (default 24h):** Battery check.
   *   **Offset Polling (default 0):** Keep disabled unless you need real-time offset updates.
   *   **Debounce Time:** Collect rapid changes before sending.

---

## 📱 Entities & Controls

### 🏠 Home Device ("Tado Home")
Global controls for the entire home. *Will be linked to your Internet Bridge device.*

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.away_mode` | Switch | Toggle between Home and Away presence. |
| `button.turn_off_all_zones` | Button | **Bulk:** Turns off heating in ALL zones. |
| `button.boost_all_zones` | Button | **Bulk:** Boosts all zones to 25°C. |
| `button.resume_all_schedules` | Button | **Bulk:** Returns all zones to Smart Schedule. |
| `sensor.api_calls_remaining` | Sensor | Real-time remaining API quota. |
| `sensor.api_status` | Sensor | Connection health (`connected`, `throttled`). |

### 🌡️ Zone Devices
Controls specific to a heating zone (Room).

| Entity | Type | Description |
| :--- | :--- | :--- |
| `switch.schedule` | Switch | **ON** = Smart Schedule, **OFF** = Manual Overlay. |
| `button.resume_schedule` | Button | Force resume schedule (stateless trigger). |

### 🔧 Physical Devices (Valves/Thermostats)
Hardware-specific entities. *Linked to your HomeKit devices.*

| Entity | Type | Description |
| :--- | :--- | :--- |
| `binary_sensor.battery` | Binary Sensor | Battery health (Normal/Low). |
| `switch.child_lock` | Switch | Toggle Child Lock on the device. |
| `number.temperature_offset` | Number | Interactive temperature calibration (-10 to +10°C). |

---

## ⚡ Services

For advanced automation, use these services:
- `tado_hijack.turn_off_all_zones`
- `tado_hijack.boost_all_zones`
- `tado_hijack.resume_all_schedules`
- `tado_hijack.manual_poll`

---

## 🐛 Troubleshooting

Enable debug logging in `configuration.yaml`. Logs are safe to share (auto-redacted).
```yaml
logger:
  default: info
  logs:
    custom_components.tado_hijack: debug
```

---

**Disclaimer:** This is an unofficial integration. Not affiliated with Tado GmbH. Use at your own risk.
