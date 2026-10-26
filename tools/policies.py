from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi

from agent.settings import ROOT
from tools.base import ToolResult

POLICY_DIR = ROOT / "mock_company" / "policies"
FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
TOKEN_RE = re.compile(r"[a-z0-9₹]+", re.I)


class SearchPolicyArgs(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)


class ReadPolicyArgs(BaseModel):
    filename: str = Field(min_length=1)


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER_RE.match(text)
    meta: dict[str, str] = {}
    body = text
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        body = text[match.end() :]
    return meta, body


def load_policies() -> list[dict[str, Any]]:
    docs = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(text)
        docs.append(
            {
                "filename": path.name,
                "meta": meta,
                "body": body.strip(),
                "text": text,
                "tokens": _tokenize(path.name + " " + body),
            }
        )
    return docs


def _snippet(body: str, query: str, width: int = 240) -> str:
    tokens = _tokenize(query)
    lowered = body.lower()
    idx = -1
    for token in tokens:
        idx = lowered.find(token)
        if idx >= 0:
            break
    if idx < 0:
        idx = 0
    start = max(0, idx - 40)
    return body[start : start + width].strip()


def search_policy(_settings, args: SearchPolicyArgs) -> ToolResult:
    docs = load_policies()
    if not docs:
        return ToolResult(ok=False, error="no policy documents found")
    bm25 = BM25Okapi([d["tokens"] for d in docs])
    scores = bm25.get_scores(_tokenize(args.query))
    ranked = sorted(zip(docs, scores, strict=True), key=lambda item: item[1], reverse=True)
    results = []
    for doc, score in ranked[: args.top_k]:
        if score <= 0:
            continue
        results.append(
            {
                "filename": doc["filename"],
                "score": float(score),
                "snippet": _snippet(doc["body"], args.query),
                "conflict_group": doc["meta"].get("conflict_group"),
                "position": doc["meta"].get("position"),
            }
        )
    conflict = _conflict(results)
    return ToolResult(
        ok=True,
        data={"results": results, "conflict": conflict, "query": args.query},
        evidence=[
            {
                "kind": "policy_search",
                "query": args.query,
                "filenames": [r["filename"] for r in results],
                "conflict": conflict,
            }
        ],
    )


def read_policy(_settings, args: ReadPolicyArgs) -> ToolResult:
    filename = Path(args.filename).name
    if filename != args.filename or not filename.endswith(".md"):
        return ToolResult(ok=False, error="policy filename must be a markdown file in the policy directory")
    path = POLICY_DIR / filename
    if not path.exists():
        return ToolResult(ok=False, error=f"policy {filename} not found")
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(text)
    return ToolResult(
        ok=True,
        data={"filename": filename, "body": body, "meta": meta},
        evidence=[{"kind": "policy_read", "filename": filename}],
    )


def _conflict(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    groups: dict[str, set[str]] = {}
    files: dict[str, list[str]] = {}
    for item in results:
        group = item.get("conflict_group")
        position = item.get("position")
        if group and position:
            groups.setdefault(group, set()).add(position)
            files.setdefault(group, []).append(item["filename"])
    for group, positions in groups.items():
        if len(positions) > 1:
            return {"group": group, "positions": sorted(positions), "filenames": files[group]}
    return None
