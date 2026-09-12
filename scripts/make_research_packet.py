#!/usr/bin/env python3
"""Create a compact Markdown research packet from a local corpus index."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from extract_evidence import body_relevance, resolve_path, snippet, tokens
from search_corpus import score


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a source-grounded research packet.")
    parser.add_argument("query")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    index: dict[str, Any] = json.loads(args.index.read_text(encoding="utf-8"))
    query_terms = tokens(args.query)
    ranked = sorted(
        index.get("documents", []),
        key=lambda item: (-score(item, args.query, query_terms), str(item.get("title", ""))),
    )
    rows: list[tuple[int, dict[str, Any], str]] = []
    for document in ranked:
        path = resolve_path(index, document)
        if path is None:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        excerpt = snippet(text, query_terms, 360)
        if excerpt:
            rows.append((body_relevance(text, query_terms), document, excerpt))
    rows.sort(key=lambda item: (-item[0], str(item[1].get("title", ""))))

    limit = max(args.limit, 1)
    lines = [
        f"# 文献研究包：{args.query}",
        "",
        "> 本研究包仅基于已配置的本地文献索引生成。正文结论仍需回到原始 Markdown 核对上下文。",
        "",
        f"- 候选文献数：{min(len(rows), limit)}",
        f"- 语料根目录：`{index.get('corpus_root', '')}`",
        "",
        "## 候选证据",
        "",
    ]
    if not rows:
        lines.append("当前索引中未找到包含检索词的可读取文献。")
    for number, (body_score, document, excerpt) in enumerate(rows[:limit], start=1):
        lines.extend([
            f"### {number}. {document.get('title', '未命名文献')}",
            "",
            f"- 文献编号：`{document.get('id', '')}`",
            f"- 集合：{document.get('collection', '')}",
            f"- 标题置信度：{document.get('title_confidence', 'unknown')}",
            f"- 正文命中次数：{body_score}",
            f"- 来源路径：`{document.get('relative_path', '')}`",
            "",
            f"> {excerpt}",
            "",
        ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "documents": min(len(rows), limit)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
