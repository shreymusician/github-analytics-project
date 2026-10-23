"""python -m repolens.web [--port 8765] [--host 127.0.0.1] [--public-url URL] [--no-open]

Runs GitHub Intel: a landing page, accounts, and the app behind a login. Every user brings their own model API keys.
Settings can also come from environment variables (handy in Docker):
  REPOLENS_HOST, REPOLENS_PORT, REPOLENS_PUBLIC_URL (e.g. https://repolens.example.com), REPOLENS_ALLOWED_HOSTS
  (comma separated host[:port] values the server answers to), REPOLENS_SECURE_COOKIES=1 (when served over HTTPS),
  REPOLENS_TRUST_PROXY=1 (when behind a reverse proxy that sets X-Forwarded-For), REPOLENS_DATA_DIR,
  REPOLENS_REQUIRE_VERIFIED=1, REPOLENS_SECRET_KEY (encrypts stored API keys), REPOLENS_SMTP_HOST/PORT/USER/PASSWORD,
  REPOLENS_MAIL_FROM, REPOLENS_USE_SERVER_KEYS=1 (a private install that lets users share the owner's .env keys).
"""
from __future__ import annotations

import argparse
import os
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .accounts import Accounts, Mailer, load_secret
from .server import make_server
from .service import Service


def flag(name: str) -> bool:
    return (os.environ.get(name) or "").lower() in ("1", "true", "yes", "on")


def main(argv: list[str] | None = None) -> int:
    load_dotenv(".env")
    env = os.environ.get
    ap = argparse.ArgumentParser(prog="repolens.web", description="Run the GitHub Intel web app.")
    ap.add_argument("--host", default=env("REPOLENS_HOST", "127.0.0.1"), help="address to listen on (default 127.0.0.1; use 0.0.0.0 in Docker)")
    ap.add_argument("--port", type=int, default=int(env("REPOLENS_PORT", "8765")))
    ap.add_argument("--public-url", default=env("REPOLENS_PUBLIC_URL"), help="the address users type, used in emailed links")
    ap.add_argument("--data-dir", default=env("REPOLENS_DATA_DIR", "data"))
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    a = ap.parse_args(argv)

    public = (a.public_url or f"http://127.0.0.1:{a.port}").rstrip("/")
    allowed = {h.strip() for h in (env("REPOLENS_ALLOWED_HOSTS") or "").split(",") if h.strip()}
    if a.public_url:
        allowed.add(urlparse(public).netloc)
    secure = flag("REPOLENS_SECURE_COOKIES") or public.startswith("https://")
    data = Path(a.data_dir)
    require_verified = flag("REPOLENS_REQUIRE_VERIFIED")
    accounts = Accounts(data / "users.db", load_secret(data / "secret.key"), Mailer(), base_url=public, require_verified=require_verified)
    service = Service(".", use_server_keys=flag("REPOLENS_USE_SERVER_KEYS"))
    server = make_server(service, accounts, a.host, a.port, allowed_hosts=allowed or None, secure_cookies=secure,
                         trust_proxy=flag("REPOLENS_TRUST_PROXY"), require_verified=require_verified)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"GitHub Intel is running at {public + '/' if a.public_url else url}\n"
          f"  accounts: {data / 'users.db'}   email: {'SMTP' if accounts.mailer.real else 'printed here (no SMTP configured)'}   "
          f"cookies: {'secure' if secure else 'plain http (local use)'}\nCtrl+C to stop.")
    if not a.no_open and not a.public_url:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
