"""Minimal IBIS support.

Full IV/VT 2-EQ/2-WF is planned; v0.1 ships a documented behavioral stand-in
and a lightweight .ibs section scanner for model discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class IbisModelInfo:
    name: str
    model_type: str
    path: str


def list_models(path: str | Path) -> list[IbisModelInfo]:
    """Scan an .ibs file for [Model] names (tolerant, not a full IBIS parser)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    models: list[IbisModelInfo] = []
    current: IbisModelInfo | None = None
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("|") or raw.startswith("#"):
            continue
        upper = raw.upper()
        if upper.startswith("[MODEL]"):
            name = raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) > 1 else ""
            current = IbisModelInfo(name=name, model_type="unknown", path=str(path))
            models.append(current)
        elif current and upper.startswith("MODEL_TYPE"):
            parts = re.split(r"\s+", raw, maxsplit=1)
            if len(parts) > 1:
                current.model_type = parts[1].strip()
    return models
