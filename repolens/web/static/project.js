"use strict";
/* "The project" tab: how RepoLens itself is built, read live from the repository's own files. */

RL.loadProject = async function () {
  if (RL.projectLoaded) return;
  const root = RL.$("project-root");
  let d;
  try { d = await RL.api("/api/project"); } catch (e) { RL.clear(root).appendChild(h("div", { class: "errbox" }, e.message)); return; }
  RL.projectLoaded = true;
  RL.clear(root);
  const s = d.stats, rm = d.roadmap;

  root.appendChild(h("div", { class: "card" }, h("h2", {}, "How RepoLens is built"),
    h("p", { class: "muted" }, "Everything on this tab is read live from this project's own files and git history, so it can't drift from the truth.")));

  root.appendChild(h("div", { class: "stats" }, [["commits", s.commits], ["modules", s.modules], ["lines of code", s.code_lines], ["test functions", s.test_functions],
    ["test files", s.test_files], ["scripts", s.scripts], ["docs", s.docs]].map(([k, v]) => h("div", { class: "stat" }, h("b", {}, RL.num(v)), h("span", {}, k)))));

  // progress
  if (rm.overall) {
    root.appendChild(h("div", { class: "big-pcts" },
      h("div", { class: "card" }, h("b", {}, rm.overall.core + "%"), h("div", {}, "of the core product (V0–V4)")),
      h("div", { class: "card" }, h("b", {}, rm.overall.full + "%"), h("div", {}, "of the full roadmap (V0–V6)"))));
    const sym = { done: "[x]", partial: "[~]", todo: "[ ]" };
    root.appendChild(h("div", { class: "card" }, h("h3", {}, "Roadmap progress"),
      h("p", { class: "muted small" }, "Percentages come from a weighted checklist (done = 1, partial = ½, todo = 0; harder items weigh more). Click a version to see its checklist. Updated " + (rm.updated || "?") + "."),
      rm.versions.map((v) => h("details", { class: "rm" },
        h("summary", {}, h("span", {}, h("b", {}, v.id), " ", v.name), RL.bar(v.percent, 100, RL.kindOfScore(v.percent)), h("b", {}, v.percent + "%")),
        h("p", { class: "muted small" }, v.goal),
        h("ul", {}, v.items.map((i) => h("li", {}, h("span", { class: "st" }, sym[i.s] || "[?]"), h("span", {}, i.t, i.note ? h("span", { class: "muted small" }, " — " + i.note) : null))))))));
  }

  // pipeline
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "The pipeline: what happens to a repository"),
    h("div", { class: "legend" }, RL.badge("own algorithms", "info"), RL.badge("AI model (narration only)", "warn"), RL.badge("verification", "good")),
    h("div", { class: "pipeline" }, d.pipeline.map((st) => h("div", { class: "stage " + (st.kind === "ai" ? "ai" : st.kind === "verify" ? "verify" : "") },
      h("div", { class: "n" }, "STEP " + st.n), h("b", {}, st.title), h("p", { class: "small" }, st.text), h("div", { class: "small muted" }, "modules: ", h("code", {}, st.module))))),
    h("p", { class: "muted small", style: "margin-top:10px" }, "Core rule: custom algorithms produce the facts; models only put them into words, and every sentence must cite evidence or it is dropped.")));

  // modules
  const layers = {};
  d.modules.forEach((m) => (layers[m.layer] = layers[m.layer] || []).push(m));
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Code map"), h("p", { class: "muted small" }, "One card per module, grouped by layer. The sentence is the module's own docstring."),
    Object.keys(layers).map((l) => [h("h4", { style: "margin-top:12px" }, l + " (" + layers[l].length + ")"),
      h("div", { class: "mods" }, layers[l].map((m) => h("div", { class: "mod", title: m.path }, h("b", {}, m.name), " ", h("span", { class: "muted small" }, m.lines + " lines"), h("div", { class: "small" }, m.summary || "—"))))])));

  // verification
  const v = d.verification, ver = [];
  if (v.gate_a) ver.push(h("div", { class: "card" }, h("h4", {}, "Review set (10 real repos)"), h("p", {}, `${v.gate_a.narrated}/${v.gate_a.repos} narrated, ${v.gate_a.crashes} crashes, ${v.gate_a.dropped_statements} statements dropped.`)));
  if (v.audit) {
    const c = v.audit.counts, tot = Object.values(c).reduce((a, b) => a + b, 0);
    ver.push(h("div", { class: "card" }, h("h4", {}, "Second-model audit"), h("p", {}, `${c.supported || 0} of ${tot} claims supported by the evidence; ${c.partial || 0} partly; ${c.unsupported || 0} unsupported.`),
      RL.bar(c.supported || 0, tot || 1, "good"), h("p", { class: "muted small" }, `${v.audit.independent}/${v.audit.audits} audits were done by a different model than the writer. A model auditing a model is a check, not proof.`)));
  }
  if (v.fact_check) ver.push(h("div", { class: "card" }, h("h4", {}, "Fact-check against GitHub"), h("p", {}, `${v.fact_check.agree} of ${v.fact_check.checks} facts agree with GitHub's own data.`), RL.bar(v.fact_check.agree, v.fact_check.checks || 1, "good")));
  if (v.answerability) {
    const a = v.answerability, pct = (x) => Math.round(x * 100) + "%";
    const rows = Object.entries(a).map(([arm, r]) => h("tr", {}, h("td", {}, arm), h("td", {}, pct(r.accuracy)), h("td", {}, pct(r.wrong_rate)), h("td", {}, pct(r.unknown_rate))));
    ver.push(h("div", { class: "card" }, h("h4", {}, "Reader test"), h("p", { class: "small" }, "Questions graded by code: can a reader find key facts in the README alone vs in the report?"),
      h("table", {}, h("thead", {}, h("tr", {}, ["source", "correct", "wrong", "don't know"].map((t) => h("th", {}, t)))), h("tbody", {}, rows)),
      h("p", { class: "muted small" }, "Caveat: the questions target facts the report was built to surface, so this favors the report.")));
  }
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Does it work? The evidence"), ver.length ? h("div", { class: "verify-grid" }, ver) : h("p", { class: "muted" }, "No verification reports found in reports/gate_a on this machine.")));

  // decisions
  const decWrap = h("div", {});
  const search = h("input", { type: "search", placeholder: "Search the " + d.decisions.length + " design decisions…", "aria-label": "Search decisions", style: "width:100%;margin-bottom:8px" });
  const drawDec = () => {
    const q = search.value.trim().toLowerCase();
    RL.clear(decWrap);
    d.decisions.filter((x) => !q || (x.title + " " + x.text).toLowerCase().includes(q)).forEach((x) =>
      decWrap.appendChild(h("details", { class: "dec" }, h("summary", {}, RL.badge(x.id, "info"), " ", x.title), h("p", { class: "small" }, x.text + (x.text.length >= 700 ? " …" : "")))));
    if (!decWrap.firstChild) decWrap.appendChild(h("p", { class: "muted" }, "No decision matches."));
  };
  search.addEventListener("input", drawDec); drawDec();
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Why it's built this way"), h("p", { class: "muted small" }, "Every significant choice is written down in docs/DECISIONS.md with its reasons."), search, decWrap));

  // commits
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Recent commits"), h("p", { class: "muted small" }, "Small, well-described commits are a project rule."),
    d.commits.map((c) => h("div", { class: "commit" }, h("code", {}, c.hash), h("span", { class: "d muted" }, c.date), h("span", {}, c.subject)))));

  // limits
  if ((rm.limits || []).length) root.appendChild(h("div", { class: "card" }, h("h3", {}, "Honest limits"), h("ul", { class: "limits" }, rm.limits.map((l) => h("li", {}, l)))));
};
