"""Simulation result types."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Waveform:
    name: str
    t_s: np.ndarray
    v_v: np.ndarray


@dataclass
class SiCheckResult:
    name: str
    passed: bool
    value: float
    limit: float
    message: str


@dataclass
class SimulationResult:
    waveforms: list[Waveform] = field(default_factory=list)
    checks: list[SiCheckResult] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def waveform_dict(self) -> dict[str, Waveform]:
        return {w.name: w for w in self.waveforms}
