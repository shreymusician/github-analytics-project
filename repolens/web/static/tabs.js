"use strict";
/* The three working tabs: Find, Analyze, Reports. */

const EXAMPLE_GOALS = ["a RAG chatbot over my documents", "a movie recommender system", "a Discord bot in python", "fine-tune a small language model"];
const EXAMPLE_REPOS = ["Cinnamon/kotaemon", "jaymody/picoGPT", "feyninc/chonkie"];

RL.chips = function (box, items, fn) {
  items.forEach((t) => { const b = h("button", { type: "button" }, t); b.addEventListener("click", () => fn(t)); box.append(" ", b); });
};

/* ------------------------------------------------------------------ Find */
RL.initFind = function () {
  const form = RL.$("find-form"), go = RL.$("find-go");
  RL.chips(RL.$("examples"), EXAMPLE_GOALS, (t) => { RL.$("goal").value = t; form.requestSubmit(); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const goal = RL.$("goal").value.trim();
    if (!goal) return;
    go.disabled = true;
    RL.clear(RL.$("find-results"));
    try {
      const res = await RL.runJob("/api/find", { goal, language: RL.$("lang").value || null, top: Number(RL.$("top").value) }, RL.$("find-progress"));
      RL.showFind(res);
    } catch (err) {
      RL.$("find-results").appendChild(h("div", { class: "errbox" }, err.message));
    } finally { go.disabled = false; }
  });
};

RL.showFind = function (res) {
  const box = RL.clear(RL.$("find-results"));
  box.appendChild(h("div", { class: "card" },
    h("h3", {}, `Top ${res.ranked.length} for “${res.goal}”`),
    h("p", { class: "muted small" }, "Search words (", res.how, "): ", res.queries.map((q) => h("code", {}, q)).flatMap((c) => [c, " "]), res.language ? ` · language: ${res.language}` : ""),
    res.ranked.length < res.requested ? h("p", { class: "small" }, RL.badge("fewer than requested", "warn"), " Only these passed the quality filters. Try describing the goal differently or dropping the language filter.") : null,
    res.order.length > 1 ? h("div", { class: "order" }, h("b", {}, "Suggested order to study them (simplest first):"), h("ol", {}, res.order.map((n) => h("li", {}, n)))) : null,
    h("p", { class: "muted small" }, "Ranking uses GitHub search data and a model's reading of each description. Nothing has been downloaded or analyzed yet. Scores are uncalibrated first guesses.")));
  if (!res.ranked.length) {
    box.appendChild(h("div", { class: "card empty" }, h("h3", {}, "No good matches"), h("p", { class: "muted" }, "Try other words, or remove the language filter.")));
    return;
  }
  const cards = h("div", { class: "cards" });
  res.ranked.forEach((c, i) => cards.appendChild(RL.repoCard(c, i + 1, res.goal)));
  box.appendChild(cards);
};

RL.repoCard = function (c, rank, goal) {
  const parts = Object.entries(c.parts).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const actions = h("div", { class: "actions" });
  const deeper = h("button", { type: "button", class: "primary" }, "Analyze this repo in depth →");
  deeper.addEventListener("click", () => { RL.$("source").value = c.full_name; RL.showTab("analyze"); RL.$("analyze-form").requestSubmit(); });
  actions.append(deeper, h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, "GitHub ↗"),
    h("span", { style: "margin-left:auto" }, h("span", { class: "muted small" }, "Good pick? "), RL.feedback("find", c.full_name, { goal })));
  return h("div", { class: "card repo" },
    h("h3", {}, h("span", { class: "rank" }, rank), c.full_name,
      c.archived ? RL.badge("archived", "warn") : null, c.collection ? RL.badge("collection of projects", "warn") : null, c.weak ? RL.badge("weak match", "bad") : null),
    c.description ? h("p", {}, c.description) : null,
    h("div", { class: "meta" }, h("span", {}, `${RL.num(c.stars)} stars`), h("span", {}, `pushed ${(c.pushed_at || "").slice(0, 10)}`), c.language ? h("span", {}, c.language) : null,
      c.size_mb !== null ? h("span", {}, `${c.size_mb} MB`) : null),
    c.topics && c.topics.length ? h("div", { class: "meta" }, c.topics.slice(0, 8).map((t) => RL.badge(t))) : null,
    c.model_why ? h("div", { class: "quote" }, `Model's view (${c.model_rating}/3): ${c.model_why}`) : null,
    h("div", { class: "score" }, h("span", { class: "big" }, c.score.toFixed(2)), h("span", { class: "muted small" }, "score — here is where it came from:")),
    h("div", { class: "parts" }, parts.map(([k, v]) => h("div", { class: "part" }, h("span", {}, k), RL.bar(v, 0.35), h("span", { class: "muted" }, (v > 0 ? "+" : "") + v.toFixed(2))))),
    c.matched_terms.length || c.dep_hits.length ? h("p", { class: "small muted" },
      c.matched_terms.length ? `Matched your words: ${c.matched_terms.join(", ")}. ` : "", c.dep_hits.length ? `Uses libraries: ${c.dep_hits.join(", ")}.` : "") : null,
    actions);
};

/* ------------------------------------------------------------------ Analyze */
RL.initAnalyze = function () {
  const form = RL.$("analyze-form");
  RL.chips(RL.$("analyze-examples"), EXAMPLE_REPOS, (t) => { RL.$("source").value = t; });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const source = RL.$("source").value.trim();
    if (!source) return;
    const ok = await RL.confirm("Analyze " + source + "?", [
      h("p", {}, "RepoLens will make a read-only partial copy of this repository on your computer (history, but file contents only for the latest commit) and analyze it. Nothing from it is ever run."),
      h("p", { class: "muted small" }, "It can take from under a minute to a few minutes for big repositories. If you have model keys, short pieces of the code (secrets scrubbed) are sent to your configured providers for the explanation.")], "Analyze");
    if (!ok) return;
    const go = RL.$("analyze-go"); go.disabled = true;
    RL.clear(RL.$("analyze-result"));
    try {
      const res = await RL.runJob("/api/analyze", { source }, RL.$("analyze-progress"));
      RL.$("analyze-result").appendChild(RL.renderReport(res));
    } catch (err) {
      RL.$("analyze-result").appendChild(h("div", { class: "errbox" }, err.message));
    } finally { go.disabled = false; }
  });
};

/* ------------------------------------------------------------------ Reports */
RL.initReports = function () {
  const filter = RL.$("report-filter");
  filter.addEventListener("input", () => RL.drawReportList());
};

RL.loadReports = async function () {
  if (RL.reportList) return;
  try { RL.reportList = await RL.api("/api/reports"); } catch (e) { RL.$("report-groups").textContent = e.message; return; }
  RL.drawReportList();
};

RL.drawReportList = function () {
  const box = RL.clear(RL.$("report-groups")), q = RL.$("report-filter").value.trim().toLowerCase();
  const items = (RL.reportList || []).filter((r) => !q || (r.label + " " + r.group).toLowerCase().includes(q));
  if (!items.length) { box.textContent = RL.reportList && RL.reportList.length ? "Nothing matches." : "No saved reports yet. Analyze a repo first."; return; }
  const groups = {};
  items.forEach((r) => (groups[r.group] = groups[r.group] || []).push(r));
  Object.keys(groups).sort().forEach((g) => {
    box.appendChild(h("h4", {}, g));
    groups[g].forEach((r) => {
      const b = h("button", { type: "button", "aria-current": RL.currentReport === r.path ? "true" : "false" }, r.label, " ", h("span", { class: "muted small" }, r.kind));
      b.addEventListener("click", () => RL.openReport(r));
      box.appendChild(b);
    });
  });
};

RL.openReport = async function (r) {
  RL.currentReport = r.path; RL.drawReportList();
  const view = RL.clear(RL.$("report-view"));
  view.appendChild(h("div", { class: "card" }, h("span", { class: "spinner" }), " Loading…"));
  try {
    const d = await RL.api("/api/report?path=" + encodeURIComponent(r.path));
    RL.clear(view);
    view.appendChild(d.profile ? RL.renderReport(d) : h("div", { class: "card md" }, RL.markdown(d.markdown || "")));
  } catch (e) { RL.clear(view).appendChild(h("div", { class: "errbox" }, e.message)); }
};
