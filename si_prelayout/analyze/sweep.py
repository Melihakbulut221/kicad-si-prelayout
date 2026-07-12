"""What-if / corner sweeps."""

from __future__ import annotations

from dataclasses import dataclass, field

from si_prelayout.analyze.checks import run_checks
from si_prelayout.circuit.mna import TransientSimulator
from si_prelayout.domain.results import SimulationResult
from si_prelayout.domain.topology import IbisDriver, Project, Resistor, Tline


def _run(project: Project) -> SimulationResult:
    result = TransientSimulator(project).run()
    v_high, v_low = 3.3, 0.0
    for c in project.topology:
        if isinstance(c, IbisDriver):
            v_high, v_low = c.v_high, c.v_low
            break
    result.checks = run_checks(
        result.waveforms, project.analyze.checks, v_high=v_high, v_low=v_low
    )
    return result


@dataclass
class SweepPoint:
    label: str
    params: dict
    result: SimulationResult


@dataclass
class SweepResult:
    points: list[SweepPoint] = field(default_factory=list)


def _set_series_r(project: Project, ohms: float) -> None:
    for c in project.topology:
        if isinstance(c, Resistor) and c.to == "floating":
            c.ohms = ohms
            return


def _set_first_tline_length(project: Project, length_m: float) -> None:
    for c in project.topology:
        if isinstance(c, Tline):
            c.length_m = length_m
            return


def sweep_series_r(project: Project, values_ohm: list[float]) -> SweepResult:
    out = SweepResult()
    for r in values_ohm:
        p = Project.model_validate(project.model_dump(mode="json"))
        _set_series_r(p, r)
        out.points.append(
            SweepPoint(
                label=f"Rseries={r:g}Ω",
                params={"rseries_ohm": r},
                result=_run(p),
            )
        )
    return out


def sweep_length(project: Project, lengths_m: list[float]) -> SweepResult:
    out = SweepResult()
    for length in lengths_m:
        p = Project.model_validate(project.model_dump(mode="json"))
        _set_first_tline_length(p, length)
        out.points.append(
            SweepPoint(
                label=f"L={length*1e3:g}mm",
                params={"length_m": length},
                result=_run(p),
            )
        )
    return out


def sweep_corners(project: Project) -> SweepResult:
    out = SweepResult()
    for corner in ("min", "typ", "max"):
        p = Project.model_validate(project.model_dump(mode="json"))
        for c in p.topology:
            if isinstance(c, IbisDriver):
                c.corner = corner  # type: ignore[assignment]
        out.points.append(
            SweepPoint(
                label=f"corner={corner}",
                params={"corner": corner},
                result=_run(p),
            )
        )
    return out
