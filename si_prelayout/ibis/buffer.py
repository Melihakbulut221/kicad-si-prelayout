"""2-EQ/2-WF IBIS buffer: extract Ku/Kd and evaluate pad current."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from si_prelayout.domain.topology import Corner
from si_prelayout.ibis.parser import IbisModel, VtWaveform, WaveKind


@dataclass
class SwitchingTables:
    """Ku(t), Kd(t) for rising and falling relative to edge start."""

    t_rise: np.ndarray
    ku_rise: np.ndarray
    kd_rise: np.ndarray
    t_fall: np.ndarray
    ku_fall: np.ndarray
    kd_fall: np.ndarray


def _pad_current_from_iv(
    model: IbisModel, v_pad: float, ku: float, kd: float, corner: Corner
) -> float:
    vcc = model.vcc_for(corner)
    i = 0.0
    if model.pullup is not None:
        # IBIS pullup table is vs (Vcc - Vpad)
        i += ku * float(model.pullup.current(vcc - v_pad, corner))
    if model.pulldown is not None:
        i += kd * float(model.pulldown.current(v_pad, corner))
    if model.power_clamp is not None:
        i += float(model.power_clamp.current(vcc - v_pad, corner))
    if model.gnd_clamp is not None:
        i += float(model.gnd_clamp.current(v_pad, corner))
    return i


def _fixture_current(v_pad: float, wf: VtWaveform, corner: Corner) -> float:
    """Current into the buffer from the pad (IBIS sign convention)."""
    vf = wf.v_fixture
    if corner == Corner.MIN and wf.v_fixture_min is not None:
        vf = wf.v_fixture_min
    elif corner == Corner.MAX and wf.v_fixture_max is not None:
        vf = wf.v_fixture_max
    # Fixture current leaves the pad toward the fixture load; into-buffer is opposite.
    return -(v_pad - vf) / max(wf.r_fixture, 1e-9)


def _extract_k_pair(
    model: IbisModel,
    w1: VtWaveform,
    w2: VtWaveform,
    corner: Corner,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve 2EQ/2UK along shared timebase → (t, Ku, Kd)."""
    t = np.unique(np.concatenate([w1.t, w2.t]))
    t = t[np.isfinite(t)]
    ku = np.zeros_like(t)
    kd = np.zeros_like(t)
    vcc = model.vcc_for(corner)

    for idx, ti in enumerate(t):
        v1 = float(w1.voltage(ti, corner))
        v2 = float(w2.voltage(ti, corner))
        # Currents leaving the buffer into the fixture
        i1 = _fixture_current(v1, w1, corner)
        i2 = _fixture_current(v2, w2, corner)
        # Clamp contributions (always on)
        ipc1 = (
            float(model.power_clamp.current(vcc - v1, corner))
            if model.power_clamp
            else 0.0
        )
        ipc2 = (
            float(model.power_clamp.current(vcc - v2, corner))
            if model.power_clamp
            else 0.0
        )
        igc1 = float(model.gnd_clamp.current(v1, corner)) if model.gnd_clamp else 0.0
        igc2 = float(model.gnd_clamp.current(v2, corner)) if model.gnd_clamp else 0.0

        # Remaining = Ku*Ipu + Kd*Ipd
        rhs1 = i1 - ipc1 - igc1
        rhs2 = i2 - ipc2 - igc2
        ipu1 = (
            float(model.pullup.current(vcc - v1, corner)) if model.pullup else 0.0
        )
        ipu2 = (
            float(model.pullup.current(vcc - v2, corner)) if model.pullup else 0.0
        )
        ipd1 = float(model.pulldown.current(v1, corner)) if model.pulldown else 0.0
        ipd2 = float(model.pulldown.current(v2, corner)) if model.pulldown else 0.0

        a = np.array([[ipu1, ipd1], [ipu2, ipd2]], dtype=float)
        b = np.array([rhs1, rhs2], dtype=float)
        try:
            sol = np.linalg.solve(a, b)
        except np.linalg.LinAlgError:
            sol = np.linalg.lstsq(a, b, rcond=None)[0]
        ku[idx] = float(np.clip(sol[0], -0.5, 1.5))
        kd[idx] = float(np.clip(sol[1], -0.5, 1.5))

    # Soft clamp to [0,1] with mild allowance already applied
    ku = np.clip(ku, 0.0, 1.0)
    kd = np.clip(kd, 0.0, 1.0)
    return t, ku, kd


def extract_switching_tables(
    model: IbisModel, corner: Corner = Corner.TYP
) -> SwitchingTables | None:
    """Build Ku/Kd tables if ≥2 rising and ≥2 falling waveforms exist."""
    if model.pullup is None or model.pulldown is None:
        return None
    if len(model.rising) < 2 or len(model.falling) < 2:
        return None
    # Prefer distinct fixtures
    rising = sorted(model.rising, key=lambda w: (w.v_fixture, w.r_fixture))
    falling = sorted(model.falling, key=lambda w: (w.v_fixture, w.r_fixture))
    t_r, ku_r, kd_r = _extract_k_pair(model, rising[0], rising[1], corner)
    t_f, ku_f, kd_f = _extract_k_pair(model, falling[0], falling[1], corner)
    return SwitchingTables(
        t_rise=t_r - t_r[0],
        ku_rise=ku_r,
        kd_rise=kd_r,
        t_fall=t_f - t_f[0],
        ku_fall=ku_f,
        kd_fall=kd_f,
    )


@dataclass
class IbisBufferState:
    model: IbisModel
    corner: Corner
    tables: SwitchingTables | None
    # Stimulus bookkeeping
    delay_s: float = 1e-9
    pulse_width_s: float | None = 5e-9
    logic_high: bool = False
    edge_start: float | None = None
    edge_is_rise: bool = True
    # Fallback PWL
    v_high: float = 3.3
    v_low: float = 0.0
    r_series_ohm: float = 25.0
    edge_s: float = 0.2e-9

    def _ku_kd(self, t: float) -> tuple[float, float]:
        if self.tables is None or self.edge_start is None:
            # quiescent
            return (1.0, 0.0) if self.logic_high else (0.0, 1.0)
        tau = t - self.edge_start
        if self.edge_is_rise:
            ku = float(np.interp(tau, self.tables.t_rise, self.tables.ku_rise))
            kd = float(np.interp(tau, self.tables.t_rise, self.tables.kd_rise))
            if tau >= self.tables.t_rise[-1]:
                ku, kd = 1.0, 0.0
        else:
            ku = float(np.interp(tau, self.tables.t_fall, self.tables.ku_fall))
            kd = float(np.interp(tau, self.tables.t_fall, self.tables.kd_fall))
            if tau >= self.tables.t_fall[-1]:
                ku, kd = 0.0, 1.0
        return ku, kd

    def update_stimulus(self, t: float) -> None:
        """Schedule rising/falling edges from delay + pulse width."""
        t0 = self.delay_s
        pw = self.pulse_width_s
        if self.edge_start is None and t >= t0:
            self.edge_start = t0
            self.edge_is_rise = True
            self.logic_high = True
        if pw is not None and t >= t0 + pw and self.edge_is_rise and self.edge_start == t0:
            self.edge_start = t0 + pw
            self.edge_is_rise = False
            self.logic_high = False

    def current_into_pad(self, v_pad: float, t: float) -> float:
        """Current from buffer into the pad node (circuit KCL injection)."""
        self.update_stimulus(t)
        if self.tables is not None:
            ku, kd = self._ku_kd(t)
            i_into_buffer = _pad_current_from_iv(self.model, v_pad, ku, kd, self.corner)
            return -i_into_buffer
        return 0.0

    def uses_iv_table(self) -> bool:
        return self.tables is not None and self.model.pullup is not None


def build_buffer(
    model: IbisModel,
    corner: Corner = Corner.TYP,
    delay_s: float = 1e-9,
    pulse_width_s: float | None = 5e-9,
    v_high: float | None = None,
    v_low: float = 0.0,
    r_series_ohm: float = 25.0,
    edge_s: float = 0.2e-9,
) -> IbisBufferState:
    tables = extract_switching_tables(model, corner)
    return IbisBufferState(
        model=model,
        corner=corner,
        tables=tables,
        delay_s=delay_s,
        pulse_width_s=pulse_width_s,
        v_high=v_high if v_high is not None else model.vcc_for(corner),
        v_low=v_low,
        r_series_ohm=r_series_ohm,
        edge_s=edge_s,
    )
