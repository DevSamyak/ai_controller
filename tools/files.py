from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

from agent.settings import Settings
from tools.base import ToolResult


class SaveFileArgs(BaseModel):
    relative_path: str = Field(min_length=1)
    content: str = Field(min_length=1)
    overwrite: bool = False


class ReadFileArgs(BaseModel):
    relative_path: str = Field(min_length=1)


class ListFilesArgs(BaseModel):
    relative_dir: str = "drafts"


def _safe_path(settings: Settings, relative_path: str) -> Path | ToolResult:
    workspace = settings.workspace_path.resolve()
    candidate = (workspace / relative_path).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError:
        return ToolResult(ok=False, error="path escapes workspace")
    return candidate


def save_file(settings: Settings, args: SaveFileArgs) -> ToolResult:
    target = _safe_path(settings, args.relative_path)
    if isinstance(target, ToolResult):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(args.content.encode("utf-8")).hexdigest()
    reused = False
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing == args.content:
            reused = True
        elif not args.overwrite:
            return ToolResult(
                ok=False,
                error=f"{args.relative_path} already exists with different content",
                evidence=[{"kind": "file_exists", "path": str(target)}],
            )
        else:
            target.write_text(args.content, encoding="utf-8")
    else:
        target.write_text(args.content, encoding="utf-8")
    return ToolResult(
        ok=True,
        data={
            "path": str(target),
            "relative_path": args.relative_path,
            "bytes": target.stat().st_size,
            "sha256": digest,
            "reused": reused,
        },
        evidence=[{"kind": "file_write", "path": str(target), "relative_path": args.relative_path, "reused": reused}],
    )


def read_file(settings: Settings, args: ReadFileArgs) -> ToolResult:
    target = _safe_path(settings, args.relative_path)
    if isinstance(target, ToolResult):
        return target
    if not target.exists():
        return ToolResult(ok=False, error=f"{args.relative_path} not found")
    content = target.read_text(encoding="utf-8")
    return ToolResult(
        ok=True,
        data={"path": str(target), "relative_path": args.relative_path, "content": content},
        evidence=[{"kind": "file_read", "path": str(target)}],
    )


def list_files(settings: Settings, args: ListFilesArgs) -> ToolResult:
    target = _safe_path(settings, args.relative_dir)
    if isinstance(target, ToolResult):
        return target
    if not target.exists():
        return ToolResult(ok=True, data={"files": [], "relative_dir": args.relative_dir})
    files = sorted(str(p.relative_to(settings.workspace_path)) for p in target.rglob("*") if p.is_file())
    return ToolResult(
        ok=True,
        data={"files": files, "relative_dir": args.relative_dir},
        evidence=[{"kind": "file_list", "count": len(files)}],
    )
