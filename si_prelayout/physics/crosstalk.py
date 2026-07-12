"""Coupled-line NEXT/FEXT estimates (closed-form, pre-layout spacing rules)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CrosstalkEstimate:
    next_v_ratio: float
    fext_v_ratio: float
    next_mv_per_v: float
    fext_mv_per_v: float
    notes: str


def estimate_microstrip_crosstalk(
    aggressor_edge_v: float,
    length_m: float,
    spacing_m: float,
    height_m: float,
    tr_s: float,
    er: float = 4.2,
    vf: float = 0.66,
) -> CrosstalkEstimate:
    """Rule-of-thumb microstrip NEXT/FEXT (IPC / classic SI heuristics).

    Not a substitute for multi-conductor MoM. Useful for spacing what-if.
    """
    if spacing_m <= 0 or height_m <= 0 or tr_s <= 0:
        raise ValueError("spacing, height, and edge rate must be positive")

    # Backward crosstalk coefficient ~ 1/(1+(s/h)^2) style
    s_h = spacing_m / height_m
    kb = 1.0 / (1.0 + s_h**2) * 0.5  # scaled heuristic
    # Forward crosstalk grows with length / edge rate
    c0 = 299_792_458.0
    td = length_m / (vf * c0)
    kf = 0.5 * kb * (2 * td / tr_s)  # rough FEXT factor
    kf = min(kf, 0.5)

    next_ratio = min(kb, 0.5)
    fext_ratio = min(kf, 0.5)
    return CrosstalkEstimate(
        next_v_ratio=next_ratio,
        fext_v_ratio=fext_ratio,
        next_mv_per_v=next_ratio * 1000.0,
        fext_mv_per_v=fext_ratio * 1000.0,
        notes=(
            f"s/h={s_h:.2f}, td={td*1e12:.1f}ps, tr={tr_s*1e12:.1f}ps; "
            "closed-form heuristic only"
        ),
    )


def next_peak_voltage(estimate: CrosstalkEstimate, aggressor_swing_v: float) -> float:
    return estimate.next_v_ratio * aggressor_swing_v
