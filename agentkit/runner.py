"""High-level entry point: spec file in, run report out."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .agents import Agent
from .orchestrator import Orchestrator, Report
from .spec import parse_spec


def run_spec(
    spec_path: str | Path,
    backend: Callable[[str], str],
    max_workers: int = 4,
) -> Report:
    """Parse a spec, run it through an agent, write ``report.md``.

    Args:
        spec_path: Path to the markdown spec file.
        backend: Callable ``(prompt: str) -> str`` — a model function,
            or a fake like :class:`agentkit.backends.EchoBackend`.
        max_workers: How many tasks may run concurrently per wave.

    Returns:
        The :class:`Report`. A ``report.md`` summary is also written to
        the current working directory.
    """
    tasks = parse_spec(spec_path)
    agent = Agent(name="agentkit", backend=backend)
    report = Orchestrator(agent, max_workers=max_workers).run(tasks)
    Path("report.md").write_text(report.to_markdown(), encoding="utf-8")
    return report
