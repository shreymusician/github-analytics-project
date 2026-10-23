"use strict";
/* One page for /login, /signup, /forgot and /reset. */
const MODES = {
  login: { kicker: "Welcome back", title: "Log in", sub: "Pick up where you left off: your saved searches and reports are here.", go: "Log in", pw: "current-password", api: "/api/auth/login" },
  signup: { kicker: "Free account", title: "Create your account", sub: "One account keeps your history, your own model keys and your daily allowance. It takes a minute.", go: "Create account", pw: "new-password", api: "/api/auth/signup" },
  forgot: { kicker: "Forgot it?", title: "Reset your password", sub: "Enter your email and we will send a link that lasts one hour.", go: "Send the link", api: "/api/auth/forgot" },
  reset: { kicker: "Almost there", title: "Choose a new password", sub: "Use at least 10 characters.", go: "Save new password", pw: "new-password", api: "/api/auth/reset" },
};

document.addEventListener("DOMContentLoaded", () => {
  const mode = MODES[location.pathname.replace("/", "")] ? location.pathname.replace("/", "") : "login";
  const m = MODES[mode], params = new URLSearchParams(location.search);
  RL.$("auth-kicker").textContent = m.kicker; RL.$("auth-title").textContent = m.title; RL.$("auth-sub").textContent = m.sub;
  RL.$("auth-go").textContent = m.go; document.title = `GitHub Intel - ${m.title.toLowerCase()}`;
  RL.$("pw-wrap").hidden = mode === "forgot"; RL.$("email-wrap").hidden = mode === "reset";
  RL.$("email").required = mode !== "reset"; RL.$("password").required = mode !== "forgot";
  if (m.pw) RL.$("password").autocomplete = m.pw;
  RL.$("pw-hint").hidden = !(mode === "signup" || mode === "reset");
  const links = RL.$("auth-links");
  if (mode === "login") links.append(h("a", { href: "/signup" }, "Create an account"), " · ", h("a", { href: "/forgot" }, "Forgot your password?"));
  else if (mode === "signup") links.append("Already have an account? ", h("a", { href: "/login" }, "Log in"));
  else links.append(h("a", { href: "/login" }, "Back to log in"));

  const note = (text, kind) => { RL.clear(RL.$("auth-note")); if (text) RL.$("auth-note").appendChild(h("div", { class: "note " + (kind || "") }, text)); };
  if (params.get("verified") === "1") note("Email confirmed. You can log in now.", "good");
  if (params.get("verified") === "0") note("That confirmation link is invalid or has expired. Log in and use Resend in the app.", "warn");
  if (mode === "reset" && !params.get("token")) note("This reset link is incomplete. Ask for a new one.", "warn");

  RL.$("show-pw").addEventListener("click", (e) => {
    const pw = RL.$("password"), show = pw.type === "password";
    pw.type = show ? "text" : "password"; e.target.textContent = show ? "Hide" : "Show"; e.target.setAttribute("aria-pressed", String(show));
  });

  RL.$("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const go = RL.$("auth-go"); go.disabled = true; note("");
    const body = mode === "forgot" ? { email: RL.$("email").value } : mode === "reset" ? { token: params.get("token"), password: RL.$("password").value }
      : { email: RL.$("email").value, password: RL.$("password").value };
    try {
      const r = await RL.api(m.api, body);
      if (mode === "login" || mode === "signup") { location.href = r.next || "/app"; return; }
      if (mode === "forgot") note("If that email has an account, a reset link is on its way." + (r.dev_mail ? " (No mail server is set up on this install, so the link was printed in the server console.)" : ""), "good");
      else { note("Password changed. Log in with the new one.", "good"); RL.$("auth-form").hidden = true; }
    } catch (err) { note(err.message, "bad"); go.disabled = false; }
  });
});
