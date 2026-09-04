"""Serve Rolling News locally and proxy its read-only API to Park Intel."""

from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Type
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_API_ORIGIN = "http://127.0.0.1:8001"
API_TIMEOUT_SECONDS = 30


def make_handler(
    *,
    static_dir: Path | str,
    api_origin: str,
) -> Type[SimpleHTTPRequestHandler]:
    """Create a static handler whose GET/HEAD `/api/` requests are proxied."""
    static_root = str(Path(static_dir).resolve())
    upstream_origin = api_origin.rstrip("/")

    class RollingNewsHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=static_root, **kwargs)

        def do_GET(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy_api(send_body=True)
                return
            super().do_GET()

        def do_HEAD(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy_api(send_body=False)
                return
            super().do_HEAD()

        def _proxy_api(self, *, send_body: bool) -> None:
            request = Request(
                upstream_origin + self.path,
                headers={"Accept": self.headers.get("Accept", "application/json")},
                method="GET" if send_body else "HEAD",
            )
            try:
                with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                    body = response.read() if send_body else b""
                    self.send_response(response.status)
                    self.send_header(
                        "Content-Type",
                        response.headers.get("Content-Type", "application/json"),
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if send_body:
                        self.wfile.write(body)
            except HTTPError as exc:
                body = exc.read() if send_body else b""
                self.send_response(exc.code)
                self.send_header(
                    "Content-Type",
                    exc.headers.get("Content-Type", "application/json"),
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if send_body:
                    self.wfile.write(body)
            except (TimeoutError, URLError, OSError) as exc:
                body = json.dumps({
                    "detail": "Park Intel API unavailable",
                    "error": type(exc).__name__,
                }).encode("utf-8")
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body) if send_body else 0))
                self.end_headers()
                if send_body:
                    self.wfile.write(body)

    return RollingNewsHandler


class RollingNewsServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    static_dir = Path(os.getenv("ROLLINGNEWS_STATIC_DIR", root / "rollingnews"))
    api_origin = os.getenv("PARK_INTEL_API_ORIGIN", DEFAULT_API_ORIGIN)
    host = os.getenv("ROLLINGNEWS_HOST", DEFAULT_HOST)
    port = int(os.getenv("ROLLINGNEWS_PORT", str(DEFAULT_PORT)))
    server = RollingNewsServer(
        (host, port),
        make_handler(static_dir=static_dir, api_origin=api_origin),
    )
    print(
        f"Rolling News serving {static_dir} at http://{host}:{port}; "
        f"proxying /api/ to {api_origin}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
