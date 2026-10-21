"""Optional outside signals. Every method is fail-soft: network trouble, rate limits or
missing data return None/[] and never raise, because analysis must work without them.

Endpoints verified live on 2026-10-21 (see docs/ECOSYSTEM.md):
  * GitHub REST (search 30/min with token; core 5,000/h)
  * repos.ecosyste.ms repository metadata + manifests (no clone needed)
  * OpenSSF Scorecard API (only for repos that opted in)
Known broken at the time: ecosyste.ms `dependent_repositories` and topic search (500 / ignored filters).
"""
from __future__ import annotations

import httpx

GITHUB = "https://api.github.com"
ECOSYSTEMS = "https://repos.ecosyste.ms/api/v1"
SCORECARD = "https://api.securityscorecards.dev"


class External:
    def __init__(self, github_token: str | None = None, client: httpx.Client | None = None, timeout: float = 20.0):
        self.token = github_token
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True,
                                             headers={"User-Agent": "repolens/0.1"})

    def _get(self, url: str, *, github: bool = False, params: dict | None = None):
        headers = {"Accept": "application/vnd.github+json"} if github else {}
        if github and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            r = self.client.get(url, params=params, headers=headers)
        except httpx.HTTPError:
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    # ---- repository facts: GitHub first, ecosyste.ms as fallback (same output shape)
    def repo_meta(self, owner: str, name: str) -> dict | None:
        d = self._get(f"{GITHUB}/repos/{owner}/{name}", github=True)
        src = "github"
        if d is None:
            d = self._get(f"{ECOSYSTEMS}/hosts/GitHub/repositories/{owner}/{name}")
            src = "ecosyste.ms"
        if not isinstance(d, dict) or "full_name" not in d:
            return None
        lic = d.get("license")
        return {
            "source": src, "full_name": d["full_name"], "description": d.get("description"),
            "stars": d.get("stargazers_count"), "forks": d.get("forks_count"),
            "archived": bool(d.get("archived")), "fork": bool(d.get("fork")),
            "topics": (d.get("topics") or [])[:12], "pushed_at": (d.get("pushed_at") or "")[:10],
            "license": lic.get("spdx_id") if isinstance(lic, dict) else lic,
        }

    def scorecard(self, owner: str, name: str) -> dict | None:
        d = self._get(f"{SCORECARD}/projects/github.com/{owner}/{name}")
        if not isinstance(d, dict) or "score" not in d:
            return None
        checks = [c for c in d.get("checks", []) if isinstance(c.get("score"), (int, float)) and c["score"] >= 0]
        weakest = sorted(checks, key=lambda c: c["score"])[:3]
        return {"score": d["score"], "date": d.get("date"),
                "weakest": [{"name": c["name"], "score": c["score"]} for c in weakest]}

    # ---- V3 helpers (candidate discovery and cheap verification)
    def search_repos(self, query: str, sort: str = "stars", per_page: int = 10) -> list[dict]:
        d = self._get(f"{GITHUB}/search/repositories", github=True,
                      params={"q": query, "sort": sort, "order": "desc", "per_page": per_page})
        if not isinstance(d, dict):
            return []
        return [{"full_name": i["full_name"], "stars": i["stargazers_count"], "pushed_at": i["pushed_at"][:10],
                 "archived": i["archived"], "topics": i.get("topics", [])[:8], "description": i.get("description")}
                for i in d.get("items", []) if isinstance(i, dict) and "full_name" in i]

    def manifest_dependencies(self, owner: str, name: str) -> set[str] | None:
        """Dependency names a repo declares, without cloning it. None if unavailable."""
        d = self._get(f"{ECOSYSTEMS}/hosts/GitHub/repositories/{owner}/{name}/manifests")
        if not isinstance(d, list):
            return None
        skip = {"actions", "docker", "github-actions"}      # CI actions / images are not library dependencies
        names = {str(dep.get("package_name", "")).lower().replace("_", "-")
                 for m in d if isinstance(m, dict) and m.get("ecosystem") not in skip
                 for dep in m.get("dependencies", []) if isinstance(dep, dict)}
        return {x for x in names if x and not x.startswith((".", "/"))}

    def gather(self, owner: str, name: str) -> dict:
        out = {}
        if (m := self.repo_meta(owner, name)):
            out["github"] = m
        if (s := self.scorecard(owner, name)):
            out["scorecard"] = s
        return out
