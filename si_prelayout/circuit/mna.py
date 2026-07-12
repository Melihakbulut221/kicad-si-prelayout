"""Nodal transient solver with lossless TL (MoC) companions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from si_prelayout.domain.results import SimulationResult, Waveform
from si_prelayout.domain.topology import (
    Capacitor,
    IbisDriver,
    IbisReceiver,
    Project,
    Resistor,
    Tline,
)
from si_prelayout.field2d.closed_form import resolve_trace
from si_prelayout.tline.lossless import LosslessLine, delay_seconds


@dataclass
class _CapState:
    node: int
    c: float
    v_prev: float = 0.0


def _driver_voltage(drv: IbisDriver, t: float) -> float:
    """Piecewise-linear pulse (MVP stand-in until full IBIS IV/VT)."""
    t0 = drv.delay_s
    tr = max(drv.edge_s, 1e-15)
    vh, vl = drv.v_high, drv.v_low
    pw = drv.pulse_width_s

    if t < t0:
        return vl
    if t < t0 + tr:
        return vl + (vh - vl) * (t - t0) / tr
    if pw is None:
        return vh
    if t < t0 + tr + pw:
        return vh
    if t < t0 + 2 * tr + pw:
        return vh + (vl - vh) * (t - t0 - tr - pw) / tr
    return vl


class TransientSimulator:
    """Build a nodal netlist from Project and run a fixed-step transient."""

    def __init__(self, project: Project):
        self.project = project
        self.components = {c.id: c for c in project.topology}
        self.node_of: dict[str, int] = {}  # pin -> node index (0 = gnd)
        self._lines: dict[str, LosslessLine] = {}
        self._caps: list[_CapState] = []
        self._build_nodes()

    def _pin(self, name: str) -> str:
        return name.strip()

    def _build_nodes(self) -> None:
        # Union-find style: each pin starts alone; nets merge; gnd is 0
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if ra == "gnd" or ra.endswith("#gnd"):
                parent[rb] = ra
            elif rb == "gnd" or rb.endswith("#gnd"):
                parent[ra] = rb
            else:
                parent[rb] = ra

        # Ensure component pins exist
        for c in self.project.topology:
            if isinstance(c, IbisDriver):
                parent.setdefault(f"{c.id}.out", f"{c.id}.out")
            elif isinstance(c, IbisReceiver):
                parent.setdefault(f"{c.id}.in", f"{c.id}.in")
            elif isinstance(c, Tline):
                parent.setdefault(f"{c.id}.a", f"{c.id}.a")
                parent.setdefault(f"{c.id}.b", f"{c.id}.b")
            elif isinstance(c, Resistor):
                parent.setdefault(f"{c.id}.a", f"{c.id}.a")
                if c.to == "gnd":
                    union(f"{c.id}.b", "gnd")
                else:
                    parent.setdefault(f"{c.id}.b", f"{c.id}.b")
            elif isinstance(c, Capacitor):
                parent.setdefault(f"{c.id}.a", f"{c.id}.a")
                union(f"{c.id}.b", "gnd")

        parent.setdefault("gnd", "gnd")

        for net in self.project.nets:
            pins = [self._pin(p) for p in net.connect]
            for p in pins[1:]:
                union(pins[0], p)

        # Assign integer node ids
        roots = sorted({find(p) for p in parent if find(p) != "gnd"})
        index = {r: i + 1 for i, r in enumerate(roots)}  # 1..n, 0=gnd
        index["gnd"] = 0

        for pin in list(parent.keys()):
            self.node_of[pin] = index[find(pin)]

        self.n = len(roots)  # number of non-ground nodes

    def run(self) -> SimulationResult:
        p = self.project
        dt = p.analyze.dt_s
        tstop = p.analyze.tstop_s
        nsteps = int(np.floor(tstop / dt)) + 1
        t = np.arange(nsteps) * dt

        # Prepare TL companions
        for c in p.topology:
            if isinstance(c, Tline):
                z0, dly_m = resolve_trace(p.traces[c.ref])
                td = delay_seconds(c.length_m, dly_m)
                self._lines[c.id] = LosslessLine(z0=z0, td_s=td, dt_s=dt)

        # Capacitors (receivers + explicit)
        self._caps = []
        for c in p.topology:
            if isinstance(c, IbisReceiver):
                node = self.node_of[f"{c.id}.in"]
                if node > 0:
                    self._caps.append(_CapState(node=node, c=c.c_comp_f))
                    # Die resistance stamped each step
            elif isinstance(c, Capacitor):
                node = self.node_of[f"{c.id}.a"]
                if node > 0:
                    self._caps.append(_CapState(node=node, c=c.farads))

        # Probe voltages
        probe_pins = p.analyze.probes or self._default_probes()
        records: dict[str, np.ndarray] = {
            pin: np.zeros(nsteps) for pin in probe_pins if self._node(pin) is not None
        }

        v = np.zeros(self.n + 1)  # index 0 unused / gnd

        for k in range(nsteps):
            tk = t[k]
            g = np.zeros((self.n, self.n))
            i_vec = np.zeros(self.n)

            def add_g(n1: int, n2: int, cond: float) -> None:
                if n1 > 0:
                    g[n1 - 1, n1 - 1] += cond
                if n2 > 0:
                    g[n2 - 1, n2 - 1] += cond
                if n1 > 0 and n2 > 0:
                    g[n1 - 1, n2 - 1] -= cond
                    g[n2 - 1, n1 - 1] -= cond

            def add_i(node: int, current: float) -> None:
                if node > 0:
                    i_vec[node - 1] += current

            # Resistors
            for c in p.topology:
                if isinstance(c, Resistor):
                    na = self.node_of[f"{c.id}.a"]
                    nb = self.node_of.get(f"{c.id}.b", 0)
                    if c.to == "gnd":
                        nb = 0
                    add_g(na, nb, 1.0 / c.ohms)
                elif isinstance(c, IbisReceiver):
                    na = self.node_of[f"{c.id}.in"]
                    add_g(na, 0, 1.0 / c.r_die_ohm)

            # Drivers — Norton of Vth + Rs
            for c in p.topology:
                if isinstance(c, IbisDriver):
                    na = self.node_of[f"{c.id}.out"]
                    rs = max(c.r_series_ohm, 1e-6)
                    vth = _driver_voltage(c, tk)
                    add_g(na, 0, 1.0 / rs)
                    add_i(na, vth / rs)

            # Tlines — MoC Norton companions
            line_currents: dict[str, tuple[float, float]] = {}
            for c in p.topology:
                if not isinstance(c, Tline):
                    continue
                line = self._lines[c.id]
                na = self.node_of[f"{c.id}.a"]
                nb = self.node_of[f"{c.id}.b"]
                e_a, e_b = line.companion_sources()
                z0 = line.z0
                add_g(na, 0, 1.0 / z0)
                add_g(nb, 0, 1.0 / z0)
                add_i(na, e_a / z0)
                add_i(nb, e_b / z0)
                line_currents[c.id] = (e_a, e_b)  # temp; update after solve

            # Capacitors — backward Euler: G=C/dt, Ieq = C/dt * v_prev
            for cap in self._caps:
                geq = cap.c / dt
                add_g(cap.node, 0, geq)
                add_i(cap.node, geq * cap.v_prev)

            # Solve
            if self.n == 0:
                break
            try:
                vn = np.linalg.solve(g, i_vec)
            except np.linalg.LinAlgError:
                vn = np.linalg.lstsq(g, i_vec, rcond=None)[0]
            v[1:] = vn

            # Update caps
            for cap in self._caps:
                cap.v_prev = v[cap.node]

            # Commit TL history
            for c in p.topology:
                if not isinstance(c, Tline):
                    continue
                line = self._lines[c.id]
                na = self.node_of[f"{c.id}.a"]
                nb = self.node_of[f"{c.id}.b"]
                e_a, e_b = line.companion_sources()
                z0 = line.z0
                va, vb = v[na], v[nb]
                ia = (va - e_a) / z0
                ib = (vb - e_b) / z0
                line.commit(va, ia, vb, ib)

            for pin in records:
                node = self._node(pin)
                records[pin][k] = v[node] if node is not None else 0.0

        waveforms = [Waveform(name=pin, t_s=t, v_v=arr) for pin, arr in records.items()]
        return SimulationResult(
            waveforms=waveforms,
            meta={
                "dt_s": dt,
                "tstop_s": tstop,
                "nodes": self.n,
                "engine": "moc_lossless_mna",
            },
        )

    def _node(self, pin: str) -> int | None:
        if pin in self.node_of:
            return self.node_of[pin]
        return None

    def _default_probes(self) -> list[str]:
        probes: list[str] = []
        for c in self.project.topology:
            if isinstance(c, IbisDriver):
                probes.append(f"{c.id}.out")
            elif isinstance(c, IbisReceiver):
                probes.append(f"{c.id}.in")
        return probes
