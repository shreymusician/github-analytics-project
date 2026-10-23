"use strict";
/* Tab routing, theme, and the status chips. */

RL.showTab = function (name) {
  document.querySelectorAll("#tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".panel").forEach((p) => { p.hidden = p.id !== "tab-" + name; });
  try { history.replaceState(null, "", "#" + name); } catch (e) { /* ignore */ }
  if (name === "reports") RL.loadReports();
  if (name === "project") RL.loadProject();
};

RL.initTheme = function () {
  const root = document.documentElement;
  try { const t = localStorage.getItem("repolens-theme"); if (t) root.dataset.theme = t; } catch (e) { /* storage may be blocked */ }
  RL.$("theme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("repolens-theme", root.dataset.theme); } catch (e) { /* ignore */ }
  });
};

RL.loadStatus = async function () {
  const box = RL.$("status-chips");
  try {
    const s = await RL.api("/api/status");
    RL.clear(box);
    s.providers.forEach((p) => box.appendChild(RL.badge(`${p.name}: ${p.configured ? "key set" : "no key"}`, p.configured ? "good" : "")));
    box.appendChild(RL.badge(s.github_token ? "GitHub token set" : "GitHub: no token (low rate limit)", s.github_token ? "good" : "warn"));
    if (!s.can_narrate) box.appendChild(RL.badge("no model keys: facts only", "warn"));
  } catch (e) { RL.clear(box).appendChild(RL.badge("server unreachable", "bad")); }
};

document.addEventListener("DOMContentLoaded", () => {
  RL.initTheme();
  RL.initFind(); RL.initAnalyze(); RL.initReports();
  document.querySelectorAll("#tabs [role=tab]").forEach((b) => b.addEventListener("click", () => RL.showTab(b.dataset.tab)));
  const start = location.hash.slice(1);
  RL.showTab(["find", "analyze", "reports", "project"].includes(start) ? start : "find");
  RL.loadStatus();
});
