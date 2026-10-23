"use strict";
/* Boot: who is logged in, tab routing, theme, and the status chips. */

RL.TABS = ["find", "analyze", "reports", "project", "account"];

RL.showTab = function (name) {
  document.querySelectorAll("#tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".panel").forEach((p) => { p.hidden = p.id !== "tab-" + name; });
  try { history.replaceState(null, "", location.pathname + location.search + "#" + name); } catch (e) { /* ignore */ }
  if (name === "reports") RL.loadReports();
  if (name === "project") RL.loadProject();
  if (name === "account") RL.loadAccount();
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

RL.logout = async function () {
  try { await RL.api("/api/auth/logout", {}); } catch (e) { /* the cookie may already be gone */ }
  location.href = "/";
};

/* The chips show which of YOUR model keys are set (never the keys), and whether GitHub search has a token. */
RL.drawChips = function () {
  const box = RL.clear(RL.$("status-chips"));
  (RL.me.keys || []).forEach((k) => {
    const b = RL.badge(k.provider, k.set ? "good" : "");
    b.title = k.set ? `${k.provider}: your key is set (ends in ${k.last4})` : `${k.provider}: no key set. Add one under Account.`;
    box.appendChild(b);
  });
  if (!(RL.me.keys || []).some((k) => k.set)) box.appendChild(RL.badge("no model keys: facts only", "warn"));
};

RL.banner = function () {
  const box = RL.$("banner"), params = new URLSearchParams(location.search);
  if (params.get("verified") === "1") box.appendChild(h("div", { class: "note good" }, "Email confirmed. Thank you."));
  if (!RL.me.user.verified) {
    const resend = h("button", { type: "button" }, "Resend the email");
    resend.addEventListener("click", async () => {
      try { const r = await RL.api("/api/auth/resend", {}); RL.toast(r.dev_mail ? "No mail server is set up: the link was printed in the server console." : "Sent. Check your inbox."); }
      catch (e) { RL.toast(e.message); }
    });
    box.appendChild(h("div", { class: "note warn" }, `Please confirm your email address (${RL.me.user.email}).`,
      RL.me.require_verified ? " Searching and analyzing stay locked until you do. " : " ", resend));
  }
};

document.addEventListener("DOMContentLoaded", async () => {
  RL.initTheme();
  try { RL.me = await RL.api("/api/me"); } catch (e) { return; }     // a 401 has already sent the browser to /login
  RL.csrf = RL.me.csrf;
  RL.initFind(); RL.initAnalyze(); RL.initReports();
  RL.$("logout").addEventListener("click", RL.logout);
  document.querySelectorAll("#tabs [role=tab]").forEach((b) => b.addEventListener("click", () => RL.showTab(b.dataset.tab)));
  const start = location.hash.slice(1);
  RL.showTab(RL.TABS.includes(start) ? start : "find");
  RL.drawChips();
  RL.banner();
});
