"""The researcher's three tools (A1): corpus_search, clause_lookup, request_field_lookup.

Every call checks the run budget first and records a "tool" step. Search and clause steps carry the
full passages returned, so a run can be rebuilt from its trace (D5). Arguments are validated against
an allowlist before anything runs; invalid arguments never reach the retriever.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.schemas import LabelCheckRequest, Passage, Regulation

AGENT = "researcher"
TOOLS = ("corpus_search", "clause_lookup", "request_field_lookup")
_REGULATIONS = {r.value: r for r in Regulation}
_CLAUSE_ID = re.compile(r"^[A-Za-z0-9 ,.()\-/]{1,80}$")
_FIELD_CHARS = 600


class ToolArgError(ValueError):
    """The model asked for a tool call that is not allowed."""


@dataclass
class ToolResult:
    tool: str
    args: dict
    passages: list[Passage] = field(default_factory=list)
    value: object = None
    error: str | None = None

    def summary(self) -> str:
        if self.error:
            return f"{self.tool} {self.args}: ERROR {self.error}"
        if self.tool == "request_field_lookup":
            return f"{self.tool} {self.args}: {self.value}"
        ids = ", ".join(p.passage_id for p in self.passages) or "no passages"
        return f"{self.tool} {self.args}: {ids}"


def search_k() -> int:
    try:
        return max(1, int(os.environ.get("RESEARCHER_SEARCH_K", "5") or 5))
    except ValueError:
        return 5


def field_paths(request: LabelCheckRequest) -> set[str]:
    """Every dotted path into the request that holds a value."""
    paths: set[str] = set()

    def walk(prefix: str, node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(f"{prefix}.{key}" if prefix else str(key), value)
        elif prefix:
            paths.add(prefix)

    walk("", request.model_dump(mode="json"))
    return paths


def validate(tool: str, args: object, request: LabelCheckRequest) -> dict:
    """Return clean arguments for an allowed call, or raise ToolArgError."""
    if tool not in TOOLS:
        raise ToolArgError(f"unknown tool '{tool}'")
    if not isinstance(args, dict):
        raise ToolArgError("args must be an object")
    if tool == "corpus_search":
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise ToolArgError("query must be 1-300 characters")
        reg = args.get("regulation")
        if reg in ("", "null", "none", "None"):
            reg = None
        if reg is not None and reg not in _REGULATIONS:
            raise ToolArgError(f"regulation must be one of {sorted(_REGULATIONS)} or null")
        return {"query": " ".join(query.split()), "regulation": reg}
    if tool == "clause_lookup":
        reg, clause = args.get("regulation"), args.get("clause_id")
        if reg not in _REGULATIONS:
            raise ToolArgError(f"regulation must be one of {sorted(_REGULATIONS)}")
        if not isinstance(clause, str) or not _CLAUSE_ID.match(clause.strip()):
            raise ToolArgError("clause_id has characters a clause id never has")
        return {"regulation": reg, "clause_id": clause.strip()}
    path = args.get("path")
    if not isinstance(path, str) or path not in field_paths(request):
        raise ToolArgError("path is not a field of the request")
    return {"path": path}


def _lookup_field(request: LabelCheckRequest, path: str) -> object:
    node: object = request.model_dump(mode="json")
    for part in path.split("."):
        node = node[part]  # type: ignore[index]
    if path.startswith("label.") and node not in (None, "", []):
        text = node if isinstance(node, str) else " | ".join(str(x) for x in node) if isinstance(node, list) else str(node)
        return {"untrusted_label_text": text[:_FIELD_CHARS]}
    return node


def execute(tool: str, args: dict, *, retriever, request: LabelCheckRequest, ctx: RunContext) -> ToolResult:
    """Run one validated call. BudgetExceeded propagates; any other tool failure is recorded and returned."""
    ctx.check_budget(tool_call=True)
    t0 = time.monotonic()
    result = ToolResult(tool=tool, args=args)
    try:
        if tool == "corpus_search":
            reg = _REGULATIONS[args["regulation"]] if args.get("regulation") else None
            result.passages = list(retriever.search(args["query"], ctx, k=search_k(), regulation=reg))
        elif tool == "clause_lookup":
            hit = retriever.get_clause(_REGULATIONS[args["regulation"]], args["clause_id"], ctx)
            result.passages = [hit] if hit is not None else []
        else:
            result.value = _lookup_field(request, args["path"])
    except BudgetExceeded:
        raise
    except Exception as exc:  # a failing tool must not kill the run; the agent sees the error
        result.error = f"{type(exc).__name__}: {exc}"[:300]
    latency = (time.monotonic() - t0) * 1000
    output: dict = {"passages": [p.model_dump(mode="json") for p in result.passages]}
    if tool == "request_field_lookup":
        output = {"path": args.get("path"), "value": result.value}
    ctx.record(agent=AGENT, kind="tool", name=tool, latency_ms=latency, input=dict(args), output=output,
               error=result.error)
    return result
