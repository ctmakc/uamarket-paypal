#!/usr/bin/env python3
"""Make the two settings the /admin sign-in needs.

    python3 tools/admin_password_hash.py            # asks for the password twice
    python3 tools/admin_password_hash.py --stdin    # reads it from standard input (scripts)

Prints two lines to paste into .env:

    ADMIN_PASSWORD_HASH=scrypt:32768:8:1:<salt>:<hash>
    ADMIN_SESSION_SECRET=<64 random hex characters>

The storefront (web/lib/admin/session.ts) checks the password against the hash with the same
scrypt parameters. Changing the password (a new hash) signs every open admin session out.
Colons, not dollar signs, separate the parts: docker compose would read $ in an env file
as a variable. Python standard library only; nothing is stored or sent anywhere.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import secrets
import sys
import unicodedata

N, R, P, KEY_LEN = 2 ** 15, 8, 1, 32
MIN_LENGTH = 12


def make_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(unicodedata.normalize("NFKC", password).encode(), salt=salt, n=N, r=R, p=P,
                         maxmem=256 * 1024 * 1024, dklen=KEY_LEN)
    return f"scrypt:{N}:{R}:{P}:{base64.b64encode(salt).decode()}:{base64.b64encode(key).decode()}"


def main() -> int:
    if "--stdin" in sys.argv:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Admin password: ")
        if getpass.getpass("Again: ") != password:
            print("The two passwords differ.", file=sys.stderr)
            return 1
    if len(password) < MIN_LENGTH:
        print(f"Use at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    print(f"ADMIN_PASSWORD_HASH={make_hash(password)}")
    print(f"ADMIN_SESSION_SECRET={secrets.token_hex(32)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
