"""End-to-end: spec file -> run_spec -> report.md."""

from pathlib import Path

from agentkit.backends import EchoBackend
from agentkit.runner import run_spec

SPEC = """\
# Website refresh

## Crawl sitemap
List every URL on the site and note response codes.

## Lighthouse audit
depends: crawl-sitemap
Run performance and SEO audits on the top 10 pages.

## Accessibility check
depends: crawl-sitemap
Run axe checks on key templates.

## Write summary
depends: lighthouse-audit, accessibility-check
Summarize findings and rank fixes by impact.
"""


def test_end_to_end_run(tmp_path, monkeypatch):
    spec = tmp_path / "plan.md"
    spec.write_text(SPEC, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    backend = EchoBackend()
    report = run_spec(spec, backend, max_workers=2)

    assert report.succeeded
    assert [t.id for t in report.tasks] == [
        "crawl-sitemap",
        "lighthouse-audit",
        "accessibility-check",
        "write-summary",
    ]
    assert set(report.results) == {t.id for t in report.tasks}
    assert all(r.ok and r.attempts == 1 for r in report.results.values())
    # EchoBackend is deterministic: same prompt -> same output.
    assert len(backend.calls) == 4

    report_md = tmp_path / "report.md"
    assert report_md.is_file()
    text = report_md.read_text(encoding="utf-8")
    assert "# agentkit run report" in text
    assert "write-summary" in text
    assert "[echo:" in text


def test_end_to_end_empty_spec(tmp_path, monkeypatch):
    spec = tmp_path / "empty.md"
    spec.write_text("# Nothing\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    report = run_spec(spec, EchoBackend())
    assert report.results == {}
    assert (tmp_path / "report.md").is_file()
