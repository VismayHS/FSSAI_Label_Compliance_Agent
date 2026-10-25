"""Shared helpers for talking to the LLM: rendering a prompt, and reading JSON out of a reply."""
from __future__ import annotations

import json
import re

from fssai_contracts.schemas import LLMMessage, PromptTemplate

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class UnusableReply(ValueError):
    """The model answered, but not with what the schema needs."""


def render(prompt: PromptTemplate, **values: object) -> list[LLMMessage]:
    """prompt.render(), tolerating a template whose placeholders differ (the fake store's is "{input}")."""
    try:
        return prompt.render(**values)
    except (KeyError, IndexError, ValueError):
        joined = "\n\n".join(str(v) for v in values.values())
        return [LLMMessage(role="system", content=prompt.system), LLMMessage(role="user", content=joined)]


def json_object(text: str) -> dict:
    """The first JSON object in a reply, tolerating code fences and chatter around it."""
    text = _FENCE.sub("", (text or "").strip())
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise UnusableReply("no JSON object in the reply") from None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise UnusableReply(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise UnusableReply("reply is JSON but not an object")
    return value
