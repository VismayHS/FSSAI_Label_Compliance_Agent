"""D4 audit: no credentials, provider endpoints or model ids in the repo (make audit; CI runs it on every PR).

    python scripts/audit_secrets.py            # exit 1 and list every hit, 0 when clean

Scans every file git tracks or would track (so new files count before their first commit), except binaries,
lock files and third-party vendored guidance (skills/vendor/). A line that must mention a pattern on purpose,
e.g. documentation of this check, carries the marker `audit: allow` on the same line.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOW = "audit: allow"
SKIP_PREFIXES = ("skills/vendor/",)
SKIP_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".zip", ".faiss",
                 ".pkl", "package-lock.json")

CHECKS: list[tuple[str, re.Pattern[str]]] = [
    # credentials
    ("API key (OpenAI / OpenRouter style)", re.compile(r"\bsk-(?:or-|proj-)?[A-Za-z0-9_-]{20,}")),
    ("API key (Groq)", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("API key (Google)", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("token (GitHub)", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("token (Hugging Face)", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("a key value in an env template", re.compile(r"^\s*[A-Z_]*API_KEY\s*=\s*[^\s#]+")),
    # provider endpoints
    ("LLM provider endpoint", re.compile(r"(?i)\b(?:api\.openai\.com|api\.groq\.com|generativelanguage\.googleapis\.com"
                                         r"|openrouter\.ai/api|api\.anthropic\.com|api\.together\.xyz|api\.mistral\.ai"
                                         r"|api\.deepseek\.com|integrate\.api\.nvidia\.com|api\.cohere\.ai)\b")),
    # model ids
    ("LLM model id", re.compile(r"(?i)\b(?:gpt-(?:3\.5|4|4o|4\.1|5)[\w.-]*|o[134]-mini|llama-?3[\w.-]*|gemini-[0-9][\w.-]*"
                                r"|mixtral-[\w.-]+|claude-(?:[0-9]|opus|sonnet|haiku)[\w.-]*|deepseek-(?:chat|r1|v[0-9])[\w.-]*"
                                r"|qwen[0-9][\w.-]*|gemma-?[0-9][\w.-]*)\b")),
    ("embedding model id", re.compile(r"(?i)\b(?:all-MiniLM-L\d+[\w.-]*|bge-(?:small|base|large)[\w.-]*"
                                      r"|e5-(?:small|base|large)[\w.-]*|text-embedding-[\w.-]+)\b")),
]


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return sorted({line for line in out.splitlines() if line})


def scan(rel: str) -> list[tuple[int, str, str]]:
    if rel.startswith(SKIP_PREFIXES) or rel.lower().endswith(SKIP_SUFFIXES) or rel == "scripts/audit_secrets.py":
        return []
    path = ROOT / rel
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
        return []  # binary, or deleted in the working tree
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        for what, pattern in CHECKS:
            match = pattern.search(line)
            if match:
                hits.append((n, what, match.group(0)))
    return hits


def main() -> int:
    files = tracked_files()
    found = 0
    for rel in files:
        for n, what, text in scan(rel):
            found += 1
            print(f"{rel}:{n}: {what}: {text[:12]}{'...' if len(text) > 12 else ''}")
    if found:
        print(f"\nD4 audit FAILED: {found} hit(s) in {len(files)} files. Move the value to .env (and an empty key "
              f"to your .env.example section), or mark a deliberate mention with '{ALLOW}'.")
        return 1
    print(f"D4 audit passed: no credentials, provider endpoints or model ids in {len(files)} files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
