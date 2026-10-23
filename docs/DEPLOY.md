# Running RepoLens for other people

Status: written but **not yet tried on a real server**. The Dockerfile has never been built (the Docker daemon was not
running when it was written). Expect to fix small things on the first deployment.

## What you get
A landing page, sign up / log in / password reset, and the app behind a login. Each user brings their own model API
keys (Groq, Gemini, OpenRouter), stored encrypted. Daily limits per user: 20 searches and 10 analyses.

## Quick local run (one machine, plain http)
```bash
python -m repolens.web          # http://127.0.0.1:8765/
```
Accounts and keys are stored in `data/users.db` and `data/secret.key` (both git-ignored). With no SMTP settings, the
"confirm your email" and "reset password" links are printed in the terminal instead of emailed.

## On a server
1. Pick a host that can run Docker, and a domain name pointing at it.
2. Make an encryption key for stored API keys and **back it up**; if it is lost, every user must re-enter their keys:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. Set the environment (a `.env` file next to `docker-compose.yml` works):
   ```
   REPOLENS_PUBLIC_URL=https://repolens.example.com
   REPOLENS_SECRET_KEY=<the key from step 2>
   GITHUB_TOKEN=<a GitHub token with no scopes; raises the search rate limit for everyone>
   REPOLENS_SMTP_HOST=smtp.example.com
   REPOLENS_SMTP_PORT=587
   REPOLENS_SMTP_USER=...
   REPOLENS_SMTP_PASSWORD=...
   REPOLENS_MAIL_FROM=RepoLens <no-reply@example.com>
   ```
4. `docker compose up -d --build`
5. Put an HTTPS reverse proxy in front (Caddy is the simplest: `reverse_proxy 127.0.0.1:8765`). The app marks cookies
   `Secure` and sends HSTS when the public URL is https, and trusts the proxy's `X-Forwarded-For` for rate limiting.
   Do not expose port 8765 directly to the internet.

## Settings
| Variable | Meaning |
|---|---|
| `REPOLENS_PUBLIC_URL` | the address users type; used in emailed links and the allowed Host check |
| `REPOLENS_ALLOWED_HOSTS` | extra `host[:port]` values to answer to |
| `REPOLENS_SECURE_COOKIES` | `1` forces Secure cookies (automatic for https URLs) |
| `REPOLENS_TRUST_PROXY` | `1` when behind a proxy that sets `X-Forwarded-For` |
| `REPOLENS_REQUIRE_VERIFIED` | `1` blocks searching, analyzing and saving keys until the email is confirmed (needs working email) |
| `REPOLENS_DATA_DIR` | where `users.db` and `secret.key` live (a volume in Docker) |
| `REPOLENS_USE_SERVER_KEYS` | `1` lets users without keys use the server's own `.env` keys (a private install only; it spends your quota) |

## Known gaps before a public launch
- Cloning arbitrary repositories on a shared server needs disk, size and time limits; only a global limit of two
  jobs at once and one job per user exist today.
- Login limits are kept in memory, so they reset on restart and are not shared across several server processes.
- One SQLite file holds all accounts; fine for hundreds of users, not for thousands.
- No account export, no admin screen, no abuse reporting.
- Never tried under real traffic or by people other than the author.
