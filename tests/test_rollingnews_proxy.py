"""End-to-end HTTP contract for the local Rolling News surface."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

from scripts.serve_rollingnews import make_handler


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"path": self.path, "items": [{"id": 1}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def test_local_surface_serves_html_and_proxies_read_only_api(tmp_path):
    (tmp_path / "index.html").write_text("ROLLING NEWS FIXTURE", encoding="utf-8")
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    upstream_thread = _start(upstream)
    upstream_origin = f"http://127.0.0.1:{upstream.server_port}"

    proxy = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(static_dir=tmp_path, api_origin=upstream_origin),
    )
    proxy_thread = _start(proxy)
    origin = f"http://127.0.0.1:{proxy.server_port}"

    try:
        with urlopen(origin + "/", timeout=3) as response:
            assert response.status == 200
            assert response.read().decode() == "ROLLING NEWS FIXTURE"

        with urlopen(origin + "/api/ui/realtime?window=24h&limit=1", timeout=3) as response:
            payload = json.load(response)
            assert response.status == 200
            assert response.headers["Content-Type"] == "application/json"
            assert payload == {
                "path": "/api/ui/realtime?window=24h&limit=1",
                "items": [{"id": 1}],
            }
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy_thread.join(timeout=3)
        upstream_thread.join(timeout=3)


def test_static_launcher_uses_the_api_proxy():
    launcher = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "rollingnews-static-service.sh"
    ).read_text(encoding="utf-8")

    assert "serve_rollingnews.py" in launcher
    assert "http.server 8787" not in launcher
