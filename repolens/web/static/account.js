"use strict";
/* The Account tab: your email, today's usage, your own model API keys, password, and deleting the account. */

const KEY_HELP = {
  groq: ["Groq", "https://console.groq.com/keys", "Free tier. Fast. Starts with gsk_."],
  gemini: ["Google Gemini", "https://aistudio.google.com/apikey", "Free tier through Google AI Studio."],
  openrouter: ["OpenRouter", "https://openrouter.ai/keys", "Has free models; a small limit per day without credits."],
};

RL.loadAccount = async function () {
  const root = RL.clear(RL.$("account-root"));
  let me;
  try { me = RL.me = await RL.api("/api/me"); } catch (e) { root.appendChild(h("div", { class: "errbox" }, e.message)); return; }
  RL.drawChips();

  root.appendChild(h("div", { class: "card" }, h("h2", {}, "Your account"),
    h("div", { class: "grid" }, RL.kv("Email", me.user.email), RL.kv("Email confirmed", me.user.verified ? "yes" : "not yet"),
      ...Object.entries(me.usage).map(([k, u]) => RL.kv(`${k} today`, `${u.used} of ${u.limit}`))),
    h("p", { class: "muted small" }, "Daily limits protect the shared GitHub search budget. They reset at midnight UTC.")));

  // API keys
  const rows = me.keys.map((k) => {
    const [name, link, note] = KEY_HELP[k.provider];
    const input = h("input", { type: "password", autocomplete: "off", spellcheck: "false", placeholder: k.set ? `set, ends in ${k.last4}. Paste a new key to replace it` : "Paste your key", "aria-label": `${name} API key` });
    const save = h("button", { type: "button", class: "primary" }, k.set ? "Replace" : "Save");
    save.addEventListener("click", async () => {
      try { await RL.api("/api/keys", { provider: k.provider, key: input.value.trim() }); input.value = ""; RL.toast(`${name} key saved (encrypted).`); RL.loadAccount(); }
      catch (e) { RL.toast(e.message); }
    });
    const remove = k.set ? h("button", { type: "button" }, "Remove") : null;
    if (remove) remove.addEventListener("click", async () => { try { await RL.api("/api/keys/delete", { provider: k.provider }); RL.toast(`${name} key removed.`); RL.loadAccount(); } catch (e) { RL.toast(e.message); } });
    return h("div", { class: "keyrow" }, h("div", {}, h("b", {}, name), " ", RL.badge(k.set ? "set" : "not set", k.set ? "good" : ""), h("div", { class: "muted small" }, note, " ",
      h("a", { href: link, target: "_blank", rel: "noopener noreferrer" }, "Get a key ↗"))), h("div", { class: "row" }, input, save, remove));
  });
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Your model API keys"),
    h("p", { class: "muted" }, "RepoLens uses YOUR keys to write the explanations, so it costs you nothing here and costs us nothing to run. Without any key you still get every computed fact (stack, history, tests, CI, scores); the written summary and walkthrough need at least one key. With several, RepoLens fails over between them automatically."),
    h("p", { class: "muted small" }, "Keys are encrypted before they are stored, are only ever decrypted to run your own jobs, and are never sent back to this page. Short excerpts of public code (secrets scrubbed) are sent to the provider you choose."), rows));

  // password
  const old = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Current password" });
  const nw = h("input", { type: "password", autocomplete: "new-password", "aria-label": "New password", placeholder: "At least 10 characters" });
  const change = h("button", { type: "button" }, "Change password");
  change.addEventListener("click", async () => {
    try { await RL.api("/api/auth/change-password", { old: old.value, new: nw.value }); old.value = nw.value = ""; RL.toast("Password changed. Other devices were logged out."); }
    catch (e) { RL.toast(e.message); }
  });
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Password"), h("div", { class: "row" }, old, nw, change)));

  // delete
  const pw = h("input", { type: "password", autocomplete: "current-password", "aria-label": "Password to confirm deletion" });
  const del = h("button", { type: "button", class: "danger" }, "Delete my account");
  del.addEventListener("click", async () => {
    const ok = await RL.confirm("Delete your account?", [h("p", {}, "This permanently deletes your account, saved keys, history and feedback. It cannot be undone.")], "Delete");
    if (!ok) return;
    try { await RL.api("/api/auth/delete-account", { password: pw.value }); location.href = "/"; } catch (e) { RL.toast(e.message); }
  });
  root.appendChild(h("div", { class: "card" }, h("h3", {}, "Delete account"), h("p", { class: "muted small" }, "Enter your password to confirm."), h("div", { class: "row" }, pw, del)));
};
