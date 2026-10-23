"""One-time (and re-runnable) setup for a fresh clone. See CONTRIBUTING.md §2.

    python scripts/setup_dev.py <your-name>      # nishkal | namith | vihaan | vismay

Switches you to your own branch, enables the repo's git hooks, creates .venv, installs the shared
contracts, runs their tests and creates .env from .env.example. Works on Windows and macOS.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import venv
from pathlib import Path

TEAM = ("nishkal", "namith", "vihaan", "vismay")
ROOT = Path(__file__).resolve().parent.parent


def run(*args: str) -> None:
    print("  $", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def git_out(*args: str) -> str:
    result = subprocess.run(("git", *args), cwd=ROOT, text=True, capture_output=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def venv_python() -> Path:
    scripts = "Scripts" if sys.platform == "win32" else "bin"
    return ROOT / ".venv" / scripts / ("python.exe" if sys.platform == "win32" else "python")


def setup_git(name: str) -> None:
    print("\n[1/4] Git: your branch and hooks")
    if not git_out("config", "user.email"):
        sys.exit(
            "  git user.email is not set. Set it to the email on your GitHub account first:\n"
            '    git config --global user.name  "Your Name"\n'
            '    git config --global user.email "you@example.com"'
        )
    print(f"  committing as {git_out('config', 'user.name')} <{git_out('config', 'user.email')}>")

    run("git", "config", "core.hooksPath", ".githooks")
    run("git", "config", "fssai.branch", name)
    run("git", "fetch", "origin")

    current = git_out("branch", "--show-current")
    if current != name:
        if git_out("status", "--porcelain", "--untracked-files=no"):
            sys.exit(f"  You have uncommitted changes on '{current}'. Commit or stash them, then re-run.")
        if git_out("rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            run("git", "switch", name)
        elif git_out("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}"):
            run("git", "switch", "--track", f"origin/{name}")
        else:
            run("git", "switch", "-c", name, "origin/main")
            run("git", "push", "-u", "origin", name)
    if not git_out("rev-parse", "--abbrev-ref", f"{name}@{{upstream}}"):
        run("git", "branch", f"--set-upstream-to=origin/{name}", name)
    run("git", "config", "push.default", "upstream")
    print(f"  on branch '{name}', pushing to origin/{name} only")


def setup_python() -> None:
    print("\n[2/4] Python: .venv")
    if sys.version_info < (3, 11):
        sys.exit(f"  Python 3.11+ is required, this is {sys.version.split()[0]}.")
    if not venv_python().exists():
        print("  creating .venv")
        venv.create(ROOT / ".venv", with_pip=True)
    py = str(venv_python())
    run(py, "-m", "pip", "install", "--quiet", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "--quiet", "-e", "contracts[test]")


def run_tests() -> None:
    print("\n[3/4] Contract tests")
    run(str(venv_python()), "-m", "pytest", "contracts", "-q")


def setup_env() -> None:
    print("\n[4/4] .env")
    env, example = ROOT / ".env", ROOT / ".env.example"
    if env.exists():
        print("  .env already exists, left as is")
    else:
        shutil.copyfile(example, env)
        print("  created .env from .env.example. Fill in your own section (never commit it).")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1].lower() not in TEAM:
        sys.exit(f"usage: python scripts/setup_dev.py <{'|'.join(TEAM)}>")
    name = sys.argv[1].lower()
    setup_git(name)
    setup_python()
    run_tests()
    setup_env()
    print(f"\nDone. Read contexts/LLM_Context.md, then contexts/{name.capitalize()}.md.")


if __name__ == "__main__":
    main()
