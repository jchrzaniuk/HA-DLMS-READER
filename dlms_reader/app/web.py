"""API formularza Ingress, bez otwartego portu hosta i zwracania haseł lub kluczy."""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .configuration import public_config
from .metadata import metadata_options
from .runtime import safe_error
from .integration_api import AccessToken, pairing_info, announce_integration

STATIC = Path(__file__).parent / "static"


def handler(runtime, ingress=False):
    token = AccessToken(runtime.store.directory)
    class Handler(BaseHTTPRequestHandler):
        def allowed(self):
            return self.client_address[0] == "172.30.32.2" if ingress else self.client_address[0] in ("127.0.0.1", "::1")

        def send(self, code, value, content_type="application/json; charset=utf-8"):
            payload = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith("application/json") else value
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {"error": "Dostęp wyłącznie przez Home Assistant Ingress."})
            route = urlsplit(self.path).path
            if route == "/api/config":
                with runtime.lock:
                    return self.send(200, public_config(runtime.store.value))
            if route == "/api/status":
                return self.send(200, runtime.snapshot())
            if route == "/api/catalog":
                return self.send(200, runtime.catalog_snapshot())
            if route == "/api/profiles":
                with runtime.lock:
                    return self.send(200, runtime.store.profiles)
            if route == "/api/metadata-options":
                return self.send(200, metadata_options())
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if route in files:
                filename, mime = files[route]
                return self.send(200, (STATIC / filename).read_bytes(), mime)
            self.send(404, {"error": "Nie znaleziono strony."})

        def do_POST(self):
            if not self.allowed():
                return self.send(403, {"error": "Dostęp wyłącznie przez Ingress."})
            # Własny nagłówek i JSON blokują żądania formularzy z innego źródła.
            if self.headers.get("X-DLMS-Request") != "1" or self.headers.get_content_type() != "application/json":
                return self.send(403, {"error": "Wymagane żądanie JSON z interfejsu dodatku."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 262144:
                    return self.send(413, {"error": "Żądanie jest za duże."})
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("Wymagany obiekt JSON.")
                route = urlsplit(self.path).path
                if route == "/api/config":
                    return self.send(200, runtime.save(body))
                if route in ("/api/profiles/save", "/api/profiles/import"):
                    with runtime.lock:
                        runtime.ensure_idle()
                        if route.endswith("/save"):
                            if set(body) - {"name", "id"}:
                                raise ValueError("Nieznane pola profilu.")
                            key = body.get("id")
                            if key is not None and key not in runtime.store.profiles:
                                raise ValueError("Profil nie istnieje.")
                            key = runtime.store.save_profile(body["name"], profile_id=key)
                            runtime.store.save({"profile": key})
                        else:
                            if set(body) != {"version", "name", "settings"} or type(body["version"]) is not int or body["version"] != 1:
                                raise ValueError("Nieobsługiwany format profilu. Wymagany plik JSON w wersji 1.")
                            key = runtime.store.save_profile(body["name"], body["settings"])
                        return self.send(200, {"id": key, "profiles": runtime.store.profiles})
                if route == "/api/pairing":
                    return self.send(200, pairing_info(runtime, token))
                if route == "/api/discover":
                    announce_integration(runtime, token)
                    return self.send(200, {"ok": True})
                if route == "/api/start":
                    runtime.start()
                elif route == "/api/stop":
                    runtime.stop()
                elif route in ("/api/test", "/api/objects"):
                    runtime.test(enumerate_objects=route == "/api/objects")
                else:
                    return self.send(404, {"error": "Nieznana operacja."})
                self.send(202, runtime.snapshot())
            except RuntimeError as error:
                self.send(409, {"error": str(error)})
            except (ValueError, TypeError, KeyError) as error:
                self.send(400, {"error": str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else "Nieprawidłowa konfiguracja JSON."})
            except Exception as error:
                self.send(502, {"error": safe_error(error)})

        def log_message(self, format, *args):
            # Nie zapisuj adresów URL, treści żądań ani błędów z danymi dostępowymi.
            logging.getLogger("dlms.http").debug("Zakończono żądanie HTTP.")

    return Handler


def serve(runtime, bind="127.0.0.1", port=8099):
    server = ThreadingHTTPServer((bind, port), handler(runtime, ingress=bool(os.environ.get("SUPERVISOR_TOKEN"))))
    server.daemon_threads = True
    return server
