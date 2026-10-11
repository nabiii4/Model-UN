// Small helpers for building the page safely.
// Rule (section 14): user text always goes in with textContent, never innerHTML.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith("--")) node.style.setProperty(prop, v); else node.style[prop] = v;
      }
    }
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Inline SVG made from our own trusted markup (never user text).
export function svg(markup) {
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

let _pageData;
export function pageData() {
  if (!_pageData) {
    try { _pageData = JSON.parse($("#page-data")?.textContent || "{}"); } catch { _pageData = {}; }
  }
  return _pageData;
}

let _copy;
export function copy(key, vars = {}) {
  if (!_copy) {
    try { _copy = JSON.parse($("#copy-data")?.textContent || "{}"); } catch { _copy = {}; }
  }
  let text = _copy[key] || "";
  for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
  return text;
}

export function reducedMotion() {
  return document.documentElement.dataset.motion === "reduce" ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function announce(message) {
  const live = $("#live");
  if (!live) return;
  live.textContent = "";
  setTimeout(() => { live.textContent = message; }, 50);
}

export function toast(message, { error = false, ms = 3800 } = {}) {
  const stack = $("#toasts");
  if (!stack || !message) return;
  const t = el("div", { class: "toast" + (error ? " error" : ""), role: error ? "alert" : "status", text: message });
  stack.append(t);
  setTimeout(() => t.remove(), ms);
}

export function friendly(err) {
  return (err && (err.message || (err.data && err.data.message))) || copy("error.generic") || "Something went wrong.";
}

export function setBusy(button, busy, busyLabel) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.dataset.label || button.textContent;
    if (busyLabel) button.textContent = busyLabel;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  } else {
    if (button.dataset.label) button.textContent = button.dataset.label;
    delete button.dataset.label;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

// localStorage can throw (private windows, blocked storage). Never let that break the page.
export function lsGet(key, fallback = null) {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
}
export function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
export function lsRemove(key) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}

// ----- modal with a focus trap; resolves with the clicked action's value -----
export function modal({ title, body, actions = [{ label: "OK", value: true, primary: true }], dismissValue = null, labelledBy } = {}) {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const titleId = "modal-title-" + Math.random().toString(36).slice(2);
    const box = el("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": labelledBy || titleId });
    const close = (value) => {
      document.removeEventListener("keydown", onKey, true);
      backdrop.remove();
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const closeBtn = el("button", { class: "icon-btn close-x", type: "button", "aria-label": "Close", text: "✕", on: { click: () => close(dismissValue) } });
    box.append(closeBtn);
    if (title) box.append(el("h2", { id: titleId, text: title }));
    if (body) box.append(body instanceof Node ? body : el("p", { text: body }));
    const row = el("div", { class: "btn-row", style: { marginTop: "16px" } });
    for (const a of actions) {
      row.append(el("button", { class: "btn" + (a.primary ? " primary" : "") + (a.danger ? " danger" : ""), type: "button", text: a.label,
        on: { click: async () => {
          if (a.onClick) { const keep = await a.onClick(box); if (keep === false) return; }
          close(a.value);
        } } }));
    }
    if (actions.length) box.append(row);
    const backdrop = el("div", { class: "modal-backdrop", on: { mousedown: (e) => { if (e.target === backdrop) close(dismissValue); } } }, box);
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); close(dismissValue); }
      if (e.key === "Tab") {
        const f = $$('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])', box).filter((x) => !x.disabled && x.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener("keydown", onKey, true);
    document.body.append(backdrop);
    const focusTarget = $("input, textarea, select", box) || $(".btn.primary", box) || closeBtn;
    setTimeout(() => focusTarget.focus(), 20);
  });
}

export function confirmDialog(message, { title = "Are you sure?", ok = "Yes", cancel = "Cancel", danger = false } = {}) {
  return modal({ title, body: message, actions: [
    { label: cancel, value: false },
    { label: ok, value: true, primary: !danger, danger },
  ], dismissValue: false });
}

// ----- small visual pieces -----
export function pips(n, max = 5) {
  const wrap = el("span", { class: "pips", role: "img", "aria-label": `Difficulty ${n} of ${max}` });
  for (let i = 1; i <= max; i++) wrap.append(el("i", { class: i <= n ? "on" : "" }));
  return wrap;
}

export function fearMeter(value, label = "") {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const cover = el("span", { class: "fill-cover", style: { width: `${100 - v}%` } });
  const node = el("div", { class: "fear-meter" },
    el("div", { class: "fear-labels" }, el("span", { text: "Friend" }), el("strong", { class: "fear-pct", text: `${label}${v}% scary` }), el("span", { text: "Scary" })),
    el("div", { class: "fear-bar", role: "meter", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(v), "aria-label": "Fear meter" }, cover));
  node.setValue = (nv) => {
    const x = Math.max(0, Math.min(100, Math.round(nv)));
    cover.style.width = `${100 - x}%`;
    node.querySelector(".fear-pct").textContent = `${label}${x}% scary`;
    node.querySelector(".fear-bar").setAttribute("aria-valuenow", String(x));
  };
  return node;
}

export function heatDial(value) {
  const wrap = el("div", { class: "heat-dial" });
  const s = svg(`<svg viewBox="0 0 120 70" aria-hidden="true" focusable="false">
    <defs><linearGradient id="heatgrad" x1="0" x2="1"><stop offset="0" stop-color="#2B6CB0"/><stop offset="1" stop-color="#D64545"/></linearGradient></defs>
    <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="url(#heatgrad)" stroke-width="12" stroke-linecap="round"/>
    <g class="needle"><line x1="60" y1="60" x2="60" y2="18" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></g>
    <circle cx="60" cy="60" r="6" fill="currentColor"/></svg>`);
  const label = el("div", { class: "label" });
  wrap.append(s, label);
  wrap.setValue = (v) => {
    const n = Math.max(1, Math.min(5, v));
    s.querySelector(".needle").style.transform = `rotate(${(n - 3) * 36}deg)`;
    label.textContent = `Heat ${n}/5`;
    wrap.setAttribute("aria-label", `Heat ${n} of 5`);
  };
  wrap.setAttribute("role", "img");
  wrap.setValue(value);
  return wrap;
}

export function confetti() {
  if (reducedMotion()) return;
  const box = el("div", { class: "confetti", "aria-hidden": "true" });
  const colors = ["#C9A27E", "#E8C9A0", "#5B616B", "#FFE45C", "#2F9E67"];
  for (let i = 0; i < 60; i++) {
    box.append(el("i", { style: { left: `${Math.random() * 100}%`, background: colors[i % colors.length], animationDelay: `${Math.random() * 0.8}s` } }));
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 3600);
}

export function tiltFor(id) {
  let h = 0;
  for (const c of String(id)) h = (h * 31 + c.charCodeAt(0)) | 0;
  return ((Math.abs(h) % 400) / 100 - 2).toFixed(2);
}
