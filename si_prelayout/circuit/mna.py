"""Nodal transient solver: MoC TLs + behavioral/IBIS drivers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from si_prelayout.field2d.loss_models import attenuation_neper_per_m
from si_prelayout.ibis.buffer import IbisBufferState, build_buffer
from si_prelayout.ibis.parser import parse_ibis
from si_prelayout.native import backend_name, make_lossless_line, solve_dense
from si_prelayout.tline.lossless import delay_seconds


@dataclass
class _CapState:
    node: int
    c: float
    v_prev: float = 0.0


@dataclass
class _LineState:
    line: object
    atten: float  # e^(-αℓ) applied to traveling waves
    r_series: float  # total series loss resistance


def _driver_voltage(drv: IbisDriver, t: float) -> float:
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
    """Fixed-step nodal transient with lossless/attenuated MoC lines."""

    def __init__(self, project: Project):
        self.project = project
        self.components = {c.id: c for c in project.topology}
        self.node_of: dict[str, int] = {}
        self._lines: dict[str, _LineState] = {}
        self._caps: list[_CapState] = []
        self._ibis_bufs: dict[str, IbisBufferState] = {}
        self._ibis_cache: dict[str, object] = {}
        self._build_nodes()
        self._load_ibis_buffers()
        self._tie_unused_die_nodes()

    def _tie_unused_die_nodes(self) -> None:
        """Short .die to .out when no IBIS IV model (PWL drivers)."""
        for c in self.project.topology:
            if not isinstance(c, IbisDriver):
                continue
            if c.id in self._ibis_bufs and self._ibis_bufs[c.id].uses_iv_table():
                continue
            # Rebuild mapping: force same node by reassigning
            nout = self.node_of[f"{c.id}.out"]
            self.node_of[f"{c.id}.die"] = nout

    def _build_nodes(self) -> None:
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
            if ra == "gnd":
                parent[rb] = ra
            elif rb == "gnd":
                parent[ra] = rb
            else:
                parent[rb] = ra

        for c in self.project.topology:
            if isinstance(c, IbisDriver):
                parent.setdefault(f"{c.id}.out", f"{c.id}.out")
                # Die node stays separate (package/series R to .out)
                parent.setdefault(f"{c.id}.die", f"{c.id}.die")
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
            pins = [p.strip() for p in net.connect]
            for p in pins[1:]:
                union(pins[0], p)

        # If a driver has no IBIS IV model, short die to out
        # (done after load — for now always keep die; PWL stamps on out)
        roots = sorted({find(p) for p in parent if find(p) != "gnd"})
        index = {r: i + 1 for i, r in enumerate(roots)}
        index["gnd"] = 0
        for pin in parent:
            self.node_of[pin] = index[find(pin)]
        self.n = len(roots)

    def _load_ibis_buffers(self) -> None:
        for c in self.project.topology:
            if not isinstance(c, IbisDriver):
                continue
            path = None
            if c.ibis and c.ibis in self.project.ibis_files:
                path = self.project.ibis_files[c.ibis].path
            elif c.ibis:
                path = c.ibis
            if not path:
                continue
            p = Path(path)
            if not p.is_file():
                # resolve relative to CWD / examples
                for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
                    cand = base / path
                    if cand.is_file():
                        p = cand
                        break
            if not p.is_file():
                continue
            ibis = parse_ibis(p)
            model_name = c.model
            if model_name not in ibis.models:
                # try project ibis_files model override
                ref = self.project.ibis_files.get(c.ibis or "")
                if ref:
                    model_name = ref.model
            if model_name not in ibis.models:
                continue
            model = ibis.get(model_name)
            self._ibis_bufs[c.id] = build_buffer(
                model,
                corner=c.corner,
                delay_s=c.delay_s,
                pulse_width_s=c.pulse_width_s,
                v_high=c.v_high,
                v_low=c.v_low,
                r_series_ohm=c.r_series_ohm,
                edge_s=c.edge_s,
            )

    def run(self) -> SimulationResult:
        p = self.project
        dt = p.analyze.dt_s
        tstop = p.analyze.tstop_s
        nsteps = int(np.floor(tstop / dt)) + 1
        t = np.arange(nsteps) * dt

        # Default edge for loss estimate
        edge = 0.2e-9
        for c in p.topology:
            if isinstance(c, IbisDriver):
                edge = c.edge_s
                break

        for c in p.topology:
            if not isinstance(c, Tline):
                continue
            ref = p.traces[c.ref]
            z0, dly_m = resolve_trace(ref)
            td = delay_seconds(c.length_m, dly_m)
            atten = 1.0
            r_series = 0.0
            if getattr(ref, "lossy", False):
                vf = ref.velocity_factor
                fe = 0.35 / max(edge, 1e-15)
                alpha = attenuation_neper_per_m(
                    z0,
                    vf,
                    fe,
                    r_dc=getattr(ref, "r_dc_per_m", 5.0),
                    r_skin=getattr(ref, "r_skin", 5e-5),
                    er=ref.er,
                    tand=getattr(ref, "tand", 0.02),
                )
                atten = float(np.exp(-alpha * c.length_m))
                r_series = max(
                    getattr(ref, "r_dc_per_m", 5.0) * c.length_m,
                    2.0 * alpha * z0 * c.length_m,
                )
            line = make_lossless_line(z0, td, dt, atten=atten)
            self._lines[c.id] = _LineState(line=line, atten=atten, r_series=r_series)

        self._caps = []
        for c in p.topology:
            if isinstance(c, IbisReceiver):
                node = self.node_of[f"{c.id}.in"]
                cc = c.c_comp_f
                # Prefer IBIS C_comp if driver-side model somehow shared — receivers stay as-is
                if node > 0 and cc > 0:
                    self._caps.append(_CapState(node=node, c=cc))
            elif isinstance(c, Capacitor):
                node = self.node_of[f"{c.id}.a"]
                if node > 0:
                    self._caps.append(_CapState(node=node, c=c.farads))

        # Add C_comp from IBIS drivers at die node
        for cid, buf in self._ibis_bufs.items():
            node = self.node_of.get(f"{cid}.die", self.node_of[f"{cid}.out"])
            cc = buf.model.c_comp_for(buf.corner)
            if node > 0 and cc > 0:
                self._caps.append(_CapState(node=node, c=cc))

        probe_pins = p.analyze.probes or self._default_probes()
        records = {
            pin: np.zeros(nsteps)
            for pin in probe_pins
            if pin in self.node_of
        }

        v = np.zeros(self.n + 1)

        for k in range(nsteps):
            tk = t[k]
            # Newton iterations for nonlinear IBIS stamps
            for _newton in range(6):
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

                for c in p.topology:
                    if isinstance(c, Resistor):
                        na = self.node_of[f"{c.id}.a"]
                        nb = 0 if c.to == "gnd" else self.node_of[f"{c.id}.b"]
                        add_g(na, nb, 1.0 / c.ohms)
                    elif isinstance(c, IbisReceiver):
                        add_g(self.node_of[f"{c.id}.in"], 0, 1.0 / c.r_die_ohm)

                # Linear PWL drivers (no IBIS table)
                for c in p.topology:
                    if not isinstance(c, IbisDriver):
                        continue
                    if c.id in self._ibis_bufs and self._ibis_bufs[c.id].uses_iv_table():
                        continue
                    na = self.node_of[f"{c.id}.out"]
                    rs = max(c.r_series_ohm, 1e-6)
                    vth = _driver_voltage(c, tk)
                    add_g(na, 0, 1.0 / rs)
                    add_i(na, vth / rs)

                # Nonlinear IBIS drivers on die node + series R to pad
                for c in p.topology:
                    if not isinstance(c, IbisDriver):
                        continue
                    if c.id not in self._ibis_bufs or not self._ibis_bufs[
                        c.id
                    ].uses_iv_table():
                        continue
                    buf = self._ibis_bufs[c.id]
                    ndie = self.node_of[f"{c.id}.die"]
                    nout = self.node_of[f"{c.id}.out"]
                    rs = max(c.r_series_ohm, 1.0)
                    add_g(ndie, nout, 1.0 / rs)
                    vdie = float(v[ndie])
                    i0 = buf.current_into_pad(vdie, tk)
                    eps = 1e-3
                    i1 = buf.current_into_pad(vdie + eps, tk)
                    geq = (i1 - i0) / eps
                    # Floor conductance for Newton stability
                    geq = float(np.clip(geq, 1e-4, 10.0))
                    add_g(ndie, 0, geq)
                    add_i(ndie, i0 - geq * vdie)
                    # Soft rail clamp via high-G diodes approx
                    vcc = buf.model.vcc_for(buf.corner)
                    if vdie > vcc + 0.5:
                        add_g(ndie, 0, 1.0)
                        add_i(ndie, -(vcc + 0.5))
                    if vdie < -0.5:
                        add_g(ndie, 0, 1.0)
                        add_i(ndie, 0.5)

                # Tlines
                for c in p.topology:
                    if not isinstance(c, Tline):
                        continue
                    st = self._lines[c.id]
                    na = self.node_of[f"{c.id}.a"]
                    nb = self.node_of[f"{c.id}.b"]
                    e_a, e_b = st.line.companion_sources()
                    z0 = st.line.z0 + 0.5 * st.r_series
                    add_g(na, 0, 1.0 / z0)
                    add_g(nb, 0, 1.0 / z0)
                    add_i(na, e_a / z0)
                    add_i(nb, e_b / z0)

                for cap in self._caps:
                    geq = cap.c / dt
                    add_g(cap.node, 0, geq)
                    add_i(cap.node, geq * cap.v_prev)

                if self.n == 0:
                    break
                try:
                    vn = solve_dense(g, i_vec)
                except Exception:
                    vn = np.linalg.lstsq(g, i_vec, rcond=None)[0]
                v[1:] = vn

            for cap in self._caps:
                cap.v_prev = v[cap.node]

            for c in p.topology:
                if not isinstance(c, Tline):
                    continue
                st = self._lines[c.id]
                na = self.node_of[f"{c.id}.a"]
                nb = self.node_of[f"{c.id}.b"]
                e_a, e_b = st.line.companion_sources()
                z0 = st.line.z0 + 0.5 * st.r_series
                va, vb = float(v[na]), float(v[nb])
                ia = (va - e_a) / z0
                ib = (vb - e_b) / z0
                st.line.commit(va, ia, vb, ib)

            for pin in records:
                records[pin][k] = v[self.node_of[pin]]

        waveforms = [Waveform(name=pin, t_s=t, v_v=arr) for pin, arr in records.items()]
        return SimulationResult(
            waveforms=waveforms,
            meta={
                "dt_s": dt,
                "tstop_s": tstop,
                "nodes": self.n,
                "engine": "moc_mna_ibis",
                "solver_backend": backend_name(),
                "ibis_drivers": list(self._ibis_bufs.keys()),
            },
        )

    def _default_probes(self) -> list[str]:
        probes: list[str] = []
        for c in self.project.topology:
            if isinstance(c, IbisDriver):
                probes.append(f"{c.id}.out")
            elif isinstance(c, IbisReceiver):
                probes.append(f"{c.id}.in")
        return probes
