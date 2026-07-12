"""JSON report + timing / edge metrics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from si_prelayout.domain.results import SimulationResult, Waveform
from si_prelayout.domain.topology import Project


def edge_timing(wf: Waveform, v_lo: float, v_hi: float) -> dict:
    """Measure delay to mid, 20–80 rise/fall on first edges."""
    t, v = wf.t_s, wf.v_v
    mid = 0.5 * (v_lo + v_hi)
    v20 = v_lo + 0.2 * (v_hi - v_lo)
    v80 = v_lo + 0.8 * (v_hi - v_lo)

    def first_cross(level: float, rising: bool) -> float | None:
        for i in range(1, len(v)):
            if rising and v[i - 1] < level <= v[i]:
                frac = (level - v[i - 1]) / max(v[i] - v[i - 1], 1e-18)
                return float(t[i - 1] + frac * (t[i] - t[i - 1]))
            if (not rising) and v[i - 1] > level >= v[i]:
                frac = (v[i - 1] - level) / max(v[i - 1] - v[i], 1e-18)
                return float(t[i - 1] + frac * (t[i] - t[i - 1]))
        return None

    t_mid_r = first_cross(mid, True)
    t20 = first_cross(v20, True)
    t80 = first_cross(v80, True)
    t_mid_f = first_cross(mid, False)
    rise = (t80 - t20) if (t20 is not None and t80 is not None) else None
    return {
        "t_mid_rise_s": t_mid_r,
        "t_mid_fall_s": t_mid_f,
        "rise_20_80_s": rise,
        "v_min": float(np.min(v)),
        "v_max": float(np.max(v)),
    }


def result_to_dict(
    project: Project, result: SimulationResult, v_lo: float = 0.0, v_hi: float = 3.3
) -> dict:
    probes = []
    for wf in result.waveforms:
        probes.append(
            {
                "name": wf.name,
                "timing": edge_timing(wf, v_lo, v_hi),
                "n_samples": int(len(wf.t_s)),
            }
        )
    return {
        "project": project.name,
        "description": project.description,
        "meta": result.meta,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "value": c.value,
                "limit": c.limit,
                "message": c.message,
            }
            for c in result.checks
        ],
        "probes": probes,
    }


def write_json_report(
    project: Project,
    result: SimulationResult,
    path: str | Path,
    v_lo: float = 0.0,
    v_hi: float = 3.3,
) -> None:
    payload = result_to_dict(project, result, v_lo=v_lo, v_hi=v_hi)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
