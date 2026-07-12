"""User-friendly CLI for si-prelayout."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import typer
from rich.console import Console
from rich.table import Table

from si_prelayout.api import analyze_file, load_project, run_simulation
from si_prelayout.analyze.sweep import sweep_length, sweep_series_r
from si_prelayout.field2d.closed_form import resolve_trace
from si_prelayout.report.markdown import write_markdown_report

app = typer.Typer(
    name="si-prelayout",
    help="Open-source pre-layout Signal Integrity simulator (LineSim-style).",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def analyze(
    project: Path = typer.Argument(..., exists=True, help="Path to .si.yml project"),
    report: Optional[Path] = typer.Option(
        None, "--report", "-r", help="Write Markdown report to this path"
    ),
    plot: Optional[Path] = typer.Option(
        None, "--plot", "-p", help="Save waveform PNG to this path"
    ),
    json_out: Optional[Path] = typer.Option(
        None, "--json", "-j", help="Write JSON report with timing metrics"
    ),
) -> None:
    """Run a topology simulation and print SI checks."""
    console.print(f"[bold]Analyzing[/bold] {project}")
    proj = load_project(project)
    result = run_simulation(proj)

    table = Table(title=f"SI checks — {proj.name}")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for c in result.checks:
        status = "[green]PASS[/green]" if c.passed else "[red]FAIL[/red]"
        table.add_row(c.name, status, c.message)
    console.print(table)

    for wf in result.waveforms:
        console.print(
            f"  probe [cyan]{wf.name}[/cyan]: "
            f"{wf.v_v.min():.3f} … {wf.v_v.max():.3f} V"
        )

    if report:
        write_markdown_report(proj, result, report)
        console.print(f"Report → {report}")

    if json_out:
        from si_prelayout.domain.topology import IbisDriver
        from si_prelayout.report.json_report import write_json_report

        vh, vl = 3.3, 0.0
        for c in proj.topology:
            if isinstance(c, IbisDriver):
                vh, vl = c.v_high, c.v_low
                break
        write_json_report(proj, result, json_out, v_lo=vl, v_hi=vh)
        console.print(f"JSON → {json_out}")

    if plot:
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for wf in result.waveforms:
            ax.plot(wf.t_s * 1e9, wf.v_v, label=wf.name)
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("Voltage (V)")
        ax.set_title(proj.name)
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(plot, dpi=140)
        plt.close(fig)
        console.print(f"Plot → {plot}")


@app.command("z0")
def impedance(
    width_mil: float = typer.Option(..., help="Trace width (mil)"),
    height_mil: float = typer.Option(..., help="Dielectric height (mil)"),
    er: float = typer.Option(4.2, help="Relative permittivity"),
    style: str = typer.Option("microstrip", help="microstrip|stripline"),
) -> None:
    """Quick closed-form Z0 preview (not a substitute for 2D MoM)."""
    from si_prelayout.domain.topology import TraceRef

    mil = 25.4e-6
    ref = TraceRef(
        name="tmp",
        style=style,  # type: ignore[arg-type]
        width_m=width_mil * mil,
        height_m=height_mil * mil,
        er=er,
    )
    z0, dly = resolve_trace(ref)
    console.print(f"Z0 ≈ [bold]{z0:.2f} Ω[/bold]")
    console.print(f"Delay ≈ {dly * 1e9 / 0.0254:.2f} ns/in ({dly*1e9:.3f} ns/m)")


@app.command()
def sweep(
    project: Path = typer.Argument(..., exists=True),
    series_r: Optional[str] = typer.Option(
        None, "--series-r", help="Comma-separated ohms, e.g. 10,22,33,47"
    ),
    length_mm: Optional[str] = typer.Option(
        None, "--length-mm", help="Comma-separated mm, e.g. 40,80,120"
    ),
) -> None:
    """What-if sweep on series R and/or first TL length."""
    proj = load_project(project)
    if series_r:
        vals = [float(x) for x in series_r.split(",") if x.strip()]
        result = sweep_series_r(proj, vals)
        table = Table(title="Series-R sweep")
        table.add_column("Case")
        table.add_column("Peak@rx")
        table.add_column("Checks")
        for pt in result.points:
            rx = next((w for w in pt.result.waveforms if w.name.endswith(".in")), None)
            peak = f"{rx.v_v.max():.3f} V" if rx is not None else "—"
            n_fail = sum(1 for c in pt.result.checks if not c.passed)
            table.add_row(pt.label, peak, f"{n_fail} fail" if n_fail else "all pass")
        console.print(table)
    if length_mm:
        vals = [float(x) * 1e-3 for x in length_mm.split(",") if x.strip()]
        result = sweep_length(proj, vals)
        table = Table(title="Length sweep")
        table.add_column("Case")
        table.add_column("Peak@rx")
        table.add_column("Checks")
        for pt in result.points:
            rx = next((w for w in pt.result.waveforms if w.name.endswith(".in")), None)
            peak = f"{rx.v_v.max():.3f} V" if rx is not None else "—"
            n_fail = sum(1 for c in pt.result.checks if not c.passed)
            table.add_row(pt.label, peak, f"{n_fail} fail" if n_fail else "all pass")
        console.print(table)
    if not series_r and not length_mm:
        console.print("[yellow]Specify --series-r and/or --length-mm[/yellow]")
        raise typer.Exit(1)


@app.command("xtalk")
def crosstalk(
    spacing_mil: float = typer.Option(..., help="Edge-to-edge spacing (mil)"),
    height_mil: float = typer.Option(..., help="Dielectric height (mil)"),
    length_mil: float = typer.Option(2000.0, help="Coupled length (mil)"),
    edge_ns: float = typer.Option(0.2, help="Aggressor edge rate (ns)"),
    swing_v: float = typer.Option(3.3, help="Aggressor swing (V)"),
) -> None:
    """Closed-form microstrip NEXT/FEXT spacing estimate."""
    from si_prelayout.physics.crosstalk import estimate_microstrip_crosstalk

    mil = 25.4e-6
    est = estimate_microstrip_crosstalk(
        aggressor_edge_v=swing_v,
        length_m=length_mil * mil,
        spacing_m=spacing_mil * mil,
        height_m=height_mil * mil,
        tr_s=edge_ns * 1e-9,
    )
    console.print(f"NEXT ≈ [bold]{est.next_mv_per_v:.1f} mV/V[/bold] "
                  f"→ {est.next_v_ratio * swing_v:.3f} V peak")
    console.print(f"FEXT ≈ [bold]{est.fext_mv_per_v:.1f} mV/V[/bold] "
                  f"→ {est.fext_v_ratio * swing_v:.3f} V peak")
    console.print(f"[dim]{est.notes}[/dim]")


@app.command()
def ui() -> None:
    """Launch the Streamlit web UI."""
    import shutil
    import subprocess

    ui_path = Path(__file__).resolve().parent.parent / "ui" / "app.py"
    if not ui_path.exists():
        console.print(f"[red]UI not found:[/red] {ui_path}")
        raise typer.Exit(1)
    streamlit = shutil.which("streamlit")
    if not streamlit:
        console.print(
            "[red]streamlit not installed.[/red] Run: pip install -e '.[ui]'"
        )
        raise typer.Exit(1)
    console.print("[bold]Opening SI Pre-Layout Studio…[/bold]")
    raise SystemExit(subprocess.call([streamlit, "run", str(ui_path)]))


@app.command("validate")
def validate_project(
    project: Path = typer.Argument(..., exists=True),
) -> None:
    """Validate a .si.yml project without simulating."""
    proj = load_project(project)
    console.print(f"[green]OK[/green] {proj.name}: {len(proj.topology)} components, "
                  f"{len(proj.nets)} nets")


if __name__ == "__main__":
    app()
