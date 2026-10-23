"""Wersjonowane API pomiarów z uwierzytelnianiem, tylko do odczytu."""

import hmac
import json
import os
import secrets
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .configuration import atomic_json

API_PORT = 8098


class AccessToken:
    def __init__(self, directory):
        path = directory / "integration-token.json"
        if path.exists():
            self.value = json.loads(path.read_text())["token"]
            path.chmod(0o600)
        else:
            self.value = secrets.token_urlsafe(32)
            atomic_json(path, {"token": self.value})

    def accepts(self, authorization):
        return hmac.compare_digest((authorization or "").encode(), f"Bearer {self.value}".encode())


def api_handler(runtime, token):
    class IntegrationHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not token.accepts(self.headers.get("Authorization")):
                self.reply(401, {"error": "authentication_required"})
            elif self.path != "/v1/data":
                self.reply(404, {"error": "not_found"})
            else:
                self.reply(200, runtime.integration_snapshot())

        def do_POST(self):
            self.reply(405, {"error": "read_only_api"})

        def reply(self, code, data):
            payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if code == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    return IntegrationHandler


def serve_api(runtime, token, bind="127.0.0.1", port=API_PORT):
    server = ThreadingHTTPServer((bind, port), api_handler(runtime, token))
    server.daemon_threads = True
    return server


def pairing_info(runtime, token):
    host = "127.0.0.1"
    if runtime.supervisor_token:
        request = urllib.request.Request("http://supervisor/addons/self/info", headers={
            "X-Supervisor-Token": runtime.supervisor_token})
        with urllib.request.urlopen(request, timeout=10) as response:
            host = json.load(response)["data"]["hostname"]
    return {"host": host, "port": int(os.environ.get("DLMS_API_PORT", API_PORT)), "token": token.value}


def announce_integration(runtime, token):
    if not runtime.supervisor_token:
        raise ValueError("Automatyczne wykrywanie wymaga Supervisora Home Assistant.")
    data = {"service": "dlms_reader", "config": pairing_info(runtime, token)}
    request = urllib.request.Request("http://supervisor/discovery", data=json.dumps(data).encode(),
                                    headers={"X-Supervisor-Token": runtime.supervisor_token,
                                             "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
    if result.get("result") != "ok":
        raise ConnectionError("Nie udało się zgłosić integracji Home Assistant.")
