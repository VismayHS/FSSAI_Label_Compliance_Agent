"""FilePromptStore: versioned prompts loaded from files (contexts/Namith.md M1.1, L2).

Layout: ``prompts/<name>/<version>.yaml`` shipped inside this package, with the fields
``name``, ``version``, ``system``, ``user_template`` and ``notes``.

Rules (checked by conformance.check_prompt_store):
- ``get(name)`` returns the version pinned by ``PROMPT_<NAME>_VERSION``, else the newest one;
- ``get(name, version)`` pins that version explicitly (so a run or an eval can name what it used);
- every system prompt starts with ``[prompt:<name>@<version>]`` (LLM_Context §6.5). A file whose
  tag, name or version disagree with its location is rejected loudly, never silently used.

Env pinning. ``PROMPT_RESEARCHER_ACT_VERSION`` pins ``researcher.act``. A family variable
(``PROMPT_RESEARCHER_VERSION``) pins every ``researcher.*`` prompt that has no variable of its own, so
one switch moves the whole research agent between variants (L2).

Switch on: IMPL_PROMPTS=fssai_prompts.store:FilePromptStore
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from fssai_contracts.schemas import PromptTemplate

_VERSION = re.compile(r"^\d+(\.\d+){0,2}$")
_NAME = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


class PromptError(ValueError):
    """A prompt file is missing, malformed or inconsistent with its tag."""


def _vkey(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def env_var_names(name: str) -> list[str]:
    """Env variables that can pin ``name``, most specific first."""
    parts = name.upper().replace("-", "_").split(".")
    names = [f"PROMPT_{'_'.join(parts)}_VERSION"]
    if len(parts) > 1:
        names.append(f"PROMPT_{parts[0]}_VERSION")
    return names


@dataclass(frozen=True)
class PromptInfo:
    name: str
    versions: tuple[str, ...]
    pinned: str | None
    pinned_by: str | None
    selected: str


class FilePromptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path(__file__).parent / "prompts"
        self._cache: dict[tuple[str, str], PromptTemplate] = {}

    # ------------------------------------------------------------------ discovery

    def names(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.is_dir() else []

    def versions(self, name: str) -> list[str]:
        folder = self.root / name
        if not _NAME.match(name) or not folder.is_dir():
            raise PromptError(f"unknown prompt '{name}' (known: {', '.join(self.names()) or 'none'})")
        found = [p.stem for p in folder.glob("*.yaml")]
        bad = [v for v in found if not _VERSION.match(v)]
        if bad:
            raise PromptError(f"{name}: file names must be versions like 1.0.0, got {bad}")
        if not found:
            raise PromptError(f"prompt '{name}' has no versions")
        return sorted(found, key=_vkey)

    def pinned(self, name: str) -> tuple[str, str] | None:
        """(version, variable) pinned in the environment for ``name``, if any."""
        for var in env_var_names(name):
            value = os.environ.get(var, "").split("#", 1)[0].strip()
            if value:
                return value, var
        return None

    # ------------------------------------------------------------------ loading

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        available = self.versions(name)
        if version is None:
            pin = self.pinned(name)
            if pin:
                version = pin[0]
                if version not in available:
                    raise PromptError(f"{pin[1]}={version} but '{name}' only has {available}")
            else:
                version = available[-1]
        elif version not in available:
            raise PromptError(f"prompt '{name}' has no version {version} (has {available})")
        key = (name, version)
        if key not in self._cache:
            self._cache[key] = self._load(name, version)
        return self._cache[key]

    def _load(self, name: str, version: str) -> PromptTemplate:
        path = self.root / name / f"{version}.yaml"
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise PromptError(f"{path}: not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise PromptError(f"{path}: expected a mapping")
        for field in ("name", "version", "system", "user_template"):
            if not str(data.get(field, "")).strip():
                raise PromptError(f"{path}: missing '{field}'")
        if data["name"] != name or str(data["version"]) != version:
            raise PromptError(f"{path}: file says {data['name']}@{data['version']}, location says {name}@{version}")
        tag = f"[prompt:{name}@{version}]"
        if not str(data["system"]).startswith(tag):
            raise PromptError(f"{path}: system prompt must start with {tag}")
        return PromptTemplate(name=name, version=version, system=str(data["system"]).strip(),
                              user_template=str(data["user_template"]))

    def validate_all(self) -> list[str]:
        """Load every prompt file; return the problems found (empty = all good)."""
        problems = []
        for name in self.names():
            try:
                versions = self.versions(name)
            except PromptError as exc:
                problems.append(str(exc))
                continue
            for v in versions:
                try:
                    self._load(name, v)
                except PromptError as exc:
                    problems.append(str(exc))
        return problems

    def describe(self) -> list[PromptInfo]:
        out = []
        for name in self.names():
            versions = self.versions(name)
            pin = self.pinned(name)
            out.append(PromptInfo(name=name, versions=tuple(versions),
                                  pinned=pin[0] if pin else None, pinned_by=pin[1] if pin else None,
                                  selected=pin[0] if pin else versions[-1]))
        return out
