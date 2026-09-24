"""Dependency-aware orchestration: topological ordering plus fan-out/fan-in.

The ``Orchestrator`` takes a set of tasks, validates and orders them by
their ``depends_on`` edges, then executes them in waves: every task whose
dependencies have all finished runs concurrently in a thread pool, and
each task receives the outputs of its dependencies as prompt context.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agents import Agent, Result
from .spec import Task


class CycleError(ValueError):
    """Raised when task dependencies contain a cycle."""


@dataclass
class Report:
    """Everything about one orchestrated run."""

    tasks: list[Task]
    results: dict[str, Result]
    started_at: str = ""
    finished_at: str = ""

    @property
    def succeeded(self) -> bool:
        """True when every task completed without error."""
        return bool(self.results) and all(r.ok for r in self.results.values())

    @property
    def failed(self) -> list[Result]:
        """Results for tasks that exhausted their retries."""
        return [r for r in self.results.values() if not r.ok]

    def to_markdown(self) -> str:
        """Render the report as markdown."""
        lines = ["# agentkit run report", ""]
        if self.started_at:
            lines.append(f"_Started: {self.started_at}_")
        if self.finished_at:
            lines.append(f"_Finished: {self.finished_at}_")
        total = len(self.results)
        ok = sum(1 for r in self.results.values() if r.ok)
        lines.append(f"_Tasks: {total}, succeeded: {ok}, failed: {total - ok}_")
        lines.append("")
        for task in self.tasks:
            result = self.results.get(task.id)
            if result is None:
                status = "skipped"
            elif result.ok:
                status = "ok"
            else:
                status = "failed"
            attempts = result.attempts if result else 0
            lines.append(f"## {task.title} `{task.id}` — {status} ({attempts} attempt(s))")
            lines.append("")
            if task.depends_on:
                lines.append(f"_Depends on: {', '.join(task.depends_on)}_")
                lines.append("")
            if result and result.ok:
                lines.append("```")
                lines.append(result.output)
                lines.append("```")
            elif result:
                lines.append(f"> Error: {result.error}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


class Orchestrator:
    """Runs tasks in dependency order, fanning out independent work.

    Args:
        agent: The worker used for every task.
        max_workers: Thread pool size for each concurrent wave.
    """

    def __init__(self, agent: Agent, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self.agent = agent
        self.max_workers = max_workers

    @staticmethod
    def _validate(tasks: list[Task]) -> dict[str, Task]:
        by_id = {t.id: t for t in tasks}
        for task in tasks:
            for dep in task.depends_on:
                if dep not in by_id:
                    raise ValueError(
                        f"Task '{task.id}' depends on unknown task '{dep}'"
                    )
        return by_id

    def order(self, tasks: list[Task]) -> list[Task]:
        """Return tasks in topological order. Raises CycleError on cycles."""
        by_id = self._validate(tasks)
        # Kahn's algorithm.
        indegree = {t.id: 0 for t in tasks}
        dependents: dict[str, list[str]] = {t.id: [] for t in tasks}
        for task in tasks:
            for dep in task.depends_on:
                indegree[task.id] += 1
                dependents[dep].append(task.id)
        queue = [tid for tid, deg in indegree.items() if deg == 0]
        ordered: list[str] = []
        while queue:
            tid = queue.pop(0)
            ordered.append(tid)
            for child in dependents[tid]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if len(ordered) != len(tasks):
            stuck = sorted(set(indegree) - set(ordered))
            raise CycleError(
                "Dependency cycle detected among tasks: " + ", ".join(stuck)
            )
        return [by_id[tid] for tid in ordered]

    def run(self, tasks: list[Task]) -> Report:
        """Execute tasks wave by wave; return a Report. Never partially skips.

        Each wave runs every task whose dependencies are all finished.
        A task's prompt context contains the outputs of its dependencies.
        Failed tasks still count as finished for wave purposes, and their
        error is recorded in the report.
        """
        by_id = self._validate(tasks)
        # Fail fast on cycles with a clear message.
        self.order(tasks)

        started_at = datetime.now(timezone.utc).isoformat()
        results: dict[str, Result] = {}
        remaining = dict(by_id)
        finished: set[str] = set()

        while remaining:
            ready = [
                t
                for t in remaining.values()
                if all(d in finished for d in t.depends_on)
            ]
            # order() already ruled out cycles, so ready is never empty here.
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(
                        self.agent.run,
                        task,
                        {d: results[d].output for d in task.depends_on},
                    ): task
                    for task in ready
                }
                for future in as_completed(futures):
                    task = futures[future]
                    results[task.id] = future.result()
            for task in ready:
                finished.add(task.id)
                del remaining[task.id]

        finished_at = datetime.now(timezone.utc).isoformat()
        return Report(
            tasks=list(tasks),
            results=results,
            started_at=started_at,
            finished_at=finished_at,
        )
