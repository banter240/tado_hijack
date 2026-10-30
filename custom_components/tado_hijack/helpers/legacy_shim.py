"""Compatibility shim for Home Assistant < 2026.11.

Home Assistant 2026.11 renamed the climate and water heater temperature
properties to their native_ equivalents. This mixin keeps the integration
loadable on older versions: when the base class has no
``native_temperature_unit``, it defines the legacy properties forwarding to
the native_* implementations. On 2026.11+ the block is skipped entirely, so
no deprecated members are defined and no deprecation warnings are logged.

List these mixins before ``ClimateEntity`` or ``WaterHeaterEntity``. On older
cores those bases still own the legacy properties, and a mixin later in the
MRO never overrides them.

``NativeLegacyRangeMixin`` is only for a class that implements
``native_target_temperature_high`` and ``native_target_temperature_low``.
Water heater state always reads both bounds, and the stock properties already
return the legacy attr.

Forwarding through ``self.native_*`` preserves subclass overrides such as
``TadoHotWaterX.native_target_temperature``.

TODO(shim): remove when min_homeassistant_version >= 2026.11 (the legacy
API is dropped in Home Assistant 2027.11).
"""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity

# Climate and water heater entities were renamed together in 2026.11, so a
# single feature probe covers both base classes.
_HAS_NATIVE_TEMPERATURE_API = hasattr(ClimateEntity, "native_temperature_unit")


class NativeLegacyShimMixin:
    """Expose the legacy temperature API on Home Assistant < 2026.11."""

    if not _HAS_NATIVE_TEMPERATURE_API:
        native_temperature_unit = property(
            lambda self: self._attr_native_temperature_unit
        )
        temperature_unit = property(lambda self: self.native_temperature_unit)
        current_temperature = property(lambda self: self.native_current_temperature)
        target_temperature = property(lambda self: self.native_target_temperature)


class NativeLegacyRangeMixin:
    """Forward the legacy high and low bounds on Home Assistant < 2026.11."""

    if not _HAS_NATIVE_TEMPERATURE_API:
        target_temperature_high = property(
            lambda self: self.native_target_temperature_high
        )
        target_temperature_low = property(
            lambda self: self.native_target_temperature_low
        )
