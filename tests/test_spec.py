"""Tests for spec parsing."""

from pathlib import Path

import pytest

from agentkit.spec import Task, parse_spec, slugify


def write_spec(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "spec.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_slugify():
    assert slugify("Do The Thing!") == "do-the-thing"
    assert slugify("  Spaces   Everywhere  ") == "spaces-everywhere"
    assert slugify("!!!") == "task"


def test_basic_two_tasks(tmp_path):
    p = write_spec(
        tmp_path,
        "# My Spec\n\n## First Task\nSome detail.\n\n## Second Task\nMore detail.\n",
    )
    tasks = parse_spec(p)
    assert [t.id for t in tasks] == ["first-task", "second-task"]
    assert tasks[0].title == "First Task"
    assert tasks[0].detail == "Some detail."
    assert tasks[1].depends_on == []


def test_depends_line_parsed_and_not_in_detail(tmp_path):
    p = write_spec(
        tmp_path,
        "## Build\nBuild it.\ndepends: plan, design\nMore words.\n",
    )
    (task,) = parse_spec(p)
    assert task.depends_on == ["plan", "design"]
    assert "depends:" not in task.detail.lower()
    assert "Build it." in task.detail
    assert "More words." in task.detail


def test_depends_case_insensitive_and_spacing(tmp_path):
    p = write_spec(tmp_path, "## X\nDepends:  a ,b,c  \n")
    (task,) = parse_spec(p)
    assert task.depends_on == ["a", "b", "c"]


def test_duplicate_headings_get_unique_ids(tmp_path):
    p = write_spec(tmp_path, "## Audit\none\n\n## Audit\ntwo\n\n## Audit\nthree\n")
    tasks = parse_spec(p)
    assert [t.id for t in tasks] == ["audit", "audit-2", "audit-3"]


def test_preamble_and_doc_title_ignored(tmp_path):
    p = write_spec(
        tmp_path,
        "# Big Plan\n\nSome intro prose.\n\n## Real Task\nThe work.\n",
    )
    tasks = parse_spec(p)
    assert len(tasks) == 1
    assert tasks[0].id == "real-task"


def test_empty_spec(tmp_path):
    p = write_spec(tmp_path, "# Nothing here\n\nJust prose.\n")
    assert parse_spec(p) == []


def test_subheadings_stay_in_detail(tmp_path):
    p = write_spec(tmp_path, "## Task\n### A subheading\nBody.\n")
    (task,) = parse_spec(p)
    assert "### A subheading" in task.detail


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_spec("/does/not/exist.md")


def test_task_dataclass_defaults():
    t = Task(id="x", title="X")
    assert t.detail == ""
    assert t.depends_on == []
