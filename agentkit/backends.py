"""Backends: how agentkit talks to a model.

A backend is any callable ``(prompt: str) -> str``. agentkit ships one
deterministic fake for tests and demos; for real work, bring your own
model function.

Bring-your-own-model example::

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

    run_spec("SPEC.md", backend=claude_backend, max_workers=4)

Or with OpenAI::

    from openai import OpenAI

    client = OpenAI()

    def gpt_backend(prompt: str) -> str:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

Notes for real backends:
- Raise on API errors — agentkit retries per the agent's ``retries``.
- Keep the function synchronous; agentkit handles concurrency itself.
- Timeouts are enforced per attempt by ``Agent`` (default 60s).
"""

from __future__ import annotations

import hashlib


class EchoBackend:
    """Deterministic fake backend for tests and demos.

    Returns a stable, prompt-derived string — no network, no randomness,
    no cost. Useful for dry runs and CI.
    """

    def __init__(self, prefix: str = "echo") -> None:
        self.prefix = prefix
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        return (
            f"[{self.prefix}:{digest}] processed prompt "
            f"({len(prompt)} chars, {len(prompt.splitlines())} lines)"
        )
