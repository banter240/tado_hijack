# Library Patches & Upstream Compatibility

Tado Hijack depends on the `tadoasync` library. To ensure full compatibility with Home Assistant and to fix critical bugs in the library's data handling, several runtime patches are applied.

---

## 🛠️ Applied Patches

The patches are managed in `custom_components/tado_hijack/lib/patches.py` and are applied during integration setup.

### 1. `ZoneState` Deserialization Fixes
The `tadoasync` library uses strict dataclasses for API responses. Several edge cases in Tado's API break this strictness:

- **Null `nextTimeBlock` Handling:** Tado's API occasionally returns `null` for the next schedule block instead of an empty object or a valid block. This patch ensures `nextTimeBlock` is converted to an empty dictionary to prevent deserialization crashes.
- **Hot Water Activity Rescue:** The standard library drops `activityDataPoints` during deserialization. However, this object contains the critical `hotWaterInUse` field. The patch intercepts the raw JSON and injects this data into the `heatingPower` attribute so it can be exposed as a sensor in Home Assistant.
- **Sensor Data Integrity:** Ensures `sensorDataPoints` is never `None` during processing.

### 2. Energy IQ Meter Reading Fix
The original `set_meter_readings` method in `tadoasync` was missing required URI components for the Energy IQ endpoint.
- **Patched Logic:** Rewrites the method to target `homes/{home_id}/meterReadings` specifically on the Energy IQ host, ensuring meter uploads actually reach Tado's servers.

### 3. User-Agent Compatibility
Updates the internal `VERSION` string of the library to ensure that the User-Agent header sent to Tado's servers identifies as a patched version, preventing potential blocks or compatibility flags.

---

## 🚀 Tado X (Hops API) Integration

Tado X uses a completely different communication protocol called "Hops" (`hops.tado.com`). Since `tadoasync` does not natively support Tado X, we implemented a custom shim.

### Architecture: The `TadoXApi` Bridge
Located in `lib/tadox_api.py`, this component utilizes the existing authenticated session from the Classic client but redirects requests to the Hops endpoints.

- **Data Mapping:** Room states from Hops are transformed into the `UnifiedTadoData` model.
- **Duck Typing:** Handles the shift from Classic's `.celsius` keys to Hops' `.value` keys.
- **Presence (Home/Away):** Not part of Hops. Read via classic v2 `GET /homes/{id}/state`, write via `presenceLock` - same as v3.
- **Matter Synchronization:** Optimized to work alongside Matter push updates while providing cloud-only features (Schedules, Presence Lock) that Matter cannot access.
