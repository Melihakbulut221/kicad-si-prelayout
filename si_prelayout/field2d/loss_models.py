"""Causal dielectric (Djordjevic–Sarkar) and skin-effect helpers."""

from __future__ import annotations

import cmath
import math

import numpy as np

EPS0 = 8.854187817e-12
MU0 = 4e-7 * math.pi
C0 = 299_792_458.0


def djordjevic_sarkar_er(
    f_hz: float | np.ndarray,
    er_inf: float,
    delta_er: float,
    f1_hz: float = 1e9,
    f2_hz: float = 1e12,
) -> np.ndarray:
    """Wideband causal dielectric model → complex εr(f).

    er(f) = er_inf + Δer/m * ln((f2 + j f)/(f1 + j f)) / ln(f2/f1)
    with m = ln(10)/ln(f2/f1) variant commonly used; here we use the
    logarithmic form that yields roughly constant tand over decades.
    """
    f = np.asarray(f_hz, dtype=float)
    j = 1j
    m = math.log(f2_hz / f1_hz)
    er = er_inf + (delta_er / m) * np.log((f2_hz + j * f) / (f1_hz + j * f))
    return er


def tand_from_er(er_complex: np.ndarray) -> np.ndarray:
    return -np.imag(er_complex) / np.maximum(np.real(er_complex), 1e-12)


def skin_resistance(
    f_hz: float | np.ndarray,
    r_dc_ohm_per_m: float,
    r_skin_ohm_per_m_per_sqrt_hz: float,
) -> np.ndarray:
    """R(f) ≈ Rdc + Rskin * sqrt(f)."""
    f = np.asarray(f_hz, dtype=float)
    return r_dc_ohm_per_m + r_skin_ohm_per_m_per_sqrt_hz * np.sqrt(np.maximum(f, 0.0))


def rlgc_per_meter(
    f_hz: float,
    z0: float,
    vf: float,
    r_dc: float = 0.0,
    r_skin: float = 0.0,
    er: float = 4.2,
    tand: float = 0.02,
    use_ds: bool = True,
) -> tuple[complex, complex, complex, complex]:
    """Approximate per-meter RLGC at one frequency for a SE line."""
    v = vf * C0
    # Lossless baseline: L = Z0/v, C = 1/(Z0*v)
    l = z0 / v
    c = 1.0 / (z0 * v)
    r = float(skin_resistance(f_hz, r_dc, r_skin))
    if use_ds and f_hz > 0:
        # Map tand @ f into G = ω C tand
        er_c = djordjevic_sarkar_er(f_hz, er_inf=er * 0.95, delta_er=er * 0.1)
        tand_f = float(tand_from_er(er_c))
    else:
        tand_f = tand
    g = 2 * math.pi * f_hz * c * tand_f
    return complex(r), complex(l), complex(g), complex(c)


def propagation_constant(
    r: complex, l: complex, g: complex, c: complex, f_hz: float
) -> complex:
    w = 2 * math.pi * f_hz
    return cmath.sqrt((r + 1j * w * l) * (g + 1j * w * c))


def attenuation_neper_per_m(
    z0: float,
    vf: float,
    f_hz: float,
    r_dc: float = 10.0,
    r_skin: float = 1e-4,
    er: float = 4.2,
    tand: float = 0.02,
) -> float:
    r, l, g, c = rlgc_per_meter(f_hz, z0, vf, r_dc, r_skin, er, tand)
    gamma = propagation_constant(r, l, g, c, f_hz)
    return float(gamma.real)
