"""Make an API key for one client (docs/security.md).

    python tools/scripts/make_api_key.py <client-id> [--role analyst|reviewer]

Prints the key once (give it to that client, e.g. paste it into the web client) and the `API_KEYS` entry to add to
`.env`. The entry holds only the key's SHA-256, so `.env` never holds a usable key and a leaked `.env` can't be
replayed against the API. Then `docker compose up -d --force-recreate api`.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import secrets
import sys


def make(client_id: str, role: str = "analyst") -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", client_id):
        raise ValueError("client id: 1-64 letters, digits or . _ -")
    if role not in ("analyst", "reviewer"):
        raise ValueError("role: analyst or reviewer")
    key = "fssai_" + secrets.token_urlsafe(32)  # 256 bits: guessing is not a realistic attack
    return key, f"{client_id}:{hashlib.sha256(key.encode()).hexdigest()}:{role}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("client_id")
    ap.add_argument("--role", choices=("analyst", "reviewer"), default="analyst")
    args = ap.parse_args(argv)
    key, entry = make(args.client_id, args.role)
    print(f"key (give to {args.client_id}; shown once):  {key}")
    print(f"API_KEYS entry (comma-separate several):    {entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
