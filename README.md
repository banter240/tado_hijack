<div align="center">

# Tado Hijack for Home Assistant 🏴‍☠️

<br>

[![Latest Release](https://img.shields.io/github/v/release/banter240/tado_hijack?style=for-the-badge&color=e10079&logo=github)](https://github.com/banter240/tado_hijack/releases/latest)
[![Dev Release](https://img.shields.io/github/v/release/banter240/tado_hijack?include_prereleases&label=dev&style=for-the-badge&color=orange&logo=github)](https://github.com/banter240/tado_hijack/releases)
[![Downloads](https://img.shields.io/github/downloads/banter240/tado_hijack/total?style=for-the-badge&color=green&logo=github)](https://github.com/banter240/tado_hijack/releases)
[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5?style=for-the-badge&logo=home-assistant)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/banter240/tado_hijack?style=for-the-badge&color=blue)](LICENSE)

[![Discord](https://img.shields.io/discord/1460909918482858060?logo=discord&logoColor=white&style=for-the-badge&color=5865F2)](https://discord.gg/kxUsjHyxfT)
[![Discussions](https://img.shields.io/github/discussions/banter240/tado_hijack?style=for-the-badge&logo=github&color=7289DA)](https://github.com/banter240/tado_hijack/discussions)
[![Open Issues](https://img.shields.io/github/issues/banter240/tado_hijack?style=for-the-badge&color=red&logo=github)](https://github.com/banter240/tado_hijack/issues)
[![Stars](https://img.shields.io/github/stars/banter240/tado_hijack?style=for-the-badge&color=yellow&logo=github)](https://github.com/banter240/tado_hijack/stargazers)

<br>

<a href="https://buymeacoffee.com/banter240" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 50px !important;width: 181px !important;" ></a>

<br>

**The only Tado integration that survives when they cut your API to 100 calls/day.**

<br>

### 🧠 **Auto-Adaptive. Zero-Configuration. Bulletproof.**

While other integrations **die** when Tado slashes API limits, Tado Hijack **just adapts**. Our Auto Quota system intelligently recalculates your polling speed in real-time — whether Tado gives you 1,000 calls or 100, **your smart home keeps running**.

</div>

<br>

---

<br>

> [!NOTE]
> **High API Usage is Expected (And Good!):**
> **You might see 800-1,500 API calls per day.** This is **completely normal** and exactly how Auto Quota is designed to work!
>
> - Tado currently gives you **1,000 calls/day** — we use them efficiently for responsive updates (every ~90s)
> - **If Tado cuts you to 100 calls/day**, Auto Quota **automatically slows down** to maintain optimal performance
>
> **TL;DR:** High usage now = fast updates. Low quota later = automatic slowdown. This is the whole point of Auto Quota! 🚀

<br>

---

<br>

<div align="center">

**[🆚 Comparison](#feature-comparison)** • **[🚀 Highlights](#key-highlights)** • **[📊 API Strategy](#api-consumption-strategy)** • **[🛠️ Architecture](#architecture)**<br>**[📦 Installation](#installation)** • **[⚙️ Configuration](#configuration)** • **[📱 Entities](#entities--controls)** • **[⚡ Services](#services)**<br>**[📋 Constraints](#known-constraints)** • **[🐛 Troubleshooting](#troubleshooting)** • **[❓ FAQ](#frequently-asked-questions-faq)** • **[📚 Docs](#documentation)** • **[☕ Support](#support-the-project)**

</div>

<br>

---

<br>

## 🔥 **Why Tado Hijack?**

<br>

Tado is forcing you into a subscription by choking the "free" API — **already cut from 20k → 5k → 1k calls/day**, with **100 calls/day planned next**. Most integrations will simply stop working. **We engineered a different solution.**

<br>

### **The Tado Hijack Advantage:**

> [!IMPORTANT]
> **What Tado Hijack Does (and Doesn't Do):**
>
> **Temperature Control (Climate Entities):**
> - **Default Mode:** Use **HomeKit Device** (v3) or **Matter** (Tado X) for local temperature control
> - **Full Cloud Mode (All Generations):** Optional cloud-polling climate entities
>   - ⚠️ **Recommended for V2 bridges (GW)** which lack HomeKit/Matter support
>   - V2's 20k calls/day makes cloud polling viable
>   - V3/X can also use cloud mode, but HomeKit/Matter is preferred (1k calls/day, reducing to 100 soon)
>
> **What Tado Hijack Adds:**
> - Cloud-only features: Schedules, Hot Water, AC Pro, QuickActions
> - Hardware settings: Child Lock, Temperature Offset, Battery status
> - API quota management and intelligent polling
> - **Indoor Climate Intelligence:** Dew point, mold risk (level + binary), absolute humidity, and ventilation recommendation sensors per zone — for both v3 Classic and Tado X
> - **Device Unification:** Injects these features into your existing HomeKit devices (V3 only - Matter lacks serial numbers for linking)
> - **V2 Support:** First integration supporting legacy GW bridges via Full Cloud Mode
>
> **TL;DR:** HomeKit/Matter = Temperature Control | Tado Hijack = Cloud Features + Smarts<br>
> **V2 Bridges:** Enable Full Cloud Mode for basic climate control (API-intensive!)

<br>

- **🧠 Fully Autonomous:** Set it once, forget forever. Auto Quota adapts to **any** API limit Tado throws at you (1k, 100 — doesn't matter).
- **💎 Extreme Batching:** 10 commands across 10 rooms? **Still only 1 API call.** We fuse everything.
- **🛡️ Threshold Protection:** Reserve quota exclusively for your automations. Background polling **never** touches this buffer.
- **🌙 Night-Savings Reinvestment:** Sleep 23:00-07:00? We pause polling and reinvest those saved calls into lightning-fast daytime updates.
- **🔗 Device Unification (V3/HomeKit only):** We don't replace your HomeKit devices — we **upgrade** them with cloud power-features (Hot Water, AC Pro, Schedules) in one unified device. _Note: Matter (Tado X) doesn't expose serial numbers, so features appear as separate entities._
- **🌟 Universal Hardware Support:** First integration supporting **V2 (GW bridges), V3 Classic, AND Tado X** in one unified architecture with generation-aware features.
- **🕒 Dynamic Reset Detection:** Monitors Tado's 12-13h reset window and auto-detects quota refresh by tracking percentage jumps.
- **📡 Real-Time Quota Transparency:** See your remaining "API Gold" live. Know exactly when Tado tries to silence you.

<br>

**Bottom Line:** Other integrations require constant manual adjustments, feature sacrifices, or just break entirely. **Tado Hijack is engineered to outlast Tado's hostility.**

<br>

---

<br>

## Feature Comparison

<br>

| Feature                            | Official Tado | HomeKit (v3) |     **Tado Hijack**     |
| :--------------------------------- | :-----------: | :----------: | :---------------------: |
| **Temperature Control**            |      ✅       |      ✅      |  🔗 (HK/Matter) / ☁️ (V2 Cloud Mode)  |
| **Boiler Load / Modulation**       |      ✅       |      ❌      |       ✅ **Yes**        |
| **Hot Water Power & Temp**         |      ✅       |      ❌      |       ✅ **Full**       |
| **Smart Schedules Switch**         |      ✅       |      ❌      |       ✅ **Yes**        |
| **AC Pro (Fan/Swing)**             |      ✅       |      ❌      |    ✅ **Full (v3)**     |
| **Child Lock / OWD / Early**       |      ✅       |      ❌      |       ✅ **Yes**        |
| **Indoor Climate Sensors**         |      ❌       |      ❌      |  ✅ **Both Gens**       |
| **Local Control (v3)**             |      ❌       |      ✅      |    ✅ (via HK Link)     |
| **Tado X Support**                 |      ❌       |      ❌      |  ✅ **Local + Cloud**   |
| **Multi-Generation Support**       |      ❌       |   v3 only    |   ✅ **v3 / X / v2**    |
| **Device Unification**             |      ❌       |      ❌      |    ✅ **V3 only**    |
| **Dynamic Presence-Aware Overlay** |      ❌       |      ❌      |    ✅ **Exclusive**     |
| **Auto Quota (Weighted)**          |      ❌       |     N/A      |       ✅ **Yes**        |
| **Economy Window (Night Mode)**    |      ❌       |     N/A      |       ✅ **Yes**        |
| **Command Batching**               |      ❌       |     N/A      | ✅ **Extreme (1 Call)** |
| **API Quota Visibility**           |      ❌       |     N/A      |    ✅ **Real-time**     |
| **Privacy Redaction (Logs)**       |      ❌       |     N/A      |      ✅ **Strict**      |

<br>

> [!IMPORTANT]
> **🌟 Local Matter Control for Tado X:**
> Tado Hijack is the **first and only** integration that combines **Matter local control** with Tado X cloud features!
>
> - **Other integrations:** Support Tado X only via **full cloud** (no local control, 100% API dependent)
> - **Tado Hijack:** Uses **Matter** for local temperature control + cloud API for advanced features (Schedules, QuickActions, etc.)
>
> We support **BOTH** Tado v3 Classic (HomeKit) **AND** Tado X (Matter) through a unified architecture. Note: Some features are v3-specific (Hot Water, AC, Early Start) due to hardware limitations.

<br>

---

<br>

## Generation Support: V2, V3 Classic & Tado X

**Quick Reference:** This integration supports V2 (GW bridges), V3 Classic (HomeKit), and Tado X (Matter).

| Feature Category              | V2 (GW) | v3 Classic | Tado X | Notes                        |
| :---------------------------- | :-----: | :--------: | :----: | :--------------------------- |
| **Temperature Control**       | ☁️ |     ✅     |   ✅   | All: Cloud mode available / V3: HomeKit / X: Matter |
| **Hot Water**                 | ✅ |     ❌     |        | Cloud API + water_heater entity |
| **AC Pro (Fan/Swing)**        | ✅ |     ❌     |        | Cloud API + climate entity   |
| **QuickActions (Bulk)**       | ✅ |     ✅     |        | boost/off/resume = 1 call    |
| **set_mode_all (Bulk)**       | ✅ |     ❌     |        | v3=1 call, X=N calls         |
| **Hardware Settings**         | ✅ |     ✅     |        | Child Lock, Offset, etc.     |
| **Indoor Climate Sensors**    | ❌ |     ✅     |   ✅   | Dew point, mold risk, AH, ventilation. v3: built-in fallback. Tado X: link temperature source on zone device. |

> See [FAQ](#frequently-asked-questions-faq) for detailed setup instructions and temperature source configuration.

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

### The Local "Missing Link"

<br>

**We don't replace local control. We enhance it.**

**For V3 (HomeKit):** Tado Hijack detects your existing HomeKit devices and **injects** cloud-only features directly into them — creating one unified device with both local control and cloud power-features.

**For Tado X (Matter):** Matter doesn't expose serial numbers for device linking, so Tado Hijack features appear as separate entities alongside your Matter climate entities.

<br>

> [!IMPORTANT]
> **Hybrid Architecture:**
> This integration is designed to work **alongside** native local control:
>
> - **Tado v3 Classic:** Works with HomeKit Device integration (provides `climate` entity for local temperature control)
> - **Tado X:** Works with Matter integration (provides `climate` entity for local temperature control)
> - **Tado Hijack:** Provides the "Missing Links" for **both generations** (Schedules, Hot Water, AC Modes, Hardware Settings)
>   - **V3 Bonus:** Device Unification (features injected into HomeKit devices)
>
> _Note: **Full Cloud Mode** provides climate entities via API polling but consumes API quota for temperature changes. See [Full Cloud Mode](#full-cloud-mode-all-generations) for details._

<br>

> [!NOTE]
> **No Redundancy (Default Mode):** By default, Tado Hijack does **not** create climate entities, as local protocols (HomeKit/Matter) already handle temperature control efficiently. We focus on cloud-only features: **Schedules, Hot Water, AC Modes, Hardware Settings**.
>
> **Full Cloud Mode:** Optionally enables cloud-polling climate entities, **but consumes API quota** for every temperature change. Only recommended for V2 bridges (20k calls/day) or users without HomeKit/Matter access.

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
- **🌡️ Indoor Climate Intelligence:** Per-zone sensors for **dew point**, **mold risk** (level + binary), **indoor absolute humidity**, and **ventilation recommendation** — calculated from room temperature and humidity using the Magnus formula and EU building-physics thresholds. Available for both v3 Classic and Tado X. Each zone device exposes optional **Temperature Source** and **Humidity Source** selectors to link any sensor or climate entity as the data source.
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
| **Refresh Offsets** | **1–N**  | On Demand  | Fetches device offsets. 1 call with `entity_id`, N without. | `GET /devices/{s}/temperatureOffset` (×1 or ×N)                                  |
| **Refresh Away**    | **1–M**  | On Demand  | Fetches zone away temps. 1 call with `entity_id`, M without. | `GET /zones/{z}/awayConfiguration` (×1 or ×M)                                   |
| **Zone Overlay**    | **1**  | On Demand     | **Fused:** All zone changes in 1 call.   | `POST /homes/{id}/overlay`                                                             |
| **Home/Away**       | **1**  | On Demand     | Force presence lock.                     | `PUT /homes/{id}/presenceLock`                                                         |

_Note: Endpoints shown are v3 API. Tado X uses different endpoints (Hops API) but similar polling logic. See [Generation Support](#generation-support-v3-classic--tado-x) for differences._

<br>

> [!TIP]
> **API Optimization Features:**
>
> - **Zero Waste Writes:** Commands don't trigger a poll. We use Local State Patching to update the UI instantly without confirmation calls.
> - **Throttled Mode:** When quota runs low, periodic polling auto-disables to preserve quota for your automations.
> - **Granular Refresh:** Hardware configs (Offsets, Away Temps) are never fetched automatically — only on-demand when you need them.

<br>

### Auto API Quota & Economy Window

<br>

**This is where Tado Hijack becomes truly unstoppable.**

<br>

While other integrations die when Tado cuts their API limits, **we simply adapt**. Auto API Quota is a **fully autonomous, self-optimizing system** that intelligently distributes your precious API calls across the day — no matter what Tado throws at you.

<br>

#### 🧠 **Zero-Touch Intelligence**

Once enabled, you **never need to touch your polling intervals again**. The system:

- **🔄 Adapts to ANY Limit:** Tado reduces your quota from 20k → 5k → 1k → 100? **We don't care.** The brain recalculates instantly and adjusts your polling speed to match. Your smart home keeps running.
- **🎯 Threshold Protection:** You configure a "Throttle Threshold" (default: 20 calls). This quota is **reserved** exclusively for your automations, scripts, and manual app usage. The periodic background polling **never** touches this buffer — ensuring your automations always work, even when quota runs low.
- **📉 Dynamic Slowdown:** If you exceed the threshold (e.g., heavy automation day), Auto Quota doesn't panic. It **automatically slows down** background polling for the rest of the day to compensate, preventing you from hitting the hard limit.
- **🌙 Night-Savings Reinvestment:** Configure an Economy Window (e.g., 23:00 - 07:00) where polling slows to a crawl (or stops entirely with Interval 0). The system calculates the **exact API savings** from your sleep hours and **reinvests** them into faster updates during your active Performance Phase.
- **🕒 Adaptive Reset Learning:** Learns YOUR specific reset time through pattern detection. Tado's quota resets vary by user (7:30, 12:04, etc.). After observing 2+ resets at the same hour, the system adapts to your schedule and optimizes quota distribution accordingly. Always plans minimum 20h ahead for conservative budgeting.
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
| **Tado cuts limit further to 100 calls**      | 💀 Integration dies or polls once per day. Automations fail.     | ✅ Auto-adjusts polling speed. Threshold ensures automations still work. |
| **Heavy automation day** (50+ external calls) | 💀 Quota exhausted by noon. No updates for rest of day.          | ✅ Detects excess usage, slows background polling to compensate.         |
| **Using API Proxy** (3000 calls/day)          | ⚠️ Hardcoded to slow intervals, wasting available quota.         | ✅ Maximizes proxy quota with optimized high-speed polling.              |
| **Night time** (23:00 - 07:00)                | ⚠️ Keeps polling at same rate, wasting quota while you sleep.    | ✅ Slows to 1h (or pauses). Saves 8+ hours of calls for daytime.         |

<br>

#### ⚙️ **How It Works**

<br>

**The Math behind the Intelligence:**

The system distributes your daily quota budget across the full day, and continuously recalculates how much is left for polling:

```
# 1. Daily polling budget based on your total limit
DAILY_CEILING = (Limit - Background_24h - Throttle_Threshold) × Auto_API_Quota_%

# 2. Effective threshold rises with actual external usage above the configured floor
BASELINE_POLLING    = max(Actual_Polls_Today, DAILY_CEILING × Day_Progress)
INFERRED_EXTERNAL   = max(0, Consumed - Background_Consumed - BASELINE_POLLING)
EFFECTIVE_THRESHOLD = max(Throttle_Threshold, INFERRED_EXTERNAL)
DAILY_CEILING       = (Limit - Background_24h - EFFECTIVE_THRESHOLD) × Auto_API_Quota_%

# 3. How much of that budget is still available for remaining polls
POLLS_DONE     = Consumed - Background_Consumed - INFERRED_EXTERNAL
PLANNED_BUDGET = DAILY_CEILING - POLLS_DONE

# 4. Capped against what is actually remaining in your account
AVAILABLE_NOW = Remaining - EFFECTIVE_THRESHOLD - Future_Background

# 5. Final budget for the rest of the day
FINAL_BUDGET = max(0, min(PLANNED_BUDGET, AVAILABLE_NOW) - Safety_Reserve)
```

> **💡 Adaptive Reset Window Learning:**
> Tado's quota reset time **varies by user** (some get 7:30 AM, others 12:04 PM). The system learns YOUR specific reset schedule by observing reset patterns:
> - **First reset:** Noted, system stays conservative (assumes 12:30 default)
> - **2+ resets at same hour:** Pattern learned! System adapts to your schedule (e.g., 7:30 → normalized to 7:30)
> - **Planning horizon:** Always plans minimum **20 hours ahead** to prevent quota burning
> - **Normalization:** All resets in the same hour (e.g., 7:03, 7:35, 7:58) are normalized to X:30 for pattern grouping
>
> The safety reserve (default: 2 calls) is distributed evenly across a **3-hour window** (±1h around the expected reset hour) to keep polling active even when the main budget runs out.

<br>

**Adaptive Behavior & Safety:**

Instead of a static timer, your polling interval breathes with your quota and your life:

- **Performance Phase:** While you are awake, updates arrive as fast as every **20s** (or **120s** if using a proxy).
- **Economy Phase:** During your sleep window, the integration drops to a slow heartbeat (e.g., 1h) or pauses completely, saving every single call for the next morning.
- **🛡️ Safety Floor (Minimum Polling):** To protect your Tado account, we enforce minimum intervals:
  - **Standard:** Minimum **5 seconds** per update (configurable 5s-12h in Advanced Settings, default: 20s).
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
> **Exceptions:** Device configs (Child Lock, Offset) require individual API calls per device. See [Services](#services) table for complete API impact breakdown.

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

Tado Hijack is now an **official HACS integration**! No custom repository needed.

1. Open **HACS** -> **Integrations**.
2. Search for **"Tado Hijack"** and click **Download**.
3. **Restart Home Assistant**.
4. Go to **Settings** -> **Devices & Services** -> **Add Integration** -> Search for **"Tado Hijack"**.
5. **Select your hardware generation** (determined by your physical Tado bridge):
   - **Tado v3 Classic** - If you own an **IB01** or **GW01** bridge (black square box)
   - **Tado X** - If you own a **Bridge X (IB02)** (newer Matter-based system)

<br>

> [!IMPORTANT]
> **Hardware Generation:**
> Select your generation during setup based on your physical bridge: IB01/GW01 = **v3 Classic**, IB02 = **Tado X**. If unsure, choose v3 Classic (most common). See [Generation Support](#generation-support-v3-classic--tado-x) for feature differences.

<br>

---

<br>

## Configuration

<br>

| Option                             | Default   | Description                                                                                                                                                                                                                                                |
| :--------------------------------- | :-------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status Polling**                 | `30m`     | Base interval for room states. **Note:** Dynamically overridden by _Auto API Quota_ when enabled; serves as fallback during throttling or budget exhaustion.                                                                                               |
| **Presence Polling**               | `12h`     | Interval for Home/Away state. High interval saves mass quota. (1 API call)                                                                                                                                                                                 |
| **Auto API Quota**                 | `80%`     | Target X% of FREE quota. **Note:** The official API is currently limited to **1,000 calls/day**. Using the **API Proxy** bypasses this limitation, granting **3,000 calls per account**. Uses a weighted profile to prioritize performance hours.          |
| **Reduced Polling Active**         | `Off`     | Enable the time-based weighted polling profile.                                                                                                                                                                                                            |
| **Reduced Polling Start**          | `22:00`   | Start time for the economy window (e.g. when you sleep).                                                                                                                                                                                                   |
| **Reduced Polling End**            | `07:00`   | End time for the economy window.                                                                                                                                                                                                                           |
| **Reduced Polling Interval**       | `3600s`   | Polling interval during the economy window. Set to **0** to pause polling entirely.                                                                                                                                                                        |
| **Hardware Sync**                  | `86400s`  | Interval for battery, firmware and device metadata. Set to 0 for initial load only.                                                                                                                                                                        |
| **Offset Update**                  | `0` (Off) | Interval for temperature offsets. Costs 1 API call per valve.                                                                                                                                                                                              |
| **Min Polling Window**             | `20s`     | **Performance Floor:** The absolute fastest speed Auto Quota will poll (5s-12h, default: 20s).                                                                                                                                                                          |
| **Debounce Time**                  | `5s`      | **Batching Window:** Fuses actions into single calls.                                                                                                                                                                                                      |
| **Refresh After Resume**           | `On`      | Auto-refresh target temperature/state after resume schedule (HVAC AUTO). Required because schedules are Tado cloud-side. Uses 1s grace period to merge multiple resumes. Costs 1 API call.                                                                 |
| **Throttle Threshold**             | `20`      | **External Protection Buffer:** Reserve N calls for everything outside of Hijack's periodic background polling (External Automations, Scripts, Manual App use). Polling stops when remaining quota hits this floor to ensure your automations never stall. |
| **Quota Safety Reserve**           | `2`       | **Reset Window Bridge:** API calls reserved from quota percentage for the reset window (12:00-13:00 Berlin). Distributed evenly during the window to bridge uncertainty when reset time varies (e.g., 12:05 vs 12:30). Set to 0 to disable (not recommended). |
| **Disable Polling When Throttled** | `Off`     | Stop periodic polling entirely when throttled.                                                                                                                                                                                                             |
| **API Proxy URL**                  | `None`    | **Advanced:** URL of local `tado-api-proxy` workaround.                                                                                                                                                                                                    |
| **API Proxy Token**                | `None`    | **Security:** Authentication token for your proxy. Injected into the path (`/token/api/v2`).                                                                                                                                                               |
| **Call Jitter**                    | `Off`     | **Anti-Ban Protection:** Adds random delays before API calls to obfuscate automation patterns (Proxy only).                                                                                                                                                |
| **Jitter Strength**                | `10%`     | The percentage of random variation applied to intervals and delays (Proxy only).                                                                                                                                                                           |
| **Log Level**                      | `INFO`    | Control integration verbosity (DEBUG, INFO, WARNING, ERROR).                                                                                                                                                                                               |
| **Suppress Redundant Calls**      | `Off`     | **API Optimization:** Skip API calls when target state matches cached state (temperature, mode, presence, power). Saves quota on accidental double-clicks or UI interactions. Only sends when actual change detected. Values not in cache always send. |
| **Suppress Redundant Buttons**     | `Off`     | **Aggressive Optimization:** Also skip button actions (resume_all, boost_all, turn_off_all, set_mode_all) when ALL zones already match target state. Requires 'Suppress Redundant Calls' to be enabled. Individual explicit actions always send. |
| **Dew Point Sensor**               | `On`      | Create a dew point temperature sensor per zone (Magnus formula, T + RH). v3: falls back to cloud zone state. Tado X: requires a linked temperature source on the zone device. |
| **Mold Risk Sensors**              | `On`      | Create a mold risk level sensor (`none`/`low`/`medium`/`high`) and a binary moisture sensor per zone. Uses dew point spread — correctly distinguishes cold-but-dry from cold-and-humid rooms. |
| **Outdoor Weather Entity**         | `None`    | Select a weather entity providing outdoor temperature + humidity. When set, creates an indoor absolute humidity sensor (g/m³) and a ventilation recommendation binary sensor per zone. |
| **Ventilation Threshold**          | `1.0 g/m³`| Minimum indoor-outdoor AH difference required before _Ventilation Recommended_ turns ON. Prevents automation chatter from negligible differences. |
| **Temperature Source** _(per zone)_| `Automatic`  | Optional: link a temperature `sensor` or `climate` entity as the data source for indoor climate sensors. Set via `select.zone_temp_source` on each zone device. Required for Tado X (cloud has no temp in Full-Matter mode). |
| **Humidity Source** _(per zone)_   | `Automatic`  | Optional: link a `climate` entity (reads `current_humidity`) or a humidity `sensor` as the data source for indoor climate sensors. Set via `select.zone_humidity_source` on each zone device. Fallback: cloud zone state humidity. |

<br>

### Zone Temperature & Humidity Sources (All Generations)

<br>

Each zone device exposes two optional source selectors that override the data used for indoor climate calculations (dew point, mold risk, absolute humidity, ventilation recommendation):

| Select Entity              | Purpose                               | Accepted types               |
| :------------------------- | :------------------------------------ | :--------------------------- |
| `select.zone_temp_source`  | Temperature override for the zone     | Any `climate` or temperature `sensor` |
| `select.zone_humidity_source` | Humidity override for the zone     | Any `climate` (reads `current_humidity`) or humidity `sensor` |

**Fallback chain when no source is selected:**

| Priority | Temperature fallback | Humidity fallback |
| :------- | :------------------- | :---------------- |
| **1. Select Entity** | Entity chosen in `select.zone_temp_source` | Entity chosen in `select.zone_humidity_source` |
| **2. Connected Climate** | Associated Climate Entity (Full-Cloud or mapped HomeKit) | Tado Hijack Humidity Sensor (`sensor.X_humidity`) |
| **3. Cloud API** | `sensor_data_points.inside_temperature` (v3 only) | `sensor_data_points.humidity` (All Gens) |

> [!TIP]
> For **Tado X**, Matter devices cannot be auto-linked because they do not expose serial numbers to Home Assistant. Therefore, the cloud API lacks room temperature. Link your Matter `climate` entity (e.g. `climate.schlafzimmer`) or a local temperature sensor via the `select.zone_temp_source` to activate dew point and mold risk sensors.

> [!NOTE]
> For **v3 Classic**, linking sources is **optional**. The built-in HomeKit linkage and zone state provides both temperature and humidity automatically. Link an external sensor only if you want higher precision or a different measurement point.

Changes take effect on the next coordinator update — no integration reload required.

<br>

### Full Cloud Mode (All Generations)

<br>

> [!WARNING]
> **Full Cloud Mode: When to Use It**
>
> Full Cloud Mode creates climate entities via cloud polling instead of HomeKit/Matter integration.
>
> **✅ RECOMMENDED FOR:**
> - **V2 Bridges (GW)** - These lack HomeKit/Matter support, making Full Cloud Mode the **only** option for climate entities
> - V2 bridges have **~20,000 calls/day** which makes cloud polling viable
>
> **⚠️ USE WITH CAUTION:**
> - **V3 Bridges (IB01/GW01)** - Currently 1k calls/day, reducing to 100 soon
> - **Tado X (IB02)** - Currently 1k calls/day, reducing to 100 soon
> - **Recommendation:** Use HomeKit (V3) or Matter (X) integration instead — no API cost, local control
> - Full Cloud Mode is **technically supported** for all generations but **not recommended** for V3/X due to quota limits
>
> **⚠️ API QUOTA IMPACT:**
> - Every temperature change = 1 API call
> - **V2:** ~20k calls/day makes cloud polling sustainable
> - **V3/X:** 1k calls/day (soon: 100) exhausted quickly by temperature changes
> - **Best Practice:** Use HomeKit/Matter for V3/X to preserve quota for advanced features
>
> **Configuration:**
> - Enable during setup: Config Flow → **Full Cloud Mode** toggle

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
| `button.tado_{home}_resume_all_schedules`  | Button | Restore Smart Schedule across all zones (1 bulk call).            |
| `button.tado_{home}_turn_off_all_zones`    | Button | Turn off all zones instantly (1 bulk call).                       |
| `button.tado_{home}_boost_all_zones`       | Button | Boost all zones to 25°C (1 bulk call).                            |
| `button.tado_{home}_full_manual_poll`      | Button | **Expensive:** Forced synchronization of all metadata and states. |
| `sensor.tado_{home}_api_limit`             | Sensor | Total daily API quota limit (1000 standard, 3000 with proxy).     |
| `sensor.tado_{home}_api_remaining`         | Sensor | **API Gold:** Your remaining daily call budget.                   |
| `sensor.tado_{home}_api_status`            | Sensor | Real-time health (`connected`, `throttled`, `rate_limited`).      |

<br>

### Diagnostic Entities (Home)

<br>

Advanced monitoring sensors available under the Internet Bridge device diagnostics section:

<br>

**Quota Reset Learning (NEW in v5.0):**
- `sensor.quota_reset_last` - Last observed reset timestamp
- `sensor.quota_reset_next` - Predicted next reset (learned pattern)
- `sensor.quota_reset_expected_window` - Learned reset window (e.g., "12:15-12:45")
- `sensor.quota_reset_pattern_confidence` - Pattern confidence (low/medium/high/confirmed)
- `sensor.quota_reset_history_count` - Number of observed resets

**Polling Intervals:**
- `sensor.current_zone_interval` - Current dynamic polling interval
- `sensor.min_interval_configured` - User-configured minimum
- `sensor.min_interval_enforced` - Actual enforced minimum (proxy-aware)
- `sensor.reduced_polling_interval` - Economy window interval
- `sensor.debounce_time` - Batching window duration
- `sensor.presence_poll_interval`, `sensor.slow_poll_interval`, `sensor.offset_poll_interval`

**Configuration Status:**
- `sensor.auto_quota_percent`, `sensor.throttle_threshold`, `sensor.jitter_percent`
- `sensor.reduced_polling_start`, `sensor.reduced_polling_end`
- `sensor.suppress_redundant_calls`, `sensor.suppress_redundant_buttons`
- `binary_sensor.reduced_polling_active`, `binary_sensor.call_jitter_enabled`
- `binary_sensor.disable_polling_when_throttled`, `binary_sensor.refresh_after_resume`

**System Info:**
- `sensor.outdoor_absolute_humidity` - Calculated absolute humidity (g/m³) from external weather entity
- `sensor.tado_generation` - Detected hardware ("Tado X" or "Tado Classic (v3)")
- `sensor.proxy_url`, `sensor.proxy_token` - Proxy configuration status
- `sensor.log_level` - Current logging level

**Manual Refresh Buttons:**
- `button.refresh_metadata` - Force hardware sync
- `button.refresh_offsets` - Force offset sync
- `button.refresh_away` - Force away config sync
- `button.refresh_presence` - Force presence sync

<br>

### Zone Devices (Rooms / Hot Water / AC)

<br>

Cloud-only features that HomeKit does not support.

<br>

| Entity                              | Type          | Description                                                                                     |
| :---------------------------------- | :------------ | :---------------------------------------------------------------------------------------------- |
| `switch.schedule`                   | Switch        | **ON** = Smart Schedule, **OFF** = Manual. Simple way to resume schedule. **Supports heating and AC zones** (v3). |
| `climate.ac_{room}`                 | Climate       | **v3 AC Only:** Full HVAC mode control (`cool`, `heat`, `dry`, `fan`, `auto`) with native slider. |
| `water_heater.hot_water`            | WaterHeater   | **v3 Only:** Modes: `auto` (schedule), `heat` (manual), `off`.                                 |
| `binary_sensor.hot_water_power`     | Binary Sensor | **v3 Only:** Boiler heating status.                                                             |
| `binary_sensor.hot_water_overlay`   | Binary Sensor | **v3 Only:** Manual override active status.                                                     |
| `binary_sensor.hot_water_connectivity` | Binary Sensor | **v3 Only:** Zone connectivity based on device connections.                                  |
| `switch.early_start`                | Switch        | **v3 Only:** Toggle pre-heating before schedule block.                                          |
| `number.open_window_timeout`        | Number        | **Config:** Open window timeout (0=OFF, 5-1439min=ON). Requires Tado subscription for detection. |
| `number.target_temperature`         | Number        | **v3 HW Only:** Set hot water target temp (manual mode).                                        |
| `number.away_temperature`           | Number        | **v3 Only:** Set away mode temperature.                                                         |
| `select.zone_temp_source`           | Select        | **Config:** Optional temperature source for indoor climate sensors. Link any `climate` or temperature `sensor`. Required for Tado X (no cloud temp in Full-Matter mode). |
| `select.zone_humidity_source`       | Select        | **Config:** Optional humidity source for indoor climate sensors. Link a `climate` entity (reads `current_humidity`) or a humidity `sensor`. Fallback: cloud zone state. |
| `select.fan_speed`                  | Select        | **v3 AC Only:** Full fan speed control.                                                         |
| `select.vertical_swing`             | Select        | **v3 AC Only:** Vertical swing control (ON/OFF or position modes).                              |
| `select.horizontal_swing`           | Select        | **v3 AC Only:** Horizontal swing control (ON/OFF or position modes).                            |
| `sensor.heating_power`              | Sensor        | **Insight:** Valve opening % or Boiler Load %.                                                  |
| `sensor.humidity`                   | Sensor        | Zone humidity (faster than HomeKit).                                                            |
| `sensor.dew_point`                  | Sensor        | **Climate:** Dew point temperature (°C) via Magnus formula. Sources: linked `zone_temp_source` → zone state (v3) → unavailable (Tado X). Enabled via _Dew Point Sensor_ feature flag. |
| `sensor.mold_risk_level`            | Sensor        | **Climate:** Mold risk level: `none` / `low` / `medium` / `high`. Uses dew point spread — cold-but-dry rooms correctly show `none`. Enabled via _Mold Risk Sensors_ feature flag. |
| `binary_sensor.mold_risk`           | Binary Sensor | **Climate:** `ON` when mold risk is `medium` or `high`. Ideal for automations and alerts.      |
| `sensor.indoor_absolute_humidity`   | Sensor        | **Climate:** Indoor absolute humidity (g/m³). Shown when _Outdoor Weather Entity_ is configured. |
| `binary_sensor.ventilation_recommended` | Binary Sensor | **Climate:** `ON` when indoor AH exceeds outdoor AH by ≥ threshold — opening windows reduces moisture. Shown when _Outdoor Weather Entity_ is configured. |
| `sensor.next_schedule_change`       | Sensor        | **Planning:** Timestamp of next schedule transition (diagnostic).                               |
| `sensor.next_schedule_temp`         | Sensor        | **Planning:** Target temp of the upcoming schedule block.                                       |
| `sensor.next_schedule_mode`         | Sensor        | **Planning:** Mode (HEAT/OFF) of the upcoming schedule block.                                   |
| `sensor.next_time_block_start`      | Sensor        | **Planning:** Start time of the next schedule block.                                            |
| `button.resume_schedule`            | Button        | Force resume schedule (stateless). **Supports heating and AC zones** (v3).                      |
| `attribute.auto_target_temperature` | Metadata      | **Transparency:** Current schedule setpoint visible in attributes during `auto` mode (AC & HW). |

<br>

> [!NOTE]
> **Schedule Planning Sensors:**
> The `next_schedule_*` sensors provide a peek into the future without extra polling.
> However, during **Away Mode**, Tado often disables the standard schedule, causing these sensors to report `Unknown`. This is normal behavior as there is no active "next block" counting down.

<br>

### Physical Devices (Valves/Thermostats)

<br>

Hardware-specific entities. _These entities are **injected** into your existing HomeKit devices (V3 only). For Tado X, they appear as separate entities (Matter lacks serial numbers for linking)._

<br>

| Entity                      | Type          | Description                                         |
| :-------------------------- | :------------ | :-------------------------------------------------- |
| `binary_sensor.battery`     | Binary Sensor | Battery health (Normal/Low).                        |
| `binary_sensor.connection`  | Binary Sensor | Device connectivity to Tado cloud.                  |
| `switch.child_lock`         | Switch        | Toggle Child Lock on the device.                    |
| `switch.dazzle_mode`        | Switch        | **v3 Only:** Control display brightness/behavior.   |
| `number.temperature_offset` | Number        | Interactive temperature calibration (-10 to +10°C). |

<br>

---

<br>

## Services

<br>

For advanced automation, use these services. All manual control services feature **Pre-Validation**: Invalid combinations (e.g. `auto` + temperature) are blocked immediately with a clear error message in the Home Assistant UI.

<br>

| Service                             | Description                                                                                                                  | API Impact (v3)      | API Impact (Tado X)  |
| :---------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :------------------- | :------------------- |
| `tado_hijack.turn_off_all_zones`    | Turn off all zones instantly.                                                                                                | **1 call** (bulk)    | **1 call** (bulk)    |
| `tado_hijack.boost_all_zones`       | Boost every zone to 25°C.                                                                                                    | **1 call** (bulk)    | **1 call** (bulk)    |
| `tado_hijack.resume_all_schedules`  | Restore Smart Schedule across all zones.                                                                                     | **1 call** (bulk)    | **1 call** (bulk)    |
| `tado_hijack.set_mode`              | Set mode, temperature, and termination. Supports `hvac_mode` (auto, heat, off) and `overlay` (manual, next_block, presence). | **1 call** (batched) | **1 call** (batched) |
| `tado_hijack.set_mode_all_zones`    | Targets all HEATING and/or AC zones at once using `hvac_mode`.                                                               | **1 call** (bulk)    | **N calls** (per zone) |
| `tado_hijack.set_water_heater_mode` | Set `operation_mode` and temperature for hot water (v3 only).                                                                | **1 call**           | N/A (no HW zones)    |
| `tado_hijack.add_meter_reading`     | Upload a meter reading (integer) to Tado Energy IQ (v3 only).                                                                | **1 call**           | N/A (unsupported)    |
| `tado_hijack.manual_poll`           | Force immediate data refresh. Use `refresh_type` to control scope. Add `entity_id` for a targeted single-entity fetch (saves quota). | **1-N** (depends)    | **1-N** (depends)    |

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
> **Targeting Rooms:** You can use **any** Tado zone entity (climate, switch, sensor) or even **device entities** (battery, connection, child_lock) as the `entity_id`. Device entities automatically resolve to their zone via serial number lookup. This includes your existing **HomeKit climate** entities (e.g. `climate.living_room`).
>
> **Targeted Fetch:** When using `manual_poll` with an `entity_id`, the refresh is limited to that single entity — `offsets` costs 1 API call instead of N, `away` costs 1 instead of M. `capabilities` uses the lazy cache and only drops that zone's entry. Bulk types (`zone`, `metadata`, `presence`, `all`) always fall back to a full refresh.

<br>

> [!TIP]
> **Multi-Home Service Routing:**
> Have multiple Tado Homes configured? Our service routing is fully multi-account aware!
>
> - **Global Execution (Default):** Call `tado_hijack.resume_all_schedules` with empty data `{}` -> The command is sent to **all** configured Tado homes automatically.
> - **Targeted Execution:** Use the new `config_entry` parameter in your service call (available in the UI) to select a specific home. -> The command is routed **exclusively** to the selected home.
> - **Batched Entity Routing:** When sending multiple `entity_ids` to `set_mode` that belong to different homes, Tado Hijack automatically sorts the entities and batches the API requests to their respective homes in parallel.

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

## Frequently Asked Questions (FAQ)

<br>

### Where are my climate entities and current temperature?

In the **default mode**, Tado Hijack does **not** create `climate` entities for heating zones — HomeKit (v3) or Matter (Tado X) already handle local temperature control efficiently at zero API cost.

**Full Cloud Mode** (enabled during setup) creates cloud-polled climate entities. This is required for V2 bridges (GW) that have no HomeKit/Matter support, and optional for V3/X.

**Why prefer local protocols over cloud API?**

| Reason | Explanation |
| :----- | :---------- |
| **API Quota** | Accurate temp polling needs 720-1,440 calls/day → quota exhausted. Current limit is 1,000 calls/day. |
| **Speed** | HomeKit/Matter = instant response. Cloud API = latency + polling delays. |
| **Reliability** | Local protocols work offline. Cloud API requires internet. |
| **Cost** | HomeKit/Matter = zero API calls. Cloud API = every action costs quota. |

**What each integration provides:**

| Integration | Temperature Control | Cloud Features | API Calls |
| :---------- | :-----------------: | :------------: | :-------: |
| **HomeKit/Matter** | ✅ (`climate` entities, current temp) | ❌ | 0 |
| **Tado Hijack** | ❌ | ✅ (Schedules, Hot Water, AC Pro, Hardware) | Optimized |

**Setup:** Install HomeKit/Matter first → then Tado Hijack → **V3:** Features get injected into HomeKit devices | **Tado X:** Features appear as separate entities (Matter limitation).

<br>

### Why are my Tado X dew point / mold risk sensors unavailable?

For Tado X (without Full Cloud Mode), the cloud API does not deliver room temperature because the TRV measures it locally and reports it directly via Matter. Since Matter devices do not expose serial numbers in Home Assistant, Tado Hijack cannot auto-link them.

You **must** use the **Temperature Source** selector (`select.zone_temp_source`) on your Tado X zone device and select the corresponding Matter `climate` entity or a temperature sensor (e.g. `climate.schlafzimmer_tado`). Once set, the dew point, mold risk, and absolute humidity sensors activate for that zone immediately.

See [Zone Temperature & Humidity Sources](#zone-temperature--humidity-sources-all-generations) for details.

<br>

---

<br>

### Do I need both integrations? Can I use Hijack alone?

**Recommended setup:** Both integrations for complete experience.

**With both (Recommended):**
- ✅ Temperature control (HomeKit/Matter)
- ✅ Cloud features (Tado Hijack)
- ✅ Unified devices (features injected into local entities)

**Hijack only (Limited):**
- ✅ Hot Water (v3) and AC (v3) climate entities via cloud API
- ✅ Schedule controls, hardware devices, device settings
- ❌ No climate entities for regular heating zones

<br>

---

<br>

## Documentation

<br>

Looking for more technical details or want to contribute?

<br>

### 🎯 Features Guide

**[FEATURES.md](https://github.com/banter240/tado_hijack/blob/main/docs/FEATURES.md)** — User-friendly guide to all smart features:

- Smart Batching & Debouncing (quota savings explained)
- Auto Quota Management (weighted intervals, adaptive polling)
- Optimistic Updates (instant UI response)
- Multi-Track Polling (fast/slow/medium/away/presence)
- Bulk Operations (1 API call for all zones)
- Reset Window Detection (learns Tado's quota reset time)
- Economy Mode, Throttle Protection, Proxy Support
- Privacy & Security (automatic PII redaction)

<br>

### 🏗️ Multi-Generation Architecture

**[ARCHITECTURE.md](https://github.com/banter240/tado_hijack/blob/main/docs/ARCHITECTURE.md)** — Complete technical overview of multi-generation support:

- Unified architecture supporting Tado v3 Classic (HomeKit) and Tado X (Matter)
- Provider pattern and generation abstraction (TadoV3 vs TadoX executors)
- Generation-specific API layers (my.tado.com vs hops.tado.com)
- Duck typing strategy for data model compatibility
- Feature matrix comparing v3 Classic and Tado X implementations
- API layer architecture with mermaid diagrams

<br>

### 📐 Design & System Pipeline

**[DESIGN.md](https://github.com/banter240/tado_hijack/blob/main/docs/DESIGN.md)** — Deep dive into the integration's design:

- Complete system pipeline and execution flow
- Specialized managers (Coordinator, DataManager, ApiManager, CommandMerger, RateLimitManager, OptimisticManager)
- Auto quota calculation with weighted profiles
- State integrity mechanisms (Field Locking, Pending Commands, Rollback Context)
- Error handling and resilience patterns
- Concurrency control and thread-safety

<br>

---

<br>

## Support the Project

**Tado Hijack is developed entirely in my free time** to fight back against API restrictions and keep our smart homes running freely.

If this integration saved you from buying a Tado subscription, fixed your API headaches, or you just love the advanced features, please consider supporting the ongoing development!

<a href="https://buymeacoffee.com/banter240" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 50px !important;width: 181px !important;" ></a>

Every coffee helps to keep the motivation high, fund test hardware for new features, and fuels the late-night coding sessions required to outsmart the API limits. **Thank you! ❤️**

<br>

---

<br>

**Disclaimer:** This is an unofficial integration. Built by the community, for the community. Not affiliated with Tado GmbH. Use at your own risk.
