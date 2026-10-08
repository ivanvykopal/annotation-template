"""Static file server with CORS for Label Studio valueType=url embeds.

Serves a directory of HTML snapshots (default: snapshots/ next to this file)
on 127.0.0.1:8765 with Access-Control-Allow-Origin echoed for the local
Label Studio origins (python -m http.server sends no CORS headers, which
made HyperText url fetches fail with TypeError: Failed to fetch).

Run (supervised service):
    python cors_server.py [--root DIR] [--port PORT]
"""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent / "snapshots"
DEFAULT_PORT = 8765


def make_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    class CorsHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        # only the local Label Studio origins may read snapshots
        ALLOWED_ORIGINS = {"http://localhost:8080", "http://127.0.0.1:8080",
                           "http://localhost:8081", "http://127.0.0.1:8081"}

        def end_headers(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin in self.ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
            super().end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802 (stdlib handler naming)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            pass

    return CorsHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT,
        help=f"directory to serve (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"port to listen on (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()

    handler = make_handler(args.root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving {args.root} on 127.0.0.1:{args.port} "
          f"with CORS for local Label Studio origins")
    server.serve_forever()


if __name__ == "__main__":
    main()
