"use strict";
/* Shared helpers. Everything is built with DOM calls (never innerHTML), so text from repositories or models
   can never become markup. */
const RL = {};
RL.token = (document.querySelector('meta[name="token"]') || {}).content || "";

RL.h = function (tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  const add = (kid) => {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) kid.forEach(add);
    else el.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid)));
  };
  kids.forEach(add);
  return el;
};
const h = RL.h;

RL.clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
RL.$ = (id) => document.getElementById(id);

RL.api = async function (path, body) {
  const opts = { headers: { "X-Token": RL.token } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error("Could not reach the RepoLens server. Is it still running?"); }
  let data = null;
  try { data = await r.json(); } catch (e) { /* fall through */ }
  if (!r.ok) throw new Error((data && data.error) || `Request failed (${r.status}).`);
  return data;
};

/* Start a background job and poll it. `box` shows live progress. Resolves with the job result. */
RL.runJob = function (path, body, box) {
  RL.clear(box);
  const list = h("ul"), clock = h("span", { class: "muted small" }, "");
  box.appendChild(h("div", { class: "card prog" }, h("div", {}, h("span", { class: "spinner" }), " ", h("b", {}, "Working…"), " ", clock), list));
  return RL.api(path, body).then(({ job }) => new Promise((resolve, reject) => {
    let since = 0, fails = 0;
    const started = Date.now();
    const tick = async () => {
      clock.textContent = `${Math.round((Date.now() - started) / 1000)}s`;
      try {
        const s = await RL.api(`/api/jobs/${job}?since=${since}`);
        fails = 0;
        (s.progress || []).forEach((line) => list.appendChild(h("li", {}, line)));
        since = s.next;
        if (s.status === "done") { RL.clear(box); return resolve(s.result); }
        if (s.status === "error") { RL.clear(box); return reject(new Error(s.error || "The job failed.")); }
      } catch (e) {
        if (++fails >= 5) { RL.clear(box); return reject(e); }
      }
      setTimeout(tick, 1000);
    };
    tick();
  })).catch((e) => { RL.clear(box); throw e; });
};

RL.toast = function (msg) {
  const t = h("div", { class: "toast" }, msg);
  RL.$("toasts").appendChild(t);
  setTimeout(() => t.remove(), 3500);
};

RL.confirm = function (title, bodyNodes, okText) {
  return new Promise((resolve) => {
    const m = RL.$("modal"), ok = RL.$("modal-ok"), cancel = RL.$("modal-cancel");
    RL.$("modal-title").textContent = title;
    RL.clear(RL.$("modal-body")).appendChild(h("div", {}, bodyNodes));
    ok.textContent = okText || "OK";
    m.hidden = false; ok.focus();
    const done = (v) => { m.hidden = true; ok.onclick = cancel.onclick = null; document.removeEventListener("keydown", esc); resolve(v); };
    const esc = (e) => { if (e.key === "Escape") done(false); };
    document.addEventListener("keydown", esc);
    ok.onclick = () => done(true); cancel.onclick = () => done(false);
  });
};

/* A small popover used to show the evidence behind a citation. */
RL.popover = {
  el: null,
  show(anchor, title, text) {
    const p = this.el = RL.$("popover");
    RL.clear(p).appendChild(h("div", {}, h("b", {}, title), "\n", text));
    p.hidden = false;
    const r = anchor.getBoundingClientRect(), w = p.offsetWidth, ph = p.offsetHeight;
    let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
    let top = r.bottom + 6;
    if (top + ph > window.innerHeight - 8) top = Math.max(8, r.top - ph - 6);
    p.style.left = left + "px"; p.style.top = top + "px";
  },
  hide() { if (this.el) this.el.hidden = true; },
};
document.addEventListener("click", (e) => { if (!e.target.closest(".cite") && !e.target.closest("#popover")) RL.popover.hide(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") RL.popover.hide(); });

RL.badge = (text, kind) => h("span", { class: "badge " + (kind || "") }, text);
RL.num = (n) => (typeof n === "number" ? n.toLocaleString() : "—");
RL.kindOfScore = (n) => (n >= 75 ? "good" : n >= 45 ? "warn" : "bad");

/* A horizontal bar. `value` is 0..1 of `max`; negative values are drawn red. */
RL.bar = function (value, max, cls) {
  const pct = Math.max(0, Math.min(100, (Math.abs(value) / (max || 1)) * 100));
  return h("div", { class: "bar " + (cls || "") }, h("i", { class: value < 0 ? "neg" : "", style: `width:${pct}%` }));
};

RL.feedback = function (kind, target, extra) {
  const wrap = h("span", { class: "fb" });
  const send = async (rating, btn) => {
    try {
      await RL.api("/api/feedback", Object.assign({ kind, target, rating }, extra || {}));
      wrap.querySelectorAll("button").forEach((b) => { b.classList.remove("on"); b.disabled = true; });
      btn.classList.add("on");
      RL.toast("Thanks! Saved to data/feedback on this machine.");
    } catch (e) { RL.toast(e.message); }
  };
  const up = h("button", { type: "button", title: "This was useful", "aria-label": "Useful" }, "Useful");
  const down = h("button", { type: "button", title: "This was not useful", "aria-label": "Not useful" }, "Not useful");
  up.addEventListener("click", () => send("up", up));
  down.addEventListener("click", () => send("down", down));
  wrap.append(up, " ", down);
  return wrap;
};
