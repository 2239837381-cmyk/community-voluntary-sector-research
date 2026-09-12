import json
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from urllib.request import urlopen
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_corpus_index import title_for  # noqa: E402
from api_server import ApiHandler, CorpusService, ThreadingHTTPServer  # noqa: E402
from search_corpus import score, tokens  # noqa: E402


class CorpusToolsTests(unittest.TestCase):
    def test_title_recovery_priority(self):
        title, source, confidence = title_for(
            Path("CITE001.md"),
            "---\ntitle: Front matter title\n---\n# Heading title\n",
        )
        self.assertEqual(title, "Front matter title")
        self.assertEqual(source, "front_matter")
        self.assertEqual(confidence, "high")

    def test_identifier_is_marked_low_confidence(self):
        title, source, confidence = title_for(Path("CITE015.md"), "## 摘要\n正文内容足够长。")
        self.assertEqual(title, "CITE015")
        self.assertEqual(source, "filename_identifier")
        self.assertEqual(confidence, "low")

    def test_index_uses_relative_paths_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "collection").mkdir()
            (root / "collection" / "paper.md").write_text(
                "# A useful paper\n\n" + "community volunteering evidence " * 30,
                encoding="utf-8",
            )
            config = root / "config.json"
            output = root / "index.json"
            config.write_text(json.dumps({"corpus_root": "."}), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_corpus_index.py"), "--config", str(config), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            document = json.loads(output.read_text(encoding="utf-8"))["documents"][0]
            self.assertEqual(document["relative_path"], "collection/paper.md")
            self.assertNotIn("absolute_path", document)

    def test_search_score_prefers_title_match(self):
        title_match = {"title": "志愿者领导力", "relative_path": "a.md", "summary": ""}
        body_only = {"title": "其他主题", "relative_path": "b.md", "summary": "志愿者领导力"}
        query_terms = tokens("志愿者领导力")
        self.assertGreater(score(title_match, "志愿者领导力", query_terms), score(body_only, "志愿者领导力", query_terms))

    def test_api_returns_search_and_evidence_without_absolute_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "paper.md"
            source.write_text("# Volunteer leadership\n\n" + "志愿者领导力与组织承诺。" * 30, encoding="utf-8")
            index = root / "index.json"
            index.write_text(json.dumps({
                "corpus_root": str(root),
                "documents": [{
                    "id": "doc-test",
                    "title": "Volunteer leadership",
                    "relative_path": "paper.md",
                    "collection": "test",
                    "language": "zh",
                    "summary": "志愿者领导力与组织承诺",
                }],
            }, ensure_ascii=False), encoding="utf-8")
            service = CorpusService(index)
            results = service.search("志愿者领导力")
            evidence = service.evidence("志愿者领导力")
            self.assertEqual(results[0]["id"], "doc-test")
            self.assertEqual(evidence[0]["id"], "doc-test")
            self.assertNotIn("absolute_path", results[0])
            self.assertNotIn("text", evidence[0])

            handler = type("TestApiHandler", (ApiHandler,), {})
            handler.service = service
            handler.api_key = ""
            handler.cors_origin = ""
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/v1/search?{urlencode({'q': '志愿者领导力'})}"
                with urlopen(url, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload["count"], 1)
            finally:
                server.shutdown()
                server.server_close()

    def test_public_catalog_contains_metadata_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "collection").mkdir()
            (root / "collection" / "paper.pdf").write_bytes(b"pdf placeholder")
            (root / "collection" / "paper.md").write_text(
                "# Public title\n\n## 摘要\n这是摘要内容。\n\n## 关键词\n共同体、志愿服务\n",
                encoding="utf-8",
            )
            config = root / "config.json"
            output = root / "catalog.json"
            config.write_text(json.dumps({"corpus_root": str(root)}), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPTS / "build_public_catalog.py"), "--config", str(config), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            document = json.loads(output.read_text(encoding="utf-8"))["documents"][0]
            self.assertEqual(document["title"], "Public title")
            self.assertEqual(document["content_level"], "metadata_abstract")
            self.assertEqual(document["abstract"], "这是摘要内容。")
            self.assertNotIn("absolute_path", document)
            self.assertNotIn("text", document)
            service = CorpusService(output, catalog_path=output)
            self.assertEqual(service.search("共同体")[0]["id"], document["id"])
            self.assertTrue(service.evidence("共同体"))


if __name__ == "__main__":
    unittest.main()
