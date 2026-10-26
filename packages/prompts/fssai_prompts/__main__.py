"""python -m fssai_prompts list: print every prompt name, version and which one is pinned."""
from __future__ import annotations

import sys

from .store import FilePromptStore


def main(argv: list[str]) -> int:
    if argv[:1] != ["list"]:
        print("usage: python -m fssai_prompts list")
        return 2
    store = FilePromptStore()
    for name in store.names():
        versions = store.versions(name)
        pinned = store.pinned(name)
        active = pinned or versions[-1]
        print(f"{name}: versions={', '.join(versions)} active={active}" + (" (pinned)" if pinned else " (latest)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
