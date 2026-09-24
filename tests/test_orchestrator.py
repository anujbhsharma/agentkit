"""Tests for dependency ordering, cycle detection, and concurrent runs."""

import threading
import time

import pytest

from agentkit.agents import Agent
from agentkit.backends import EchoBackend
from agentkit.orchestrator import CycleError, Orchestrator
from agentkit.spec import Task


def t(task_id: str, *deps: str) -> Task:
    return Task(id=task_id, title=task_id, depends_on=list(deps))


def make_orchestrator(**kw) -> Orchestrator:
    return Orchestrator(Agent("w", backend=EchoBackend()), **kw)


def test_topological_order_respects_dependencies():
    orch = make_orchestrator()
    tasks = [t("d", "b", "c"), t("b", "a"), t("c", "a"), t("a")]
    ordered = orch.order(tasks)
    pos = {task.id: i for i, task in enumerate(ordered)}
    assert pos["a"] < pos["b"] < pos["d"]
    assert pos["a"] < pos["c"] < pos["d"]


def test_order_preserves_independent_tasks():
    orch = make_orchestrator()
    tasks = [t("x"), t("y"), t("z")]
    assert [task.id for task in orch.order(tasks)] == ["x", "y", "z"]


def test_cycle_detection_two_nodes():
    orch = make_orchestrator()
    with pytest.raises(CycleError, match="[Cc]ycle"):
        orch.order([t("a", "b"), t("b", "a")])


def test_cycle_detection_self_dependency():
    orch = make_orchestrator()
    with pytest.raises(CycleError):
        orch.order([t("a", "a")])


def test_cycle_detection_longer_loop():
    orch = make_orchestrator()
    tasks = [t("a", "c"), t("b", "a"), t("c", "b"), t("ok")]
    with pytest.raises(CycleError) as exc_info:
        orch.order(tasks)
    # The message names the stuck tasks so it's debuggable.
    for stuck in ("a", "b", "c"):
        assert stuck in str(exc_info.value)


def test_unknown_dependency_raises_clear_error():
    orch = make_orchestrator()
    with pytest.raises(ValueError, match="unknown task 'ghost'"):
        orch.order([t("a", "ghost")])


def test_run_executes_all_tasks_with_context():
    prompts: dict[str, str] = {}

    def recording(prompt: str) -> str:
        # task id is embedded as "Task [id]:" in the prompt.
        for line in prompt.splitlines():
            if line.startswith("Task ["):
                tid = line.split("[")[1].split("]")[0]
                prompts[tid] = prompt
        return f"output-for-task"

    orch = Orchestrator(Agent("w", backend=recording), max_workers=4)
    tasks = [t("a"), t("b", "a"), t("c", "a"), t("d", "b", "c")]
    report = orch.run(tasks)

    assert report.succeeded
    assert set(report.results) == {"a", "b", "c", "d"}
    # 'a' had no context; dependents saw 'a's output.
    assert "output of 'a'" not in prompts["a"]
    assert "output-for-task" in prompts["b"]
    assert "output-for-task" in prompts["c"]
    assert "output-for-task" in prompts["d"]


def test_independent_tasks_run_concurrently():
    active = {"current": 0, "peak": 0}
    lock = threading.Lock()

    def slow(prompt: str) -> str:
        with lock:
            active["current"] += 1
            active["peak"] = max(active["peak"], active["current"])
        time.sleep(0.2)
        with lock:
            active["current"] -= 1
        return "done"

    orch = Orchestrator(Agent("w", backend=slow), max_workers=4)
    report = orch.run([t("a"), t("b"), t("c"), t("d")])
    assert report.succeeded
    assert active["peak"] >= 2  # real parallelism happened


def test_failed_task_does_not_block_dependents():
    def sometimes(prompt: str) -> str:
        if "Task [bad]" in prompt:
            raise RuntimeError("always fails")
        return "fine"

    orch = Orchestrator(Agent("w", backend=sometimes, retries=1), max_workers=2)
    report = orch.run([t("bad"), t("downstream", "bad")])
    assert not report.succeeded
    assert not report.results["bad"].ok
    assert report.results["downstream"].ok  # still ran
    assert len(report.failed) == 1


def test_report_markdown_contains_tasks():
    orch = make_orchestrator()
    report = orch.run([t("alpha"), t("beta", "alpha")])
    md = report.to_markdown()
    assert "alpha" in md and "beta" in md
    assert "ok" in md


def test_empty_run():
    orch = make_orchestrator()
    report = orch.run([])
    assert report.results == {}
    assert not report.succeeded  # nothing ran


def test_invalid_max_workers():
    with pytest.raises(ValueError):
        Orchestrator(Agent("w", backend=EchoBackend()), max_workers=0)
