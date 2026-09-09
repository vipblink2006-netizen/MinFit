from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import socket
from urllib.parse import parse_qs, urlparse
from workflow_api import (
    analyze,
    authenticate_user,
    create_client,
    list_clients,
    delete_client,
    create_or_update_project,
    delete_project,
    get_broker_selection,
    get_system_stats,
    list_projects,
    list_users,
    parse_raw_project_text,
    save_broker_selection,
    save_user,
    sync_market_data,
    toggle_project_status,
    toggle_user_status,
    verify_session,
    revoke_session,
)


ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("PORT", "5173"))


class ReactRouterHandler(SimpleHTTPRequestHandler):
    """Serve static assets and fall back to index.html for React Router routes with stateful session auth middleware."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _set_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"]
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _api_error(self, error: Exception) -> None:
        self._send_json({"error": str(error)}, 400)

    def _get_authenticated_session(self) -> dict[str, Any] | None:
        """Extract and verify Bearer token from Authorization header against Sessions table."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ", 1)[1].strip()
        return verify_session(token)

    def _require_auth(self, allowed_roles: list[str] | None = None) -> dict[str, Any] | None:
        """Enforce authentication and role permissions. Send 401/403 and return None if unauthorized."""
        session = self._get_authenticated_session()
        if not session:
            self._send_json({"error": "Unauthorized. Vui lòng đăng nhập để tiếp tục."}, 401)
            return None
        if allowed_roles and session.get("role") not in allowed_roles:
            self._send_json({"error": "Forbidden. Bạn không có quyền truy cập chức năng này."}, 403)
            return None
        return session

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        endpoint = parsed_url.path
        query = parse_qs(parsed_url.query)

        if endpoint == "/api/projects":
            try:
                broker_id = query.get("broker_id", [None])[0]
                include_inactive = query.get("include_inactive", ["0"])[0] in ("1", "true")
                self._send_json({"projects": list_projects(broker_id=broker_id, include_inactive=include_inactive)})
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/projects/sync-market":
            if not self._require_auth(allowed_roles=["admin"]): return
            try:
                self._send_json(sync_market_data())
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/broker/selection":
            session = self._require_auth(allowed_roles=["broker", "admin"])
            if not session: return
            try:
                broker_id = query.get("broker_id", [session["user_id"]])[0]
                self._send_json({"selected_project_ids": get_broker_selection(broker_id)})
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/users" or endpoint == "/api/admin/users":
            if not self._require_auth(allowed_roles=["admin"]): return
            try:
                self._send_json({"users": list_users(), "stats": get_system_stats()})
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/admin/system-stats":
            if not self._require_auth(allowed_roles=["admin"]): return
            try:
                self._send_json(get_system_stats())
            except Exception as error:
                self._api_error(error)
            return
        elif endpoint == "/api/clients":
            session = self._require_auth(allowed_roles=["broker", "admin"])
            if not session: return
            try:
                broker_id = query.get("broker_id", [session["user_id"]])[0]
                self._send_json({"clients": list_clients(broker_id=broker_id)})
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
            client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

            if endpoint == "/api/auth/login":
                self._send_json(authenticate_user(payload, client_ip=client_ip))
            elif endpoint == "/api/auth/logout":
                auth_header = self.headers.get("Authorization", "")
                token = auth_header.split(" ", 1)[1].strip() if "Bearer " in auth_header else ""
                if token:
                    revoke_session(token)
                self._send_json({"success": True, "message": "Đã đăng xuất thành công."})
            elif endpoint == "/api/analyze":
                self._send_json(analyze(payload))
            elif endpoint == "/api/clients":
                session = self._require_auth(allowed_roles=["broker", "admin"])
                if not session: return
                if "broker_id" not in payload:
                    payload["broker_id"] = session["user_id"]
                self._send_json({"client": create_client(payload)}, 201)
            elif endpoint == "/api/clients/delete":
                if not self._require_auth(allowed_roles=["broker", "admin"]): return
                cid = int(payload.get("client_id", 0))
                self._send_json(delete_client(cid))
            elif endpoint == "/api/projects/sync-market":
                if not self._require_auth(allowed_roles=["admin"]): return
                self._send_json(sync_market_data())
            elif endpoint == "/api/projects/parse-text":
                if not self._require_auth(allowed_roles=["admin"]): return
                self._send_json(parse_raw_project_text(payload.get("raw_text", "")))
            elif endpoint == "/api/projects":
                if not self._require_auth(allowed_roles=["admin"]): return
                self._send_json(create_or_update_project(payload))
            elif endpoint == "/api/projects/toggle":
                if not self._require_auth(allowed_roles=["admin"]): return
                pid = str(payload.get("project_id", ""))
                is_active = bool(payload.get("is_active", True))
                self._send_json(toggle_project_status(pid, is_active))
            elif endpoint == "/api/projects/delete":
                if not self._require_auth(allowed_roles=["admin"]): return
                pid = str(payload.get("project_id", ""))
                self._send_json(delete_project(pid))
            elif endpoint == "/api/broker/selection":
                session = self._require_auth(allowed_roles=["broker", "admin"])
                if not session: return
                broker_id = str(payload.get("broker_id", session["user_id"]))
                project_ids = list(payload.get("project_ids", []))
                self._send_json(save_broker_selection(broker_id, project_ids))
            elif endpoint == "/api/users":
                if not self._require_auth(allowed_roles=["admin"]): return
                self._send_json(save_user(payload))
            elif endpoint == "/api/users/toggle":
                if not self._require_auth(allowed_roles=["admin"]): return
                uid = str(payload.get("user_id", ""))
                self._send_json(toggle_user_status(uid))
            else:
                self.send_error(404)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._api_error(error)

    def do_DELETE(self):
        parsed_url = urlparse(self.path)
        endpoint = parsed_url.path
        if endpoint.startswith("/api/projects/"):
            if not self._require_auth(allowed_roles=["admin"]): return
            project_id = endpoint.split("/")[-1]
            try:
                self._send_json(delete_project(project_id))
            except Exception as error:
                self._api_error(error)
            return
        self.send_error(404)


if __name__ == "__main__":
    ThreadingHTTPServer.allow_reuse_address = True
    port = DEFAULT_PORT
    server = None
    
    for attempt in range(10):
        try:
            server = ThreadingHTTPServer((HOST, port), ReactRouterHandler)
            break
        except OSError as e:
            if "Address already in use" in str(e):
                port += 1
            else:
                raise

    if server is None:
        raise RuntimeError("Không thể tìm thấy cổng mạng khả dụng để khởi chạy MinFit.")

    print(f"\n=======================================================")
    print(f"🚀 MinFit PropTech Web App đã sẵn sàng!")
    print(f"👉 Mở trình duyệt tại: http://localhost:{port}")
    print(f"👉 Hoặc địa chỉ IP:   http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng máy chủ MinFit.")
        server.server_close()
