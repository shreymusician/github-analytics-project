"use strict";
/* Renders one repository report (from /api/jobs result or /api/report) and a tiny, safe Markdown viewer. */

/* Text followed by clickable citation chips; clicking a chip shows the exact evidence it points at. */
RL.cited = function (text, ids, evidence) {
  const out = h("span", {}, text || "");
  (ids || []).forEach((id) => {
    const chip = h("button", { type: "button", class: "cite", "aria-label": `Show evidence ${id}` }, id);
    chip.addEventListener("click", () => {
      const ev = (evidence || {})[id];
      RL.popover.show(chip, id, ev || "(This evidence item is not in the saved report.)");
    });
    out.append(" ", chip);
  });
  return out;
};

RL.kv = (k, v) => h("div", { class: "kv" }, h("b", {}, k), h("span", {}, v === null || v === undefined || v === "" ? "—" : v));
RL.yesNo = (v) => (v === true ? "yes" : v === false ? "no" : "unknown");

RL.gauge = function (title, g) {
  const reasons = (g.evidence || []).map((e) =>
    h("li", {}, h("span", { class: "m " + (e.ok ? "yes" : "no") }, e.ok === true ? "+" : e.ok === false ? "–" : "·"), h("span", {}, e.note), h("small", {}, `${e.weight} pts`)));
  return h("div", { class: "card gauge" }, h("h3", {}, title), h("div", { class: "num" }, `${g.score}`, h("span", { class: "muted small" }, " / 100")),
    RL.bar(g.score, 100, RL.kindOfScore(g.score)), h("ul", { class: "reasons" }, reasons));
};

RL.renderReport = function (data) {
  const p = data.profile, ev = data.evidence || {}, f = data.facts || {};
  const nar = ((data.narrative || {}).narrative) || null, arch = ((data.architecture || {}).architecture) || null;
  const gh = (p.external || {}).github || {}, hist = p.history, a = p.architecture, root = h("div", {});

  const maturity = nar && nar.maturity ? nar.maturity.level : null;
  root.appendChild(h("div", { class: "card" },
    h("div", { class: "row" }, h("h2", { style: "margin:0" }, p.repo), maturity ? RL.badge(maturity, maturity === "usable" || maturity === "production" ? "good" : "warn") : null,
      RL.badge(hist.status, hist.status === "active" ? "good" : hist.status === "stale" ? "warn" : "bad"),
      h("a", { href: `https://github.com/${p.repo}`, target: "_blank", rel: "noopener noreferrer" }, "open on GitHub ↗"),
      h("span", { style: "margin-left:auto" }, h("span", { class: "muted small" }, "Was this report useful? "), RL.feedback("report", p.repo))),
    nar && nar.summary ? h("p", { style: "font-size:1.05rem;margin-top:10px" }, RL.cited(nar.summary.text, nar.summary.evidence, ev))
      : h("p", { class: "muted" }, "No model summary in this report (no API key was available, or the models were rate-limited). The facts below are still computed by the project's own algorithms."),
    h("div", { class: "muted small" }, `Commit ${(p.sha || "").slice(0, 10)} · narrated by ${(data.narrative || {}).provider || "—"} · explained by ${(data.architecture || {}).provider || "—"}`)));

  // at a glance
  const libs = (p.stack.recognized_dependencies || []).slice(0, 8).join(", ");
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "At a glance"), h("div", { class: "grid" },
    RL.kv("Main language", p.stack.primary_language), RL.kv("Last commit", `${hist.last_commit} (${hist.idle_days} days ago)`),
    RL.kv("Commits / people", `${RL.num(hist.commits)} / ${RL.num(hist.contributors)}`), RL.kv("History shape", hist.shape),
    RL.kv("Tests", f.tests ? `yes (${f.tests} files)` : "none found"), RL.kv("CI", f.ci || "none found"),
    RL.kv("Docker", RL.yesNo(f.docker)), RL.kv("License", RL.yesNo(f.license)),
    RL.kv("Stars", gh.stars !== undefined ? RL.num(gh.stars) : gh.stargazers_count !== undefined ? RL.num(gh.stargazers_count) : "—"),
    RL.kv("Bus factor", hist.bus_factor), RL.kv("Main libraries", libs || "—"), RL.kv("Code size", `${RL.num(p.metrics.source_files)} source files`))));

  // what it is
  if (nar) {
    const rows = [];
    if (nar.scope) rows.push(h("p", {}, h("b", {}, "Scope. "), RL.cited(nar.scope.text, nar.scope.evidence, ev)));
    if (nar.audience) rows.push(h("p", {}, h("b", {}, "Who it's for. "), RL.cited(nar.audience.text, nar.audience.evidence, ev)));
    if (nar.maturity) rows.push(h("p", {}, h("b", {}, "Maturity: " + nar.maturity.level + ". "), RL.cited(nar.maturity.text, nar.maturity.evidence, ev)));
    if (rows.length) root.appendChild(h("div", { class: "card" }, h("h3", {}, "What it is"), rows));
  }

  // how it works
  if (arch) {
    const steps = (arch.how_it_works || []).map((s) => h("li", {}, RL.cited(s.text, s.evidence, ev)));
    const comps = (arch.components || []).map((c) => h("div", {}, h("b", {}, c.name), h("div", {}, h("span", { class: "file" }, c.file)), h("div", { class: "small" }, RL.cited(c.role, c.evidence, ev))));
    root.appendChild(h("div", { class: "card" }, h("h3", {}, "How it works"),
      steps.length ? h("ol", { class: "steps" }, steps) : h("p", { class: "muted" }, "No walkthrough was produced."),
      comps.length ? [h("h4", { style: "margin-top:16px" }, "Key parts"), h("div", { class: "comp" }, comps)] : null,
      h("p", { class: "muted small" }, "Click a chip (S3, E12…) to see the exact source excerpt or fact the statement is based on. Statements without valid evidence are dropped before you see them.")));
  } else {
    root.appendChild(h("div", { class: "card" }, h("h3", {}, "How it works"), h("p", { class: "muted" }, "No explanation available for this report.")));
  }

  // health
  root.appendChild(h("div", { class: "gauges" }, RL.gauge("Completeness", p.completeness), RL.gauge("Runnable / deployable", p.deployability)));
  root.appendChild(h("p", { class: "muted small" }, "Scores are rules over measurable facts (tests, README, CI…), shown with their reasons. They are first guesses, not verdicts."));

  // read first
  const lp = nar && nar.learning_path || [];
  const rf = (a.read_first || []).map((r) => h("li", {}, h("span", { class: "file" }, r.file), " ",
    h("span", { class: "muted small" }, `imported by ${r.imported_by}, imports ${r.imports}`)));
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Read these first"),
    lp.length ? h("ol", {}, lp.map((l) => h("li", {}, h("span", { class: "file" }, l.file), " — ", RL.cited(l.text, l.evidence, ev)))) : null,
    rf.length ? [h("h4", { style: "margin-top:12px" }, "Most central files (import graph, PageRank)"), h("ol", {}, rf)] : null,
    a.entry_points && a.entry_points.length ? h("p", { class: "small" }, h("b", {}, "Entry points: "), a.entry_points.map((e) => h("span", {}, h("span", { class: "file" }, e), " "))) : null));

  // run + caveats
  if (nar && ((nar.how_to_run || []).length || (nar.caveats || []).length)) {
    root.appendChild(h("div", { class: "card" },
      (nar.how_to_run || []).length ? [h("h3", {}, "How to run it"), (nar.how_to_run).map((s) => h("p", {}, RL.cited(s.text, s.evidence, ev)))] : null,
      (nar.caveats || []).length ? [h("h3", {}, "Caveats"), h("ul", {}, nar.caveats.map((c) => h("li", {}, RL.cited(c.text, c.evidence, ev))))] : null));
  }

  // history
  const hs = (hist.hotspots || []).map((x) => h("li", {}, h("span", { class: "file" }, x.file), ` — ${x.changes} changes`));
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "History"), h("div", { class: "grid" },
    RL.kv("First commit", hist.first_commit), RL.kv("Span", `${RL.num(hist.span_days)} days`), RL.kv("Longest quiet gap", `${hist.longest_gap_days} days`),
    RL.kv("Top author share", `${Math.round((hist.top_author_share || 0) * 100)}%`), RL.kv("Low-effort commit messages", `${Math.round((hist.low_effort_message_ratio || 0) * 100)}%`)),
    hs.length ? [h("h4", { style: "margin-top:12px" }, "Most-changed files"), h("ul", {}, hs)] : null));

  // markdown view
  if (data.markdown) {
    const box = h("div", { class: "md", hidden: true });
    const btn = h("button", { type: "button" }, "Show the plain Markdown report");
    btn.addEventListener("click", () => {
      box.hidden = !box.hidden;
      if (!box.firstChild) box.appendChild(RL.markdown(data.markdown));
      btn.textContent = box.hidden ? "Show the plain Markdown report" : "Hide the Markdown report";
    });
    root.appendChild(h("div", { class: "card" }, btn, box));
  }
  return root;
};

/* ------------------------------------------------------------------ safe mini Markdown */
RL.inline = function (text) {
  const out = [], re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|_[^_]+_)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out.push(h("b", {}, RL.inline(t.slice(2, -2))));
    else if (t.startsWith("`")) out.push(h("code", {}, t.slice(1, -1)));
    else if (t.startsWith("[")) { const i = t.indexOf("]("); out.push(h("a", { href: t.slice(i + 2, -1), target: "_blank", rel: "noopener noreferrer" }, t.slice(1, i))); }
    else out.push(h("i", {}, t.slice(1, -1)));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
};

RL.markdown = function (src) {
  const root = h("div", {}), lines = src.replace(/\r/g, "").split("\n");
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.trim()) { i++; continue; }
    let m;
    if ((m = /^(#{1,4})\s+(.*)/.exec(ln))) { root.appendChild(h("h" + m[1].length, {}, RL.inline(m[2]))); i++; continue; }
    if (ln.startsWith("```")) {
      const buf = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++; root.appendChild(h("pre", {}, h("code", {}, buf.join("\n")))); continue;
    }
    if (/^\s*\|/.test(ln) && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1] || "")) {
      const cells = (s) => s.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(ln), body = []; i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) body.push(cells(lines[i++]));
      root.appendChild(h("table", {}, h("thead", {}, h("tr", {}, head.map((c) => h("th", {}, RL.inline(c))))),
        h("tbody", {}, body.map((r) => h("tr", {}, r.map((c) => h("td", {}, RL.inline(c))))))));
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(ln)) {
      const ordered = /^\s*\d+\./.test(ln), list = h(ordered ? "ol" : "ul", {});
      let cur = null;
      while (i < lines.length && (/^\s*([-*]|\d+\.)\s+/.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && cur))) {
        const l = lines[i], top = /^\s{0,1}([-*]|\d+\.)\s+/.exec(l);
        if (top) { cur = h("li", {}, RL.inline(l.replace(/^\s*([-*]|\d+\.)\s+/, ""))); list.appendChild(cur); }
        else cur.append(h("div", { class: "small muted" }, RL.inline(l.replace(/^\s*([-*]|\d+\.)?\s*/, ""))));
        i++;
      }
      root.appendChild(list); continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*([-*]|\d+\.)\s)/.test(lines[i])) para.push(lines[i++]);
    root.appendChild(h("p", {}, RL.inline(para.join(" "))));
  }
  return root;
};
