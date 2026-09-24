"""Parse markdown spec files into Task objects.

Spec format::

    # Optional document title (ignored)

    ## Do the thing
    Free-form detail text for the agent...

    depends: other-task, another-task

    ## Other task
    Detail for this one. No dependencies.

Rules:
- ``## Heading`` lines start a new task. The task id is the slugified
  heading (lowercase, non-alphanumerics become dashes).
- A line matching ``depends: id1, id2`` (case-insensitive) declares
  dependencies on other task ids. It is metadata, not detail text.
- Everything else under a heading is the task's detail.
- Duplicate headings get ``-2``, ``-3`` suffixes so ids stay unique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DEPENDS_RE = re.compile(r"^\s*depends\s*:\s*(.+?)\s*$", re.IGNORECASE)


@dataclass
class Task:
    """A single unit of work parsed from a spec file."""

    id: str
    title: str
    detail: str = ""
    depends_on: list[str] = field(default_factory=list)


def slugify(text: str) -> str:
    """Turn a heading into a URL-friendly id."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "task"


def parse_spec(path: str | Path) -> list[Task]:
    """Read a markdown spec file and return its tasks in document order."""
    text = Path(path).read_text(encoding="utf-8")

    tasks: list[Task] = []
    seen: dict[str, int] = {}
    title: str | None = None
    detail_lines: list[str] = []
    depends: list[str] = []

    def flush() -> None:
        nonlocal title, detail_lines, depends
        if title is None:
            return
        base = slugify(title)
        n = seen.get(base, 0)
        seen[base] = n + 1
        task_id = base if n == 0 else f"{base}-{n + 1}"
        tasks.append(
            Task(
                id=task_id,
                title=title,
                detail="\n".join(detail_lines).strip(),
                depends_on=depends,
            )
        )
        title, detail_lines, depends = None, [], []

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            title = line[3:].strip()
            continue
        if title is None:
            continue  # preamble / document title: not a task
        match = DEPENDS_RE.match(line)
        if match:
            depends = [d.strip() for d in match.group(1).split(",") if d.strip()]
            continue
        detail_lines.append(line)

    flush()
    return tasks
