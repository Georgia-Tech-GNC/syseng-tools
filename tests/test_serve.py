from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from syseng_tools.serve import create_static_server, validate_generated_html


class ServeTests(unittest.TestCase):
    def test_missing_html_directory_points_author_to_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            html_dir = Path(tmpdir) / "build" / "strictdoc" / "html"

            with self.assertRaises(SystemExit) as raised:
                validate_generated_html(html_dir)

        message = str(raised.exception)
        self.assertIn("Generated StrictDoc HTML not found", message)
        self.assertIn("Run: syseng export", message)

    def test_missing_index_points_author_to_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            html_dir = Path(tmpdir) / "build" / "strictdoc" / "html"
            html_dir.mkdir(parents=True)

            with self.assertRaises(SystemExit) as raised:
                validate_generated_html(html_dir)

        message = str(raised.exception)
        self.assertIn("Generated StrictDoc HTML index not found", message)
        self.assertIn("Run: syseng export", message)

    def test_static_server_serves_generated_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            html_dir = Path(tmpdir) / "build" / "strictdoc" / "html"
            html_dir.mkdir(parents=True)
            (html_dir / "index.html").write_text(
                "<!doctype html><title>StrictDoc</title><p>Generated docs</p>",
                encoding="utf-8",
            )

            server = create_static_server(html_dir, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                host, port = server.server_address[:2]
                with urlopen(f"http://{host}:{port}/", timeout=5) as response:
                    body = response.read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("Generated docs", body)


if __name__ == "__main__":
    unittest.main()
