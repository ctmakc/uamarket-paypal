#!/usr/bin/env python3
"""Fail when code reads an environment variable that .env.example does not document.

Scans app/, edge/ and web/ (not node_modules or build output) for:
  Python      os.getenv("X"), os.environ.get("X"), os.environ["X"], and helpers whose name
              contains "env", or is _text/_switch, called with a literal name
  TypeScript  process.env.X, process.env["X"], and env*("X") helpers
              (envBilingual("X") also reads X_UK)

Exit 0 when every name is listed in .env.example (as `NAME=` or a commented `# NAME=`),
1 otherwise. Names that belong to the runtime rather than to the shop are ignored.

    python tools/check_env.py            # report and exit
    python tools/check_env.py --list     # print every name found, with where
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ("app", "edge", "web")
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".venv", "public", "tests"}
SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".js"}

# Set by the platform or used only by the test suite; not shop configuration.
IGNORED = {
    "NODE_ENV", "NEXT_RUNTIME", "NEXT_PHASE", "PORT", "HOSTNAME", "NEXT_TELEMETRY_DISABLED",
    "SQLITE_FAST_UNSAFE", "TEST_POSTGRES_URL",
}

NAME = r"([A-Z][A-Z0-9_]{2,})"
PATTERNS = [
    re.compile(r"os\.getenv\(\s*[\"']" + NAME + r"[\"']"),
    re.compile(r"os\.environ\.(?:get|setdefault)\(\s*[\"']" + NAME + r"[\"']"),
    re.compile(r"os\.environ\[\s*[\"']" + NAME + r"[\"']\s*\]"),
    re.compile(r"\b(?:_text|_switch|\w*_env\w*|env[A-Z]\w*)\(\s*[\"'`]" + NAME + r"[\"'`]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]{2,})"),
    re.compile(r"process\.env\[\s*[\"'`]" + NAME + r"[\"'`]\s*\]"),
]
BILINGUAL = re.compile(r"\benvBilingual\(\s*[\"'`]" + NAME + r"[\"'`]")


def files():
    for top in SCAN:
        base = ROOT / top
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in SUFFIXES and path.is_file() and not (set(path.relative_to(ROOT).parts) & SKIP_DIRS):
                yield path


def names_in_code() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in files():
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(ROOT))
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                found.setdefault(match.group(1), set()).add(rel)
        for match in BILINGUAL.finditer(text):
            found.setdefault(f"{match.group(1)}_UK", set()).add(rel)
    return {k: v for k, v in found.items() if k not in IGNORED}


def names_in_example() -> set[str]:
    listed = set()
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*#?\s*([A-Z][A-Z0-9_]{2,})=", line)
        if m:
            listed.add(m.group(1))
    return listed


def main(argv: list[str]) -> int:
    code = names_in_code()
    listed = names_in_example()
    if "--list" in argv:
        for name in sorted(code):
            print(f"{name:40s} {'ok ' if name in listed else 'MISSING'} {', '.join(sorted(code[name]))}")
    missing = sorted(set(code) - listed)
    if missing:
        print(f"check_env: {len(missing)} name(s) read in code but absent from .env.example:")
        for name in missing:
            print(f"  {name}  ({', '.join(sorted(code[name]))})")
        return 1
    print(f"check_env: ok, {len(code)} names read in code, all documented in .env.example")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
