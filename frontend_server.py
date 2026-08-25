from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5173


class ReactRouterHandler(SimpleHTTPRequestHandler):
    """Serve static assets and fall back to index.html for React Router routes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        requested = ROOT / self.path.lstrip("/").split("?", 1)[0]
        if self.path != "/" and not requested.is_file():
            self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    print(f"MinFit React đang chạy tại http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), ReactRouterHandler).serve_forever()
