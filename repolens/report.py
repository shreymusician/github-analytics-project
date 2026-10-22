"""Render a Markdown report. Works with or without LLM narration."""
from __future__ import annotations

from .architecture import evidence_lines as arch_evidence_lines
from .evidence import build_packet
from .signals import _is_test as is_test_path


def _bar(score: int) -> str:
    n = round(score / 10)
    return "█" * n + "░" * (10 - n)


def _cite(item: dict) -> str:
    return " " + "".join(f"[{e}]" for e in item["evidence"])


_CODE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs", ".rb", ".php", ".kt", ".swift")


def _note(p: dict, area: str, startswith: str) -> str | None:
    return next((e["note"] for e in p[area]["evidence"] if e["ok"] is True and e["note"].startswith(startswith)), None)


def at_a_glance(p: dict) -> list[str]:
    """The facts a learner checks first, in one place. Everything here is deterministic (no model involved)."""
    st, hi, ext = p["stack"], p["history"], p.get("external", {}).get("github", {})
    langs = [k for k, v in st["languages"].items() if v >= 0.05]
    ci = _note(p, "deployability", "CI pipeline configured")
    tests = p["metrics"]["test_files"]
    libs = [d for d in st.get("dependencies", [])][:6] or [i["module"] for i in p["architecture"].get("third_party_imports", [])][:6]
    dirs = sorted({f.split("/")[0] for f in st.get("path_index", [])
                   if "/" in f and f.lower().endswith(_CODE_SUFFIXES) and not is_test_path(f)})[:6]
    lines = ["## At a glance", "",
             f"- **Language:** {', '.join(langs) if langs else (st['primary_language'] or 'unknown')}"]
    if hi.get("commits"):
        lines.append(f"- **Maintenance:** {hi['status']} (last commit {hi['last_commit']}, {hi['idle_days']} days ago; "
                     f"{hi['commits']} commits, {hi['contributors']} contributor(s))")
    lines += [f"- **Tests:** {'yes (' + str(tests) + ' test files)' if tests else 'no'}",
              f"- **CI:** {ci.removeprefix('CI pipeline configured ').strip('()') if ci else 'none found'}",
              f"- **Docker:** {'yes' if _note(p, 'deployability', 'Dockerfile present') else 'no'}",
              f"- **License:** {'yes' + (' (' + ext['license'] + ')' if ext.get('license') else '') if _note(p, 'completeness', 'license present') else 'no'}"]
    if ext:
        lines.append(f"- **GitHub:** {ext.get('stars')} stars, archived: {'yes' if ext.get('archived') else 'no'}")
    if libs:
        lines.append(f"- **Main libraries:** {', '.join(libs)}")
    if dirs:
        lines.append(f"- **Source folders:** {', '.join(dirs)}")
    return lines + [""]


def render(result: dict) -> str:
    p, nar = result["profile"], result["narrative"]
    n = nar["narrative"] if nar else None
    st, ar, hi = p["stack"], p["architecture"], p["history"]
    L: list[str] = [f"# Repo report: {p['repo']}", "", f"Commit `{(p['sha'] or 'unknown')[:10]}`", ""]
    L += at_a_glance(p)

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

    arch = (result.get("architecture") or {}).get("architecture")
    if arch and (arch["how_it_works"] or arch["components"]):
        L += ["## How it works", ""]
        L += [f"{i}. {x['text']}{_cite(x)}" for i, x in enumerate(arch["how_it_works"], 1)]
        if arch["components"]:
            L += ["", "**Key parts**", ""]
            L += [f"- `{c['file']}` **{c['name']}**: {c['role']}{_cite(c)}" for c in arch["components"]]
        L += [""]

    L += ["## Scores", "",
          f"- Completeness: **{p['completeness']['score']}/100** `{_bar(p['completeness']['score'])}`",
          f"- Deployability: **{p['deployability']['score']}/100** `{_bar(p['deployability']['score'])}`",
          "", "_Heuristic scores from rule checks, not yet calibrated against labeled data. Reasons:_", ""]
    for area in ("completeness", "deployability"):
        L += [f"**{area.capitalize()}**"]
        L += [f"- {'–' if e['ok'] is None else '✓' if e['ok'] else '✗'} {e['note']}" for e in p[area]["evidence"]]
        L += [""]
    if p.get("analysis_depth") == "partial":
        graphed = ar.get("python_modules", 0) + ar.get("js_modules", 0)
        L += ["> **Partial analysis:** stub-function and TODO checks cover Python only (checks marked – were not run). "
              + ("The import graph covers Python and JavaScript/TypeScript." if graphed
                 else "No import graph could be built for this repo's languages yet."), ""]

    cen = st.get("file_census")
    if cen:
        authored = cen.get("authored") or {}
        L += ["## Composition", ""]
        if authored:
            L += ["**What the authors wrote** (by size, excluding binary assets): "
                  + " · ".join(f"**{c}** {v:.0%}" for c, v in list(authored.items())[:5]),
                  f"Binary assets and data (images, weights, datasets) add {cen.get('assets_share_bytes', 0):.0%} of all bytes. "
                  f"{cen['total_files']} files in total.", ""]
        else:
            L += [f"No authored text/code found; binary assets are {cen.get('assets_share_bytes', 0):.0%} of bytes.", ""]
    L += ["## Stack", f"- Languages: {', '.join(f'{k} {v:.0%}' for k, v in st['languages'].items()) or 'none detected'}",
          f"- Capabilities: {', '.join(st['capability_tags']) or 'none recognized'}",
          f"- Dependencies: {st['dependency_count']} (pinned ratio {st['pinned_ratio']})", ""]

    if ar.get("read_first"):
        L += ["## Read these first", ""]
        learn = {x["file"]: x for x in (n or {}).get("learning_path", [])}
        for r in ar["read_first"]:
            why = f": {learn[r['file']]['text']}{_cite(learn[r['file']])}" if r["file"] in learn else ""
            L += [f"- `{r['file']}` (imported by {r['imported_by']}, imports {r.get('imports', '?')}){why}"]
        listed = {r["file"] for r in ar["read_first"]}
        L += [f"- `{f}`: {x['text']}{_cite(x)}" for f, x in learn.items() if f not in listed]
        L += [""]
    elif n and n.get("learning_path"):
        L += ["## Read these first", ""] + [f"- `{x['file']}`: {x['text']}{_cite(x)}" for x in n["learning_path"]] + [""]
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
    if arch and (arch["how_it_works"] or arch["components"]):
        a = result["architecture"]
        L += ["", f"_\"How it works\" by {a['provider']}; {a['dropped']} unsupported statement(s) dropped. "
                  "S-IDs reference the source evidence below._", "", "<details><summary>Source evidence</summary>", ""]
        L += arch_evidence_lines(p)
        L += ["", "</details>"]
    return "\n".join(L) + "\n"
