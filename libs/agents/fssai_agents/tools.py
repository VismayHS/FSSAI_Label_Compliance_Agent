"""The research agent's tools and the argument allowlist that guards them (L4: injected text can reach a model that holds tools).

Every argument the model proposes is validated here, never trusted: tool names and regulation ids come from a
fixed set, free strings are length-bounded and character-limited, and request_field_lookup only resolves paths
that exist in the request model.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import LabelCheckRequest, Passage, Regulation

TOOLS = ("corpus_search", "clause_lookup", "request_field_lookup", "finish")
_QUERY = re.compile(r"^[\w\s%().,;:'\"/&+\-–]{2,300}$", re.U)
_CLAUSE = re.compile(r"^[\w\s().,;:'\-–+~]{1,80}$", re.U)
_PATH = re.compile(r"^[a-z_]+(\.[a-z_0-9]+){0,2}$")
MAX_K = 8


class BadToolCall(ValueError):
    """The model asked for a tool call that is not allowed."""


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict

    def key(self) -> str:
        return json.dumps([self.tool, self.args], sort_keys=True)


def request_paths(request: LabelCheckRequest) -> list[str]:
    """Every readable path in the request: package.*, nutrition.*, label.* (nutrition.other.* included)."""
    paths: list[str] = []
    for top, value in request.model_dump(mode="json").items():
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    paths.extend(f"{top}.{k}.{kk}" for kk in v)
                paths.append(f"{top}.{k}")
    return paths


def parse_regulation(value: object) -> Regulation | None:
    if value in (None, "", "null", "any"):
        return None
    try:
        return Regulation(str(value).strip())
    except ValueError:
        raise BadToolCall(f"unknown regulation '{value}'") from None


def validate(call: dict, request: LabelCheckRequest) -> ToolCall:
    """Check a proposed {"tool", "args"} against the allowlist; raise BadToolCall on anything else."""
    if not isinstance(call, dict):
        raise BadToolCall("action must be an object")
    tool = str(call.get("tool", "")).strip()
    args = call.get("args") or {}
    if tool not in TOOLS:
        raise BadToolCall(f"unknown tool '{tool}'")
    if not isinstance(args, dict):
        raise BadToolCall("args must be an object")
    if tool == "finish":
        return ToolCall("finish", {})
    if tool == "corpus_search":
        query = " ".join(str(args.get("query", "")).split())
        if not _QUERY.match(query):
            raise BadToolCall("query must be 2-300 plain characters")
        out: dict = {"query": query}
        reg = parse_regulation(args.get("regulation"))
        if reg:
            out["regulation"] = reg.value
        return ToolCall(tool, out)
    if tool == "clause_lookup":
        reg = parse_regulation(args.get("regulation"))
        clause = " ".join(str(args.get("clause_id", "")).split())
        if reg is None or not _CLAUSE.match(clause):
            raise BadToolCall("clause_lookup needs a regulation and a clause_id")
        return ToolCall(tool, {"regulation": reg.value, "clause_id": clause})
    path = str(args.get("path", "")).strip()
    if not _PATH.match(path) or path not in request_paths(request):
        raise BadToolCall(f"'{path}' is not a field of the request")
    return ToolCall(tool, {"path": path})


def field_value(request: LabelCheckRequest, path: str) -> object:
    node: object = request.model_dump(mode="json")
    for part in path.split("."):
        node = node[part]  # type: ignore[index]
    return node


class Toolbox:
    """Executes validated calls against a Retriever and records the tool step (D5), full passages included."""

    def __init__(self, retriever, request: LabelCheckRequest, ctx: RunContext) -> None:
        self.retriever, self.request, self.ctx = retriever, request, ctx

    def run(self, call: ToolCall, k: int = 5) -> tuple[list[Passage], object]:
        """(passages, extra). `extra` is the field value for request_field_lookup, else None."""
        self.ctx.check_budget(tool_call=True)
        t0 = time.monotonic()
        passages: list[Passage] = []
        extra: object = None
        error: str | None = None
        try:
            if call.tool == "corpus_search":
                reg = Regulation(call.args["regulation"]) if "regulation" in call.args else None
                passages = list(self.retriever.search(call.args["query"], self.ctx, k=min(k, MAX_K), regulation=reg))
            elif call.tool == "clause_lookup":
                p = self.retriever.get_clause(Regulation(call.args["regulation"]), call.args["clause_id"], self.ctx)
                passages = [p] if p else []
            else:
                extra = field_value(self.request, call.args["path"])
        except Exception as exc:  # noqa: BLE001 - a failing tool is an observation, not a crash
            error = f"{type(exc).__name__}: {exc}"
        out: dict = {"passages": [p.model_dump(mode="json") for p in passages]}
        if call.tool == "request_field_lookup":
            out["value"] = extra
        if call.tool == "clause_lookup":
            out["found"] = bool(passages)
        self.ctx.record(agent="researcher", kind="tool", name=call.tool, input=call.args, output=out,
                        latency_ms=(time.monotonic() - t0) * 1000, error=error)
        if error:
            raise ToolFailed(error)
        return passages, extra


class ToolFailed(RuntimeError):
    """A tool call raised; the step is already recorded."""
