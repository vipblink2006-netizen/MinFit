from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from workflow_api import analyze, create_client, list_projects, sync_market_data


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5173


class ReactRouterHandler(SimpleHTTPRequestHandler):
    """Serve static assets and fall back to index.html for React Router routes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _api_error(self, error: Exception) -> None:
        self._send_json({"error": str(error)}, 400)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        endpoint = self.path.split("?", 1)[0]
        if endpoint == "/api/projects":
            try:
                self._send_json({"projects": list_projects()})
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/projects/sync-market":
            try:
                self._send_json(sync_market_data())
            except Exception as error:
                self._api_error(error)
            return

        requested = ROOT / self.path.lstrip("/").split("?", 1)[0]
        if self.path != "/" and not requested.is_file():
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        endpoint = self.path.split("?", 1)[0]
        if not endpoint.startswith("/api/"):
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if endpoint == "/api/analyze":
                self._send_json(analyze(payload))
            elif endpoint == "/api/clients":
                self._send_json({"client": create_client(payload)}, 201)
            elif endpoint == "/api/projects/sync-market":
                self._send_json(sync_market_data())
            else:
                self.send_error(404)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._api_error(error)


if __name__ == "__main__":
    print(f"MinFit React đang chạy tại http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), ReactRouterHandler).serve_forever()
