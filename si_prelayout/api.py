"""Public Python API."""

from __future__ import annotations

from pathlib import Path

from si_prelayout.analyze.checks import run_checks
from si_prelayout.circuit.mna import TransientSimulator
from si_prelayout.domain.results import SimulationResult
from si_prelayout.domain.topology import IbisDriver, Project
from si_prelayout.io.topology_yaml import load_project as _load
from si_prelayout.io.topology_yaml import save_project
from si_prelayout.report.markdown import write_markdown_report


def load_project(path: str | Path) -> Project:
    return _load(path)


def run_simulation(project: Project) -> SimulationResult:
    sim = TransientSimulator(project)
    result = sim.run()
    v_high = 3.3
    v_low = 0.0
    for c in project.topology:
        if isinstance(c, IbisDriver):
            v_high = c.v_high
            v_low = c.v_low
            break
    result.checks = run_checks(
        result.waveforms,
        project.analyze.checks,
        v_high=v_high,
        v_low=v_low,
    )
    return result


def analyze_file(
    path: str | Path, report_path: str | Path | None = None
) -> SimulationResult:
    project = load_project(path)
    result = run_simulation(project)
    if report_path is not None:
        write_markdown_report(project, result, report_path)
    return result


__all__ = [
    "load_project",
    "save_project",
    "run_simulation",
    "analyze_file",
    "write_markdown_report",
]
