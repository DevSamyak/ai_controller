#!/usr/bin/env python3
"""Build dist/ai-operator-source.zip without venv, secrets, or runtime data."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "ai-operator-source.zip"

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "dist",
    "ui/dist",
    ".playwright-browsers",
    "playwright-report",
}
SKIP_FILES = {".env", ".DS_Store"}
SKIP_SUFFIX = {".sqlite3", ".db", ".pyc", ".log"}


def skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    if path.name in SKIP_FILES:
        return True
    if path.suffix in SKIP_SUFFIX:
        return True
    if rel.parts[:1] == ("workspace",) and path.suffix == ".md":
        return True
    if rel.parts[:1] == ("logs",) and path.suffix in {".jsonl", ".txt"}:
        return True
    return False


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file() or skip(path):
                continue
            zf.write(path, path.relative_to(ROOT).as_posix())
            count += 1
    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        zf.testzip()
    required = ["README.md", "requirements.txt", ".env.example", "server/api.py", "ui/src/App.jsx"]
    missing = [name for name in required if name not in names]
    banned = [name for name in names if name.endswith(".env") or ".venv/" in name or name.endswith(".sqlite3")]
    if missing or banned:
        raise SystemExit(f"package check failed missing={missing} banned={banned}")
    print(f"Wrote {OUT} ({count} files)")


if __name__ == "__main__":
    main()
