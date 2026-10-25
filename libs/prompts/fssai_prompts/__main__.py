"""``python -m fssai_prompts list`` shows each prompt, its versions and which one is in force."""
from __future__ import annotations

import sys

from .store import FilePromptStore, PromptError


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    store = FilePromptStore()
    if cmd == "list":
        print(f"{'name':<22}{'versions':<22}{'pinned':<10}in force")
        for info in store.describe():
            pin = f"{info.pinned} ({info.pinned_by})" if info.pinned else "-"
            print(f"{info.name:<22}{', '.join(info.versions):<22}{pin:<10}{info.selected}")
        return 0
    if cmd == "check":
        problems = store.validate_all()
        for p in problems:
            print("PROBLEM:", p)
        print("all prompts valid" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if cmd == "show" and len(argv) >= 2:
        try:
            t = store.get(argv[1], argv[2] if len(argv) > 2 else None)
        except PromptError as exc:
            print(exc)
            return 1
        print(f"--- {t.name}@{t.version}\n{t.system}\n--- user_template\n{t.user_template}")
        return 0
    print("usage: python -m fssai_prompts [list|check|show <name> [version]]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
