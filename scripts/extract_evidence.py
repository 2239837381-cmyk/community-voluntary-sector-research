#!/usr/bin/env python3
"""Extract query-centered evidence snippets from a local Markdown corpus."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def tokens(query: str) -> list[str]:
    latin = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    return sorted(set(latin + cjk), key=len, reverse=True)


def resolve_path(index: dict[str, Any], document: dict[str, Any]) -> Path | None:
    absolute = document.get("absolute_path")
    if absolute:
        candidate = Path(str(absolute))
        if candidate.is_file():
            return candidate
    root = index.get("corpus_root")
    relative = document.get("relative_path")
    if root and relative:
        candidate = Path(str(root)) / str(relative)
        if candidate.is_file():
            return candidate
    return None


def snippet(text: str, terms: list[str], context: int) -> str:
    positions = [text.lower().find(term.lower()) for term in terms]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return ""
    position = min(positions)
    start = max(0, position - context)
    end = min(len(text), position + context)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    if start:
        excerpt = "…" + excerpt
    if end < len(text):
        excerpt += "…"
    return excerpt


def relevance(document: dict[str, Any], query: str, terms: list[str]) -> int:
    title = str(document.get("title", "")).lower()
    path = str(document.get("relative_path", "")).lower()
    summary = str(document.get("summary", "")).lower()
    query_lower = query.lower()
    score = 0
    if query_lower in title:
        score += 80
    if query_lower in summary:
        score += 20
    for term in terms:
        score += 18 * title.count(term)
        score += 8 * path.count(term)
        score += 3 * summary.count(term)
    return score


def body_relevance(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term.lower()) for term in terms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract evidence snippets from a local literature corpus.")
    parser.add_argument("query")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--context", type=int, default=320)
    args = parser.parse_args()

    index = json.loads(args.index.read_text(encoding="utf-8"))
    query_terms = tokens(args.query)
    evidence: list[dict[str, Any]] = []
    candidates: list[tuple[int, dict[str, Any], str]] = []
    for document in index.get("documents", []):
        path = resolve_path(index, document)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = snippet(text, query_terms, max(args.context, 40))
        if not excerpt:
            continue
        candidates.append((body_relevance(text, query_terms), document, excerpt))

    for body_score, document, excerpt in sorted(
        candidates,
        key=lambda item: (-item[0], -relevance(item[1], args.query, query_terms), str(item[1].get("title", ""))),
    )[:max(args.limit, 1)]:
        evidence.append({
            "id": document.get("id"),
            "title": document.get("title"),
            "collection": document.get("collection"),
            "relative_path": document.get("relative_path"),
            "relevance": relevance(document, args.query, query_terms),
            "body_matches": body_score,
            "evidence_excerpt": excerpt,
        })

    print(json.dumps({"query": args.query, "evidence": evidence}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
