"""Render a Markdown report. Works with or without LLM narration."""
from __future__ import annotations

from .evidence import build_packet


def _bar(score: int) -> str:
    n = round(score / 10)
    return "█" * n + "░" * (10 - n)


def _cite(item: dict) -> str:
    return " " + "".join(f"[{e}]" for e in item["evidence"])


def render(result: dict) -> str:
    p, nar = result["profile"], result["narrative"]
    n = nar["narrative"] if nar else None
    st, ar, hi = p["stack"], p["architecture"], p["history"]
    L: list[str] = [f"# Repo report: {p['repo']}", "", f"Commit `{(p['sha'] or 'unknown')[:10]}`", ""]

    if n and n.get("summary"):
        L += ["## What it is", n["summary"]["text"] + _cite(n["summary"]), ""]
        for key, title in (("scope", "Scope"), ("audience", "Who it's for")):
            if n.get(key):
                L += [f"**{title}:** {n[key]['text']}{_cite(n[key])}", ""]
        if n.get("maturity"):
            m = n["maturity"]
            L += [f"**Maturity:** {m['level']}. {m['text']}{_cite(m)}", ""]
    else:
        L += ["## What it is",
              "_No AI narration available (no API keys configured or all providers failed). "
              "The facts below come from deterministic analysis._", ""]
        if st["primary_language"]:
            L += [f"A {st['primary_language']} project"
                  + (f" with capabilities: {', '.join(st['capability_tags'][:6])}." if st["capability_tags"] else "."), ""]

    L += ["## Scores", "",
          f"- Completeness: **{p['completeness']['score']}/100** `{_bar(p['completeness']['score'])}`",
          f"- Deployability: **{p['deployability']['score']}/100** `{_bar(p['deployability']['score'])}`",
          "", "_Heuristic scores from rule checks, not yet calibrated against labeled data. Reasons:_", ""]
    for area in ("completeness", "deployability"):
        L += [f"**{area.capitalize()}**"]
        L += [f"- {'✓' if e['ok'] else '✗'} {e['note']}" for e in p[area]["evidence"]]
        L += [""]

    cen = st.get("file_census")
    if cen:
        L += ["## Composition (all files, by size)", "",
              " · ".join(f"**{c}** {d['share_bytes']:.0%}" for c, d in list(cen["categories"].items())[:6]),
              f"({cen['total_files']} files)", ""]
    L += ["## Stack", f"- Languages: {', '.join(f'{k} {v:.0%}' for k, v in st['languages'].items()) or 'none detected'}",
          f"- Capabilities: {', '.join(st['capability_tags']) or 'none recognized'}",
          f"- Dependencies: {st['dependency_count']} (pinned ratio {st['pinned_ratio']})", ""]

    if ar.get("read_first"):
        L += ["## Read these first", ""]
        learn = {x["file"]: x for x in (n or {}).get("learning_path", [])}
        for r in ar["read_first"]:
            why = f": {learn[r['file']]['text']}{_cite(learn[r['file']])}" if r["file"] in learn else ""
            L += [f"- `{r['file']}` (imported by {r['imported_by']}){why}"]
        L += [""]
    if ar.get("subsystems"):
        L += ["## Subsystems (found from import coupling)", ""]
        L += [f"- **{s['name']}** ({s['size']} modules): {', '.join(f'`{f}`' for f in s['files'][:4])}" for s in ar["subsystems"]]
        L += [""]

    if n and n.get("how_to_run"):
        L += ["## How to run", ""] + [f"- {x['text']}{_cite(x)}" for x in n["how_to_run"]] + [""]

    if hi.get("commits"):
        L += ["## History", "",
              f"{hi['commits']} commits, {hi['first_commit']} to {hi['last_commit']}; status **{hi['status']}**, "
              f"shape **{hi['shape']}**, {hi['contributors']} contributor(s), bus factor {hi['bus_factor']}.",
              "", "Started with: " + " → ".join(f"“{m}”" for m in hi["origin_story"][:4]), ""]

    if n and n.get("caveats"):
        L += ["## Caveats", ""] + [f"- {x['text']}{_cite(x)}" for x in n["caveats"]] + [""]

    if nar:
        L += ["---", f"_Narration by {nar['provider']}; {nar['dropped']} unsupported statement(s) dropped. "
                     "Bracketed IDs reference the evidence below._", "", "<details><summary>Evidence</summary>", ""]
        L += [f"- **{it['id']}** {it['text'].splitlines()[0][:200]}" for it in build_packet(p)["items"]]
        L += ["", "</details>"]
    return "\n".join(L) + "\n"
