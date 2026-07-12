"""Basic closed-form and simulation smoke tests."""

from pathlib import Path

import numpy as np

from si_prelayout.api import load_project, run_simulation
from si_prelayout.domain.topology import TraceRef
from si_prelayout.field2d.closed_form import microstrip_z0, resolve_trace

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_microstrip_z0_ballpark():
    # ~50Ω class geometry
    z0 = microstrip_z0(width_m=0.15e-3, height_m=0.1e-3, er=4.2)
    assert 40 < z0 < 70


def test_resolve_explicit_z0():
    ref = TraceRef(name="t", z0_ohm=50.0, velocity_factor=0.66)
    z0, dly = resolve_trace(ref)
    assert z0 == 50.0
    assert dly > 0


def test_series_terminated_runs():
    project = load_project(EXAMPLES / "series_terminated.si.yml")
    result = run_simulation(project)
    assert result.waveforms
    recv = next(w for w in result.waveforms if w.name.endswith(".in"))
    # Receiver should see activity above ~1 V after the edge
    assert float(np.max(recv.v_v)) > 1.0
    assert result.checks


def test_parallel_terminated_runs():
    project = load_project(EXAMPLES / "parallel_terminated.si.yml")
    result = run_simulation(project)
    assert len(result.waveforms) >= 1
