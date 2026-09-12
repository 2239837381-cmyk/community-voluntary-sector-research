#!/usr/bin/env python3
"""Build a compact, local-only index for a Markdown literature corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def front_matter_title(text: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    if end == -1:
        return ""
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() in {"title", "题名", "标题"}:
            return value.strip().strip('"\'')
    return ""


def labelled_title(text: str) -> str:
    labels = r"title|article\s+title|paper\s+title|题名|标题|论文题目|文章标题"
    for line in text.splitlines()[:120]:
        match = re.match(rf"^\s*(?:{labels})\s*[:：]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            candidate = clean_title(match.group(1))
            if candidate:
                return candidate
    return ""


def clean_title(value: str) -> str:
    value = re.sub(r"[*`_]", "", value)
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n:-：")
    return value


def is_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"(?:cite|citation|ref|doc|paper)?[-_ ]?\d+", value.strip(), flags=re.IGNORECASE))


def title_for(path: Path, text: str) -> tuple[str, str, str]:
    title = front_matter_title(text)
    if title:
        return clean_title(title), "front_matter", "high"
    title = labelled_title(text)
    if title:
        return title, "label", "high"
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            candidate = clean_title(match.group(1))
            if candidate and candidate not in {"摘要", "关键词", "引言", "简介", "方法", "结果", "讨论", "结论", "参考文献"}:
                return candidate, "heading", "high"
    filename_title = clean_title(path.stem)
    if filename_title and not is_identifier(filename_title):
        return filename_title, "filename", "medium"
    return filename_title or "未命名文献", "filename_identifier", "low"


def summary_for(text: str, limit: int = 700) -> str:
    body = re.sub(r"(?s)^---\n.*?\n---\s*", "", text, count=1)
    body = re.sub(r"^#{1,6}\s+", "", body, flags=re.MULTILINE)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit]


def chinese_ratio(text: str) -> float:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return 0.0
    return sum("\u4e00" <= character <= "\u9fff" for character in letters) / len(letters)


def preference_score(path: Path, text: str) -> float:
    labels = {part.lower() for part in path.parts}
    score = 0.0
    if "zh_clean" in labels:
        score += 40
    elif "zh_existing" in labels:
        score += 30
    elif any("翻译" in part or "阅读" in part for part in path.parts):
        score += 20
    elif "markdown" in labels:
        score += 10
    return score + chinese_ratio(text[:6000]) * 10 + min(len(text), 100000) / 100000


def is_excluded(path: Path, excluded: set[str]) -> bool:
    return any(part.lower() in excluded for part in path.parts)


def markdown_paths(root: Path, excluded: set[str]):
    """Walk only source directories, pruning large generated trees early."""
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        folder = Path(current)
        for name in filenames:
            path = folder / name
            if path.suffix.lower() in {".md", ".markdown"}:
                yield path


def count_source_pdfs(root: Path, excluded: set[str]) -> int:
    count = 0
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        count += sum(Path(name).suffix.lower() == ".pdf" for name in filenames)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local, deduplicated Markdown corpus index.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    configured_root = str(config.get("corpus_root", "")).strip()
    if not configured_root or configured_root.startswith("<"):
        parser.error("set corpus_root to a real local directory before building the index")
    root_value = Path(configured_root).expanduser()
    if not root_value.is_absolute():
        root_value = args.config.parent / root_value
    root = root_value.resolve()
    if not root.is_dir():
        parser.error(f"corpus root is not a directory: {root}")
    excluded = {str(name).lower() for name in config.get("excluded_directory_names", [])}
    candidates: dict[str, tuple[float, dict[str, Any]]] = {}
    skipped = Counter()
    for path in markdown_paths(root, excluded):
        relative = path.relative_to(root)
        if is_excluded(relative, excluded):
            skipped["excluded_directory"] += 1
            continue
        try:
            text = read_markdown(path)
        except OSError:
            skipped["unreadable"] += 1
            continue
        if len(re.sub(r"\s+", "", text)) < 160:
            skipped["too_short"] += 1
            continue
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        title, title_source, title_confidence = title_for(path, text)
        item = {
            "id": f"doc-{digest[:12]}",
            "title": title,
            "title_source": title_source,
            "title_confidence": title_confidence,
            "relative_path": relative.as_posix(),
            "collection": relative.parts[0] if relative.parts else "",
            "language": "zh" if chinese_ratio(text[:6000]) >= 0.2 else "other",
            "characters": len(text),
            "summary": summary_for(text),
        }
        if config.get("include_absolute_path", False):
            item["absolute_path"] = str(path)
        score = preference_score(relative, text)
        existing = candidates.get(digest)
        if existing is None or score > existing[0]:
            if existing is not None:
                skipped["exact_duplicate"] += 1
            candidates[digest] = (score, item)
        else:
            skipped["exact_duplicate"] += 1
    documents = sorted((item for _, item in candidates.values()), key=lambda item: (item["collection"], item["title"]))
    source_pdfs = count_source_pdfs(root, excluded)
    counts = {
        "source_pdfs": source_pdfs,
        "indexed_markdown": len(documents),
        "unindexed_pdf_estimate": max(source_pdfs - len(documents), 0),
        "coverage_ratio_estimate": round(len(documents) / source_pdfs, 4) if source_pdfs else None,
        "skipped": dict(sorted(skipped.items())),
        "collections": dict(sorted(Counter(item["collection"] for item in documents).items())),
    }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_root": str(root),
        "documents": documents,
        "counts": counts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = config.get("report_path")
    if report_path:
        report = Path(str(report_path)).expanduser()
        if not report.is_absolute():
            report = args.config.parent / report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
