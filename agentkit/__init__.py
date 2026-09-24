"""agentkit — a small toolkit for orchestrating multi-agent workflows.

Write a markdown spec, point it at any model backend, and get a
dependency-ordered, parallel-executed run report back.
"""

from .agents import Agent, Result
from .backends import EchoBackend
from .orchestrator import CycleError, Orchestrator, Report
from .runner import run_spec
from .spec import Task, parse_spec

__all__ = [
    "Agent",
    "CycleError",
    "EchoBackend",
    "Orchestrator",
    "Report",
    "Result",
    "Task",
    "parse_spec",
    "run_spec",
]
__version__ = "0.1.0"
