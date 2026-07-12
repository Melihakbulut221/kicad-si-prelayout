"""Lossless transmission line — method of characteristics (Bergeron)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class LosslessLine:
    """Two-port lossless TL history for MoC companion model."""

    z0: float
    td_s: float
    dt_s: float
    _hist_a: list[float] = field(default_factory=list)  # voltage wave toward a
    _hist_b: list[float] = field(default_factory=list)
    _delay_steps: int = 0

    def __post_init__(self) -> None:
        self._delay_steps = max(1, int(round(self.td_s / self.dt_s)))
        # Initialize history to 0 V waves
        self._hist_a = [0.0] * (self._delay_steps + 2)
        self._hist_b = [0.0] * (self._delay_steps + 2)
        self._k = 0

    def companion_sources(self) -> tuple[float, float]:
        """Return (E_a, E_b) Thevenin open-circuit voltages seen at each end.

        At end a: V_a = E_a - Z0 * I_a_into_line
        At end b: V_b = E_b - Z0 * I_b_into_line
        where E comes from the delayed reflected wave of the far end.
        """
        d = self._delay_steps
        k = self._k
        # Wave that left b at k-d arrives at a
        e_a = self._hist_b[k - d] if k >= d else 0.0
        e_b = self._hist_a[k - d] if k >= d else 0.0
        return e_a, e_b

    def commit(self, v_a: float, i_a_into: float, v_b: float, i_b_into: float) -> None:
        """Store outgoing characteristic waves after a time step is solved."""
        # Outgoing from a toward b: V + Z0*I (I into line at a)
        wave_ab = v_a + self.z0 * i_a_into
        wave_ba = v_b + self.z0 * i_b_into
        self._k += 1
        if self._k >= len(self._hist_a):
            self._hist_a.append(0.0)
            self._hist_b.append(0.0)
        self._hist_a[self._k] = wave_ab
        self._hist_b[self._k] = wave_ba


def delay_seconds(length_m: float, delay_per_m: float) -> float:
    return length_m * delay_per_m
