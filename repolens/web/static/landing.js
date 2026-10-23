"use strict";
/* Landing page: the goal box hands your goal to sign-up, and the buttons adapt if you are already logged in. */
document.addEventListener("DOMContentLoaded", () => {
  let loggedIn = false;
  RL.$("start-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (loggedIn) { location.href = "/app"; return; }
    try { sessionStorage.setItem("rl_goal", RL.$("start-goal").value.trim().slice(0, 300)); } catch (err) { /* storage may be blocked */ }
    location.href = "/signup";
  });
  fetch("/api/me", { credentials: "same-origin" }).then((r) => {
    if (!r.ok) return;
    loggedIn = true;
    RL.clear(RL.$("nav-actions")).appendChild(h("a", { class: "btn primary", href: "/app" }, "Open the app"));
    RL.$("start-form").querySelector("button").textContent = "Open the app";
    RL.$("start-goal").required = false;
  }).catch(() => {});
});
