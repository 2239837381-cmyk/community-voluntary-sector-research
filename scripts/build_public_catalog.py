#!/usr/bin/env python3
"""Build a public-safe catalog containing metadata and abstracts, not full text."""

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


SECTION_NAMES = {
    "abstract": {"abstract", "摘要", "内容摘要", "摘要内容"},
    "keywords": {"keywords", "keyword", "关键词", "关键字"},
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n:-：")


def is_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"(?:cite|citation|ref|doc|paper)?[-_ ]?\d+", value.strip(), flags=re.IGNORECASE))


def heading_name(line: str) -> str:
    match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
    return clean(match.group(1)).lower() if match else ""


def section(text: str, names: set[str]) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if heading_name(line) in names:
            collected: list[str] = []
            for candidate in lines[index + 1:]:
                if re.match(r"^#{1,6}\s+", candidate):
                    break
                collected.append(candidate)
            value = clean(" ".join(collected))
            if value:
                return value[:4000]
    return ""


def front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            data[key.strip().lower()] = clean(value.strip().strip('"\''))
    return data


def title_from_path(path: Path) -> tuple[str, str, str]:
    title = clean(path.stem)
    if not title:
        return "未命名文献", "filename_identifier", "low"
    if is_identifier(title):
        return title, "filename_identifier", "low"
    return title, "filename", "medium"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def markdown_files(root: Path, excluded: set[str]):
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        for name in filenames:
            path = Path(current) / name
            if path.suffix.lower() in {".md", ".markdown"}:
                yield path


def pdf_files(root: Path, excluded: set[str]):
    for current, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if name.lower() not in excluded]
        for name in filenames:
            path = Path(current) / name
            if path.suffix.lower() == ".pdf":
                yield path


def stable_id(relative: str) -> str:
    return "pdf-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a public-safe literature catalog.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index", type=Path, help="optional local index used to enrich title and summary metadata")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    configured_root = str(config.get("corpus_root", "")).strip()
    if not configured_root or configured_root.startswith("<"):
        parser.error("set corpus_root to a real local directory before building the catalog")
    root_value = Path(configured_root).expanduser()
    if not root_value.is_absolute():
        root_value = args.config.parent / root_value
    root = root_value.resolve()
    if not root.is_dir():
        parser.error(f"corpus root is not a directory: {root}")
    excluded = {str(name).lower() for name in config.get("excluded_directory_names", [])}

    markdown_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for path in markdown_files(root, excluded):
        relative = path.relative_to(root).as_posix()
        text = read_text(path)
        metadata = front_matter(text)
        title = metadata.get("title") or metadata.get("题名") or metadata.get("标题")
        if not title:
            for line in text.splitlines():
                match = re.match(r"^#\s+(.+?)\s*$", line)
                if match and clean(match.group(1)) not in {"摘要", "关键词", "引言", "简介", "方法"}:
                    title = clean(match.group(1))
                    break
        if not title:
            title, title_source, title_confidence = title_from_path(path)
        else:
            title, title_source, title_confidence = clean(title), "markdown_metadata", "high"
        collection = relative.split("/", 1)[0] if "/" in relative else ""
        markdown_by_key[(collection.lower(), path.stem.lower())] = {
            "title": title,
            "title_source": title_source,
            "title_confidence": title_confidence,
            "abstract": section(text, SECTION_NAMES["abstract"]),
            "keywords": section(text, SECTION_NAMES["keywords"]),
            "markdown_path": relative,
        }

    index_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    if args.index and args.index.is_file():
        index_payload = json.loads(args.index.read_text(encoding="utf-8"))
        for item in index_payload.get("documents", []):
            relative = str(item.get("relative_path", ""))
            key = (str(item.get("collection", "")).lower(), Path(relative).stem.lower())
            index_by_key[key] = item

    documents: list[dict[str, Any]] = []
    counts = Counter()
    for path in pdf_files(root, excluded):
        relative = path.relative_to(root).as_posix()
        collection = relative.split("/", 1)[0] if "/" in relative else ""
        key = (collection.lower(), path.stem.lower())
        source = markdown_by_key.get(key)
        if source is None and key in index_by_key:
            indexed = index_by_key[key]
            source = {
                "title": indexed.get("title", path.stem),
                "title_source": indexed.get("title_source", "index"),
                "title_confidence": indexed.get("title_confidence", "low"),
                "abstract": "",
                "keywords": "",
                "markdown_path": indexed.get("relative_path", ""),
            }
        if source is None:
            title, title_source, title_confidence = title_from_path(path)
            source = {
                "title": title,
                "title_source": title_source,
                "title_confidence": title_confidence,
                "abstract": "",
                "keywords": "",
                "markdown_path": "",
            }
        abstract = source["abstract"]
        keywords = source["keywords"]
        if abstract:
            counts["with_abstract"] += 1
        else:
            counts["without_abstract"] += 1
        if source["title_confidence"] == "low":
            counts["low_confidence_title"] += 1
        documents.append({
            "id": stable_id(relative),
            "title": source["title"],
            "title_source": source["title_source"],
            "title_confidence": source["title_confidence"],
            "collection": collection,
            "relative_path": relative,
            "abstract": abstract,
            "keywords": keywords,
            "summary": " ".join(part for part in (abstract, keywords) if part),
            "content_level": "metadata_abstract" if abstract else "metadata_only",
            "content_note": "formal abstract and keywords" if abstract else "metadata only; no abstract was identified",
        })
    documents.sort(key=lambda item: (item["collection"], item["title"], item["relative_path"]))
    counts["total_pdfs"] = len(documents)
    payload = {
        "schema_version": 1,
        "catalog_type": "public_metadata_abstract",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "counts": dict(sorted(counts.items())),
        "data_policy": "Contains metadata, abstracts and keywords only; no PDF or full Markdown text.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
