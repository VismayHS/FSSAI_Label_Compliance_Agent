"""FilePromptStore: versioned prompts loaded from files (contexts/Namith.md M1.1). Day-0 skeleton.

The file layout is yours to choose in M1.1; a simple one is prompts/<name>/<version>.yaml holding
`system` and `user_template`, shipped inside this package. Rules (checked by conformance.check_prompt_store):
- get(name) returns the version chosen by PROMPT_<NAME>_VERSION, else the newest one;
- get(name, version) pins that version, so a run or an eval can name exactly what it used;
- every system prompt starts with "[prompt:<name>@<version>]" (LLM_Context §6.5; the stub LLM keys on it).

Switch on: IMPL_PROMPTS=fssai_prompts.store:FilePromptStore
"""
from __future__ import annotations

from pathlib import Path

from fssai_contracts.schemas import PromptTemplate


class FilePromptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).parent / "prompts"

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        raise NotImplementedError("M1.1: load <name>@<version> from the prompt files")
