"""Test doubles for the agents: a scripted LLM that records steps like the real client does."""
from __future__ import annotations

import json

from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import LLMResponse


class ScriptedLLM:
    """Replies come from `script`: a list consumed in order, or a callable (messages, step) -> str.

    A reply that is a dict is dumped to JSON. An exception instance in the list is raised.
    """

    def __init__(self, script) -> None:
        self.script = script
        self.calls: list[dict] = []

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        self.calls.append({"agent": agent, "step": step, "messages": messages, "prompt": prompt})
        reply = self.script(messages, step) if callable(self.script) else self.script.pop(0)
        if isinstance(reply, Exception):
            ctx.record(agent=agent, kind="llm", name=step, error=str(reply))
            raise reply
        text = json.dumps(reply) if isinstance(reply, (dict, list)) else str(reply)
        ctx.record(agent=agent, kind="llm", name=step, prompt_name=prompt.name if prompt else None,
                   prompt_version=prompt.version if prompt else None, prompt_tokens=10, completion_tokens=5)
        return LLMResponse(text=text, model_alias="scripted", prompt_tokens=10, completion_tokens=5)


def down() -> ProviderUnavailable:
    return ProviderUnavailable("scripted outage")
