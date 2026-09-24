"""Agent abstraction: a named worker with a pluggable backend callable.

An ``Agent`` pairs a name with a ``backend`` — any callable that takes a
prompt string and returns a string. That backend can be a stub in tests,
a demo echo, or a real model call in production (see ``backends``).

``Agent.run`` executes one task with configurable retries and a
per-attempt timeout, and always returns a ``Result`` — it never raises
for backend failures, so one bad task can't take down a whole run.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Callable

from .spec import Task

# A backend is anything that turns a prompt into text.
Backend = Callable[[str], str]


@dataclass
class Result:
    """The outcome of running one task."""

    task_id: str
    output: str = ""
    attempts: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the task completed without exhausting retries."""
        return self.error is None


class Agent:
    """A named worker that runs tasks through a backend callable.

    Args:
        name: Display name, included in prompts.
        backend: Callable ``(prompt: str) -> str``. May raise; failures
            are retried.
        retries: Number of *extra* attempts after the first failure.
            ``retries=2`` means up to 3 total attempts.
        timeout: Per-attempt wall-clock timeout in seconds.
    """

    def __init__(
        self,
        name: str,
        backend: Backend,
        retries: int = 2,
        timeout: float = 60.0,
    ) -> None:
        if retries < 0:
            raise ValueError("retries must be >= 0")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        self.name = name
        self.backend = backend
        self.retries = retries
        self.timeout = timeout

    def build_prompt(self, task: Task, context: dict[str, str] | None = None) -> str:
        """Assemble the prompt for a task, including dependency outputs."""
        context = context or {}
        parts = [
            f"You are {self.name}, an autonomous worker agent.",
            "",
            f"Task [{task.id}]: {task.title}",
            "",
            task.detail.strip(),
        ]
        if context:
            parts.append("")
            parts.append("Context from completed dependencies:")
            for dep_id, output in context.items():
                parts.append("")
                parts.append(f"--- output of '{dep_id}' ---")
                parts.append(output)
        return "\n".join(parts).strip()

    def _attempt(self, prompt: str) -> str:
        """Run the backend once, enforcing the per-attempt timeout."""
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(self.backend, prompt)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"backend timed out after {self.timeout}s"
                ) from exc
        finally:
            # Don't wait: a timed-out backend may still be running, and
            # waiting would defeat the purpose of the timeout.
            pool.shutdown(wait=False, cancel_futures=True)

    def run(self, task: Task, context: dict[str, str] | None = None) -> Result:
        """Run a task, retrying on failure. Never raises for backend errors."""
        prompt = self.build_prompt(task, context)
        last_error: BaseException | None = None
        attempts = 0
        for _ in range(self.retries + 1):
            attempts += 1
            try:
                output = self._attempt(prompt)
                return Result(task_id=task.id, output=output, attempts=attempts)
            except Exception as exc:  # noqa: BLE001 — retries cover backend faults
                last_error = exc
        return Result(
            task_id=task.id,
            output="",
            attempts=attempts,
            error=f"{type(last_error).__name__}: {last_error}",
        )
