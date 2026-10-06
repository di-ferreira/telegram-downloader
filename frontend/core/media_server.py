from __future__ import annotations

import mimetypes
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import MEDIA_HOST, MEDIA_PORT
from core import paths, registry

CHUNK = 64 * 1024
MAX_PATH = 4096


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "TgDownloaderMedia/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D102 - keep quiet
        return

    # ------------------------------------------------------------- helpers
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length")

    def _lookup(self) -> tuple[Path | None, int | None]:
        try:
            parsed = urllib.parse.urlparse(self.path)
            decoded = urllib.parse.unquote(parsed.path)
            if len(decoded) > MAX_PATH:
                return None, None
            parts = decoded.split("/")
            if len(parts) < 4 or parts[1] != "s":
                return None, None
            source_id = int(parts[2])
            key = "/".join(parts[3:])
        except (ValueError, IndexError):
            return None, None

        source = registry.get_source(source_id)
        if not source:
            return None, None
        target = paths.resolve_media(Path(source["root_path"]), key)
        if target is None:
            return None, source_id
        return target, source_id

    def _error(self, code: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ----------------------------------------------------------- verbs
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(head=True)

    def do_GET(self) -> None:  # noqa: N802
        self._serve(head=False)

    def _serve(self, head: bool) -> None:
        target, _source_id = self._lookup()
        if target is None:
            self._error(404, "Not found")
            return
        try:
            size = target.stat().st_size
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            start, end, partial = self._parse_range(size)
        except OSError:
            self._error(404, "Not found")
            return

        if start is None:
            self._error(416, "Range not satisfiable")
            return

        length = max(end - start + 1, 0)
        self.send_response(206 if partial else 200)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()

        if head or length == 0:
            return

        try:
            with open(target, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _parse_range(self, size: int) -> tuple[int | None, int, bool]:
        header = self.headers.get("Range")
        if not header or not header.startswith("bytes="):
            return 0, size - 1, False

        spec = header[6:].split(",")[0].strip()
        if "-" not in spec:
            return None, 0, False
        start_s, end_s = spec.split("-", 1)
        try:
            if start_s:
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
            else:
                suffix = int(end_s)
                if suffix <= 0:
                    return None, 0, False
                start = max(size - suffix, 0)
                end = size - 1
        except ValueError:
            return None, 0, False

        if start >= size or start < 0 or end < start:
            return None, 0, False
        return start, min(end, size - 1), True


class MediaServer:
    def __init__(self) -> None:
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    @property
    def running(self) -> bool:
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    def start(self, port: int = MEDIA_PORT) -> int:
        if self.running:
            return self.port
        self._httpd = ThreadingHTTPServer((MEDIA_HOST, port), _Handler)
        self._httpd.daemon_threads = True
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="media-server", daemon=True
        )
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
        self._httpd = None
        self._thread = None
        self.port = 0


_server = MediaServer()


def ensure_server() -> MediaServer:
    if not _server.running:
        _server.start()
    return _server


def media_url(source_id: int | None, media_key: str | None) -> str | None:
    if source_id is None or not media_key:
        return None
    server = ensure_server()
    if not server.port:
        return None
    quoted = "/".join(urllib.parse.quote(seg) for seg in media_key.split("/"))
    return f"http://{MEDIA_HOST}:{server.port}/s/{int(source_id)}/{quoted}"


def server_status() -> dict:
    server = ensure_server()
    return {
        "running": server.running,
        "host": MEDIA_HOST,
        "port": server.port,
        "url": f"http://{MEDIA_HOST}:{server.port}" if server.port else None,
    }
