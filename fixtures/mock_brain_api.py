"""Mock BRAIN API server for offline testing.

Provides a lightweight HTTP server that returns recorded responses
for endpoints used by the BRAIN Alpha Ops system.
"""

from __future__ import annotations

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any, Callable

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "recorded_responses"


class MockBRAINApiHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves recorded JSON responses."""

    _fixtures_dir: Path = FIXTURES_DIR
    _custom_handlers: dict[str, Callable] = {}
    _token: str = "mock-token-12345"

    def do_GET(self) -> None:
        self._handle_request("GET")

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        self._handle_request("POST", body)

    def _handle_request(self, method: str, body: bytes = b"") -> None:
        path = self.path.split("?")[0]

        if path in self._custom_handlers:
            try:
                request_body = json.loads(body) if body else {}
            except json.JSONDecodeError:
                request_body = {}
            response = self._custom_handlers[path](method, request_body)
            self._send_json(response)
            return

        fixture_name = self._path_to_fixture_name(path)
        if fixture_name:
            fixture_file = self._fixtures_dir / fixture_name
            if fixture_file.exists():
                try:
                    data = json.loads(fixture_file.read_text(encoding="utf-8"))
                    self._send_json(data)
                except Exception as exc:
                    logger.warning("Failed to load fixture %s: %s", fixture_file, exc)
                    self._send_error(500, "Fixture load error")
            else:
                self._send_error(404, f"Fixture not found: {fixture_name}")
        elif path == "/authentication":
            self._send_json({"token": self._token})
        else:
            self._send_error(404, f"No fixture for endpoint: {path}")

    def _path_to_fixture_name(self, path: str) -> str | None:
        mapping = {
            "/data-fields": "data_fields.json",
            "/data-sets": "data_sets.json",
            "/operators": "operators.json",
            "/users/self/alphas": "user_alphas.json",
            "/simulations": "simulation.json",
            "/users/self": "user_profile.json",
            "/data-categories": "data_categories.json",
        }
        for api_path, fixture_name in mapping.items():
            if path.startswith(api_path):
                return fixture_name

        if "/alphas/" in path and path.endswith("/check"):
            return "alpha_check.json"

        return None

    def _send_json(self, data: Any) -> None:
        response = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _send_error(self, code: int, message: str) -> None:
        response = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("MockBRAIN: %s", format % args)


class MockBRAINApiServer:
    """Lightweight mock BRAIN API server for offline testing.

    Usage::

        server = MockBRAINApiServer(port=8765)
        server.start()

        # Configure client to use http://localhost:8765
        # ... run tests ...

        server.stop()
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        fixtures_dir: Path | str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None
        if fixtures_dir:
            MockBRAINApiHandler._fixtures_dir = Path(fixtures_dir)

    def start(self) -> None:
        """Start the mock server in a background thread."""
        self._server = HTTPServer((self._host, self._port), MockBRAINApiHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("MockBRAINApiServer started on %s:%d", self._host, self._port)

    def stop(self) -> None:
        """Stop the mock server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("MockBRAINApiServer stopped")

    def add_handler(self, path: str, handler: Callable) -> None:
        """Add a custom handler for a specific path.

        Args:
            path: API path (e.g., "/custom/endpoint")
            handler: Callable that takes (method, body) and returns JSON-serializable data
        """
        MockBRAINApiHandler._custom_handlers[path] = handler

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def __enter__(self) -> "MockBRAINApiServer":
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
