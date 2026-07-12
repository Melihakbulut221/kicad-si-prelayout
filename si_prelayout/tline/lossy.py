"""Lossy transmission line — cascaded RL sections + lossless MoC delays."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from si_prelayout.field2d.loss_models import attenuation_neper_per_m
from si_prelayout.tline.lossless import LosslessLine


@dataclass
class LossyLine:
    """Approximate lossy SE line: N lossless delay lumps with series R.

    Edge-rate frequency fe ≈ 0.35/tr sets R_series from α(fe)*Z0 scaling.
    Good enough for educational what-if; not a substitute for VF macromodels.
    """

    z0: float
    td_s: float
    dt_s: float
    length_m: float
    r_total_ohm: float
    n_sections: int = 4
    _sections: list[LosslessLine] = field(default_factory=list)
    _r_each: float = 0.0

    def __post_init__(self) -> None:
        n = max(1, self.n_sections)
        self._r_each = self.r_total_ohm / n
        td_each = self.td_s / n
        self._sections = [
            LosslessLine(z0=self.z0, td_s=td_each, dt_s=self.dt_s) for _ in range(n)
        ]
        # Internal node voltages between sections (length n-1); ends are external
        self._v_int = np.zeros(max(0, n - 1))
        self.n_sections = n

    @classmethod
    def from_params(
        cls,
        z0: float,
        td_s: float,
        dt_s: float,
        length_m: float,
        vf: float,
        edge_s: float = 0.2e-9,
        r_dc_per_m: float = 5.0,
        r_skin: float = 5e-5,
        er: float = 4.2,
        tand: float = 0.02,
        n_sections: int = 4,
    ) -> LossyLine:
        fe = 0.35 / max(edge_s, 1e-15)
        alpha = attenuation_neper_per_m(
            z0, vf, fe, r_dc_per_m, r_skin, er, tand
        )
        # Series resistance approx: 2 α Z0 * length (first-order)
        r_total = max(0.0, 2.0 * alpha * z0 * length_m)
        # Also include DC floor
        r_total = max(r_total, r_dc_per_m * length_m)
        return cls(
            z0=z0,
            td_s=td_s,
            dt_s=dt_s,
            length_m=length_m,
            r_total_ohm=r_total,
            n_sections=n_sections,
        )

    def companion_sources(self) -> tuple[float, float]:
        """Thevenin waves at external ports (first and last section)."""
        e_a, _ = self._sections[0].companion_sources()
        _, e_b = self._sections[-1].companion_sources()
        return e_a, e_b

    def stamp_extra_r(self) -> float:
        """Effective series R seen outside when using single-section stamp.

        For multi-section we stamp ends only with Z0 and fold R into commit
        via voltage drops on internal solves — see solver integration.
        """
        return self._r_each

    @property
    def sections(self) -> list[LosslessLine]:
        return self._sections
