"""Closed-form microstrip / stripline helpers for quick Z0 preview."""

from __future__ import annotations

import math

from si_prelayout.domain.topology import TraceRef

C0 = 299_792_458.0


def microstrip_z0(width_m: float, height_m: float, er: float) -> float:
    """IPC-2141 / Hammerstad-style microstrip Z0 (ohms)."""
    w_h = width_m / height_m
    er_eff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / w_h)
    if w_h <= 1:
        z0 = (60 / math.sqrt(er_eff)) * math.log(8 / w_h + w_h / 4)
    else:
        z0 = (120 * math.pi) / (
            math.sqrt(er_eff) * (w_h + 1.393 + 0.667 * math.log(w_h + 1.444))
        )
    return z0


def stripline_z0(width_m: float, height_m: float, er: float) -> float:
    """Symmetric stripline Z0 (ohms). height_m = full dielectric between planes."""
    b = height_m
    we = width_m
    # Simplified Wheeler
    x = we / b
    z0 = (60 / math.sqrt(er)) * math.log(4 / (math.pi * x * (0.8 + x)))
    return max(z0, 1.0)


def resolve_trace(ref: TraceRef) -> tuple[float, float]:
    """Return (Z0 ohms, delay s/m)."""
    if ref.z0_ohm is not None:
        v = ref.velocity_factor * C0
        return ref.z0_ohm, 1.0 / v

    if ref.width_m is None or ref.height_m is None:
        raise ValueError(
            f"Trace '{ref.name}' needs z0_ohm or both width_m and height_m"
        )

    if ref.style == "microstrip":
        z0 = microstrip_z0(ref.width_m, ref.height_m, ref.er)
        # effective er approx for delay
        w_h = ref.width_m / ref.height_m
        er_eff = (ref.er + 1) / 2 + (ref.er - 1) / 2 / math.sqrt(1 + 12 / w_h)
        v = C0 / math.sqrt(er_eff)
    else:
        z0 = stripline_z0(ref.width_m, ref.height_m, ref.er)
        v = C0 / math.sqrt(ref.er)

    return z0, 1.0 / v
