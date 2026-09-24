"""Tests for the agentkit web UI: `agentkit serve` and its JSON API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from agentkit.server import serve_in_thread

TINY_SPEC = """\
# Tiny

## First task
Do the first thing.

## Second task
depends: first-task
Do the second thing with the first thing's output.
"""

CYCLE_SPEC = """\
# Cyclic

## Task a
depends: task-b
A needs B.

## Task b
depends: task-a
B needs A.
"""


@pytest.fixture()
def server():
    srv, thread = serve_in_thread(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    thread.join(timeout=5)
    srv.server_close()


def _get(base: str, path: str):
    with urllib.request.urlopen(base + path) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def _post(base: str, path: str, payload: dict):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_index_returns_html(server):
    status, content_type, body = _get(server, "/")
    assert status == 200
    assert "text/html" in content_type
    text = body.decode("utf-8")
    assert "<html" in text
    assert "agentkit" in text
    # No build step: the UI is one self-contained file, no CDN references.
    assert "http://" not in text and "https://" not in text


def test_examples_endpoint(server):
    status, _content_type, data = _get(server, "/api/examples")
    assert status == 200
    examples = json.loads(data.decode("utf-8"))["examples"]
    names = [e["name"] for e in examples]
    assert "website-audit.md" in names
    assert "research-brief.md" in names
    assert all(e["content"].strip() for e in examples)


def test_run_two_task_spec(server):
    status, data = _post(server, "/api/run", {"spec": TINY_SPEC, "workers": 2})
    assert status == 200
    assert len(data["tasks"]) == 2
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["first-task"]["status"] == "ok"
    assert by_id["second-task"]["status"] == "ok"
    assert all(t["attempts"] >= 1 for t in data["tasks"])
    assert all(t["output"] for t in data["tasks"])
    # Dependency order: the prerequisite comes first.
    assert [t["id"] for t in data["tasks"]] == ["first-task", "second-task"]
    assert "First task" in data["report_markdown"]
    assert "Second task" in data["report_markdown"]


def test_run_invalid_spec_returns_clean_json_error(server):
    status, data = _post(server, "/api/run", {"spec": CYCLE_SPEC, "workers": 2})
    assert status == 400
    assert "error" in data
    assert "cycle" in data["error"].lower()
    assert "Traceback" not in json.dumps(data)


def test_run_rejects_bad_workers(server):
    status, data = _post(server, "/api/run", {"spec": TINY_SPEC, "workers": 99})
    assert status == 400
    assert "error" in data


def test_run_rejects_empty_spec(server):
    status, data = _post(server, "/api/run", {"spec": "   ", "workers": 2})
    assert status == 400
    assert "error" in data


def test_unknown_path_is_json_404(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(server + "/nope")
    assert excinfo.value.code == 404
    body = json.loads(excinfo.value.read().decode("utf-8"))
    assert "error" in body
