"""Frequency-domain TL response + simple vector-fit style rational fit.

Full Gustavsen VF with passivity enforcement is roadmap work. This module
builds S21/ABCD samples from RLGC and fits a stable real-pole model that can
drive recursive convolution later.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from si_prelayout.field2d.loss_models import rlgc_per_meter


@dataclass
class RationalFit:
    """H(s) ≈ sum r_k / (s - p_k) + d  (real poles)."""

    poles: np.ndarray
    residues: np.ndarray
    d: float
    f_hz: np.ndarray
    h_samples: np.ndarray
    h_fit: np.ndarray
    rmse: float


def tline_s21(
    f_hz: np.ndarray,
    length_m: float,
    z0: float,
    vf: float,
    r_dc: float = 5.0,
    r_skin: float = 5e-5,
    er: float = 4.2,
    tand: float = 0.02,
) -> np.ndarray:
    """Approx matched-line S21 = exp(-γ ℓ)."""
    out = np.zeros(len(f_hz), dtype=complex)
    for i, f in enumerate(f_hz):
        if f <= 0:
            out[i] = 1.0 + 0j
            continue
        r, l, g, c = rlgc_per_meter(f, z0, vf, r_dc, r_skin, er, tand)
        w = 2 * np.pi * f
        gamma = np.sqrt((r + 1j * w * l) * (g + 1j * w * c))
        out[i] = np.exp(-gamma * length_m)
    return out


def fit_real_poles(
    f_hz: np.ndarray,
    h: np.ndarray,
    n_poles: int = 6,
) -> RationalFit:
    """Fit magnitude/phase samples with a real-pole rational model via Prony-ish LS.

    Uses frequency-domain least squares on basis 1/(jω - p) with candidate
    poles placed on the negative real axis (stable).
    """
    f = np.asarray(f_hz, dtype=float)
    h = np.asarray(h, dtype=complex)
    w = 2 * np.pi * f
    # Candidate poles: log-spaced on negative real axis
    p_cands = -np.logspace(6, 11, n_poles)  # -1e6 … -1e11 rad/s-ish
    # Design matrix for complex LS: [1/(jw-p)] + constant
    a = np.zeros((len(f), n_poles + 1), dtype=complex)
    for k, p in enumerate(p_cands):
        a[:, k] = 1.0 / (1j * w - p)
    a[:, -1] = 1.0
    # Solve min ||A x - H|| ; use real/imag stacked
    a_r = np.vstack([a.real, a.imag])
    h_r = np.concatenate([h.real, h.imag])
    x, *_ = np.linalg.lstsq(a_r, h_r, rcond=None)
    residues = x[:-1]
    d = float(x[-1])
    h_fit = a @ x
    rmse = float(np.sqrt(np.mean(np.abs(h - h_fit) ** 2)))
    return RationalFit(
        poles=p_cands,
        residues=residues.astype(float),
        d=d,
        f_hz=f,
        h_samples=h,
        h_fit=h_fit,
        rmse=rmse,
    )


def recursive_convolution_step(
    x_hist: list[float],
    state: np.ndarray,
    poles: np.ndarray,
    residues: np.ndarray,
    d: float,
    dt: float,
    x_now: float,
) -> tuple[float, np.ndarray]:
    """One step of recursive convolution for real-pole H(s).

    y[n] = d*x[n] + sum state updates.
    α_k = exp(p_k * dt),  state' = α*state + r*(α-1)/p * x  (trapezoidal-ish).
    """
    y = d * x_now
    new_state = np.zeros_like(state)
    for k, (p, r) in enumerate(zip(poles, residues)):
        alpha = float(np.exp(p * dt))
        # Input coefficient for zero-order hold
        if abs(p) < 1e-30:
            beta = r * dt
        else:
            beta = r * (alpha - 1.0) / p
        new_state[k] = alpha * state[k] + beta * x_now
        y += new_state[k]
    return float(y), new_state
