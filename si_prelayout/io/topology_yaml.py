"""Load / save topology projects."""

from __future__ import annotations

from pathlib import Path

import yaml

from si_prelayout.domain.topology import Project


def load_project(path: str | Path) -> Project:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Project file must be a mapping: {path}")
    project = Project.model_validate(data)
    # Resolve IBIS paths relative to the project file
    base = path.parent
    for ref in project.ibis_files.values():
        if ref.path and not Path(ref.path).is_file():
            cand = (base / ref.path).resolve()
            if cand.is_file():
                ref.path = str(cand)
            else:
                # also try repo-root-ish: parent of examples/
                cand2 = (base.parent / ref.path).resolve()
                if cand2.is_file():
                    ref.path = str(cand2)
    return project


def save_project(project: Project, path: str | Path) -> None:
    payload = project.model_dump(mode="json")
    Path(path).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
