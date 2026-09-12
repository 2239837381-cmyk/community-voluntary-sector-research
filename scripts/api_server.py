#!/usr/bin/env python3
"""Small dependency-free HTTP API for a local literature corpus."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any

from extract_evidence import body_relevance, resolve_path, snippet, tokens
from search_corpus import score


def bounded_int(value: str | None, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value or default), maximum))
    except ValueError:
        return default


class CorpusService:
    def __init__(self, index_path: Path, allow_full_text: bool = False, catalog_path: Path | None = None):
        self.index_path = catalog_path or index_path
        self.allow_full_text = allow_full_text
        self.public_catalog = catalog_path is not None
        self.index: dict[str, Any] = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.documents = {str(item.get("id")): item for item in self.index.get("documents", [])}

    def search(self, query: str, limit: int = 8, collection: str | None = None, language: str | None = None) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        matches = []
        for document in self.documents.values():
            if collection and document.get("collection") != collection:
                continue
            if language and document.get("language") != language:
                continue
            relevance = score(document, query, query_terms)
            if relevance:
                matches.append({"score": relevance, **document})
        matches.sort(key=lambda item: (-item["score"], str(item.get("title", ""))))
        return [self.public_document(item) for item in matches[:max(limit, 1)]]

    def evidence(self, query: str, limit: int = 5, context: int = 320) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        candidates: list[tuple[int, int, dict[str, Any], str]] = []
        for document in self.documents.values():
            if self.public_catalog:
                text = " ".join(str(document.get(key, "")) for key in ("abstract", "summary", "keywords"))
            else:
                path = resolve_path(self.index, document)
                if path is None:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            excerpt = snippet(text, query_terms, max(context, 40))
            if excerpt:
                candidates.append((body_relevance(text, query_terms), score(document, query, query_terms), document, excerpt))
        candidates.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("title", ""))))
        return [
            {
                **self.public_document(document),
                "body_matches": body_score,
                "evidence_excerpt": excerpt,
            }
            for body_score, _, document, excerpt in candidates[:max(limit, 1)]
        ]

    def document(self, document_id: str, include_text: bool = False) -> dict[str, Any] | None:
        document = self.documents.get(document_id)
        if document is None:
            return None
        result = self.public_document(document)
        if include_text and self.allow_full_text and not self.public_catalog:
            path = resolve_path(self.index, document)
            if path is not None:
                result["text"] = path.read_text(encoding="utf-8", errors="replace")
        return result

    @staticmethod
    def public_document(document: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in document.items() if key != "absolute_path"}


class ApiHandler(BaseHTTPRequestHandler):
    service: CorpusService
    api_key: str
    cors_origin: str

    def log_message(self, format: str, *args: Any) -> None:
        print("[api] " + format % args)

    def authorized(self) -> bool:
        if not self.api_key:
            return True
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, f"Bearer {self.api_key}")

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.cors_origin:
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        if self.cors_origin:
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json({"status": "ok", "documents": len(self.service.documents)})
            return
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, 401)
            return
        params = parse_qs(parsed.query)
        if parsed.path == "/api/v1/search":
            query = params.get("q", [""])[0].strip()
            if not query:
                self.send_json({"error": "q is required"}, 400)
                return
            results = self.service.search(
                query,
                bounded_int(params.get("limit", [None])[0], 8, 50),
                params.get("collection", [None])[0],
                params.get("language", [None])[0],
            )
            self.send_json({"api_version": "1", "query": query, "count": len(results), "matches": results})
            return
        if parsed.path == "/api/v1/evidence":
            query = params.get("q", [""])[0].strip()
            if not query:
                self.send_json({"error": "q is required"}, 400)
                return
            results = self.service.evidence(
                query,
                bounded_int(params.get("limit", [None])[0], 5, 20),
                bounded_int(params.get("context", [None])[0], 320, 1200),
            )
            self.send_json({"api_version": "1", "query": query, "count": len(results), "evidence": results})
            return
        prefix = "/api/v1/documents/"
        if parsed.path.startswith(prefix):
            document_id = unquote(parsed.path[len(prefix):]).strip()
            include_text = params.get("include_text", ["0"])[0] == "1"
            result = self.service.document(document_id, include_text)
            if result is None:
                self.send_json({"error": "document not found"}, 404)
            else:
                self.send_json({"api_version": "1", "document": result})
            return
        self.send_json({"error": "not found"}, 404)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve a local literature index over HTTP.")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, help="serve a public metadata/abstract catalog instead of full local index")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--api-key", default=os.environ.get("LIT_API_KEY", ""))
    parser.add_argument("--allow-full-text", action="store_true")
    parser.add_argument("--cors-origin", default="")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.api_key:
        parser.error("--api-key or LIT_API_KEY is required when exposing the API beyond localhost")
    service = CorpusService(args.index, args.allow_full_text, args.catalog)
    handler = type("ConfiguredApiHandler", (ApiHandler,), {})
    handler.service = service
    handler.api_key = args.api_key
    handler.cors_origin = args.cors_origin
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"literature API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
