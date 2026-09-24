"""Tests for Agent retry and timeout behavior."""

import time

import pytest

from agentkit.agents import Agent, Result
from agentkit.spec import Task


def make_task(task_id: str = "demo") -> Task:
    return Task(id=task_id, title="Demo", detail="Do it.")


def test_success_first_try():
    agent = Agent("a", backend=lambda prompt: "done", retries=2)
    result = agent.run(make_task())
    assert result.ok
    assert result.output == "done"
    assert result.attempts == 1
    assert result.error is None


def test_flaky_backend_succeeds_on_retry():
    calls = {"n": 0}

    def flaky(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "recovered"

    agent = Agent("a", backend=flaky, retries=3)
    result = agent.run(make_task())
    assert result.ok
    assert result.output == "recovered"
    assert result.attempts == 3


def test_always_failing_backend_records_error():
    def bad(prompt: str) -> str:
        raise ValueError("nope")

    agent = Agent("a", backend=bad, retries=2)
    result = agent.run(make_task())
    assert not result.ok
    assert result.attempts == 3  # 1 initial + 2 retries
    assert "ValueError" in result.error
    assert "nope" in result.error


def test_zero_retries_means_single_attempt():
    agent = Agent("a", backend=lambda p: (_ for _ in ()).throw(RuntimeError("x")), retries=0)
    result = agent.run(make_task())
    assert result.attempts == 1
    assert not result.ok


def test_timeout_triggers_retry_and_error():
    def slow(prompt: str) -> str:
        time.sleep(5)
        return "too late"

    agent = Agent("a", backend=slow, retries=1, timeout=0.05)
    started = time.monotonic()
    result = agent.run(make_task())
    elapsed = time.monotonic() - started
    assert not result.ok
    assert result.attempts == 2
    assert "timed out" in result.error
    assert elapsed < 4  # proves we didn't wait out the 5s sleep


def test_prompt_includes_context():
    seen: list[str] = []
    agent = Agent("worker", backend=lambda p: seen.append(p) or "ok")
    task = make_task("child")
    agent.run(task, context={"parent": "parent-output-here"})
    assert "parent-output-here" in seen[0]
    assert "child" in seen[0]
    assert "worker" in seen[0]


def test_result_ok_property():
    assert Result(task_id="t", output="x").ok
    assert not Result(task_id="t", error="bad").ok


def test_invalid_agent_config():
    with pytest.raises(ValueError):
        Agent("a", backend=lambda p: "x", retries=-1)
    with pytest.raises(ValueError):
        Agent("a", backend=lambda p: "x", timeout=0)
