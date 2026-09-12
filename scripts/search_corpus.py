#!/usr/bin/env python3
"""Search a local corpus index and return source-grounded reading targets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def tokens(query: str) -> list[str]:
    latin = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    return sorted(set(latin + cjk), key=len, reverse=True)


def score(document: dict[str, object], query: str, query_tokens: list[str]) -> int:
    title = str(document["title"]).lower()
    path = str(document["relative_path"]).lower()
    summary = str(document["summary"]).lower()
    query_lower = query.lower()
    total = 0
    if query_lower in title:
        total += 80
    if query_lower in summary:
        total += 20
    for token in query_tokens:
        total += 18 * title.count(token)
        total += 8 * path.count(token)
        total += 3 * summary.count(token)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Search a local literature corpus index.")
    parser.add_argument("query")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--collection", action="append", default=[])
    parser.add_argument("--language")
    parser.add_argument("--min-score", type=int, default=1)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    query_tokens = tokens(args.query)
    matches = []
    for document in index["documents"]:
        if args.collection and document.get("collection") not in args.collection:
            continue
        if args.language and document.get("language") != args.language:
            continue
        relevance = score(document, args.query, query_tokens)
        if relevance >= args.min_score:
            matches.append({"score": relevance, **document})
    matches.sort(key=lambda item: (-item["score"], item["title"]))
    print(json.dumps({"query": args.query, "matches": matches[:max(args.limit, 1)]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
