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

**An optimized Tado integration designed to handle strict API limits through intelligent quota management and command batching.**

V2, V3 Classic, and Tado X.

</div>

<br>

---

<br>

<div align="center">

**[🆚 Comparison](#feature-comparison)** • **[🚀 Highlights](#key-highlights)** • **[📊 API Strategy](#api-consumption-strategy)** • **[🛠️ Architecture](#architecture)**<br>**[📦 Installation](#installation)** • **[⚙️ Configuration](#configuration)** • **[📱 Entities](#entities--controls)** • **[⚡ Services](#services)**<br>**[📋 Constraints](#known-constraints)** • **[🐛 Troubleshooting](#troubleshooting)** • **[❓ FAQ](#frequently-asked-questions-faq)** • **[📚 Docs](#documentation)** • **[☕ Support](#support-the-project)**

</div>

<br>

---

<br>

## Overview

Tado Hijack is the cloud integration for a Tado account. Remove the official Home Assistant Tado integration before you add this one. Both poll the same account.

The heating climate is created in HomeKit (V3) or Matter (Tado X). The entities are on the Hijack device. Do not remove that Tado HomeKit or Matter integration, or the clone is gone. The zone is a Hijack device too: schedules, hot water, indoor climate, and the source selects. Polling and command batching follow the limit in the last `RateLimit-Policy` header.

> [!NOTE]
> **High API Usage is Expected:**
> Auto Quota dynamically consumes the available quota to provide the fastest possible updates. If the daily limit is reduced by Tado, the system will automatically slow down to prevent account locks.

<br>

### Key Features:

- **Auto API Quota:** Dynamically adjusts polling intervals based on your remaining daily API calls and detects your account's specific reset time.
- **Command Batching:** Classic zones in one window share one call. Tado X is one call per room, or one quick action when the whole heating batch matches.
- **Multi-Generation Support:** Full support for V2 (GW bridges), V3 Classic (HomeKit), and Tado X (Matter) within a unified architecture.
- **Several homes:** One account can hold more than one home, on V2, V3 Classic, and Tado X. Setup logs in, you pick one, and the next home is another add with its own login.
- **Reverse linking:** HomeKit or Matter entities are on the Hijack device. Keep the Tado HomeKit or Matter integration, or the clone is gone. [Created in HomeKit or Matter](#created-in-homekit-or-matter).
- **Indoor Climate Sensors:** Calculates dew point, absolute humidity, and mold risk per zone.
- **Offset from an external temperature:** A linked sensor is compared with the TRV and the offset is written. Off until you choose an interval. [How it runs](#offset-from-an-external-temperature).
- **External window contact:** A binary sensor per zone turns the room off and resumes the schedule afterwards. [Handler](#external-window-sensor-handler-all-generations).
- **Offline TRV recovery:** The last intent is applied again when a HomeKit or Matter climate returns. [Details](#offline-trv-recovery-homekit-and-matter).
- **Night-Savings (Economy Window):** Slows down polling during the night to save API calls for daytime use.

<br>

---

<br>

## Feature Comparison

<br>

| Feature                            | Official Tado | HomeKit (v3) |     **Tado Hijack**     |
| :--------------------------------- | :-----------: | :----------: | :---------------------: |
| **Temperature Control**            |      ✅       |      ✅      |  🔗 (HK/Matter) / ☁️ (V2 Cloud Mode)  |
| **Heating power**                  |      ❌       |      ❌      |    zone % from the poll |
| **Hot Water**                      |      ✅       |      ❌      | v3: temp. X: no temp    |
| **Smart Schedules Switch**         |      ✅       |      ❌      |       ✅ **Yes**        |
| **AC Pro (Fan/Swing)**             |      ✅       |      ❌      |    ✅ **v3 only**       |
| **Child Lock / OWD / Early**       |      ✅       |      ❌      |       ✅ **Yes**        |
| **Indoor Climate Sensors**         |      ❌       |      ❌      |  ✅ **All Gens**        |
| **Offset from external temp**      |      ❌       |      ❌      |  linked sensor, then a write |
| **External window contact**        |      ❌       |      ❌      |  off, then resume       |
| **Offline TRV recovery**           |      ❌       |      ❌      |  replay when it returns |
| **Local Control (v3)**             |      ❌       |      ✅      |  ✅ created in HomeKit  |
| **Tado X Support**                 |      ❌       |  ✅ (Matter) |  ✅ **Local + Cloud**   |
| **Multi-Generation Support**       |      ❌       |   v3 only    |   ✅ **v3 / X / v2**    |
| **Device Unification**             |      ❌       |      ❌      |  ✅ **reverse link**  |
| **Dynamic Presence-Aware Overlay** |      ❌       |      ❌      |    ✅ **Exclusive**     |
| **Auto Quota (Weighted)**          |      ❌       |     N/A      |       ✅ **Yes**        |
| **Economy Window (Night Mode)**    |      ❌       |     N/A      |       ✅ **Yes**        |
| **Command Batching**               |      ❌       |     N/A      | Classic: 1. X: per room |
| **API Quota Visibility**           |      ❌       |     N/A      |    ✅ **Real-time**     |
| **Privacy Redaction (Logs)**       |      ❌       |     N/A      |      ✅ **Strict**      |

<br>

---

<br>

## Generation Support: V2, V3 Classic & Tado X

**Quick Reference:** This integration supports V2 (GW bridges), V3 Classic (HomeKit), and Tado X (Matter).

| Feature Category              | V2 (GW) | v3 Classic | Tado X | Notes                        |
| :---------------------------- | :-----: | :--------: | :----: | :--------------------------- |
| **Temperature Control**       | ☁️ |     ✅     |   ✅   | All: Cloud mode available / V3: HomeKit / X: Matter |
| **Hot Water**                 | ✅ |     ✅     |   ✅   | v3: auto/heat/off + temp. X: auto/heat/off, no temp. `heat` is a boost |
| **AC Pro (Fan/Swing)**        | ✅ |     ✅     |   ❌   | Cloud API + climate entity   |
| **QuickActions (Bulk)**       | ✅ |     ✅     |   ✅   | boost/off/resume = 1 call    |
| **set_mode_all (Bulk)**       | ✅ |     ✅     |   ⚠️   | v3: 1. X: 1 for a full quick action, else per room |
| **Hardware Settings**         | ✅ |     ✅     |   ✅   | Child Lock, Offset, etc.     |
| **Indoor Climate Sensors**    | ✅ |     ✅     |   ✅   | Dew point, mold, absolute humidity, ventilation. Sources: [below](#zone-temperature--humidity-sources-all-generations). |
| **Offset from external temp** | ✅ |     ✅     |   ✅   | Needs a linked temperature entity. [TL;DR](#offset-from-an-external-temperature). |
| **External window contact**   | ✅ |     ✅     |   ✅   | Binary sensor on every generation. The native timeout number is classic heating. |

> Climate placement is in the [FAQ](#where-are-my-climate-entities-and-current-temperature).

<br>

---

<br>

## Key Highlights

<br>

### Extreme Batching Technology

<br>

While other integrations waste your precious API quota for every tiny interaction, Tado Hijack features **Deep Command Merging**. On classic, several actions in one window become one bulk request. The Tado X case is in the tip below.

<br>

> [!TIP]
> **Maximum Fusion Scenario (v3 Classic):**
> Triggering a "Party Scene": **AC living_room** (Temp + Fan + Swing) + **AC kitchen** (Temp + Fan) + **Hot Water** (ON) + boost all + one room 21 °C.
>
> ❌ **Standard Integrations:** 6-8 API calls (Half your hourly quota gone).
> ✅ **Tado Hijack Classic:** **1** `POST /homes/{id}/overlay` for the whole mix.
>
> _Tado X has no overlay array on Hops: house-wide boost/off/resume is 1 `quickActions/*`; mixed room setpoints are per-room `manualControl`._
>
> _Debounce window: last write per zone, then that cheapest mix._

<br>

---

<br>

### Created in HomeKit or Matter

<br>

The heating climate is created in HomeKit or in Matter.

- **V3 Classic:** pair the Tado bridge in the **HomeKit Device** integration.
- **Tado X:** pair the bridge in the **Matter** integration.
- **V2:** no local device. That home uses [Full Cloud Mode](#full-cloud-mode-all-generations).

Hijack matches the cloud serial (`VA…`) to that device. Matter matches `serial_number` or `serial_VA…`. The entities are on the Hijack device. Child lock, offset, battery, and connection are there too.

Do not remove the Tado HomeKit or Matter integration. Those Hijack entities are a clone of it. Remove that integration and the clone is gone. [Why both devices stay](#why-do-i-still-see-a-hijack-trv-and-a-homekitmatter-trv).

<br>

---

<br>

### Cloud Features (Non-HomeKit)

- **🚿 Professional Hot Water Platform:** Native `water_heater` entity. v3: `auto` / `heat` / `off` plus a target temperature. Tado X: `auto` / `heat` / `off` via `programmer/domesticHotWater`, no temperature. `heat` is a boost. A service duration or `next_block` is held locally and then returns to the previous schedule, or to off when the programmer was forced off.
- **❄️ AC Pro Features:** Precise Fan Speed and Swing (Horizontal/Vertical) selection.
- **📅 Schedule Transparency:** View the target temperature of your active Smart Schedule directly via the `auto_target_temperature` attribute while in `auto` mode (available for Heating, AC and Hot Water).
- **🕵️‍♂️ Expert-Level Error Capturing:** Captures the actual response body from Tado\'s API (e.g. _"temperature must not be null"_), giving precise feedback for troubleshooting.
- **🔥 Valve Opening Insight:** View the percentage of how far your valves are open (updated during state polls).
- **🔋 Real Battery Status:** See the actual health of every valve.
- **🌡️ Offset from an external temperature:** Compare a linked climate or sensor with the TRV and write the offset. The number on the valve still sets one by hand. [TL;DR](#offset-from-an-external-temperature).
- **🪟 External window contact:** A binary sensor per zone turns the room off while the contact is open and resumes afterwards. [Handler](#external-window-sensor-handler-all-generations).
- **🛟 Offline TRV recovery:** A HomeKit or Matter climate that was unavailable gets the last intent when it returns. [Details](#offline-trv-recovery-homekit-and-matter).
- **✨ Dazzle Mode:** Control the display behavior of your V3+ hardware.
- **🏠 Presence Lock:** Force `home` or `away` globally via the `presence_mode` select entity. Set to `auto` to hand control back to Tado's own geofencing. **Note:** Handing control back to Tado via `auto` requires a Tado **Auto-Assist** subscription. If you don't have Auto-Assist, use `home` or `away` to manually lock the presence state via your own HA automations.
- **🔥 Dynamic Presence-Aware Overlay:** Set temperatures specifically for the current presence state — automatically resets once your home presence changes.
- **🌡️ Indoor Climate Intelligence:** Dew point, mold risk, absolute humidity, and a ventilation recommendation per zone. The temperature and humidity chain is under [Configuration](#zone-temperature--humidity-sources-all-generations).
- **🔓 API Proxy:** Optional local [tado-api-proxy](https://github.com/s1adem4n/tado-api-proxy). Setup is in the note under State Integrity.

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
> 3. The proxy's own `RateLimit-Policy` is the budget. Hijack does not switch that budget to 3,000. With a proxy URL the fastest automatic poll is 120 seconds, and jitter runs only then.

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
| **Zone Poll**       | **1**  | Adaptive      | HVAC, Valve %, Humidity.                 | v3: `GET /homes/{id}/zoneStates`<br>X: `GET hops…/rooms` (+ DHW if installed)          |
| **Presence Poll**   | **1**  | 12h (Default) | Home/Away presence state.                | **Both gens:** `GET my.tado.com/api/v2/homes/{id}/state` (not Hops)                    |
| **Hardware Sync**   | **1–2+N** | 24h (Default) | Syncs battery, firmware, device list, and zone capabilities. | v3: `GET /zones` + `GET /devices` + **1 GET `/capabilities` per zone** (no bulk)<br>X: `GET hops…/roomsAndDevices` (**1**, no caps API) |
| **Refresh Zones**   | **1–2**  | On Demand     | Updates zone/device metadata.            | v3: zones + devices<br>X: `roomsAndDevices`                                            |
| **Refresh Offsets** | **1–N**  | On Demand  | Fetches device offsets. 1 call with `entity_id`, N without. | v3: `GET /devices/{s}/temperatureOffset`<br>X: usually in metadata snapshot        |
| **Refresh Away**    | **1–M**  | On Demand  | Fetches zone away temps. 1 call with `entity_id`, M without. | v3 only (`awayConfiguration`). Tado X: not available via API                     |
| **Zone Overlay**    | **1**  | On Demand     | **Fused:** all zone changes in 1 call (Classic). | **v3:** one `POST /homes/{id}/overlay` — mix heating, AC, hot water, any temps (boost all + AC + one room 21 °C = **1**). Resume-all is `DELETE /overlay` (not HW ids).<br>**X:** house-wide `quickActions/*` (**1**). Hops has no mixed-room overlay body; different room setpoints are per-room `manualControl`. |
| **Presence**        | **1**  | On Demand     | Force presence lock (home/away=PUT, auto=DELETE). | **Both gens:** `PUT/DELETE …/presenceLock` on my.tado.com (v2)                  |

_Notes:_
- **Restart** (after the first run): `GET /me` + zoneStates + presence + zones + devices. Zone capabilities (temp min/max, AC modes) are stored locally. There is **no bulk capabilities endpoint** (1 GET per zone). They refresh on the hardware-sync interval (default 24h), via `button.refresh_capabilities` / per-room `refresh_capability`, or `manual_poll` type `capabilities` / `all`. Auto Quota reserves that daily burst as `capabilities_total` (not as zone-poll cost). Classic early start stays on the switch. A GET runs only when that state is unknown, and on a full refresh.
- **Presence is always the classic v2 API** for both v3 Classic and Tado X (`/state`, `/presenceLock`). Hops `roomsAndDevices` does **not** include home/away.
- **Refresh token:** when Tado rotates it, Hijack writes the new token to the config entry immediately. A later poll writes again only if the stored value differs.
- Room/device control for Tado X uses the Hops API (`hops.tado.com`). See [Generation Support](#generation-support-v3-classic--tado-x).
- Default presence poll is 12h → **~2 calls/day**. Manual refresh / set still costs 1 call each.

<br>

> [!TIP]
> **API Optimization Features:**
>
> - **Zero Waste Writes:** Commands don't trigger a poll. We use Local State Patching to update the UI instantly without confirmation calls.
> - **Throttled Mode:** Low remaining quota slows or pauses periodic polling. The threshold and the switch are in [Configuration](#configuration).
> - **Granular Refresh:** Hardware configs (Offsets, Away Temps) are on demand only. Calibration polls an offset only when none is known.

<br>

### Auto API Quota & Economy Window

Tado Hijack features a self-optimizing quota management system that distributes your available API calls across the day.

#### Core Mechanics

- **Adaptive Polling:** Automatically calculates and adjusts the background polling interval based on your remaining daily API quota and the time left until the next reset.
- **Threshold Protection:** The Throttle Threshold (default 20) is the reserve for automations. Background polling slows once remaining calls fall under it. The interval and the off switch are in the configuration table.
- **Night-Savings (Economy Window):** Configure an Economy Window (e.g., 23:00 - 07:00) to slow down or pause polling during sleep hours. The system reinvests these saved calls into faster updates during your active hours.
- **Adaptive Reset Learning:** Tado's quota reset time varies by user. The integration learns your specific reset schedule by observing reset patterns and optimizes the budget distribution accordingly (planning at least 20 hours ahead).
- **Proxy Support:** A proxy URL keeps that proxy's own rate-limit header. The poll floor for that case is under Adaptive Behavior below.

#### Adaptive Behavior & Safety

Your polling interval scales dynamically:
- **Performance Phase:** While active, updates can arrive as fast as every 20s (or 120s if using a proxy).
- **Economy Phase:** During your sleep window, polling drops to a heartbeat or pauses completely.
- **Safety Floor:** To protect your account, minimum intervals are strictly enforced (Standard: 5s, Proxy: 120s).

<br>

---

<br>

### Batching Capability Matrix

<br>

Not all API calls are created equal. Tado Hijack optimizes everything, but physics (and the Tado API) sets limits.

<br>

| Action Type       | Examples                                                            | Strategy      | API Cost                                      |
| :---------------- | :------------------------------------------------------------------ | :------------ | :-------------------------------------------- |
| **State Control** | Target Temp, Turn Off All, Resume Schedule, Hot Water Power, AC Fan | **FUSED**     | Classic overlay: **1**. Tado X: [Services](#services) |
| **Global Mode**   | Home/Away Presence                                                  | **DIRECT**    | **1 Call**                                    |
| **Zone Config**   | Early Start, Open Window, Dazzle Mode                               | **DEBOUNCED** | **1 Call per Zone** (Sequentially executed)   |
| **Device Config** | Child Lock, Temperature Offset                                      | **DEBOUNCED** | **1 Call per Device** (Sequentially executed) |

<br>

---

<br>

## Architecture

<br>

### Physical Device Mapping & Resolution

<br>

Device entities sit on the Hijack device. The climate they follow was created in HomeKit or Matter. How that match works is in [Created in HomeKit or Matter](#created-in-homekit-or-matter).

- **EntityResolver:** Deep-scans the Home Assistant registry to link local climate entities with Tado's cloud zones.

<br>

### Robustness & Security

<br>

- **JIT Poll Planning:** Uses high-precision timestamps instead of simple flags to decide exactly when a data fetch is required (Zero-Waste).
- **Monkey-Patching Utilities:** We actively fix `tadoasync` library limitations at runtime, including robust deserialization for tricky cloud states (like `nextTimeBlock` null errors).
- **Custom Client Layer:** Extended underlying library via inheritance to handle API communication reliably and fix common deserialization errors.
- **Safety Throttle (Anti-Spam):** While the header limit is still 0, the poll interval is the status interval and at least 5 minutes. With the default 30-minute status poll, that is 30 minutes.
- **Authenticated Proxy Support:** Fully supports path-based authentication for the API Proxy, ensuring your external communication remains secure and private.
- **Persistent Reconnect & Recovery:** While throttled, periodic polls use a 15-minute interval. With Disable Polling When Throttled on, non-forced polls wait until the reset.
- **Privacy by Design:** All standard logs and diagnostic reports are automatically redacted. Sensitive data is stripped before any output is generated. (See [Expert-Level Diagnostics](#expert-level-diagnostics) for details).
- **🎭 Pattern Obfuscation:** Multi-Level Jitter (Poll & Call) breaks temporal correlation between Home Assistant triggers and API requests to avoid pattern-based throttling (Proxy only).

<br>

---

<br>

## Installation

<br>

> [!CAUTION]
> **Remove the Official Tado Integration:**
> You **MUST** remove the official Home Assistant Tado integration before installing Tado Hijack. Keeping both active will cause conflicting commands and double your API quota consumption, likely leading to account locks.

<br>

### Via HACS (Recommended)

<br>

Tado Hijack is now an **official HACS integration**! No custom repository needed.

1. Open **HACS** -> **Integrations**.
2. Search for **"Tado Hijack"** and click **Download**.
3. **Restart Home Assistant**.
4. Go to **Settings** -> **Devices & Services** -> **Add Integration** -> Search for **"Tado Hijack"**.
5. Log in at Tado. If the account has more than one home, pick one. A home that is already set up is left out of the list. Then **select the hardware generation** (the form opens on the generation that home reports):
   - **Tado v3 Classic** - If you own an **IB01** or **GW01** bridge (black square box)
   - **Tado X** - If you own a **Bridge X (IB02)** or a **Wireless Receiver X (PR04)** (newer Matter-based system)

<br>

> [!IMPORTANT]
> **Hardware Generation:**
> Select your generation during setup based on your physical bridge: IB01/GW01 = **v3 Classic**, IB02 or PR04 = **Tado X**. If unsure, choose v3 Classic (most common). See [Generation Support](#generation-support-v3-classic--tado-x) for feature differences.
>
> **Do not remove the Tado HomeKit or Matter integration.** V3 needs HomeKit Device with the Tado bridge paired. Tado X needs Matter. The Hijack entities are a clone of that device. Remove the integration and the clone is gone. A V2 gateway has no HomeKit device and uses Full Cloud Mode. Remove only the official Tado cloud integration.

<br>

> [!NOTE]
> **Several homes:** One Tado account can hold more than one home, on V2, V3 Classic, and Tado X. Setup logs in, lists the homes, and you pick one. A home already added is left out of that list. The settings after that belong to the chosen home. Add the integration again with the same account for the next home. Each entry keeps its own refresh token. A room that exists in two homes is shown with the home name in front. Two homes with the same name get separate entry titles, and that title is the prefix on entity ids. HomeKit and Matter keep the names on the devices they created. Copies on the Hijack device use Hijack names.

<br>

---

<br>

## Configuration

<br>

| Option                             | Default   | Description                                                                                                                                                                                                                                                |
| :--------------------------------- | :-------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status Polling**                 | `30m`     | Base interval for room states. **Note:** Dynamically overridden by _Auto API Quota_ when enabled; serves as fallback during throttling or budget exhaustion.                                                                                               |
| **Presence Polling**               | `12h`     | Interval for Home/Away state. High interval saves mass quota. (1 API call)                                                                                                                                                                                 |
| **Auto API Quota**                 | `80%`     | Spread this percent of the header budget across the time left until the reset. The limit is `q=` from the last response. `3000` is an unused constant. A proxy does not grant it. The night profile runs only when Reduced Polling is on. |
| **Reduced Polling Active**         | `Off`     | Enable the time-based weighted polling profile.                                                                                                                                                                                                            |
| **Reduced Polling Start**          | `22:00`   | Start time for the economy window (e.g. when you sleep).                                                                                                                                                                                                   |
| **Reduced Polling End**            | `07:00`   | End time for the economy window.                                                                                                                                                                                                                           |
| **Reduced Polling Interval**       | `3600s`   | Polling interval during the economy window. Set to **0** to pause polling entirely.                                                                                                                                                                        |
| **Hardware Sync**                  | `86400s`  | Interval for battery, firmware and device metadata. Set to 0 for initial load only.                                                                                                                                                                        |
| **Refresh weekly plans after quota reset** | `Off` | Once after each quota reset, fetch every zone plan into the calendar cache. One call per zone. Classic uses two calls until the timetable id is known. |
| **Offset Update**                  | `0` (Off) | Interval for temperature offsets. Costs 1 API call per valve. Calibration polls only when no offset is known. |
| **Flow Temperature Optimization**  | `Off`     | Tado X option. The periodic poll does not call the flow-temperature GET, so the number and switch are not created from that poll. |
| **Replay Cloud-Only On Recovery**  | `On`      | See [Offline TRV recovery](#offline-trv-recovery-homekit-and-matter). |
| **Attach to HomeKit / Matter**     | `Off`     | Puts child lock, offset, battery, and connection on the HomeKit or Matter TRV. The clone stays off while this is on. |
| **Reverse link onto Hijack**       | `On`      | The HomeKit (V3) or Matter (Tado X) entities are on the Hijack device. Do not remove that integration, or the clone is gone. |
| **Queue and delay resume schedule** | `On`    | Window close and window-timeout end. Behavior is in the window section below.                                                                                                                                                                              |
| **Resume schedule batch window**   | `120s`    | How long those cloud resumes wait so nearby rooms share one batch. `0` sends on the next pass.                                                                                                                                                             |
| **Offset threshold cooldown**      | `300` s   | After a threshold-mode offset write, wait this long before another one. A calibration that waited for an open window also waits until this cooldown has passed. |
| **Offset pause after window**      | `300` s   | Threshold mode skips the zone while its window sensor is open. A calibration on an hour interval that comes due then waits as well, and this pause runs after the window closes. |
| **Min Polling Window**             | `20s`     | **Performance Floor:** The absolute fastest speed Auto Quota will poll (5s-12h, default: 20s).                                                                                                                                                                          |
| **Debounce Time**                  | `5s`      | **Batching Window:** Fuses actions into single calls.                                                                                                                                                                                                      |
| **Refresh After Resume**           | `On`      | After a queued resume, an extra poll runs for air conditioning and classic hot water. A heating resume does not add that poll. Tado X hot water polls after the programmer call either way. |
| **Throttle Threshold**             | `20`      | Remaining under this number slows periodic polling to 15 minutes. Status becomes `throttled`. Remaining at 0 is `rate_limited`. Polling waits for the reset only when Disable Polling When Throttled is on. `0` never throttles. |
| **Quota Safety Reserve**           | `2`       | **Reset Window Bridge:** API calls reserved from quota percentage for the ±1h window around the expected reset time. Distributed evenly during the window to bridge uncertainty when reset time varies (e.g., 11:05 vs 11:30 UTC). Set to 0 to disable (not recommended). |
| **Disable Polling When Throttled** | `Off`     | Stop periodic polling entirely when throttled.                                                                                                                                                                                                             |
| **API Proxy URL**                  | `None`    | **Advanced:** URL of local `tado-api-proxy` workaround.                                                                                                                                                                                                    |
| **API Proxy Token**                | `None`    | **Security:** Authentication token for your proxy. Injected into the path (`/token/api/v2`).                                                                                                                                                               |
| **Call Jitter**                    | `Off`     | **Anti-Ban Protection:** Adds random delays before API calls to obfuscate automation patterns (Proxy only).                                                                                                                                                |
| **Jitter Strength**                | `10%`     | The percentage of random variation applied to intervals and delays (Proxy only).                                                                                                                                                                           |
| **Log Level**                      | `INFO`    | Control integration verbosity (DEBUG, INFO, WARNING, ERROR).                                                                                                                                                                                               |
| **Show Version in Logs**           | `On`      | Prepends `[vX.Y.Z]` to every log message from this integration. Makes the running version immediately visible in any log snippet — useful when sharing logs for support.                                                                                   |
| **Suppress Redundant Calls**      | `Off`     | **API Optimization:** Skip API calls when target state matches cached state (temperature, mode, presence, power). Saves quota on accidental double-clicks or UI interactions. Only sends when actual change detected. Values not in cache always send. |
| **Suppress Redundant Buttons**     | `Off`     | **Aggressive Optimization:** Also skip button actions (resume_all, boost_all, turn_off_all, set_mode_all) when ALL zones already match target state. Requires 'Suppress Redundant Calls' to be enabled. Individual explicit actions always send. |
| **Dew Point Sensor**               | `On`      | Dew point per zone from room temperature and humidity (Magnus). The source chain is in the section below. |
| **Mold Risk Sensors**              | `On`      | Create a mold risk level sensor (`none`/`low`/`medium`/`high`) and a binary moisture sensor per zone. Uses dew point spread — correctly distinguishes cold-but-dry from cold-and-humid rooms. |
| **Extended Data Fetch**            | `On`      | Fetch extended zone data (e.g. additional capabilities) during polling. Disable to reduce API payload size. |
| **Outdoor Weather Entity**         | `None`    | Select a weather entity providing outdoor temperature + humidity. When set, creates an indoor absolute humidity sensor (g/m³) and a ventilation recommendation binary sensor per zone. |
| **Ventilation Threshold**          | `1.0 g/m³`| Minimum indoor-outdoor AH difference required before _Ventilation Recommended_ turns ON. Prevents automation chatter from negligible differences. |
| **Temperature Source** _(per zone)_| `device`  | See the section below. Offset calibration runs only with a source other than `device`. |
| **Humidity Source** _(per zone)_   | `device`  | See the section below. |
| **Window Sensor** _(per zone)_    | `none`       | Optional contact sensor. Behavior is in [External Window Sensor Handler](#external-window-sensor-handler-all-generations). |
| **Window Mode** _(per zone)_       | `direct`     | `direct` or `timeout`. Same section. |

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
| **2. Connected Climate** | Full-cloud climate, or the HomeKit/Matter climate matched by serial | This integration's humidity sensor (cloud percentage) |
| **3. Cloud API** | `sensor_data_points.inside_temperature` (All Gens) | `sensor_data_points.humidity` (All Gens) |

On `device`, temperature uses the serial-matched climate. Humidity on `device` stays the cloud percentage until the humidity select points at that climate's `current_humidity`.

Changes take effect on the next coordinator update — no integration reload required.

<br>

### Offset from an external temperature

<br>

Point the zone temperature select at a climate or a temperature sensor. On `device` that select feeds dew point and mold. Calibration starts once an entity is chosen.

The reference is that entity's `current_temperature`, or its state. The raw reading is the TRV inside temperature minus the current offset. The written offset is `reference − raw`, clamped to −10…10°C, step 0.1. A gap under the spread, or under 0.1°C, is left as it is. One write per measuring device in the room. The cloud is read only when no offset is known. The offset number on the valve still sets a value by hand.

The home select starts at `off`. Clock slots are `3h` through `24h`, local time, on the hour. `threshold` watches the linked sensor, waits 5 seconds, and writes when the gap reaches the spread (home default 0.5°C). A zone number above 0 replaces that spread. `0` on the zone number clears the override. `on_reset` runs from the quota-reset detector only when the **home** select is `on_reset`, and then for every linked zone. A zone select of `inherit` uses the home choice. The home button runs the same pass immediately, including while the interval is `off`.

An open window skips the write. The pause after close and the cooldown after a threshold write are the two config rows above (both default 300 seconds). An hour slot that came due during either wait runs once both have passed. While the account is throttled, an interval run, a threshold run, and the button wait. A run from the quota reset still goes out.

<br>

### External Window Sensor Handler (All Generations)

<br>

Each zone device exposes selectors that connect external contact sensors to zone control. One zone holds up to 8 contacts. The room is open while any of them is open, and closed only when all of them are closed.

| Entity                           | Purpose                                                        | Accepted values |
| :------------------------------- | :------------------------------------------------------------- | :-------------- |
| `select.zone_window_sensor`      | Add a contact. One contact shows that sensor, and `none` unlinks it. Several contacts show `multiple` | Any `binary_sensor`, `none`, or `multiple` |
| `select.zone_window_sensor_remove` | Remove one linked contact                                    | A linked `binary_sensor`, or `none` |
| `sensor.window_contacts`         | Diagnostic list of the linked contacts                         | Entity ids, or `none` |
| `select.zone_window_mode`        | How open/close transitions are translated into zone actions   | `direct`, `timeout` |
| `number.window_open_delay`       | Wait after the room opens before the zone turns off           | Seconds, `0`–`3600`, default `0` |
| `number.window_close_delay`      | Wait after the room closes before the zone resumes            | Seconds, `0`–`3600`, default `0` |
| `switch.window_resume_schedule`  | After close, resume the schedule when it was running          | On by default. Off keeps the restored setpoint |

**Mode matrix (timer = the zone's open window detection timeout):**

| Mode                | Window opens                                      | Window closes before timer fires     | Timer fires |
| :------------------ | :------------------------------------------------ | :----------------------------------- | :---------- |
| `direct`            | Zone off                                         | Schedule resumes                     | —           |
| `timeout`           | Zone off + self-heal timer armed                | Timer cancelled, schedule resumes    | Schedule resumes (window may still be open) |

After a timer-triggered resume the cycle is complete: staying open without a new `close -> open` transition does not re-fire, so a stuck sensor cannot keep the zone off forever.

The open delay and the close delay are their own timer. `0` acts at once. They follow the room, so one contact closing while another stays open does not resume. A flip back before the wait ends cancels that wait, so no cloud call goes out. A room that is already open or already closed at startup is not delayed again. The timeout is a second timer. It starts only after the zone has actually turned off, and a close cancels it. `sensor.window_contacts` lists the linked entity ids. The same list is the `contacts` attribute. An empty list is `none`. Unlinking the last contact does not send a resume.

A linked HomeKit or Matter climate is turned off on open. While the contact stays open, that climate is turned off again if it leaves off. Close and the timeout put the stored setpoint back on that climate. When the schedule was running before the window, that resume is the same batched cloud call as a zone with no local climate. A manual setpoint from before the window stays manual. The zone switch is on by default. Off skips the resume and leaves the restored setpoint. The pre-open snapshot is kept across a restart.

A zone with no linked climate sends one cloud off, the same manual off as `hvac_mode: off` with `overlay: manual`. Direct mode has no end. Timeout mode sends that zone's open-window duration. Close and the timeout resume the schedule when it was running. With the zone switch off, the stored setpoint is sent back as a manual overlay instead. Full cloud mode always uses this path, because there is no local climate and no watcher.

**Queue and delay send of resume schedule** (default on, 120 seconds) holds those cloud resumes:

- Every zone that closes or whose timeout ends inside that window is one batch. On v3 that is one call. On Tado X it is one call per room, or one quick action when every heating room is in the batch.
- If no schedule was running, the manual setpoint is sent in that batch.
- With the option off, the cloud resume is sent as soon as the window closes or the timeout ends.

Those cloud commands go through the coordinator's command queue, so batching, redundancy suppression and optimistic patches apply. On Home Assistant start (or when a sensor is first linked), an already-open window takes effect without waiting for a transition. A window that was already open at startup and has no stored snapshot resumes on close. Each zone uses its own open window detection timeout (`zone.open_window_detection.timeout_in_seconds`); if open window detection is disabled for a zone, timeout modes behave like `direct` for that zone.

Changes take effect immediately — no integration reload required.

<br>

### Offline TRV recovery (HomeKit and Matter)

<br>

Room commands still go to the Tado cloud. If the local climate entity for a TRV is `unavailable`, Hijack keeps the last intent for that serial and applies it when the entity is back: a temperature via `climate.set_temperature`, off via `climate.set_hvac_mode` (or a low setpoint if the entity has no off mode). Resume schedule cannot be done on the local entity. With **Replay Cloud-Only On Recovery** enabled, that resume is sent to the cloud again, once per zone.

A valve that is offline during an open window is turned off locally when it returns, until the window closes or the timeout restores the stored setpoint. On the cloud path, a timed off that expires while the valve is offline resumes the schedule when it returns. Devices that return within 0.2 s share one batch. A slower reboot is several batches, not one.

The tracker reads the current entity state at mapping time and watches the entity registry, so a TRV that is already offline at startup, or whose HomeKit/Matter entity appears a bit later, is still covered.

<br>

### Full Cloud Mode (All Generations)

<br>

> [!WARNING]
> **Full Cloud Mode: When to Use It**
>
> Full Cloud Mode creates climate entities via cloud polling instead of HomeKit/Matter integration.
>
> **✅ RECOMMENDED FOR:**
> - **V2 Bridges (GW)** — no HomeKit device, so full cloud mode is how that home gets a Hijack climate
>
> **⚠️ USE WITH CAUTION:**
> - **V3 (IB01/GW01)** and **Tado X (IB02)** — the TRV climate is already HomeKit or Matter. Full cloud mode adds a Hijack heating climate whose temperature changes are cloud calls
>
> **⚠️ API QUOTA IMPACT:**
> - The budget is `q=` on the last response. This integration does not assume 100, 1,000, or 20,000
> - Help center, 27 January 2026: 100 requests/day, and 20,000 with Auto-Assist or AI Assist
> - Tado on r/tado, 26 May 2026: they maintain 1,000 requests/day and plan to reduce that further. Auto-Assist and AI Assist stay at 20,000
> - On V3 and Tado X, leave the climate created in HomeKit or Matter. Reverse linking shows it on the Hijack device. Spend the header budget on schedules, presence, hot water, and hardware settings
>
> **Configuration:**
> - Enable during setup: Config Flow → **Full Cloud Mode** toggle

<br>

---

<br>

## Entities & Controls

<br>

### Home Device

<br>

Global controls for the home. Classic links them to the Internet Bridge. Tado X keeps them on this device. Each Bridge X and Wireless Receiver X only shows its name, firmware, serial, and connection.

<br>

| Entity                                     |  Type  | Description                                                       |
| :----------------------------------------- | :----: | :---------------------------------------------------------------- |
| `select.tado_{home}_presence_mode`         | Select | Who controls presence: `home` / `away` = manual lock, `auto` = geofencing. Does not flip when geofencing changes the effective state. |
| `binary_sensor.tado_{home}_presence_state` | Binary Sensor | Effective presence. `on` = home, `off` = away. |
| `number.tado_{home}_max_flow_temperature`  | Number | Tado X OpenTherm. Not created from the periodic poll. The flow-temperature GET is not on that path. |
| `switch.tado_{home}_flow_auto_adaptation`  | Switch | Tado X OpenTherm only. Flow temperature auto adaptation. |
| `switch.tado_{home}_polling_active`        | Switch | **Master Switch:** Instantly stop/start all periodic API polls.   |
| `switch.tado_{home}_reduced_polling_logic` | Switch | **Logic Switch:** Toggle the timed "Economy" profile.             |
| `select.tado_{home}_offset_cal_interval`   | Select | When to compare the linked sensor with the TRV: a clock slot, `on_reset`, or `threshold` (keep watching). A write still needs the deviation in the row below. Off by default. Zones can override (`inherit` uses this value). Cooldown and window pause are the two config rows above. |
| `number.tado_{home}_offset_cal_spread_threshold` | Number | Default minimum delta (°C) before an offset is written. Zones can override it; `0` on the zone number clears the override. |
| `button.tado_{home}_calibrate_offsets`     | Button | Run that calibration now (same formula, same linked thermostats). Works even if the interval is `off`. 1 write per measuring device that needs a change, and a GET only when no offset is known. |
| `button.tado_{home}_resume_all_schedules`  | Button | Restore Smart Schedule across all zones (1 bulk call).            |
| `button.tado_{home}_turn_off_all_zones`    | Button | Turn off all zones instantly (1 bulk call).                       |
| `button.tado_{home}_boost_all_zones`       | Button | One bulk call. Classic overlay at 25°C. Tado X is `quickActions/boost` with no temperature in the body. |
| `button.tado_{home}_full_manual_poll`      | Button | **Expensive:** Forced sync of metadata, states, offsets, away temps, active timetable types (classic), and weekly plans (1 GET per compatible zone for each of those; no bulk timetable/plan endpoint). |
| `sensor.tado_{home}_api_limit`             | Sensor | Limit from the last `RateLimit-Policy` header. `0` until a header arrives. |
| `sensor.tado_{home}_api_remaining`         | Sensor | **API Gold:** Your remaining daily call budget.                   |
| `sensor.tado_{home}_api_status`            | Sensor | Real-time health (`connected`, `throttled`, `rate_limited`).      |
| `sensor.tado_{home}_home_mode`             | Sensor | Aggregate zone mode across all heating/AC zones: `schedule`, `manual`, `boost`, `off`, or `mixed` (zones differ). When `mixed`, attributes name the rooms: `on_schedule` is the room list still following the schedule, `off_schedule` maps each other room to `manual`, `off`, or `boost`. |
| `binary_sensor.tado_{home}_heating_demand` | Binary Sensor | **ON** if any heating zone reports heating power above 0%. Derived from polled zone data (v3 + Tado X) - not a physical thermostat relay. Handy for boiler automations. |

<br>

### Diagnostic Entities (Home)

<br>

Advanced monitoring sensors in the diagnostics of that same home device:

<br>

**Quota Reset Learning (NEW in v5.0):**
- `sensor.quota_reset_last` - Last observed reset timestamp
- `sensor.quota_reset_next` - Predicted next reset (learned pattern)
- `sensor.quota_reset_expected_window` - Learned reset window in local time (e.g., "13:30 (learned)")
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
- `binary_sensor.disable_polling_when_throttled`, `binary_sensor.refresh_after_resume`, `binary_sensor.refresh_plans_after_reset`

**System Info:**
- `sensor.outdoor_absolute_humidity` - Calculated absolute humidity (g/m³) from external weather entity
- `sensor.outdoor_weather_entity` - Configured outdoor weather entity ID
- `sensor.ventilation_ah_threshold` - Configured ventilation AH threshold (g/m³)
- `sensor.scan_interval` - Base scan interval (seconds)
- `sensor.tado_generation` - Detected hardware ("Tado X" or "Tado Classic (v3)")
- `sensor.proxy_url`, `sensor.proxy_token` - Proxy configuration status
- `sensor.log_level` - Current logging level
- `sensor.quota_safety_reserve` - Configured safety reserve calls
- `binary_sensor.full_cloud_mode` - Full Cloud Mode enabled status
- `binary_sensor.link_local_devices` - Attach to HomeKit / Matter
- `binary_sensor.proxy_local_entities` - Reverse link onto Hijack
- `binary_sensor.feature_dew_point` - Dew Point feature flag status
- `binary_sensor.feature_mold_detection` - Mold Detection feature flag status
- `binary_sensor.fetch_extended_data` - Extended data fetching status

**Manual Refresh Buttons:**
- `button.refresh_metadata` - Force hardware sync (zones/devices)
- `button.refresh_capabilities` - Refetch zone capabilities (1 GET per zone; no bulk endpoint)
- `button.refresh_offsets` - GET current offsets from Tado (not calibrate)
- `button.calibrate_offsets` - Write offsets from linked `zone_temp_source` now (GET only when no offset is known)
- `button.refresh_away` - Force away config sync
- `button.refresh_presence` - Force presence sync
- `button.refresh_all_zone_plans` - Fetch every room's weekly plan (calendar cache)

Writes share one debounce queue (default 5s). Last write per key wins. Call counts are in the [API Consumption Table](#api-consumption-table) and [Services](#services).

- A hot-water resume is its own DELETE per zone. The bulk resume covers the other zones.
- Home-all plus the same room again in that window is still one call.
- Poll types union into one coordinator refresh.
- Tado X can PATCH child lock and offset on the same device together.

<br>

### Zone Devices (Rooms / Hot Water / AC)

<br>

Cloud-only features that HomeKit does not support.

<br>

| Entity                              | Type          | Description                                                                                     |
| :---------------------------------- | :------------ | :---------------------------------------------------------------------------------------------- |
| `switch.schedule`                   | Switch        | **ON** = Smart Schedule, **OFF** = Manual. Simple way to resume schedule. **Supports heating and AC zones** (all generations). |
| `climate.ac_{room}`                 | Climate       | **v3 AC Only:** Full HVAC mode control (`cool`, `heat`, `dry`, `fan`, `auto`) with native slider. |
| `water_heater.hot_water`            | WaterHeater   | v3: target temperature. Tado X: programmer only. Modes are under [Cloud Features](#cloud-features-non-homekit). |
| `binary_sensor.hot_water_schedule`  | Binary Sensor | **Tado X:** on while the hot-water schedule is in an on block, off otherwise. |
| `binary_sensor.power`     | Binary Sensor | **HW Only:** Boiler heating status.                                                             |
| `binary_sensor.overlay`   | Binary Sensor | **HW Only:** Manual override active status.                                                     |
| `binary_sensor.connectivity` | Binary Sensor | **HW Only:** Zone connectivity based on device connections.                                  |
| `switch.early_start`                | Switch        | **v3 Only:** Toggle pre-heating before schedule block.                                          |
| `select.timetable_type`             | Select        | Active timetable: same every day, Mon-Fri/Sat/Sun, or per weekday. Writes debounce then merge (1 PUT per zone; API has no bulk). **v3 only** (heating and hot water). Tado X has no schedule mode; the week is always seven weekdays. |
| `select.timetable_type_all_zones`   | Select        | Same options for all compatible zones at once. Unknown if zones differ or nothing is cached. **v3 only.** |
| `button.refresh_timetable`          | Button        | Queue a debounced GET of the active timetable for one zone (same zone mashed = 1 call). **v3 only.** |
| `button.refresh_all_timetables`     | Button        | Queue a debounced GET for all compatible zones (coalesced with per-zone refreshes in the same window; still 1 GET per zone). **v3 only.** |
| `button.refresh_zone_plan`          | Button        | Fetch this zone's weekly plan from Tado (classic: 1 GET when the timetable type is cached, otherwise 2; Tado X room or hot water: 1 GET). Debounced; mashed button = 1 call. Does **not** run when you open the calendar. |
| `button.refresh_all_zone_plans`     | Button        | Fetch every capable zone's weekly plan (1-2 GET per zone, coalesced with per-room fetches in the same window). Includes Tado X hot water when the programmer is controllable. Cheaper than a full poll. |
| `calendar.zone_plan`                | Calendar      | Read-only week view of ON windows (`Tado <room> Weekly Plan`). Heating shows the temperature. Tado X hot water shows ON. **Cache only** - opening the calendar never hits Tado. Fetch with `refresh_zone_plan`, `refresh_all_zone_plans`, or `full_manual_poll` / `manual_poll` type `all` or `schedule`. General polling can fetch every plan once after the quota reset (default off). `set_schedule` updates the cache only after Tado accepts the write; a failed write leaves the previous plan. Not part of periodic poll. Attributes `timetable`, `day`, `blocks`, `plan` match `set_schedule`. |
| `number.open_window_timeout`        | Number        | **Config:** Open window timeout (0=OFF, 5-1439min=ON). Requires Tado subscription for detection. |
| `number.target_temperature`         | Number        | **HW & AC:** Set target temperature for hot water (manual mode) or AC zones.                                            |
| `number.away_temperature`           | Number        | **v3 Only:** Set away mode temperature.                                                         |
| `select.zone_temp_source`           | Select        | Temperature for dew point, mold, and offset calibration. Chain: [sources](#zone-temperature--humidity-sources-all-generations). |
| `button.calibrate_offset`           | Button        | **Config:** Calibrate this room's TRV offset against the linked `zone_temp_source` now. 1 write per measuring device in the room that needs a change, and a GET only when no offset is known. |
| `button.refresh_capability`         | Button        | **Config:** Refetch this zone's capabilities (1 GET; no bulk endpoint). |
| `select.zone_humidity_source`       | Select        | Humidity for those sensors. Same section. |
| `select.fan_speed`                  | Select        | **v3 AC Only:** Full fan speed control.                                                         |
| `select.vertical_swing`             | Select        | **v3 AC Only:** Vertical swing control (ON/OFF or position modes).                              |
| `select.horizontal_swing`           | Select        | **v3 AC Only:** Horizontal swing control (ON/OFF or position modes).                            |
| `sensor.zone_mode`                  | Sensor        | **Mode:** Current operating mode: `schedule`, `manual`, `boost`, `off`. Classic: boost detected via 25°C setpoint. Tado X: native boost field. Heating and AC zones only. |
| `sensor.heating_power`              | Sensor        | Zone heating power % from the room poll.                                                       |
| `sensor.humidity`                   | Sensor        | Cloud zone humidity.                                                                            |
| `sensor.dew_point`                  | Sensor        | **Climate:** Dew point (°C), Magnus, from the temperature and humidity chains above. Enabled via _Dew Point Sensor_. |
| `sensor.mold_risk_level`            | Sensor        | **Climate:** Mold risk level: `none` / `low` / `medium` / `high`. Uses dew point spread — cold-but-dry rooms correctly show `none`. Enabled via _Mold Risk Sensors_ feature flag. |
| `binary_sensor.mold_risk`           | Binary Sensor | **Climate:** `ON` when mold risk is `medium` or `high`. Ideal for automations and alerts.      |
| `sensor.indoor_absolute_humidity`   | Sensor        | **Climate:** Indoor absolute humidity (g/m³). Shown when _Outdoor Weather Entity_ is configured. |
| `binary_sensor.ventilation_recommended` | Binary Sensor | **Climate:** `ON` when indoor AH exceeds outdoor AH by ≥ threshold — opening windows reduces moisture. Shown when _Outdoor Weather Entity_ is configured. |
| `sensor.next_schedule_change`       | Sensor        | **Planning:** When the cached week next changes power or temperature. Same cache as the calendar. |
| `sensor.next_schedule_temp`         | Sensor        | **Planning:** Temperature at that change. Unknown when the next change is off or has no temperature. |
| `sensor.next_schedule_mode`         | Sensor        | **Planning:** `HEATING` or `OFF` at that change.                                                |
| `sensor.next_time_block_start`      | Sensor        | **Planning:** Start of the next block, including a block with the same setting.                 |
| `button.resume_schedule`            | Button        | Force resume schedule (stateless). **Supports heating and AC zones** (all generations).                      |
| `attribute.auto_target_temperature` | Metadata      | **Transparency:** Current schedule setpoint visible in attributes during `auto` mode (Heating, AC & HW). |

<br>

> [!NOTE]
> **Schedule Planning Sensors:**
> These four sensors read the weekly plan cache, the same blocks as the zone calendar. They refresh when the plan is fetched or written, and on a local timer at the next block start. That timer does not call Tado. An empty cache stays `unknown` until a plan fetch.

<br>

### Physical Devices (Valves/Thermostats)

<br>

Hardware-specific entities. They stay on the Hijack device. With attach on, they move onto the HomeKit or Matter TRV when the serial matches. See [Created in HomeKit or Matter](#created-in-homekit-or-matter).

<br>

| Entity                      | Type          | Description                                         |
| :-------------------------- | :------------ | :-------------------------------------------------- |
| `binary_sensor.battery_state`     | Binary Sensor | Battery health (Normal/Low).                        |
| `binary_sensor.connection_state`  | Binary Sensor | Device connectivity to Tado cloud.                  |
| `binary_sensor.bridge_connection` | Binary Sensor | **Bridge:** Cloud connectivity for the Internet Bridge or a Wireless Receiver X. |
| `switch.child_lock`         | Switch        | Toggle Child Lock on the device.                    |
| `switch.dazzle_mode`        | Switch        | **v3 Only:** Control display brightness/behavior.   |
| `number.temperature_offset` | Number        | Interactive temperature calibration (-10 to +10°C). |
| `button.identify`           | Button        | **Full Cloud Only:** Identify device (ring/check). |

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
| `tado_hijack.boost_all_zones`       | Classic: one overlay at 25°C. Tado X: one `quickActions/boost`, no temperature in the body.                                  | **1 call** (bulk)    | **1 call** (bulk)    |
| `tado_hijack.resume_all_schedules`  | Restore Smart Schedule across all zones.                                                                                     | **1 call** (bulk)    | **1 call** (bulk)    |
| `tado_hijack.set_mode`              | Set mode, temperature, and termination. Supports `hvac_mode` (auto, heat, off) and `overlay` (manual, next_block, presence). | **1 call** (one debounce window) | **1** `quickActions` when the batch is every heating zone on the same boost, off, or resume; otherwise **1** `manualControl` per room |
| `tado_hijack.set_mode_all_zones`    | Targets all HEATING and/or AC zones at once using `hvac_mode`.                                                               | **1 call** (bulk overlay) | **1** if every room matches a quickAction; else **N** `manualControl` |
| `tado_hijack.set_water_heater_mode` | Set `operation_mode` and temperature for hot water. Tado X `duration` and `next_block` are held locally, then return to the schedule, or to off when the programmer was forced off. | **1 call** (v3)      | **1**, plus a boost refresh every 50 min while a long ON hold is active |
| `tado_hijack.add_meter_reading`     | Upload a meter reading (integer) to Tado Energy IQ. Optional `date` backfills a historic reading; defaults to today.         | **1 call**           | **1 call**           |
| `tado_hijack.set_schedule`          | Write Smart Schedule time blocks (`blocks` or a `schedule` helper). Classic: `one_day` has no day picker, `three_day` = Mon-Fri/Sat/Sun, `seven_day` = any weekdays. Tado X is always per weekday, including hot water (`power` ON or OFF, no temperature, one PUT per day). `all_days` writes the same blocks to Monday-Sunday (7 calls). `days` writes the named weekdays. `one_day`, `three_day`, and `activate` are classic. | **1-7** | **1-7** |
| `tado_hijack.manual_poll`           | Force immediate data refresh. Use `refresh_type` to control scope. Add `entity_id` for a targeted single-entity fetch (saves quota). | **1-N** (depends)    | **1-N** (depends)    |

<br>

> [!TIP]
> **Post-action polling (`refresh_after`):**
>
> - A queued resume polls again only for air conditioning and classic hot water. A heating resume does not add that poll.
> - A classic `duration` waits until the timer ends. `next_block` and `presence` do not poll early.
> - Tado X hot water does not use the flag. Resume, boost, and off each poll after the programmer call. A duration hold sends at once, so that poll runs at once, again on the 50-minute boost, and again when the hold ends.

<br>

> [!TIP]
> **Targeting Rooms:** You can use **any** Tado zone entity (climate, switch, sensor) or even **device entities** (battery, connection, child_lock) as the `entity_id`. Device entities automatically resolve to their zone via serial number lookup. This includes the climate created in **HomeKit or Matter** (e.g. `climate.living_room`). The reverse-linked copy forwards to that climate.
>
> **Targeted Fetch:** When using `manual_poll` with an `entity_id`, the refresh is limited to that single entity — `offsets` costs 1 API call instead of N, `away` / `timetable` / `schedule` cost 1 instead of M. `capabilities` uses the persisted cache and only drops that zone's entry. Bulk types (`zone`, `metadata`, `presence`, `all`) always fall back to a full refresh. `all` (and `button.full_manual_poll`) also fetches active timetable types (classic only) and weekly plans (classic: 1 GET per zone when the timetable type is cached, otherwise 2; Tado X: 1 GET per room). Type `schedule` fetches only weekly plans. Type `timetable` is a no-op on Tado X.

<br>

> [!TIP]
> **Multi-Home Service Routing:**
> A service call with no home and no entity runs on every configured home.
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

**Quick bathroom Heat (15 Min at 24°C):**

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

### `set_schedule` Examples (YAML)

Tuesday and Wednesday (seven_day only):

```yaml
service: tado_hijack.set_schedule
data:
  entity_id: climate.living_room
  all_days: false
  days:
    - tuesday
    - wednesday
  timetable: seven_day
  activate: true
  blocks:
    - {start: "00:00", end: "06:30", temperature: 16}
    - {start: "06:30", end: "22:00", temperature: 21}
    - {start: "22:00", end: "00:00", temperature: 16}
```

On Tado X omit `timetable` and `activate`. `all_days: true` copies the blocks onto Monday through Sunday. One weekday is `days: [tuesday]`. `one_day` and `three_day` are rejected.

Same plan every day (`one_day` has no day picker; do not pass `days`. Classic only):

```yaml
service: tado_hijack.set_schedule
data:
  entity_id: climate.living_room
  timetable: one_day
  activate: true
  blocks:
    - {start: "00:00", end: "07:00", temperature: 16}
    - {start: "07:00", end: "22:00", temperature: 21}
    - {start: "22:00", end: "00:00", temperature: 16}
```

Copy today's plan from the zone calendar (fetch the plan first with the room button or `refresh_all_zone_plans`):

```yaml
service: tado_hijack.set_schedule
data:
  entity_id: calendar.tado_home_1_zone_plan
  timetable: "{{ state_attr('calendar.tado_home_1_zone_plan', 'timetable') }}"
  days:
    - "{{ state_attr('calendar.tado_home_1_zone_plan', 'day') }}"
  blocks: "{{ state_attr('calendar.tado_home_1_zone_plan', 'blocks') }}"
```

`plan` is the same blocks keyed by day (`monday`, `monday_to_friday`, ...). Event description in the calendar UI is that day's JSON.

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

- **No Bulk Device Config:** Temperature offsets, child lock, and window detection are one call per device. Ten devices are ten calls.
- **Schedule target is cloud-side:** After Resume Schedule, the setpoint is the one Tado's schedule returns. When an extra poll runs is in the post-action tip under [Services](#services).
- **Sequential Execution:** Device configuration commands run one after another, with a small delay.

<br>

### Hybrid Cloud Dependency

<br>

The climate created in HomeKit or Matter still changes temperature when the Tado cloud is unreachable. The copy on the Hijack device follows it. Schedules, hot water, and classic air conditioning need the cloud.

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

The heating climate is on the Hijack device. It was created in HomeKit (V3) or Matter (Tado X). Do not remove that integration, or the clone is gone. Classic air conditioning is always a Hijack climate. Full cloud mode adds a Hijack heating climate, and a V2 gateway needs that mode.

See [Full Cloud Mode](#full-cloud-mode-all-generations).

<br>

### Why do I still see a Hijack TRV and a HomeKit/Matter TRV?

The entities are on the Hijack device. HomeKit or Matter is the Tado device they were cloned from.

**Do not remove the Tado HomeKit or Matter integration.** Remove it and the clone is gone.

Zone-level entities (schedules, indoor climate, source selectors) stay on the Hijack zone device.

<br>

### Why are my Tado X dew point / mold risk sensors unavailable?

They need a temperature and a humidity. The chain is in [Zone Temperature & Humidity Sources](#zone-temperature--humidity-sources-all-generations).

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
- Auto quota from the rate-limit header. The weighted interval runs when the economy window is on
- Optimistic Updates (instant UI response)
- Multi-Track Polling (fast/slow/medium/away/presence)
- Bulk operations (classic overlay is one call; Tado X quick actions are one call)
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
- Specialized managers (Coordinator, DataManager, ApiManager, CommandMerger, RateLimitManager, OptimisticManager, PropertyManager)
- Auto quota calculation with weighted profiles
- State integrity mechanisms (Field Locking, Pending Commands, Rollback Context)
- Error handling and resilience patterns
- Concurrency control and thread-safety

<br>

### 🚀 Compatibility & Tado X

**[COMPATIBILITY.md](https://github.com/banter240/tado_hijack/blob/main/docs/COMPATIBILITY.md)** — Library patches and Tado X integration details:

- Runtime patches for `tadoasync` library bugs
- Fixes for ZoneState deserialization, Energy IQ URI, and User-Agent compatibility. Quota is conserved by batching and adaptive polling
- Architecture of the Tado X (Hops API) bridge
- Duck typing for multi-generation data model support
- Integration strategy for Matter alongside Cloud features

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
