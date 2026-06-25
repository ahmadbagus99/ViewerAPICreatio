from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from storage import Storage


ROOT = Path(__file__).resolve().parent
STORAGE = Storage(ROOT)
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
SESSION_COOKIE = "viewer_admin_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "creatio-api"


def public_base_url() -> str:
    return os.environ.get("VIEWER_PUBLIC_URL", "http://127.0.0.1:8090").rstrip("/")


def admin_credentials() -> tuple[str, str]:
    return (
        os.environ.get("VIEWER_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME),
        os.environ.get("VIEWER_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
    )


def session_secret() -> bytes:
    value = os.environ.get("VIEWER_SESSION_SECRET", "").strip()
    if not value:
        value = f"{admin_credentials()[1]}:creatio-viewer-session"
    return value.encode("utf-8")


def encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_part(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session(username: str) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    payload = {
        "username": username,
        "expires": int(time.time()) + SESSION_TTL_SECONDS,
        "csrf": csrf,
    }
    encoded = encode_part(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = encode_part(
        hmac.new(session_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}", csrf


def parse_session(value: str) -> dict[str, Any] | None:
    try:
        encoded, signature = value.split(".", 1)
        expected = encode_part(
            hmac.new(session_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(decode_part(encoded))
        if int(payload.get("expires", 0)) < int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def public_catalog() -> dict[str, Any]:
    items = [
        item
        for item in STORAGE.read_catalog().get("items", [])
        if item.get("visibility", "public") == "public"
    ]
    return {"items": items}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        path = self.path.split("?", 1)[0]
        if path.endswith((".html", ".js", ".css")) or path == "/":
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def proxy_slug(self) -> str | None:
        path = unquote(urlsplit(self.path).path)
        match = re.fullmatch(r"/api/proxy/([^/]+)", path)
        return match.group(1) if match else None

    def proxy_api_request(self, slug: str) -> None:
        try:
            item = STORAGE.get_item(slug)
            if item is None or item.get("visibility", "public") != "public":
                self.send_json(404, {"error": "Documentation not found."})
                return

            base_url = str(item.get("baseUrl", "")).strip().rstrip("/")
            query = dict(parse_qsl(urlsplit(self.path).query, keep_blank_values=True))
            target_url = str(query.get("url", "")).strip()
            if not base_url or not target_url:
                self.send_json(400, {"error": "The API proxy target is invalid."})
                return

            base = urlsplit(base_url)
            target = urlsplit(target_url)
            base_path = base.path.rstrip("/")
            target_in_base = (
                target.scheme in {"http", "https"}
                and target.scheme.lower() == base.scheme.lower()
                and target.hostname == base.hostname
                and target.port == base.port
                and (
                    not base_path
                    or target.path == base_path
                    or target.path.startswith(f"{base_path}/")
                )
            )
            if not target_in_base or target.username or target.password:
                self.send_json(403, {"error": "The API proxy target is not allowed."})
                return

            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else None
            excluded_request_headers = HOP_BY_HOP_HEADERS | {
                "host",
                "content-length",
                "origin",
                "referer",
                "cookie",
                "accept-encoding",
            }
            headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in excluded_request_headers
            }
            request = Request(
                target_url,
                data=body,
                headers=headers,
                method=self.command,
            )
            try:
                response = urlopen(request, timeout=60)
            except HTTPError as exc:
                response = exc

            with response:
                response_body = response.read()
                self.send_response(response.status)
                excluded_response_headers = HOP_BY_HOP_HEADERS | {
                    "content-length",
                    "content-encoding",
                    "set-cookie",
                    "access-control-allow-origin",
                    "access-control-allow-credentials",
                    "access-control-allow-headers",
                    "access-control-allow-methods",
                }
                for name, value in response.headers.items():
                    if name.lower() not in excluded_response_headers:
                        self.send_header(name, value)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except (URLError, ValueError, OSError) as exc:
            self.send_json(502, {"error": f"The target API could not be reached: {exc}"})

    def proxy_oauth_token(self, slug: str) -> None:
        try:
            item = STORAGE.get_item(slug)
            if not item or item.get("authMode") != "oauth":
                self.send_json(
                    404, {"error": "OAuth is not configured for this documentation."}
                )
                return
            token_url = str(item.get("oauthTokenUrl", "")).strip()
            if not token_url:
                self.send_json(400, {"error": "OAuth Token URL has not been configured."})
                return
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith(
                "application/x-www-form-urlencoded"
            ):
                self.send_json(
                    400,
                    {"error": "The OAuth token request must be form-urlencoded."},
                )
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            form_data = dict(
                parse_qsl(body.decode("utf-8"), keep_blank_values=True)
            )
            authorization = self.headers.get("Authorization", "")
            if authorization.startswith("Basic "):
                try:
                    decoded = base64.b64decode(
                        authorization.removeprefix("Basic ").strip()
                    ).decode("utf-8")
                    client_id, _, client_secret = decoded.partition(":")
                    form_data.setdefault("client_id", client_id)
                    form_data.setdefault("client_secret", client_secret)
                except Exception:
                    self.send_json(
                        400, {"error": "Invalid OAuth client credentials."}
                    )
                    return
            body = urlencode(form_data).encode("utf-8")
            request = Request(
                token_url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                with urlopen(request, timeout=30) as response:
                    response_body = response.read()
                    status = response.status
                    response_type = response.headers.get(
                        "Content-Type", "application/json"
                    )
            except HTTPError as exc:
                response_body = exc.read()
                status = exc.code
                response_type = exc.headers.get(
                    "Content-Type", "application/json"
                )
            self.send_response(status)
            self.send_header("Content-Type", response_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except URLError as exc:
            self.send_json(502, {"error": f"The OAuth server could not be reached: {exc.reason}"})

    def bearer_scanner(self) -> dict[str, Any] | None:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ").strip()
        if not token:
            return None
        return STORAGE.authenticate_scanner(token)

    def session(self) -> dict[str, Any] | None:
        for cookie in self.headers.get("Cookie", "").split(";"):
            name, _, value = cookie.strip().partition("=")
            if name == SESSION_COOKIE:
                return parse_session(value)
        return None

    def require_admin(self, csrf: bool = False) -> dict[str, Any] | None:
        session = self.session()
        if session is None:
            self.send_json(401, {"error": "The admin session is invalid or has expired."})
            return None
        if csrf and not hmac.compare_digest(
            self.headers.get("X-CSRF-Token", ""), str(session.get("csrf", ""))
        ):
            self.send_json(403, {"error": "Invalid CSRF token."})
            return None
        return session

    def do_GET(self) -> None:
        proxy_slug = self.proxy_slug()
        if proxy_slug:
            self.proxy_api_request(proxy_slug)
            return
        path = unquote(self.path.split("?", 1)[0])
        if path in {"/api/catalog", "/docs/catalog.json"}:
            self.send_json(200, public_catalog())
            return
        if path == "/api/scanner/status":
            scanner = self.bearer_scanner()
            if scanner is None:
                self.send_json(401, {"error": "Invalid scanner token."})
                return
            self.send_json(
                200,
                {
                    "scannerId": scanner["scannerId"],
                    "name": scanner["name"],
                    "status": scanner["status"],
                    "service": "Creatio API Viewer",
                },
            )
            return
        if path == "/api/scanner/documents":
            scanner = self.bearer_scanner()
            if scanner is None:
                self.send_json(401, {"error": "Invalid scanner token."})
                return
            if scanner.get("status") != "approved":
                self.send_json(403, {"error": "The scanner has not been approved or has been revoked."})
                return
            self.send_json(
                200,
                {"items": STORAGE.documents_for_scanner(scanner["scannerId"])},
            )
            return
        if path == "/api/admin/session":
            session = self.require_admin()
            if session is not None:
                self.send_json(
                    200,
                    {"username": session["username"], "csrfToken": session["csrf"]},
                )
            return
        if path == "/api/admin/instances":
            if self.require_admin() is not None:
                self.send_json(200, STORAGE.read_catalog())
            return
        if path == "/api/admin/scanners":
            if self.require_admin() is not None:
                scanners = []
                for scanner in STORAGE.read_scanners().get("items", []):
                    scanners.append(
                        {
                            key: value
                            for key, value in scanner.items()
                            if key != "tokenHash"
                        }
                    )
                self.send_json(200, {"items": scanners})
            return
        document_match = re.fullmatch(r"/docs/([^/]+)/openapi\.json", path)
        if document_match:
            item = STORAGE.get_item(document_match.group(1))
            if item is None or item.get("visibility", "public") != "public":
                self.send_json(404, {"error": "Documentation not found."})
                return
            document = STORAGE.read_document(document_match.group(1))
            if document is None:
                self.send_json(404, {"error": "Documentation not found."})
                return
            self.send_json(200, document)
            return
        super().do_GET()

    def do_POST(self) -> None:
        proxy_slug = self.proxy_slug()
        if proxy_slug:
            self.proxy_api_request(proxy_slug)
            return
        path = unquote(self.path.split("?", 1)[0])
        oauth_match = re.fullmatch(r"/api/oauth/token/([^/]+)", path)
        if oauth_match:
            self.proxy_oauth_token(oauth_match.group(1))
            return
        if path == "/api/admin/login":
            self.login()
            return
        if path == "/api/scanners/register":
            self.register_scanner()
            return
        if path == "/api/admin/logout":
            self.logout()
            return
        if path != "/api/publish":
            self.send_json(404, {"error": "Endpoint not found."})
            return
        self.publish()

    def register_scanner(self) -> None:
        try:
            payload = self.read_payload()
            scanner_id = str(payload.get("scannerId", "")).strip()
            name = str(payload.get("name", "")).strip()
            token = str(payload.get("token", ""))
            if not scanner_id or not name or len(token) < 32:
                self.send_json(400, {"error": "Invalid scanner registration data."})
                return
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            existing = STORAGE.get_scanner(scanner_id)
            if existing and not hmac.compare_digest(
                str(existing.get("tokenHash", "")), token_hash
            ):
                self.send_json(409, {"error": "Scanner ID is already registered."})
                return
            scanner = {
                **(existing or {}),
                "scannerId": scanner_id,
                "name": name,
                "tokenHash": token_hash,
                "status": (existing or {}).get("status", "pending"),
                "registeredAt": (existing or {}).get(
                    "registeredAt", datetime.now(timezone.utc).isoformat()
                ),
                "lastSeenAt": datetime.now(timezone.utc).isoformat(),
            }
            STORAGE.save_scanner(scanner)
            self.send_json(
                200,
                {
                    "scannerId": scanner_id,
                    "name": name,
                    "status": scanner["status"],
                },
            )
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def login(self) -> None:
        try:
            payload = self.read_payload()
            username = str(payload.get("username", ""))
            password = str(payload.get("password", ""))
            expected_username, expected_password = admin_credentials()
            if not (
                hmac.compare_digest(username, expected_username)
                and hmac.compare_digest(password, expected_password)
            ):
                self.send_json(401, {"error": "Incorrect username or password."})
                return
            token, csrf = create_session(username)
            cookie = (
                f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age={SESSION_TTL_SECONDS}"
            )
            if os.environ.get("VIEWER_COOKIE_SECURE", "false").lower() == "true":
                cookie += "; Secure"
            body = json.dumps({"username": username, "csrfToken": csrf}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def logout(self) -> None:
        if self.require_admin(csrf=True) is None:
            return
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header(
            "Set-Cookie",
            f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def publish(self) -> None:
        scanner = self.bearer_scanner()
        if scanner is None:
            self.send_json(401, {"error": "A valid Scanner Bearer token is required."})
            return
        if scanner.get("status") != "approved":
            self.send_json(403, {"error": "The scanner has not been approved or has been revoked."})
            return
        try:
            payload = self.read_payload()
            name = str(payload.get("name", "")).strip()
            slug = str(payload.get("slug", "")).strip() or slugify(name)
            openapi = payload.get("openapi")
            metadata = payload.get("metadata") or {}
            if not name:
                self.send_json(400, {"error": "Documentation name is required."})
                return
            if not isinstance(openapi, dict):
                self.send_json(400, {"error": "Invalid OpenAPI payload."})
                return
            existing = STORAGE.get_item(slug) or {}
            if (
                existing.get("ownerScannerId")
                and existing.get("ownerScannerId") != scanner.get("scannerId")
            ):
                self.send_json(
                    409,
                    {"error": "The documentation slug is already owned by another scanner."},
                )
                return
            item = {
                "name": name,
                "slug": slug,
                "url": f"/docs/{slug}/openapi.json",
                "viewerPage": f"{public_base_url()}/?doc={slug}",
                "baseUrl": metadata.get("baseUrl"),
                "packagePrefix": metadata.get("packagePrefix"),
                "authMode": metadata.get("authMode", "bpmcsrf"),
                "oauthTokenUrl": metadata.get("oauthTokenUrl", ""),
                "fileCount": metadata.get("fileCount", 0),
                "packageCount": metadata.get("packageCount", 0),
                "endpointCount": metadata.get("endpointCount", 0),
                "generatedAt": metadata.get("generatedAt"),
                "publishedAt": datetime.now(timezone.utc).isoformat(),
                "description": existing.get("description", ""),
                "status": existing.get("status", "active"),
                "visibility": existing.get("visibility", "public"),
                "ownerScannerId": scanner.get("scannerId"),
                "ownerScannerName": scanner.get("name"),
            }
            STORAGE.publish(item, openapi)
            self.send_json(200, {"item": item, "url": item["viewerPage"]})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def do_PUT(self) -> None:
        proxy_slug = self.proxy_slug()
        if proxy_slug:
            self.proxy_api_request(proxy_slug)
            return
        path = unquote(self.path.split("?", 1)[0])
        scanner_match = re.fullmatch(r"/api/admin/scanners/([^/]+)", path)
        if scanner_match:
            if self.require_admin(csrf=True) is None:
                return
            try:
                scanner = STORAGE.get_scanner(scanner_match.group(1))
                if scanner is None:
                    self.send_json(404, {"error": "Scanner not found."})
                    return
                payload = self.read_payload()
                status = str(payload.get("status", "")).strip()
                if status not in {"approved", "revoked"}:
                    self.send_json(400, {"error": "Invalid scanner status."})
                    return
                scanner["status"] = status
                scanner["updatedAt"] = datetime.now(timezone.utc).isoformat()
                STORAGE.save_scanner(scanner)
                self.send_json(
                    200,
                    {
                        "scanner": {
                            key: value
                            for key, value in scanner.items()
                            if key != "tokenHash"
                        }
                    },
                )
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/admin/instances/([^/]+)", path)
        if not match:
            self.send_json(404, {"error": "Endpoint not found."})
            return
        if self.require_admin(csrf=True) is None:
            return
        try:
            slug = match.group(1)
            existing = STORAGE.get_item(slug)
            if existing is None:
                self.send_json(404, {"error": "Instance not found."})
                return
            payload = self.read_payload()
            name = str(payload.get("name", "")).strip()
            status = str(payload.get("status", "active")).strip()
            visibility = str(payload.get("visibility", "public")).strip()
            if not name:
                self.send_json(400, {"error": "Documentation name is required."})
                return
            if status not in {"active", "deprecated"}:
                self.send_json(400, {"error": "Invalid status."})
                return
            if visibility not in {"public", "private"}:
                self.send_json(400, {"error": "Invalid visibility."})
                return
            item = {
                **existing,
                "name": name,
                "description": str(payload.get("description", "")).strip(),
                "baseUrl": str(payload.get("baseUrl", "")).strip(),
                "packagePrefix": str(payload.get("packagePrefix", "")).strip(),
                "status": status,
                "visibility": visibility,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            STORAGE.save_item(item)
            self.send_json(200, {"item": item})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def do_DELETE(self) -> None:
        proxy_slug = self.proxy_slug()
        if proxy_slug:
            self.proxy_api_request(proxy_slug)
            return
        path = unquote(self.path.split("?", 1)[0])
        admin_scanner_match = re.fullmatch(r"/api/admin/scanners/([^/]+)", path)
        if admin_scanner_match:
            if self.require_admin(csrf=True) is None:
                return
            try:
                if not STORAGE.delete_scanner(admin_scanner_match.group(1)):
                    self.send_json(404, {"error": "Scanner not found."})
                    return
                self.send_json(200, {"ok": True})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return
        scanner_match = re.fullmatch(r"/api/scanner/documents/([^/]+)", path)
        if scanner_match:
            scanner = self.bearer_scanner()
            if scanner is None:
                self.send_json(401, {"error": "Invalid scanner token."})
                return
            if scanner.get("status") != "approved":
                self.send_json(403, {"error": "The scanner has not been approved or has been revoked."})
                return
            try:
                if not STORAGE.delete_for_scanner(
                    scanner_match.group(1), scanner["scannerId"]
                ):
                    self.send_json(
                        404,
                        {"error": "Documentation not found or not owned by this scanner."},
                    )
                    return
                self.send_json(200, {"ok": True})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/admin/instances/([^/]+)", path)
        if not match:
            self.send_json(404, {"error": "Endpoint not found."})
            return
        if self.require_admin(csrf=True) is None:
            return
        try:
            if not STORAGE.delete(match.group(1)):
                self.send_json(404, {"error": "Instance not found."})
                return
            self.send_json(200, {"ok": True})
        except Exception as exc:
            self.send_json(500, {"error": str(exc)})

    def do_PATCH(self) -> None:
        proxy_slug = self.proxy_slug()
        if proxy_slug:
            self.proxy_api_request(proxy_slug)
            return
        self.send_json(404, {"error": "Endpoint not found."})


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8090"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Creatio API Viewer running at http://{host}:{port}")
    print(f"Admin user: {admin_credentials()[0]}")
    print(f"Storage backend: {STORAGE.backend}")
    server.serve_forever()


if __name__ == "__main__":
    main()
