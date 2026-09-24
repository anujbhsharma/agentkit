"""Regenerate the recorded demo runs served by the GitHub Pages demo.

Reads ``examples/*.md`` and executes each with the real ``Orchestrator`` +
``EchoBackend`` pipeline — the same components ``agentkit serve``'s
``POST /api/run`` uses (see ``agentkit.server.run_spec_text``) — then writes
``docs/runs/<name>.json``.

One deliberate difference from a live run: the report's ``started_at`` /
``finished_at`` timestamps are cleared before rendering, so the artifact is
fully deterministic — re-running this script produces byte-identical JSON.
Everything else (task outputs, ordering, report sections) is exactly what the
live code produces.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make the repo root importable no matter where this is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentkit.agents import Agent
from agentkit.backends import EchoBackend
from agentkit.orchestrator import Orchestrator
from agentkit.spec import parse_spec

HERE = Path(__file__).resolve().parent
EXAMPLES_DIR = HERE.parent / "examples"
RUNS_DIR = HERE / "runs"

EXAMPLES = ["website-audit.md", "research-brief.md"]
WORKERS = 4


def run_example(name: str) -> dict:
    """Run one example spec; return the recorded payload (timestamps cleared)."""
    spec_text = (EXAMPLES_DIR / name).read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", encoding="utf-8", delete=True
    ) as tmp:
        tmp.write(spec_text)
        tmp.flush()
        tasks = parse_spec(tmp.name)

    orchestrator = Orchestrator(
        Agent(name="agentkit", backend=EchoBackend()), max_workers=WORKERS
    )
    report = orchestrator.run(tasks)
    # Clear wall-clock timestamps so the artifact is deterministic.
    report.started_at = ""
    report.finished_at = ""

    ordered = orchestrator.order(tasks)
    cards = [
        {
            "id": task.id,
            "title": task.title,
            "status": "ok" if report.results[task.id].ok else "error",
            "attempts": report.results[task.id].attempts,
            "output": report.results[task.id].output,
            "error": report.results[task.id].error,
            "depends_on": list(task.depends_on),
        }
        for task in ordered
    ]
    return {
        "spec_name": name,
        "tasks": cards,
        "report_markdown": report.to_markdown(),
    }


def main() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    for name in EXAMPLES:
        payload = run_example(name)
        out = RUNS_DIR / f"{Path(name).stem}.json"
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        ok = sum(1 for t in payload["tasks"] if t["status"] == "ok")
        print(f"wrote {out} ({len(payload['tasks'])} tasks, {ok} ok)")


if __name__ == "__main__":
    main()
