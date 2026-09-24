# agentkit

A small, sharp toolkit for orchestrating multi-agent workflows. You write a
markdown spec, agentkit turns the headings into tasks, sorts them by
dependency, fans the independent ones out across threads, feeds each task
the outputs of its dependencies, and hands you a report. That's the whole
trick — and it's enough to run surprisingly serious pipelines.

No frameworks, no YAML DSLs, no orchestration servers. A spec file, a model
function, and a report.

## How it works

```
 SPEC.md (## headings = tasks, "depends:" = edges)
     │
     ▼
 parse_spec() ──► [Task graph]
     │
     ▼  topological sort (cycles → loud, clear error)
 ┌───┴───────────────────────────────┐
 │  wave 1: task A        task B      │  ◄── independent tasks run
 │            │               │       │      concurrently (threads)
 │            └──────┬────────┘       │
 │                   ▼                │
 │  wave 2: task C (gets A + B        │  ◄── dependency outputs become
 │          outputs as prompt context)│      prompt context (fan-in)
 └───────────────────────────────────┘
     │
     ▼
 report.md + Report object
```

Each task is executed by an `Agent`: a name plus a *backend* — any callable
`(prompt: str) -> str`. Agents get configurable retries and a per-attempt
timeout, and they never raise for backend failures: a dead task records its
error in the report instead of killing the run.

## Quickstart

```python
from agentkit import run_spec
from agentkit.backends import EchoBackend

# Dry run with the deterministic fake backend (no network, no cost).
report = run_spec("examples/website-audit.md", EchoBackend(), max_workers=4)

print(report.succeeded)          # True
print(report.results["write-summary"].output)
# → "[echo:9f2ac41d] processed prompt (812 chars, 24 lines)"
```

Or from the command line:

```bash
pip install .
agentkit run examples/website-audit.md --workers 4 --out report.md
```

## Bring your own model

A backend is one function. That's the entire interface:

```python
import os
from anthropic import Anthropic
from agentkit import run_spec

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def claude_backend(prompt: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

run_spec("SPEC.md", backend=claude_backend)
```

Works the same with OpenAI, a local Ollama server, or a stub in your
tests — raise on errors and agentkit's retries do the rest.

## Web UI

Specs are more fun in a browser. One command, zero dependencies beyond
the standard library:

```bash
agentkit serve            # http://127.0.0.1:8000
agentkit serve --port 9000
```

What you get:

- **Spec editor** (left) — write markdown, or load either bundled example
  with one click. Set the worker count, hit Run.
- **Task cards** (right) — every task rendered in dependency order with
  its status, attempt count, and output.
- **Report** — the same `report.md` the CLI writes, rendered readably
  right under the cards.

The UI runs on the **demo backend (EchoBackend)**: deterministic fake
outputs, no network, no cost, nothing leaves your machine. It's a
playground for specs and dependency graphs — point real model backends
at it via the Python API when you're ready to spend tokens.

Prefer JSON? The UI is just a thin client over a tiny API:

```bash
# list the bundled example specs
curl http://127.0.0.1:8000/api/examples

# run a spec; returns {tasks: [...], report_markdown: "..."}
curl -X POST http://127.0.0.1:8000/api/run \
  -H 'Content-Type: application/json' \
  -d '{"spec": "## Hello\nSay hi.", "workers": 2}'
```

Errors come back as clean JSON (`{"error": "..."}`) with 4xx/500 status
codes — tracebacks never reach the client.

## The spec format

```markdown
# Anything (document title is ignored)

## Crawl sitemap
Free-form instructions for the agent...

## Lighthouse audit
depends: crawl-sitemap
This runs after the crawl, and receives the crawl's output as context.
```

`##` headings become tasks (ids are slugified headings), and a
`depends: id1, id2` line declares dependencies. Cycles and unknown
dependencies fail fast with explicit errors.

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE).
