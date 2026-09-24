"""Command-line interface: ``agentkit run SPEC.md``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backends import EchoBackend
from .runner import run_spec
from .server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentkit",
        description="Run a markdown spec as a multi-agent workflow.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Execute a spec file.")
    run_p.add_argument("spec", help="Path to the SPEC.md file.")
    run_p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Max concurrent tasks per wave (default: 4).",
    )
    run_p.add_argument(
        "--out",
        default="report.md",
        help="Where to write the markdown report (default: report.md).",
    )

    serve_p = sub.add_parser("serve", help="Start the web UI.")
    serve_p.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "run":
        spec = Path(args.spec)
        if not spec.is_file():
            print(f"error: spec file not found: {spec}", file=sys.stderr)
            return 2
        # The CLI ships with the deterministic demo backend.
        # For real models, use the Python API: run_spec(path, my_backend).
        report = run_spec(str(spec), EchoBackend(), max_workers=args.workers)
        out = Path(args.out)
        if out.resolve() != Path("report.md").resolve():
            out.write_text(report.to_markdown(), encoding="utf-8")

        ok = sum(1 for r in report.results.values() if r.ok)
        total = len(report.results)
        print(f"ran {total} task(s): {ok} ok, {total - ok} failed -> {args.out}")
        for task in report.tasks:
            result = report.results[task.id]
            mark = "ok" if result.ok else "FAIL"
            print(f"  [{mark}] {task.id} ({result.attempts} attempt(s))")
        return 0 if report.succeeded else 1

    if args.command == "serve":
        serve(port=args.port)
        return 0

    return 2  # unreachable with required subparsers


if __name__ == "__main__":
    raise SystemExit(main())
