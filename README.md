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

**The only Tado integration that survives when they cut your API to 100 calls/day.**

<br>

### 🧠 **Auto-Adaptive. Zero-Configuration. Bulletproof.**

While other integrations **die** when Tado slashes API limits, Tado Hijack **just adapts**. Our Auto Quota system intelligently recalculates your polling speed in real-time — whether Tado gives you 5,000 calls or 100, **your smart home keeps running**.

</div>

<br>

---

<br>

> [!IMPORTANT]
> **Migration Note (Zone Sensor Naming):**
> Zone sensor entity names have been standardized to use zone names (e.g., `sensor.wohnzimmer_mitte_humidity`) instead of the old format (e.g., `sensor.tado_daheim_12_humidity`).
> **Note:** Existing installations will likely retain the old IDs due to Home Assistant's registry persistence. To apply the new naming scheme, deleting and re-adding the **Tado Home configuration entry** is recommended.

<br>

> [!NOTE]
> **High API Usage is Expected (And Good!):**
> **You might see 2,000-4,000 API calls per day.** This is **completely normal** and exactly how Auto Quota is designed to work!
>
> **Why so many calls?**
>
> - Tado currently gives you **5,000 calls/day** — we use them efficiently to keep your home responsive (updates every 20-30s).
> - Other integrations waste this quota by polling too slowly or hitting the limit too early.
> - **When Tado cuts you to 100 calls/day**, Auto Quota **automatically slows down** to ~15 minutes per update. Your smart home keeps running — just slower.
>
> **TL;DR:** High usage now = fast updates. Low quota later = automatic slowdown. **This is the whole point of Auto Quota.** Don't panic — enjoy the speed while it lasts! 🚀

<br>

> [!NOTE]
> **Migration v6:**
> All polling intervals have been reset to their default values. This migration was necessary because the configuration schema switched from **hours to seconds** to allow for much higher precision and consistency across all features. Please review your settings in the integration options.

<br>

> [!WARNING]
> **Compatibility Note (Tado X / Matter):**
> This integration is currently optimized for **Tado V3+** (IB01) systems.
> **Tado X** devices use the new Matter architecture and a different API which is **not yet supported**. Support is planned for a future release; current focus is on perfecting the V3+ and HomeKit experience.

<br>

---

<br>

## 🔥 **Why Tado Hijack?**

<br>

Tado is forcing you into a subscription by choking the "free" API from **5,000 → 100 calls/day**. Most integrations will simply stop working. **We engineered a different solution.**

<br>

### **The Tado Hijack Advantage:**

- **🧠 Fully Autonomous:** Set it once, forget forever. Auto Quota adapts to **any** API limit Tado throws at you (5k, 1k, 100 — doesn't matter).
- **💎 Extreme Batching:** 10 commands across 10 rooms? **Still only 1 API call.** We fuse everything.
- **🛡️ Threshold Protection:** Reserve quota exclusively for your automations. Background polling **never** touches this buffer.
- **🌙 Night-Savings Reinvestment:** Sleep 23:00-07:00? We pause polling and reinvest those saved calls into lightning-fast daytime updates.
- **🔗 HomeKit Injection:** We don't replace your local HomeKit devices — we **upgrade** them with cloud power-features (Hot Water, AC Pro, Schedules) in one unified device.
- **🕒 Dynamic Reset Detection:** Monitors Tado's 12-13h reset window and auto-detects quota refresh by tracking percentage jumps.
- **📡 Real-Time Quota Transparency:** See your remaining "API Gold" live. Know exactly when Tado tries to silence you.

<br>

**Bottom Line:** Other integrations require constant manual adjustments, feature sacrifices, or just break entirely. **Tado Hijack is engineered to outlast Tado's hostility.**

<br>

---

<br>

## 📖 Table of Contents

<br>

- [🆚 Feature Comparison](#feature-comparison)
- [🚀 Key Highlights](#key-highlights)
  - [🧠 Extreme Batching Technology](#extreme-batching-technology)
  - [🤝 The HomeKit "Missing Link"](#the-homekit-missing-link)
  - [🛠️ Unleashed Features](#unleashed-features-non-homekit)
  - [🛡️ State Integrity & Robustness](#state-integrity--robustness)
- [📊 API Consumption Strategy](#api-consumption-strategy)
  - [📊 API Consumption Table](#api-consumption-table)
  - [📈 Auto API Quota & Economy Window](#auto-api-quota--economy-window)
  - [🧠 Batching Capability Matrix](#batching-capability-matrix)
- [🛠️ Architecture](#architecture)
  - [🔧 Physical Device Mapping](#physical-device-mapping--resolution)
  - [🛡️ Robustness & Security](#robustness--security)
- [📦 Installation](#installation)
- [⚙️ Configuration](#configuration)
- [📱 Entities & Controls](#entities--controls)
  - [🏠 Home Device (Internet Bridge)](#home-device-internet-bridge)
  - [🌡️ Zone Devices (Rooms / Hot Water / AC)](#zone-devices-rooms--hot-water--ac)
  - [🔧 Physical Devices (Valves/Thermostats)](#physical-devices-valvesthermostats)
- [⚡ Services](#services)
  - [📝 set_mode Examples (YAML)](#set_mode-examples-yaml)
- [📋 Known Constraints](#known-constraints)
- [🐛 Troubleshooting](#troubleshooting)
- [📚 Documentation](#documentation)

<br>

---

<br>

## Feature Comparison

<br>

| Feature                            | Official Tado | HomeKit (Local) |     **Tado Hijack**     |
| :--------------------------------- | :-----------: | :-------------: | :---------------------: |
| **Temperature Control**            |      ✅       |       ✅        |    🔗 (via HK Link)     |
| **Boiler Load / Modulation**       |      ✅       |       ❌        |       ✅ **Yes**        |
| **Hot Water Power & Temp**         |      ✅       |       ❌        |       ✅ **Full**       |
| **Smart Schedules Switch**         |      ✅       |       ❌        |       ✅ **Yes**        |
| **AC Pro (Fan/Swing)**             |      ✅       |       ❌        |       ✅ **Full**       |
| **Child Lock / OWD / Early**       |      ✅       |       ❌        |       ✅ **Yes**        |
| **Local Control**                  |      ❌       |       ✅        |    ✅ (via HK Link)     |
| **Dynamic Presence-Aware Overlay** |      ❌       |       ❌        |    ✅ **Exclusive**     |
| **Auto Quota (Weighted)**          |      ❌       |       N/A       |       ✅ **Yes**        |
| **Economy Window (Night Mode)**    |      ❌       |       N/A       |       ✅ **Yes**        |
| **Command Batching**               |      ❌       |       N/A       | ✅ **Extreme (1 Call)** |
| **HomeKit Injection**              |      ❌       |       N/A       |    ✅ **One Device**    |
| **API Quota Visibility**           |      ❌       |       N/A       |    ✅ **Real-time**     |
| **Privacy Redaction (Logs)**       |      ❌       |       N/A       |      ✅ **Strict**      |

<br>

---

<br>

## Key Highlights

<br>

### Extreme Batching Technology

<br>

While other integrations waste your precious API quota for every tiny interaction, Tado Hijack features **Deep Command Merging**. We collect multiple actions and fuse them into a single, highly efficient bulk request.

<br>

> [!TIP]
> **Maximum Fusion Scenario:**
> Triggering a "Party Scene": **AC Living Room** (Temp + Fan + Swing) + **AC Kitchen** (Temp + Fan) + **Hot Water** (ON).
>
> ❌ **Standard Integrations:** 6-8 API calls (Half your hourly quota gone).
> ✅ **Tado Hijack:** **1 single API call** for everything.
>
> _Note: This works within your configurable **Debounce Window**. Every action is automatically fused._

<br>

> [!IMPORTANT]
> **Universal Batching:** This applies to manual dashboard interactions AND automated service calls (like `set_mode`). 10 changes at once? **Still only 1 API call.**

<br>

---

<br>

### The HomeKit "Missing Link"

<br>

**We don't replace HomeKit. We fix it.**

Almost no other integration does this: Tado Hijack automatically detects your existing HomeKit devices and **injects** the missing cloud-only power-features directly into them. You get the rock-solid local control of HomeKit combined with advanced cloud features in **one single unified device**.

<br>

> [!IMPORTANT]
> **Hybrid Architecture:**
> This integration is designed to work **alongside** the native HomeKit Device integration.
>
> - **HomeKit:** Provides the `climate` entity (Local Temperature Control & Current Temp).
> - **Tado Hijack:** Provides the "Missing Links" (Schedules, Hot Water, AC Modes, Hardware Settings).
>
> _Note: Without HomeKit, regular heating valves will NOT have a climate entity._

<br>

> [!NOTE]
> **No Redundancy:** Tado Hijack does **not** provide temperature control for regular heating valves (TRVs), as HomeKit already handles this perfectly. We focus strictly on the features HomeKit cannot see: **Cloud-only controls** and logical Zone Schedules.

<br>

---

<br>

### Unleashed Features (Non-HomeKit)

<br>

We bring back the controls Tado "forgot" to give you:

- **🚿 Professional Hot Water Platform:** Native `water_heater` entity with standardized `auto`, `heat`, and `off` modes. Full Pre-Validation ensures you never send invalid configurations.
- **❄️ AC Pro Features:** Precise Fan Speed and Swing (Horizontal/Vertical) selection.
- **📅 Schedule Transparency:** View the target temperature of your active Smart Schedule directly via the `auto_target_temperature` attribute while in `auto` mode (available for AC and Hot Water).
- **🕵️‍♂️ Expert-Level Error Capturing:** No more generic "422" errors. Tado Hijack captures the actual response body from Tado's API (e.g. _"temperature must not be null"_), giving you and the community precise feedback for troubleshooting.
- **🔥 Valve Opening Insight:** View the percentage of how far your valves are open (updated during state polls).
- **🔋 Real Battery Status:** Don't guess; see the actual health of every valve.
- **🌡️ Temperature Offset:** Interactive calibration for your thermostats.
- **✨ Dazzle Mode:** Control the display behavior of your V3+ hardware.
- **🏠 Presence Lock:** Force Home/Away modes regardless of what Tado thinks.
- **🔥 Dynamic Presence-Aware Overlay:** Set temperatures specifically for the current presence state — an exclusive feature that automatically resets once your home presence changes.
- **🔓 Rate Limit Bypass:** Support for local [tado-api-proxy](https://github.com/s1adem4n/tado-api-proxy).

<br>

---

<br>

### State Integrity & Robustness

<br>

Tado Hijack implements enterprise-grade state management to ensure your settings never get lost or overwritten:

- **💾 State Memory:** AC fan speed, swing positions, and target temperatures survive Home Assistant restarts. No more "reset to default" frustration.
- **🔒 Field Locking:** Prevents concurrent API calls from overwriting each other. Change fan speed, then swing, then temperature in rapid succession — all settings are preserved.
- **🎯 Pending Command Tracking:** Rapidly clicking temperature buttons (+/-) or dragging a slider? Multiple UI events collapse into **1 API call** with the final value. Zero waste, zero duplicates.
- **⏮️ Rollback on Error:** If an API call fails (e.g., invalid payload), the UI automatically reverts to the previous state with a clear error message. No "ghost states" where the UI lies about what's active.
- **🧵 Thread-Safe Queue:** All write operations pass through a single serialized queue. Automations, dashboard changes, and service calls never conflict or race.

<br>

> [!TIP]
> **tado-api-proxy TL;DR:**
> The proxy acts as a local cache and authentication handler. It allows you to use your integration without being strictly bound to Tado's cloud limits.
>
> 1. Run the [Docker Container](https://github.com/s1adem4n/tado-api-proxy#docker-setup).
> 2. Set your `API Proxy URL` in Hijack Options (e.g., `http://192.168.1.10:8080`).
> 3. Enjoy unlimited local-like polling (safety floor still applies).

<br>

---

<br>

## API Consumption Strategy

<br>

Tado's API limits are restrictive. That's why Tado Hijack uses a **Zero-Waste Policy**.

<br>

### API Consumption Table

<br>

| Action              |  Cost  | Frequency     | Description                              | Detailed API Calls                                                                     |
| :------------------ | :----: | :------------ | :--------------------------------------- | :------------------------------------------------------------------------------------- |
| **Zone Poll**       | **1**  | Adaptive      | HVAC, Valve %, Humidity.                 | `GET /homes/{id}/zoneStates`                                                           |
| **Presence Poll**   | **1**  | 12h (Default) | Home/Away presence state.                | `GET /homes/{id}/state`                                                                |
| **Hardware Sync**   | **2+** | 24h (Default) | Syncs battery, firmware and device list. | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices`<br>`GET /zones/{id}/capabilities` |
| **Refresh Zones**   | **2**  | On Demand     | Updates zone/device metadata.            | `GET /homes/{id}/zones`<br>`GET /homes/{id}/devices`                                   |
| **Refresh Offsets** | **N**  | On Demand     | Fetches all device offsets.              | `GET /devices/{s}/temperatureOffset` (×N)                                              |
| **Refresh Away**    | **M**  | On Demand     | Fetches all zone away temps.             | `GET /zones/{z}/awayConfiguration` (×M)                                                |
| **Zone Overlay**    | **1**  | On Demand     | **Fused:** All zone changes in 1 call.   | `POST /homes/{id}/overlay`                                                             |
| **Home/Away**       | **1**  | On Demand     | Force presence lock.                     | `PUT /homes/{id}/presenceLock`                                                         |

<br>

> [!NOTE]
> **Zero Waste Writes:**
> Unlike standard integrations, Tado Hijack does **not** trigger a costly poll after sending commands (except for Resume Schedule). We use **Local State Patching** to update the UI immediately without wasting a single API call on confirmation.

<br>

> [!TIP]
> **Throttled Mode:** When API quota runs low, the integration can automatically disable periodic polling to preserve remaining quota for your automations.

<br>

> [!IMPORTANT]
> **Granular Refresh Strategy:** To keep your quota green, hardware configurations (Offsets, Away Temperatures) are **never** fetched automatically. They remain empty until you manually trigger a specific refresh button or set a value.

<br>

### Auto API Quota & Economy Window

<br>

**This is where Tado Hijack becomes truly unstoppable.**

<br>

While other integrations die when Tado cuts their API limits, **we simply adapt**. Auto API Quota is a **fully autonomous, self-optimizing system** that intelligently distributes your precious API calls across the day — no matter what Tado throws at you.

<br>

#### 🧠 **Zero-Touch Intelligence**

Once enabled, you **never need to touch your polling intervals again**. The system:

- **🔄 Adapts to ANY Limit:** Tado reduces your quota from 5,000 → 4,000 → 1,000 → 100? **We don't care.** The brain recalculates instantly and adjusts your polling speed to match. Your smart home keeps running.
- **🎯 Threshold Protection:** You configure a "Throttle Threshold" (default: 20 calls). This quota is **reserved** exclusively for your automations, scripts, and manual app usage. The periodic background polling **never** touches this buffer — ensuring your automations always work, even when quota runs low.
- **📉 Dynamic Slowdown:** If you exceed the threshold (e.g., heavy automation day), Auto Quota doesn't panic. It **automatically slows down** background polling for the rest of the day to compensate, preventing you from hitting the hard limit.
- **🌙 Night-Savings Reinvestment:** Configure an Economy Window (e.g., 23:00 - 07:00) where polling slows to a crawl (or stops entirely with Interval 0). The system calculates the **exact API savings** from your sleep hours and **reinvests** them into faster updates during your active Performance Phase.
- **🕒 Dynamic Reset Detection:** Monitors Tado's reset window (**12-13h Berlin**) and automatically detects when quota resets occur by tracking percentage jumps, then recalculates intervals to spread your quota perfectly across the day.
- **🛡️ Works with Proxy Too:** Even if you bypass Tado's cloud limits using the API Proxy, Auto Quota still optimizes your polling patterns for maximum efficiency and account safety.

<br>

#### 🚀 **The Result: True "Set and Forget"**

Other integrations require constant babysitting:

- 💀 **Other Devs:** Hardcode new intervals when Tado changes limits. Users must manually update configurations or reinstall.
- 💀 **Other Users:** Constantly adjust polling intervals, disable features, or lose functionality when quota drops.

**Tado Hijack:** ✅ **Just works.** Forever. Regardless of what Tado does.

<br>

#### 🎯 **Real-World Scenarios**

| Scenario                                      | Other Integrations                                               | **Tado Hijack (Auto Quota)**                                             |
| :-------------------------------------------- | :--------------------------------------------------------------- | :----------------------------------------------------------------------- |
| **Tado cuts limit to 100 calls**              | 💀 Integration dies or polls every 15 minutes. Automations fail. | ✅ Auto-adjusts polling speed. Threshold ensures automations still work. |
| **Heavy automation day** (50+ external calls) | 💀 Quota exhausted by noon. No updates for rest of day.          | ✅ Detects excess usage, slows background polling to compensate.         |
| **Using API Proxy** (3000 calls/day)          | ⚠️ Hardcoded to slow intervals, wasting available quota.         | ✅ Maximizes proxy quota with optimized high-speed polling.              |
| **Night time** (23:00 - 07:00)                | ⚠️ Keeps polling at same rate, wasting quota while you sleep.    | ✅ Slows to 1h (or pauses). Saves 8+ hours of calls for daytime.         |

<br>

#### ⚙️ **How It Works**

<br>

**The Math behind the Intelligence:**

The system calculates your remaining budget by subtracting the **pro-rated background reserve** and your **protection buffer** from the currently reported remaining quota:

```
# 1. Background Reserve: Pro-rated cost for 24h maintenance syncs (Offsets, etc.)
RESERVED_BACKGROUND = Background_Sync_Cost_24h * (Seconds_Until_Reset / 86400)

# 2. Potentially Free: Your spendable quota minus the background reserve and your buffer
POTENTIALLY_FREE = Remaining_Quota - RESERVED_BACKGROUND - Throttle_Threshold

# 3. Remaining Budget: Target percentage of the potentially free quota
REMAINING_BUDGET = Max(0, POTENTIALLY_FREE * Auto_API_Quota_%)
```

<br>

**Adaptive Behavior & Safety:**

Instead of a static timer, your polling interval breathes with your quota and your life:

- **Performance Phase:** While you are awake, updates arrive as fast as every **20s** (or **120s** if using a proxy).
- **Economy Phase:** During your sleep window, the integration drops to a slow heartbeat (e.g., 1h) or pauses completely, saving every single call for the next morning.
- **🛡️ Safety Floor (Minimum Polling):** To protect your Tado account, we enforce minimum intervals:
  - **Standard:** Minimum **20 seconds** per update (configurable 20s-12h in Advanced Settings).
  - **API Proxy:** Minimum **120 seconds** per update (configurable 120s-12h in Advanced Settings).
  - _Note: These limits apply even if your budget allows for faster updates._

<br>

> [!NOTE]
> **Intelligence over Throttling:** While other integrations simply die when a limit is reached, Tado Hijack prioritizes **continuity over frequency**, gracefully slowing down to ensure your smart home stays informed 24/7 without ever hitting the hard wall.

<br>

---

<br>

### Batching Capability Matrix

<br>

Not all API calls are created equal. Tado Hijack optimizes everything, but physics (and the Tado API) sets limits.

<br>

| Action Type       | Examples                                                            | Strategy      | API Cost                                      |
| :---------------- | :------------------------------------------------------------------ | :------------ | :-------------------------------------------- |
| **State Control** | Target Temp, Turn Off All, Resume Schedule, Hot Water Power, AC Fan | **FUSED**     | **1 Call Total** (regardless of zone count)   |
| **Global Mode**   | Home/Away Presence                                                  | **DIRECT**    | **1 Call**                                    |
| **Zone Config**   | Early Start, Open Window, Dazzle Mode                               | **DEBOUNCED** | **1 Call per Zone** (Sequentially executed)   |
| **Device Config** | Child Lock, Temperature Offset                                      | **DEBOUNCED** | **1 Call per Device** (Sequentially executed) |

<br>

> **Fused (True Batching):**
> Multiple actions across multiple zones are merged into a **single** API request.
> _Example: Turning off 10 rooms at once = **1 API Call**._
>
> **Debounced (Rapid Update Protection):**
> Prevents spamming the API during rapid interactions (like clicking buttons or dragging sliders). Only the final value is sent.
> _Example: Rapidly clicking a temperature button or dragging a slider from 18°C to 22°C generates multiple events, but only **1 API Call** is sent._

<br>

> [!NOTE]
> **Why not batch everything?**
> Tado does **not** provide bulk API endpoints for device configurations (Child Lock, Offset, Window Detection). We must send these commands individually per device. We optimize what we can, but we cannot invent endpoints that don't exist.

<br>

---

<br>

## Architecture

<br>

### Physical Device Mapping & Resolution

<br>

Unlike other integrations that group everything by "Zone", Tado Hijack maps entities to their **physical devices** (Valves/Thermostats).

- **Matched via Serial Number:** Automatic injection into existing HomeKit devices.
- **EntityResolver:** A specialized engine that deep-scans the Home Assistant registry to perfectly link HomeKit climate entities with Tado's cloud logical zones.
- **No HomeKit?** We create dedicated devices containing **only** the cloud features (Battery, Offset, Child Lock, etc.), but **no** temperature control.

<br>

### Robustness & Security

<br>

- **JIT Poll Planning:** Uses high-precision timestamps instead of simple flags to decide exactly when a data fetch is required (Zero-Waste).
- **Monkey-Patching Utilities:** We actively fix `tadoasync` library limitations at runtime, including robust deserialization for tricky cloud states (like `nextTimeBlock` null errors).
- **Custom Client Layer:** Extended underlying library via inheritance to handle API communication reliably and fix common deserialization errors.
- **Safety Throttle (Anti-Spam):** If the Tado API reports an invalid limit (e.g., `<= 0` during outages), the integration automatically throttles to a **5-minute safety interval** and logs a warning to prevent rapid re-polling.
- **Authenticated Proxy Support:** Fully supports path-based authentication for the API Proxy, ensuring your external communication remains secure and private.
- **Persistent Reconnect & Recovery:** When the API quota is exhausted (throttled), the system performs a recovery check every **15 minutes** (reduced from 1h) to ensure immediate resumption of services as soon as the API becomes available or the quota resets.
- **Privacy by Design:** All standard logs and diagnostic reports are automatically redacted. Sensitive data is stripped before any output is generated. (See [Expert-Level Diagnostics](#expert-level-diagnostics) for details).
- **🎭 Pattern Obfuscation:** Multi-Level Jitter (Poll & Call) breaks temporal correlation between Home Assistant triggers and API requests to avoid pattern-based throttling (Proxy only).

<br>

---

<br>

## Installation

<br>

### Via HACS (Recommended)

<br>

1. Open **HACS** -> **Integrations** -> **Custom repositories**.
2. Add `https://github.com/banter240/tado_hijack` as **Integration**.
3. Search for **"Tado Hijack"** and download.
4. **Restart Home Assistant**.

<br>

---

<br>

## Configuration

<br>

| Option                             | Default   | Description                                                                                                                                                                                                                                                |
| :--------------------------------- | :-------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status Polling**                 | `30m`     | Base interval for room states. **Note:** Dynamically overridden by _Auto API Quota_ when enabled; serves as fallback during throttling or budget exhaustion.                                                                                               |
| **Presence Polling**               | `12h`     | Interval for Home/Away state. High interval saves mass quota. (1 API call)                                                                                                                                                                                 |
| **Auto API Quota**                 | `80%`     | Target X% of FREE quota. **Note:** While the official API is being choked to **100 calls/day**, using the **API Proxy** bypasses this trap, granting **3000 calls per account**. Uses a weighted profile to prioritize performance hours.                  |
| **Reduced Polling Active**         | `Off`     | Enable the time-based weighted polling profile.                                                                                                                                                                                                            |
| **Reduced Polling Start**          | `22:00`   | Start time for the economy window (e.g. when you sleep).                                                                                                                                                                                                   |
| **Reduced Polling End**            | `07:00`   | End time for the economy window.                                                                                                                                                                                                                           |
| **Reduced Polling Interval**       | `3600s`   | Polling interval during the economy window. Set to **0** to pause polling entirely.                                                                                                                                                                        |
| **Hardware Sync**                  | `86400s`  | Interval for battery, firmware and device metadata. Set to 0 for initial load only.                                                                                                                                                                        |
| **Offset Update**                  | `0` (Off) | Interval for temperature offsets. Costs 1 API call per valve.                                                                                                                                                                                              |
| **Min Polling Window**             | `20s`     | **Performance Floor:** The absolute fastest speed Auto Quota will poll (20s-12h).                                                                                                                                                                          |
| **Debounce Time**                  | `5s`      | **Batching Window:** Fuses actions into single calls.                                                                                                                                                                                                      |
| **Refresh After Resume**           | `On`      | Auto-refresh target temperature/state after resume schedule (HVAC AUTO). Required because schedules are Tado cloud-side. Uses 1s grace period to merge multiple resumes. Costs 1 API call.                                                                 |
| **Throttle Threshold**             | `20`      | **External Protection Buffer:** Reserve N calls for everything outside of Hijack's periodic background polling (External Automations, Scripts, Manual App use). Polling stops when remaining quota hits this floor to ensure your automations never stall. |
| **Disable Polling When Throttled** | `Off`     | Stop periodic polling entirely when throttled.                                                                                                                                                                                                             |
| **API Proxy URL**                  | `None`    | **Advanced:** URL of local `tado-api-proxy` workaround.                                                                                                                                                                                                    |
| **API Proxy Token**                | `None`    | **Security:** Authentication token for your proxy. Injected into the path (`/token/api/v2`).                                                                                                                                                               |
| **Call Jitter**                    | `Off`     | **Anti-Ban Protection:** Adds random delays before API calls to obfuscate automation patterns (Proxy only).                                                                                                                                                |
| **Jitter Strength**                | `10%`     | The percentage of random variation applied to intervals and delays (Proxy only).                                                                                                                                                                           |
| **Log Level**                      | `INFO`    | Control integration verbosity (DEBUG, INFO, WARNING, ERROR).                                                                                                                                                                                               |

<br>

---

<br>

## Entities & Controls

<br>

### Home Device (Internet Bridge)

<br>

Global controls and elite transparency for your home. _Linked to your Internet Bridge._

<br>

| Entity                                     |  Type  | Description                                                       |
| :----------------------------------------- | :----: | :---------------------------------------------------------------- |
| `switch.tado_{home}_away_mode`             | Switch | Toggle Home/Away presence lock.                                   |
| `switch.tado_{home}_polling_active`        | Switch | **Master Switch:** Instantly stop/start all periodic API polls.   |
| `switch.tado_{home}_reduced_polling_logic` | Switch | **Logic Switch:** Toggle the timed "Economy" profile.             |
| `button.tado_{home}_resume_all_schedules`  | Button | **Bulk:** Restore Smart Schedules across all zones (1 call).      |
| `button.tado_{home}_full_manual_poll`      | Button | **Expensive:** Forced synchronization of all metadata and states. |
| `sensor.tado_{home}_api_remaining`         | Sensor | **API Gold:** Your remaining daily call budget.                   |
| `sensor.tado_{home}_api_status`            | Sensor | Real-time health (`connected`, `throttled`, `rate_limited`).      |

<br>

> [!TIP]
> **Power-User Diagnostics:**
> Tado Hijack provides **over 15 additional diagnostic entities** within the standard Home Assistant **Diagnostics** section of the Internet Bridge device. These include live polling intervals, enforced safety floors, proxy authentication status, and granular sync timers for elite monitoring. Check the device page to unleash full transparency.

<br>

### Zone Devices (Rooms / Hot Water / AC)

<br>

Cloud-only features that HomeKit does not support.

<br>

| Entity                              | Type          | Description                                                                                     |
| :---------------------------------- | :------------ | :---------------------------------------------------------------------------------------------- |
| `switch.schedule`                   | Switch        | **ON** = Smart Schedule, **OFF** = Manual. Simple way to resume schedule.                       |
| `climate.ac_{room}`                 | Climate       | **AC Only:** Full HVAC mode control (`cool`, `heat`, `dry`, `fan`, `auto`) with native slider.  |
| `water_heater.hot_water`            | WaterHeater   | **Hot Water:** Modes: `auto` (schedule), `heat` (manual), `off`.                                |
| `binary_sensor.hot_water_power`     | Binary Sensor | Status if boiler is currently heating water.                                                    |
| `binary_sensor.hot_water_overlay`   | Binary Sensor | Status if a manual override is active.                                                          |
| `switch.early_start`                | Switch        | **Cloud Only:** Toggle pre-heating before schedule.                                             |
| `number.open_window_timeout`        | Number        | **Cloud Only:** Open window detection timeout (0=OFF, 5-1439min=ON).                            |
| `number.target_temperature`         | Number        | **Cloud Only:** Set target temp for HW (manual mode).                                           |
| `number.away_temperature`           | Number        | **Cloud Only:** Set away mode temperature.                                                      |
| `select.fan_speed`                  | Select        | **AC Only:** Full fan speed control.                                                            |
| `select.swing`                      | Select        | **AC Only:** Full swing control.                                                                |
| `sensor.heating_power`              | Sensor        | **Insight:** Valve opening % or Boiler Load %.                                                  |
| `sensor.humidity`                   | Sensor        | Zone humidity (faster than HomeKit).                                                            |
| `sensor.next_schedule_temp`         | Sensor        | **Planning:** Target temp of the upcoming schedule block.                                       |
| `sensor.next_schedule_mode`         | Sensor        | **Planning:** Mode (HEAT/OFF) of the upcoming schedule block.                                   |
| `sensor.next_time_block_start`      | Sensor        | **Planning:** Start time of the next schedule block.                                            |
| `button.resume_schedule`            | Button        | Force resume schedule (stateless).                                                              |
| `attribute.auto_target_temperature` | Metadata      | **Transparency:** Current schedule setpoint visible in attributes during `auto` mode (AC & HW). |

<br>

> [!NOTE]
> **Schedule Planning Sensors:**
> The `next_schedule_*` sensors provide a peek into the future without extra polling.
> However, during **Away Mode**, Tado often disables the standard schedule, causing these sensors to report `Unknown`. This is normal behavior as there is no active "next block" counting down.

<br>

### Physical Devices (Valves/Thermostats)

<br>

Hardware-specific entities. _These entities are **injected** into your existing HomeKit devices._

<br>

| Entity                      | Type          | Description                                         |
| :-------------------------- | :------------ | :-------------------------------------------------- |
| `binary_sensor.battery`     | Binary Sensor | Battery health (Normal/Low).                        |
| `binary_sensor.connection`  | Binary Sensor | Device connectivity to Tado cloud.                  |
| `switch.child_lock`         | Switch        | Toggle Child Lock on the device.                    |
| `switch.dazzle_mode`        | Switch        | Control display behavior (V3+).                     |
| `number.temperature_offset` | Number        | Interactive temperature calibration (-10 to +10°C). |

<br>

---

<br>

## Services

<br>

For advanced automation, use these services. All manual control services feature **Pre-Validation**: Invalid combinations (e.g. `auto` + temperature) are blocked immediately with a clear error message in the Home Assistant UI.

<br>

| Service                             | Description                                                                                                                  | API Impact           |
| :---------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :------------------- |
| `tado_hijack.turn_off_all_zones`    | Turn off all zones instantly.                                                                                                | **1 call** (bulk)    |
| `tado_hijack.boost_all_zones`       | Boost every zone to 25°C.                                                                                                    | **1 call** (bulk)    |
| `tado_hijack.resume_all_schedules`  | Restore Smart Schedule across all zones.                                                                                     | **1 call** (bulk)    |
| `tado_hijack.set_mode`              | Set mode, temperature, and termination. Supports `hvac_mode` (auto, heat, off) and `overlay` (manual, next_block, presence). | **1 call** (batched) |
| `tado_hijack.set_mode_all_zones`    | Targets all HEATING and/or AC zones at once using `hvac_mode`.                                                               | **1 call** (bulk)    |
| `tado_hijack.set_water_heater_mode` | Set `operation_mode` and temperature for hot water.                                                                          | **1 call**           |
| `tado_hijack.manual_poll`           | Force immediate data refresh. Use `refresh_type` to control scope.                                                           | **2-N** (depends)    |

<br>

> [!TIP]
> **Intelligent Post-Action Polling (`refresh_after`):**
> When active, the integration uses a smart decision engine to save API quota:
>
> - **Immediate Refresh:** Triggered for `auto` (Resume Schedule) or permanent manual changes. Since the target state is reached immediately, an instant GET request confirms the cloud synchronization.
> - **Intelligently Deferred:** For timed modes (`duration`), the refresh is **deferred** until the timer actually expires. Polling immediately during a timer is wasteful; we wait for the "expiry event" to fetch the new post-timer state.
> - **Event-Aware:** For `next_block` or `presence` overlays, immediate polling is suppressed as the cloud state transition depends on external time/events.

<br>

> [!TIP]
> **Targeting Rooms:** You can use **any** entity that belongs to a room as the `entity_id`. This includes Tado Hijack switches or even your existing **HomeKit climate** entities (e.g. `climate.living_room`).

<br>

### `set_mode` Examples (YAML)

<br>

**Hot Water Boost (30 Min):**

```yaml
service: tado_hijack.set_water_heater_mode
data:
  entity_id: water_heater.hot_water
  operation_mode: "heat"
  temperature: 55
  overlay: "manual"
  duration: 30
  refresh_after: false
```

<br>

**Quick Bathroom Heat (15 Min at 24°C):**

```yaml
service: tado_hijack.set_mode
data:
  entity_id: climate.bathroom
  hvac_mode: "heat"
  temperature: 24
  overlay: "manual"
  duration: 15
  refresh_after: false
```

<br>

**Manual Override (Indefinite):**

```yaml
service: tado_hijack.set_mode
data:
  entity_id: climate.living_room
  hvac_mode: "heat"
  temperature: 21
  overlay: "manual"
  refresh_after: false
```

<br>

**Resume Schedule (Auto):**

```yaml
service: tado_hijack.set_mode
data:
  entity_id: climate.kitchen
  hvac_mode: "auto"
  overlay: "manual" # Required by schema, ignored for 'auto'
  refresh_after: true
```

<br>

**Auto-Return to Schedule (Next Time Block):**

```yaml
service: tado_hijack.set_mode
data:
  entity_id: climate.kitchen
  hvac_mode: "heat"
  temperature: 22
  overlay: "next_block"
  refresh_after: false
```

<br>

---

<br>

## Known Constraints

<br>

### API Limitations (Tado Backend)

<br>

While Tado Hijack optimizes every possible interaction, some operations are inherently limited by Tado's server-side architecture:

- **No Bulk Device Config:** Tado does **not** provide bulk API endpoints for hardware-specific settings. Temperature Offsets, Child Lock, and Window Detection must be sent individually (1 API call per device). If you change these for 10 devices, it will always cost 10 calls.
- **Schedule Logic is Cloud-Side:** When you "Resume Schedule", the actual target temperature is determined by Tado's servers. To show the correct value in HA immediately, a single confirmatory poll is required (if `Refresh After Resume` is enabled).
- **Sequential Execution:** To prevent account locks and respect the backend, device configuration commands are executed sequentially with a small delay.

<br>

### Hybrid Cloud Dependency

<br>

While Tado Hijack uses the cloud for its power-features, your basic smart home remains resilient:

- **Local Resilience:** Temperature control and heating state via **HomeKit** remain fully functional even during internet outages or Tado server issues.
- **Cloud-Only Features:** Access to Smart Schedules, Hot Water control, and AC-Pro features requires a connection to Tado's servers.
- **Why Cloud?** Tado does not expose a local API for advanced logic. Tado Hijack bridges this gap while keeping your local core intact.

<br>

---

<br>

## Troubleshooting

<br>

If you encounter issues, please check the following steps before opening a GitHub issue or asking on Discord.

<br>

### Expert-Level Diagnostics

<br>

Sharing diagnostics **should be safe**. Our built-in Diagnostic Report uses **Multi-Layer Anonymization** to protect your privacy while providing all necessary technical data. However, you should always verify the content yourself before posting it publicly. If in doubt, send the report via DM to an administrator.

- **🔑 Key Pseudonymization:** Home Assistant Entity-IDs in JSON keys are transformed into unique anonymized hashes (e.g. `sensor.entity_8a3f`). This protects your room names while maintaining machine-readability for debugging.
- **🛡️ PII Masking:** All sensitive names (Zones, Homes, Mobile Devices, Titles) are replaced with `"Anonymized Name"`.
- **🕵️‍♂️ Serial Number Protection:** Every hardware identifier (VA, RU, IB, etc.), E-mail address, and cryptographic secret (Tokens, Hashes) is automatically masked via intelligent Regex everywhere in the document.
- **📊 Pure Debug Power:** Despite maximum privacy, the report contains all technical insights needed for support:
  - Detailed Quota & Adaptive Interval math.
  - API Queue & Action status.
  - Internal Entity Mappings (Anonymized but uniquely identifiable).
  - Device Metadata (Firmware, Battery, Connection status).

<br>

> [!TIP]
> **How to get the report:**
> Go to **Settings** -> **Devices & Services** -> **Tado Hijack** -> Click the three dots (⋮) -> **Download diagnostics**.

<br>

### Debug Logging

<br>

Enable verbose logging in your `configuration.yaml` to see what happens behind the scenes:

```yaml
logger:
  default: info
  logs:
    custom_components.tado_hijack: debug
```

<br>

---

<br>

## Documentation

<br>

Looking for more technical details or want to contribute?

<br>

### 📐 Architecture & Design

**[DESIGN.md](https://github.com/banter240/tado_hijack/blob/main/docs/DESIGN.md)** — Deep dive into the integration's architecture:

- Complete system pipeline and execution flow
- Specialized managers (Data, API, RateLimitManager, OptimisticManager)
- API Gold budget system and weighted quota distribution
- State integrity mechanisms (Field Locking, Pending Commands, Rollback Context)
- Rate limit bypass via API Proxy
- Concurrency control and thread-safety

<br>

### 🛠️ Developer Guide

**[DEVELOPMENT.md](https://github.com/banter240/tado_hijack/blob/main/docs/DEVELOPMENT.md)** — Everything you need for local development:

- Dummy simulation environment (test without physical hardware)
- Local development setup and workflow
- Code structure and key concepts for contributors
- Testing checklist and debugging tips
- Contributing guidelines

<br>

---

<br>

**Disclaimer:** This is an unofficial integration. Built by the community, for the community. Not affiliated with Tado GmbH. Use at your own risk.
