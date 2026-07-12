"""Markdown / text reports."""

from __future__ import annotations

from pathlib import Path

from si_prelayout.domain.results import SimulationResult
from si_prelayout.domain.topology import Project


def write_markdown_report(
    project: Project, result: SimulationResult, path: str | Path
) -> None:
    lines = [
        f"# SI report: {project.name}",
        "",
        project.description,
        "",
        "## Simulation",
        f"- Engine: `{result.meta.get('engine', 'unknown')}`",
        f"- dt: {result.meta.get('dt_s')} s",
        f"- tstop: {result.meta.get('tstop_s')} s",
        f"- nodes: {result.meta.get('nodes')}",
        "",
        "## Waveforms",
    ]
    for wf in result.waveforms:
        lines.append(
            f"- `{wf.name}`: {len(wf.t_s)} samples, "
            f"V in [{wf.v_v.min():.3f}, {wf.v_v.max():.3f}] V"
        )
    lines += ["", "## Checks"]
    if not result.checks:
        lines.append("- (none)")
    for c in result.checks:
        status = "PASS" if c.passed else "FAIL"
        lines.append(f"- **{status}** `{c.name}`: {c.message}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
