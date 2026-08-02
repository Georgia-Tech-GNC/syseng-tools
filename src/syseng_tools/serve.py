from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from syseng_tools.project import ProjectConfig


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def generated_html_dir(project: ProjectConfig) -> Path:
    return project.strictdoc_output_dir / "html"


def create_static_server(
    html_dir: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    validate_generated_html(html_dir)
    handler = partial(SimpleHTTPRequestHandler, directory=str(html_dir))
    return ThreadingHTTPServer((host, port), handler)


def serve_static_site(
    html_dir: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    with create_static_server(html_dir, host, port) as server:
        actual_host, actual_port = server.server_address[:2]
        print(f"Serving StrictDoc HTML from {html_dir}")
        print(f"Open http://{actual_host}:{actual_port}/")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def validate_generated_html(html_dir: Path) -> None:
    if not html_dir.is_dir():
        raise SystemExit(
            "Generated StrictDoc HTML not found: "
            f"{html_dir}\nRun: syseng export"
        )

    index_path = html_dir / "index.html"
    if not index_path.is_file():
        raise SystemExit(
            "Generated StrictDoc HTML index not found: "
            f"{index_path}\nRun: syseng export"
        )
