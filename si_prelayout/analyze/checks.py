"""SI waveform checks for pre-layout review."""

from __future__ import annotations

import numpy as np

from si_prelayout.domain.results import SiCheckResult, Waveform


def check_overshoot(
    wf: Waveform, v_high: float = 3.3, limit_v: float = 0.3
) -> SiCheckResult:
    peak = float(np.max(wf.v_v))
    overshoot = peak - v_high
    return SiCheckResult(
        name="overshoot",
        passed=overshoot <= limit_v + 1e-12,
        value=overshoot,
        limit=limit_v,
        message=f"Peak {peak:.3f} V → overshoot {overshoot:.3f} V (limit {limit_v} V)",
    )


def check_undershoot(
    wf: Waveform, v_low: float = 0.0, limit_v: float = 0.3
) -> SiCheckResult:
    valley = float(np.min(wf.v_v))
    undershoot = v_low - valley
    return SiCheckResult(
        name="undershoot",
        passed=undershoot <= limit_v + 1e-12,
        value=undershoot,
        limit=limit_v,
        message=f"Min {valley:.3f} V → undershoot {undershoot:.3f} V (limit {limit_v} V)",
    )


def check_monotonicity(wf: Waveform, edge: str = "rise") -> SiCheckResult:
    """Count direction reversals on the dominant edge (simple MVP metric)."""
    v = wf.v_v
    dv = np.diff(v)
    # Focus on region where signal is transitioning mid-swing
    mid = 0.5 * (float(np.max(v)) + float(np.min(v)))
    span = float(np.max(v) - np.min(v)) + 1e-15
    in_band = (v[:-1] > mid - 0.2 * span) & (v[:-1] < mid + 0.2 * span)
    if not np.any(in_band):
        return SiCheckResult(
            name="monotonicity",
            passed=True,
            value=0.0,
            limit=0.0,
            message="No mid-swing samples; skipped",
        )
    signs = np.sign(dv[in_band])
    signs = signs[signs != 0]
    reversals = float(np.sum(signs[1:] * signs[:-1] < 0)) if len(signs) > 1 else 0.0
    return SiCheckResult(
        name="monotonicity",
        passed=reversals == 0,
        value=reversals,
        limit=0.0,
        message=f"Mid-swing slope reversals: {int(reversals)}",
    )


def run_checks(
    waveforms: list[Waveform],
    names: list[str],
    v_high: float = 3.3,
    v_low: float = 0.0,
) -> list[SiCheckResult]:
    if not waveforms:
        return []
    # Prefer receiver probe if present
    wf = next((w for w in waveforms if w.name.endswith(".in")), waveforms[-1])
    out: list[SiCheckResult] = []
    for name in names:
        if name == "overshoot":
            out.append(check_overshoot(wf, v_high=v_high))
        elif name == "undershoot":
            out.append(check_undershoot(wf, v_low=v_low))
        elif name == "monotonicity":
            out.append(check_monotonicity(wf))
    return out
