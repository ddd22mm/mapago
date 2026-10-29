"""Loopback-only development server. Static files are explicitly allowlisted."""

import argparse
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mapago_tools.game import GameSession, InvalidAction, StaleAction

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/styles.css": ("styles.css", "text/css")}
COOKIE = "mapago_session"


class GameServer(ThreadingHTTPServer):
    def __init__(self, port=8765, host="127.0.0.1", public_authority=None):
        super().__init__((host, port), Handler)
        self.sessions = {}
        self.lock = threading.RLock()
        self.authority = public_authority or f"{host}:{self.server_port}"
        self.origin = f"http://{self.authority}"


class Handler(BaseHTTPRequestHandler):
    server_version = "MapagoLocal/1"

    def log_message(self, format, *args):
        pass  # Don't log cookies, requests, seeds or game state.

    def respond(self, status, payload, content_type="application/json", cookie=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; object-src 'none'; frame-ancestors 'none'")
        if cookie:
            self.send_header("Set-Cookie", f"{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/; Max-Age=14400")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host") == self.server.authority

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie[COOKIE].value if COOKIE in cookie else None
        except Exception:
            return None

    def session(self):
        entry = self.server.sessions.get(self.token())
        if not entry or time.monotonic() - entry[0] > 14400:
            raise LookupError("진행 중인 대국이 없습니다. 새 대국을 시작해 주세요.")
        return entry[1]

    def do_GET(self):
        if not self.valid_host():
            self.respond(403, {"error": "허용되지 않은 호스트입니다."})
            return
        try:
            if self.path in ASSETS:
                filename, mime = ASSETS[self.path]
                self.respond(200, (WEB_ROOT / filename).read_bytes(), mime)
            elif self.path in ("/api/game", "/api/replay"):
                with self.server.lock:
                    game = self.session()
                    payload = game.snapshot() if self.path == "/api/game" else game.seat_replay()
                    self.respond(200, payload)
            else:
                self.respond(404, {"error": "찾을 수 없는 경로입니다."})
        except LookupError as exc:
            self.respond(404, {"error": str(exc)})
        except InvalidAction as exc:
            self.respond(400, {"error": str(exc)})

    def do_POST(self):
        if not self.valid_host() or self.headers.get("Origin") != self.server.origin:
            self.respond(403, {"error": "이 대국 화면에서 요청해 주세요."})
            return
        try:
            if self.path not in ("/api/game", "/api/action"):
                self.respond(404, {"error": "찾을 수 없는 경로입니다."})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get_content_type() != "application/json":
                raise ValueError("JSON 요청 형식을 확인해 주세요.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("잘못된 요청입니다.")
            with self.server.lock:
                if self.path == "/api/game":
                    if set(data) - {"rule", "policy"}:
                        raise ValueError("지원하지 않는 대국 설정입니다.")
                    game = GameSession(data.get("rule", "mjsoul"), data.get("policy", "random-legal"))
                    now = time.monotonic()
                    self.server.sessions = {key: entry for key, entry in self.server.sessions.items()
                                            if now - entry[0] <= 14400}
                    self.server.sessions.pop(self.token(), None)
                    if len(self.server.sessions) >= 32:
                        self.respond(503, {"error": "열린 대국이 많습니다. 잠시 후 다시 시도해 주세요."})
                        return
                    token = secrets.token_urlsafe(32)
                    self.server.sessions[token] = (now, game)
                    self.respond(201, game.snapshot(), cookie=token)
                else:
                    if set(data) != {"revision", "action_id"}:
                        raise ValueError("행동과 국면 번호를 확인해 주세요.")
                    self.respond(200, self.session().act(data["revision"], data["action_id"]))
        except StaleAction as exc:
            self.respond(409, {"error": str(exc)})
        except LookupError as exc:
            self.respond(404, {"error": str(exc)})
        except (ValueError, TypeError) as exc:
            self.respond(400, {"error": str(exc)})
        except Exception:
            self.respond(500, {"error": "대국 처리에 실패했습니다. 새로고침 후 상태를 확인해 주세요."})


def main():
    parser = argparse.ArgumentParser(description="마파고 로컬 대국 화면")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--public-authority", default=os.environ.get("MAPAGO_PUBLIC_AUTHORITY"))
    args = parser.parse_args()
    with GameServer(args.port, args.host, args.public_authority) as server:
        print(f"마파고 대국 화면: {server.origin}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
