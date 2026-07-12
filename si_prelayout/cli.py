"""User-friendly CLI for si-prelayout."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import typer
from rich.console import Console
from rich.table import Table

from si_prelayout.api import analyze_file, load_project, run_simulation
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
