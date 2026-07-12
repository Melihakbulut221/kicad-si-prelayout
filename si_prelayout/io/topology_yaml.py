"""Load / save topology projects."""

from __future__ import annotations

from pathlib import Path

import yaml

from si_prelayout.domain.topology import Project


def load_project(path: str | Path) -> Project:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Project file must be a mapping: {path}")
    return Project.model_validate(data)


def save_project(project: Project, path: str | Path) -> None:
    payload = project.model_dump(mode="json")
    Path(path).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
