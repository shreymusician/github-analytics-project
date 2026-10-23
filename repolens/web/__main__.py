"""python -m repolens.web [--port 8765] [--no-open] [--token TOKEN]

Starts the local RepoLens page and prints a link that contains a secret token. Only this machine can reach it.
Your API keys stay in .env and are never sent to the page.
"""
from __future__ import annotations

import argparse
import os
import secrets
import webbrowser

from dotenv import load_dotenv

from .server import make_server
from .service import Service


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="repolens.web", description="Run the local RepoLens web page.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    ap.add_argument("--token", default=os.environ.get("REPOLENS_WEB_TOKEN"), help="fixed token (default: random each start)")
    a = ap.parse_args(argv)
    load_dotenv(".env")
    token = a.token or secrets.token_urlsafe(16)
    server = make_server(Service("."), "127.0.0.1", a.port, token)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    print(f"RepoLens is running. Open this link (it contains a secret token; only this machine can reach it):\n\n  {url}\n\nCtrl+C to stop.")
    if not a.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
