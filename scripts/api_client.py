#!/usr/bin/env python3
"""Command-line client for the literature search API."""

from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="Query a community literature API.")
    parser.add_argument("base_url")
    parser.add_argument("query")
    parser.add_argument("--mode", choices=["search", "evidence"], default="search")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--api-key", default=os.environ.get("LIT_API_KEY", ""))
    args = parser.parse_args()
    endpoint = "/api/v1/evidence" if args.mode == "evidence" else "/api/v1/search"
    url = args.base_url.rstrip("/") + endpoint + "?" + urlencode({"q": args.query, "limit": args.limit})
    headers = {"Accept": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        print(json.dumps(json.loads(response.read().decode("utf-8")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
