"""FilePromptStore: versioned prompts loaded from files (contexts/Namith.md M1.1).

Layout: prompts/<name>/<version>.yaml with fields name, version, system, user_template, notes.
Rules (checked by conformance.check_prompt_store):
- get(name) returns the version pinned by PROMPT_<NAME>_VERSION, else the newest one;
- get(name, version) pins that version;
- every system prompt starts with "[prompt:<name>@<version>]" and the file must agree with its path.

Switch on: IMPL_PROMPTS=fssai_prompts.store:FilePromptStore
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from fssai_contracts.schemas import PromptTemplate


class PromptError(RuntimeError):
    """A prompt is missing, malformed or inconsistent with its file name."""


def _version_key(version: str) -> tuple:
    """Sort 1.10.0 above 1.2.0; non-numeric parts sort after numeric ones."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-]", version))


def _env_name(name: str) -> str:
    return "PROMPT_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper() + "_VERSION"


class FilePromptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path(__file__).parent / "prompts"

    @classmethod
    def from_registry(cls) -> FilePromptStore:
        return cls()

    # ---- discovery

    def names(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.exists() else []

    def versions(self, name: str) -> list[str]:
        folder = self.root / name
        if not folder.is_dir():
            return []
        return sorted((p.stem for p in folder.glob("*.yaml")), key=_version_key)

    def pinned(self, name: str) -> str | None:
        return os.environ.get(_env_name(name), "").split("#", 1)[0].strip() or None

    # ---- loading

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        available = self.versions(name)
        if not available:
            raise PromptError(f"no prompt named '{name}' under {self.root}")
        chosen = version or self.pinned(name) or available[-1]
        if chosen not in available:
            raise PromptError(f"prompt '{name}' has no version '{chosen}' (available: {', '.join(available)})")
        return self._load(name, chosen)

    def _load(self, name: str, version: str) -> PromptTemplate:
        path = self.root / name / f"{version}.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key in ("name", "version", "system", "user_template"):
            if not data.get(key):
                raise PromptError(f"{path}: missing field '{key}'")
        if data["name"] != name or str(data["version"]) != version:
            raise PromptError(f"{path}: file says {data['name']}@{data['version']}, path says {name}@{version}")
        tag = f"[prompt:{name}@{version}]"
        if not data["system"].lstrip().startswith(tag):
            raise PromptError(f"{path}: system prompt must start with {tag}")
        return PromptTemplate(name=name, version=version, system=data["system"].strip(),
                              user_template=data["user_template"].strip())
