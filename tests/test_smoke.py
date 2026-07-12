"""Basic closed-form, IBIS, and simulation smoke tests."""

from pathlib import Path

import numpy as np

from si_prelayout.api import load_project, run_simulation
from si_prelayout.domain.topology import Corner, TraceRef
from si_prelayout.field2d.closed_form import microstrip_z0, resolve_trace
from si_prelayout.field2d.loss_models import djordjevic_sarkar_er, attenuation_neper_per_m
from si_prelayout.ibis.buffer import extract_switching_tables
from si_prelayout.ibis.parser import parse_ibis
from si_prelayout.analyze.sweep import sweep_series_r

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
IBIS = EXAMPLES / "buffers" / "generic_25ohm.ibs"


def test_microstrip_z0_ballpark():
    z0 = microstrip_z0(width_m=0.15e-3, height_m=0.1e-3, er=4.2)
    assert 40 < z0 < 70


def test_resolve_explicit_z0():
    ref = TraceRef(name="t", z0_ohm=50.0, velocity_factor=0.66)
    z0, dly = resolve_trace(ref)
    assert z0 == 50.0
    assert dly > 0


def test_djordjevic_sarkar_causal():
    er = djordjevic_sarkar_er(1e9, er_inf=4.0, delta_er=0.4)
    assert np.real(er) > 3.5
    assert np.imag(er) < 0  # lossy capacitive


def test_attenuation_positive():
    a = attenuation_neper_per_m(50.0, 0.66, 1e9)
    assert a > 0


def test_ibis_parse_and_2eq():
    model = parse_ibis(IBIS).get("GENERIC_OUTPUT")
    assert model.pullup is not None and model.pulldown is not None
    assert len(model.rising) >= 2 and len(model.falling) >= 2
    tabs = extract_switching_tables(model, Corner.TYP)
    assert tabs is not None
    assert tabs.kd_rise[0] > 0.9 and tabs.ku_rise[0] < 0.1
    assert tabs.ku_rise[-1] > 0.9 and tabs.kd_rise[-1] < 0.1


def test_series_terminated_runs():
    project = load_project(EXAMPLES / "series_terminated.si.yml")
    result = run_simulation(project)
    assert result.waveforms
    recv = next(w for w in result.waveforms if w.name.endswith(".in"))
    assert float(np.max(recv.v_v)) > 1.0
    assert result.checks


def test_parallel_terminated_runs():
    project = load_project(EXAMPLES / "parallel_terminated.si.yml")
    result = run_simulation(project)
    assert len(result.waveforms) >= 1


def test_ibis_project_runs():
    project = load_project(EXAMPLES / "ibis_series_terminated.si.yml")
    result = run_simulation(project)
    assert "U1" in result.meta.get("ibis_drivers", [])
    recv = next(w for w in result.waveforms if w.name.endswith(".in"))
    assert float(np.max(recv.v_v)) > 1.0


def test_crosstalk_heuristic():
    from si_prelayout.physics.crosstalk import estimate_microstrip_crosstalk

    est = estimate_microstrip_crosstalk(
        aggressor_edge_v=3.3,
        length_m=0.05,
        spacing_m=0.15e-3,
        height_m=0.1e-3,
        tr_s=0.2e-9,
    )
    assert 0 < est.next_v_ratio < 0.5
    assert est.fext_v_ratio >= 0


def test_vector_fit_s21():
    from si_prelayout.tline.vector_fit import fit_real_poles, tline_s21

    f = np.logspace(7, 10, 40)
    h = tline_s21(f, length_m=0.05, z0=50.0, vf=0.66)
    fit = fit_real_poles(f, h, n_poles=8)
    assert np.all(fit.poles < 0)
    assert np.isfinite(fit.rmse)
    # Real-pole-only fit is a skeleton; delay-dominated S21 needs complex poles later.
    assert fit.rmse < 1.5
    assert len(fit.h_fit) == len(h)


def test_diffpair_and_budget():
    from si_prelayout.physics.diffpair import length_budget_m, microstrip_zdiff

    zodd, zeven, zdiff = microstrip_zdiff(0.1e-3, 0.1e-3, 0.1e-3, 4.2)
    assert zdiff > zodd > 0
    assert zeven > zodd
    assert length_budget_m(10.0) > 0


def test_json_report(tmp_path):
    from si_prelayout.report.json_report import write_json_report

    project = load_project(EXAMPLES / "series_terminated.si.yml")
    result = run_simulation(project)
    path = tmp_path / "out.json"
    write_json_report(project, result, path)
    assert path.is_file()
    assert "probes" in path.read_text()


def test_sweep_series_r():
    project = load_project(EXAMPLES / "series_terminated.si.yml")
    sweep = sweep_series_r(project, [10.0, 33.0, 47.0])
    assert len(sweep.points) == 3
