"""Batteries-included web UI for agentkit: ``agentkit serve``.

A tiny HTTP server built only on the standard library. It serves a
single-page UI (``static/index.html``) and a small JSON API:

- ``GET /api/examples`` → ``[{name, content}]`` — the bundled example specs.
- ``POST /api/run`` with ``{"spec": "...", "workers": 4}`` →
  ``{"tasks": [{id, title, status, attempts, output, error}],
     "report_markdown": "..."}``.

Runs go through the deterministic ``EchoBackend`` demo backend; real model
backends plug in via the Python API (see "Bring your own model" in the
README). Errors are returned as clean JSON — tracebacks never reach the
client.
"""

from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .agents import Agent
from .backends import EchoBackend
from .orchestrator import CycleError, Orchestrator
from .spec import parse_spec

_HERE = Path(__file__).resolve().parent
STATIC_DIR = _HERE / "static"
EXAMPLES_DIR = _HERE.parent / "examples"

MAX_BODY_BYTES = 1_000_000
MAX_SPEC_CHARS = 500_000
MAX_WORKERS = 32


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _error(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    _json(handler, status, {"error": message})


def list_examples() -> list[dict[str, str]]:
    """Return the bundled example specs as ``[{name, content}]``."""
    examples = []
    if EXAMPLES_DIR.is_dir():
        for path in sorted(EXAMPLES_DIR.glob("*.md")):
            examples.append(
                {"name": path.name, "content": path.read_text(encoding="utf-8")}
            )
    return examples


def run_spec_text(spec_text: str, workers: int = 4) -> dict:
    """Run a spec given as a string; return the JSON-serializable result.

    Uses :class:`Orchestrator` + :class:`EchoBackend` directly (rather than
    :func:`run_spec`) so parallel HTTP requests don't race on a shared
    ``report.md`` in the working directory.

    Raises:
        ValueError: Bad spec (no tasks, unknown dependency, cycle, ...).
    """
    if not isinstance(spec_text, str) or not spec_text.strip():
        raise ValueError("spec must be a non-empty string")
    if len(spec_text) > MAX_SPEC_CHARS:
        raise ValueError(
            f"spec is too large (max {MAX_SPEC_CHARS} characters)"
        )

    # parse_spec reads from a path, so stage the text in a temp file.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", encoding="utf-8", delete=True
    ) as tmp:
        tmp.write(spec_text)
        tmp.flush()
        tasks = parse_spec(tmp.name)

    if not tasks:
        raise ValueError("spec contains no tasks (need at least one '## heading')")

    orchestrator = Orchestrator(
        Agent(name="agentkit", backend=EchoBackend()), max_workers=workers
    )
    report = orchestrator.run(tasks)
    ordered = orchestrator.order(tasks)

    cards = []
    for task in ordered:
        result = report.results[task.id]
        cards.append(
            {
                "id": task.id,
                "title": task.title,
                "status": "ok" if result.ok else "error",
                "attempts": result.attempts,
                "output": result.output,
                "error": result.error,
                "depends_on": list(task.depends_on),
            }
        )
    return {"tasks": cards, "report_markdown": report.to_markdown()}


class _Handler(BaseHTTPRequestHandler):
    server_version = "agentkit-ui/0.1.0"

    def log_message(self, fmt: str, *args: object) -> None:  # quieter logs
        pass

    # -- routing ------------------------------------------------------
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_index()
        elif self.path == "/api/examples":
            _json(self, 200, {"examples": list_examples()})
        else:
            _error(self, 404, "not found")

    def do_POST(self) -> None:
        if self.path == "/api/run":
            self._handle_run()
        else:
            _error(self, 404, "not found")

    # -- pages / api ---------------------------------------------------
    def _serve_index(self) -> None:
        index = STATIC_DIR / "index.html"
        if not index.is_file():
            _error(self, 500, "UI bundle missing (static/index.html not found)")
            return
        body = index.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            raise ValueError("empty request body")
        if length > MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _handle_run(self) -> None:
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            _error(self, 400, str(exc))
            return

        workers = payload.get("workers", 4)
        try:
            workers = int(workers)
        except (TypeError, ValueError):
            _error(self, 400, "workers must be an integer")
            return
        if not 1 <= workers <= MAX_WORKERS:
            _error(
                self,
                400,
                f"workers must be between 1 and {MAX_WORKERS}",
            )
            return

        try:
            result = run_spec_text(payload.get("spec", ""), workers=workers)
        except (ValueError, CycleError) as exc:
            # Bad spec, unknown dependency, dependency cycle...
            _error(self, 400, str(exc))
        except Exception as exc:  # never leak a traceback to the client
            _error(self, 500, f"run failed: {type(exc).__name__}")
        else:
            _json(self, 200, result)


def make_server(port: int = 8000) -> ThreadingHTTPServer:
    """Build (but don't start) the UI server."""
    return ThreadingHTTPServer(("127.0.0.1", port), _Handler)


def serve(port: int = 8000) -> None:
    """Start the web UI and block until interrupted."""
    server = make_server(port)
    actual = server.server_address[1]
    print(f"agentkit UI running at http://127.0.0.1:{actual}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def serve_in_thread(port: int = 0) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start the server in a daemon thread; handy for tests and embedding."""
    server = make_server(port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
