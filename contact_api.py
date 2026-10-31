"""Local Akadiwo site server with an SMTP-backed contact endpoint."""

from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SITE_FILE = ROOT / "www.akadiwo.org.com.html"
CONTACT_SCRIPT = ROOT / "contact.js"
STATIC_FILES = {
    "/": (SITE_FILE, "text/html; charset=utf-8"),
    f"/{SITE_FILE.name}": (SITE_FILE, "text/html; charset=utf-8"),
    "/contact.js": (CONTACT_SCRIPT, "text/javascript; charset=utf-8"),
}
TOPICS = {"Donate", "Volunteer", "Partner", "General question"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RATE_LIMIT: dict[str, list[float]] = {}
RATE_LOCK = threading.Lock()
RATE_WINDOW_SECONDS = 600
RATE_MAX_REQUESTS = 5
MAX_BODY_BYTES = 16_384


class SiteHandler(BaseHTTPRequestHandler):
    server_version = "AkadiwoSite/1.0"

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def serve_site(self, include_body: bool = True) -> None:
        path = urlparse(self.path).path
        resource = STATIC_FILES.get(path)
        if resource is None:
            self.send_error(404)
            return
        file_path, content_type = resource
        try:
            body = file_path.read_bytes()
        except OSError:
            self.send_error(500, "A site asset is unavailable.")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        self.serve_site()

    def do_HEAD(self) -> None:
        self.serve_site(include_body=False)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/contact.php":
            self.send_json(404, {"ok": False, "error": "Not found."})
            return
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            self.send_json(415, {"ok": False, "error": "JSON is required."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"ok": False, "error": "Invalid request."})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json(413, {"ok": False, "error": "Message is too large."})
            return
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"ok": False, "error": "Invalid request."})
            return
        if not isinstance(data, dict):
            self.send_json(400, {"ok": False, "error": "Invalid request."})
            return
        if data.get("website"):
            self.send_json(200, {"ok": True})
            return

        name = data.get("name", "").strip() if isinstance(data.get("name", ""), str) else ""
        email = data.get("email", "").strip() if isinstance(data.get("email", ""), str) else ""
        topic = data.get("topic", "").strip() if isinstance(data.get("topic", ""), str) else ""
        message = data.get("message", "").strip() if isinstance(data.get("message", ""), str) else ""
        if (not name or len(name) > 160 or len(email) > 254
                or not EMAIL_RE.fullmatch(email) or topic not in TOPICS
                or not message or len(message.encode("utf-8")) > 10_000):
            self.send_json(422, {"ok": False, "error": "Check the name, email, topic and message."})
            return
        if not self.allow_request():
            self.send_json(429, {"ok": False, "error": "Please wait before sending another message."})
            return

        host = os.getenv("AKADIWO_SMTP_HOST", "").strip()
        sender = os.getenv("AKADIWO_FROM_EMAIL", "").strip()
        recipient = os.getenv("AKADIWO_TO_EMAIL", "akadiwofoundation@gmail.com").strip()
        username = os.getenv("AKADIWO_SMTP_USER", "")
        password = os.getenv("AKADIWO_SMTP_PASSWORD", "")
        security = os.getenv("AKADIWO_SMTP_SECURITY", "starttls").strip().lower()
        try:
            port = int(os.getenv("AKADIWO_SMTP_PORT", "587"))
        except ValueError:
            port = 0
        if (not host or not EMAIL_RE.fullmatch(sender) or not EMAIL_RE.fullmatch(recipient)
                or not 1 <= port <= 65535 or security not in {"starttls", "ssl"}
                or bool(username) != bool(password)):
            self.send_json(503, {"ok": False, "error": "The message service is not configured."})
            return

        mail = EmailMessage()
        mail["Subject"] = f"Website enquiry: {topic}"
        mail["From"] = sender
        mail["To"] = recipient
        mail["Reply-To"] = email
        mail.set_content(f"Name: {name}\nEmail: {email}\nTopic: {topic}\n\n{message}")
        context = ssl.create_default_context()
        try:
            if security == "ssl":
                with smtplib.SMTP_SSL(host, port, timeout=10, context=context) as server:
                    if username:
                        server.login(username, password)
                    server.send_message(mail)
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.starttls(context=context)
                    if username:
                        server.login(username, password)
                    server.send_message(mail)
        except (OSError, smtplib.SMTPException):
            self.send_json(503, {"ok": False, "error": "The message could not be delivered."})
            return
        self.send_json(200, {"ok": True})

    def allow_request(self) -> bool:
        now = time.monotonic()
        client = self.client_address[0]
        with RATE_LOCK:
            recent = [stamp for stamp in RATE_LIMIT.get(client, [])
                      if now - stamp < RATE_WINDOW_SECONDS]
            if len(recent) >= RATE_MAX_REQUESTS:
                RATE_LIMIT[client] = recent
                return False
            recent.append(now)
            RATE_LIMIT[client] = recent
        return True

    def log_message(self, format: str, *args: object) -> None:
        if self.command == "POST":
            print(f"{self.client_address[0]} {self.command} {self.path} {args[1]}")


if __name__ == "__main__":
    host = os.getenv("AKADIWO_BIND", "127.0.0.1")
    port = int(os.getenv("AKADIWO_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), SiteHandler)
    print(f"Akadiwo site available at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
