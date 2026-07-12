"""Differential pair closed-form impedance helpers."""

from __future__ import annotations

import math

from si_prelayout.field2d.closed_form import microstrip_z0


def microstrip_zdiff(
    width_m: float,
    height_m: float,
    gap_m: float,
    er: float,
) -> tuple[float, float, float]:
    """Estimate odd/even / Zdiff for edge-coupled microstrip (heuristic).

    Returns (Zodd, Zeven, Zdiff≈2*Zodd).
    Based on classic coupled-microstrip approximations (Wadell-style).
    """
    if min(width_m, height_m, gap_m) <= 0:
        raise ValueError("width, height, gap must be positive")
    z0 = microstrip_z0(width_m, height_m, er)
    # Coupling factor decreases with s/h
    s_h = gap_m / height_m
    k = 1.0 / (1.0 + s_h**1.5)
    # Split single-ended toward odd/even
    zodd = z0 * math.sqrt((1 - 0.7 * k) / (1 + 0.7 * k))
    zeven = z0 * math.sqrt((1 + 0.7 * k) / (1 - 0.7 * k))
    zdiff = 2.0 * zodd
    return zodd, zeven, zdiff


def length_budget_m(
    skew_ps: float,
    vf: float = 0.66,
) -> float:
    """Max length mismatch for a given skew budget."""
    c0 = 299_792_458.0
    v = vf * c0
    return (skew_ps * 1e-12) * v
