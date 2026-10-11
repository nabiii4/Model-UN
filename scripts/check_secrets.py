"""Scan the project for things that look like API keys before you commit.

Run:  python scripts/check_secrets.py
It skips .env (which is never committed) and the folders git ignores.
"""
import _path  # noqa: F401

import re
import sys

from _path import ROOT

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "instance", "node_modules", "vendor", ".pytest_cache"}
SKIP_FILES = {".env"}
PATTERNS = [
    re.compile(r"\b[0-9a-f]{32}\b"),                     # Azure OpenAI keys are 32 hex characters
    re.compile(r"\b[A-Za-z0-9]{84}\b"),                  # newer Azure keys
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),            # OpenAI-style keys
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"]([A-Za-z0-9_\-]{16,})['\"]"),
]
PLACEHOLDERS = ("paste-", "your-", "placeholder", "example", "fake-", "test-")
TEXT_EXT = {".py", ".js", ".html", ".css", ".md", ".json", ".txt", ".example", ".yml", ".yaml", ".toml", ".cfg", ".ini", ""}


def main():
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts) or path.name in SKIP_FILES:
            continue
        if path.suffix not in TEXT_EXT:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for p in PATTERNS:
                m = p.search(line)
                if m and not any(ph in m.group(0).lower() for ph in PLACEHOLDERS):
                    hits.append(f"{path.relative_to(ROOT)}:{n}: looks like a key")
    if hits:
        print("Possible secrets found. Move them into .env:")
        print("\n".join(hits))
        return 1
    print("No key-looking strings found. 👍")
    return 0


if __name__ == "__main__":
    sys.exit(main())
