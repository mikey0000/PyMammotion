"""Dataclasses + helpers for structured scenario reporting.

A ``ScenarioReport`` captures the outcome of a single scenario run: per-step
timing and OK/FAIL state, the final ``result_counts`` (areas, frames, …),
and on failure a ``failure`` block with exception type + a *depth snapshot*
(how far the saga got before it raised).

These are intentionally plain dataclasses with ``to_dict`` for JSON dumping
so a REPL user can ``print(report)`` *or* ``json.dumps(report.to_dict())``
without ceremony.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


@dataclass
class ScenarioStep:
    """One observable step inside a scenario."""

    name: str
    ok: bool
    duration_s: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioReport:
    """Outcome of a single scenario run."""

    name: str
    transport: str  # "mqtt" | "ble" | "unknown"
    device_name: str
    ok: bool
    started_at: str  # ISO 8601, UTC
    duration_s: float
    steps: list[ScenarioStep] = field(default_factory=list)
    failure: dict[str, Any] | None = None
    result_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return dataclasses.asdict(self)

    def pretty(self) -> str:
        """Multi-line human-readable summary."""
        status = "PASS" if self.ok else "FAIL"
        lines = [
            f"[{status}] {self.name} ({self.transport}) on {self.device_name}",
            f"  started:  {self.started_at}",
            f"  duration: {self.duration_s:.2f}s",
        ]
        for step in self.steps:
            mark = "ok " if step.ok else "FAIL"
            extra = f"  {step.details}" if step.details else ""
            lines.append(f"    - [{mark}] {step.name} ({step.duration_s:.2f}s){extra}")
        if self.failure is not None:
            lines.append(f"  failure: {self.failure.get('type')}: {self.failure.get('message')}")
            last_step = self.failure.get("last_step")
            if last_step:
                lines.append(f"  reached step: {last_step}")
            snapshot = self.failure.get("snapshot")
            if snapshot:
                lines.append(f"  snapshot:    {snapshot}")
        if self.result_counts:
            lines.append(f"  counts:   {self.result_counts}")
        return "\n".join(lines)

    def __str__(self) -> str:  # pragma: no cover - REPL convenience
        return self.pretty()


def utc_now_iso() -> str:
    """Return an ISO 8601 timestamp in UTC, second-precision."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def dump_report(report: ScenarioReport, output_dir: Path | str | None = None) -> Path:
    """Write *report* as JSON under ``examples/dev_output/`` (or *output_dir*).

    The filename is ``scenario_report_{name}_{transport}_{timestamp}.json``.
    Returns the path written.
    """
    out = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parent.parent / "dev_output"
    out.mkdir(parents=True, exist_ok=True)
    ts = report.started_at.replace(":", "").replace("-", "").replace("+0000", "Z")
    path = out / f"scenario_report_{report.name}_{report.transport}_{ts}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
    return path


def dump_aggregate(reports: dict[str, ScenarioReport], output_dir: Path | str | None = None) -> Path:
    """Write an aggregated batch report ``scenario_report_all_{timestamp}.json``."""
    out = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parent.parent / "dev_output"
    out.mkdir(parents=True, exist_ok=True)
    ts = utc_now_iso().replace(":", "").replace("-", "").replace("+0000", "Z")
    path = out / f"scenario_report_all_{ts}.json"
    body = {
        "generated_at": utc_now_iso(),
        "reports": {name: r.to_dict() for name, r in reports.items()},
        "summary": {name: {"ok": r.ok, "duration_s": r.duration_s} for name, r in reports.items()},
    }
    path.write_text(json.dumps(body, indent=2, default=str))
    return path
