// Round setup (section 6.5). Quick Start reuses your last settings: practicing in one click.
import { get, post } from "./api.js";
import { $, $$, confirmDialog, copy, el, friendly, pageData, setBusy } from "./ui.js";

const page = pageData();
const comfort = page.comfort || {};
let setup = null;
let delegates = [];
let format = "rebuttal_duel";
let difficulty = 2;

function lockMessage(err) {
  const box = $("#lock-box");
  box.textContent = "";
  const actions = el("div", { class: "btn-row" }, el("a", { class: "btn primary", href: "/human", text: "Go to the Human Round" }));
  if (err.overtime_available) {
    actions.append(el("button", { class: "btn", type: "button", text: "I'm the odd one out", on: { click: async () => {
      let confirmed = true;
      if (err.overtime_needs_confirm) confirmed = await confirmDialog("Is everyone else paired up, and you have no partner right now? You get ONE overtime round, then a human partner first next time.", { title: "Odd one out?", ok: "Yes, I'm the odd one out" });
      if (confirmed) start({ overtime: true, confirm_overtime: true });
    } } }));
  }
  box.append(el("div", { class: "callout warn panel" }, el("p", { class: "hand lock-text", text: err.message }), actions));
  box.hidden = false;
  box.scrollIntoView({ block: "center" });
}

function fill(select, items, value) {
  select.textContent = "";
  for (const it of items) select.append(el("option", { value: it.value, text: it.label, selected: it.value === value }));
}

function renderFormats() {
  const box = $("#formats");
  box.textContent = "";
  for (const f of setup.formats) {
    const later = f.phase > 1;
    const id = `fmt-${f.id}`;
    box.append(el("label", { class: `format-card${later ? " later" : ""}`, for: id },
      el("input", { type: "radio", name: "format", id, value: f.id, checked: f.id === format, disabled: later }),
      el("strong", { text: f.name }), el("span", { class: "small", text: f.blurb }),
      later ? el("span", { class: "small muted", text: "Coming in Phase 2" }) : null));
  }
  $$('input[name="format"]').forEach((r) => r.addEventListener("change", () => { format = r.value; }));
}

function renderDifficulty() {
  const box = $("#difficulty");
  box.textContent = "";
  const cap = comfort.gentle ? 2 : 5;
  for (let i = 1; i <= 5; i++) {
    box.append(el("button", { type: "button", "aria-pressed": String(i === difficulty), disabled: i > cap, "aria-label": `Difficulty ${i}`, text: String(i),
      on: { click: () => { difficulty = i; renderDifficulty(); } } }));
  }
  const names = ["", "Friendly sparring", "Polite but firm", "Real committee", "Tough room", "Nightmare"];
  $("#difficulty-hint").textContent = `${difficulty}: ${names[difficulty]}` + (comfort.gentle ? " · Gentle mode is on, so the max is 2." : "");
}

function renderTopics(committeeId, keep) {
  const c = setup.committees.find((x) => x.id === committeeId) || setup.committees[0];
  fill($("#topic"), (c?.topics || []).map((t) => ({ value: t, label: t })), keep);
}

function delegateChanged() {
  const d = delegates.find((x) => x.id === $("#delegate").value);
  if (d) {
    difficulty = Math.min(d.difficulty || 2, comfort.gentle ? 2 : 5);
    renderDifficulty();
    $("#delegate-hint").textContent = `Base difficulty ${d.difficulty}/5 · ${(d.tags || []).join(", ")}`;
  }
}

function settingsFromForm(extra = {}) {
  const custom = $("#topic-custom").value.trim();
  const committee = setup.committees.find((x) => x.id === $("#committee").value);
  return {
    delegate_id: $("#delegate").value, format, committee: committee ? committee.name : "",
    topic: custom || $("#topic").value, my_country: $("#my-country").value.trim(), their_country: $("#their-country").value.trim(),
    mode: "type", difficulty, length: (document.querySelector('input[name="length"]:checked') || {}).value || "quick",
    options: { hints: $("#opt-hints").checked, timer: $("#opt-timer").checked, breath: $("#opt-breath").checked }, ...extra,
  };
}

async function start(extra = {}, body = null) {
  const btn = $("#start");
  $("#setup-error").textContent = "";
  const payload = body || settingsFromForm(extra);
  if (!payload.delegate_id) { $("#setup-error").textContent = "Pick an opponent first."; return; }
  if (payload.my_country && !setup.countries.includes(payload.my_country)) { $("#setup-error").textContent = "Pick your country from the list (start typing its name)."; $("#my-country").focus(); return; }
  if (payload.their_country && !setup.countries.includes(payload.their_country)) payload.their_country = "";
  if (!payload.my_country) payload.my_country = "Canada";
  setBusy(btn, true, "Setting up the room…");
  setBusy($("#quick-start"), true);
  try {
    const res = await post("/api/rounds", { ...payload, ...extra }, { timeout: 45000 });
    const next = payload.options?.breath ? `${res.url}?breath=1` : res.url;
    window.location.href = next;
  } catch (e) {
    if (e.status === 423) lockMessage(e.data);
    else if (e.data?.url) window.location.href = e.data.url;
    else {
      $("#setup-error").textContent = friendly(e);
      if (e.data?.human_round_url) $("#setup-error").append(" ", el("a", { href: "/human", text: "Start a Human Round" }));
    }
  } finally { setBusy(btn, false); setBusy($("#quick-start"), false); }
}

async function init() {
  try {
    const [s, wall, me] = await Promise.all([
      get("/api/setup-data"),
      get("/api/delegates?sort=new&limit=60"),
      page.logged_in ? get("/api/me").catch(() => null) : Promise.resolve(null),
    ]);
    setup = s;
    const mine = (me?.nightmares || []).filter((n) => n.status === "active" || n.visibility === "private");
    delegates = wall.items.filter((d) => !d.opens_blank);
    const options = [];
    const seen = new Set();
    for (const n of mine) { if (!seen.has(n.id)) { options.push({ value: n.id, label: `★ ${n.name} (mine)` }); seen.add(n.id); delegates.push({ id: n.id, name: n.name, difficulty: 2, tags: [] }); } }
    for (const d of delegates) if (!seen.has(d.id)) { options.push({ value: d.id, label: `${d.name}${d.is_example ? " (example)" : ""}` }); seen.add(d.id); }
    if (page.delegate_id && !seen.has(page.delegate_id)) {
      try {
        const d = await get(`/api/delegates/${encodeURIComponent(page.delegate_id)}`);
        if (d.opens_blank) { window.location.href = "/blank"; return; }
        options.unshift({ value: d.id, label: d.name });
        delegates.push({ id: d.id, name: d.name, difficulty: d.difficulty, tags: d.tags });
      } catch { /* not visible: fall back to the list */ }
    }
    fill($("#delegate"), options, page.delegate_id || options[0]?.value);
    fill($("#committee"), setup.committees.map((c) => ({ value: c.id, label: c.name })), setup.committees[0]?.id);
    renderTopics(setup.committees[0]?.id);
    const dl = $("#country-list");
    setup.countries.forEach((c) => dl.append(el("option", { value: c })));
    renderFormats();
    $(`input[name="length"][value="${comfort.default_length || "quick"}"]`)?.setAttribute("checked", "");
    $("#opt-timer").checked = comfort.timers !== false;
    $("#opt-hints").checked = true;
    delegateChanged();
  } catch (e) {
    $("#setup-error").textContent = friendly(e);
    return;
  }
  const last = page.last_settings;
  if (last && last.delegate_id) {
    const box = $("#quick-box");
    const name = delegates.find((d) => d.id === last.delegate_id)?.name || "your last nightmare";
    $("#quick-desc").textContent = `${name} · ${last.topic} · ${last.my_country} vs ${last.their_country} · difficulty ${last.difficulty}`;
    box.hidden = false;
    $("#quick-start").addEventListener("click", () => start({}, { ...last, their_country: last.their_country, format: last.format }));
    if (page.quick) $("#quick-start").focus();
  }
  if (page.handoff?.locked) {
    lockMessage({ message: copy("handoff.lock", { n: Math.max(1, Math.ceil(page.handoff.seconds_left / 60)) }), overtime_available: page.handoff.overtime_available, overtime_needs_confirm: page.handoff.overtime_needs_confirm });
  }
  if (page.overtime && page.handoff?.locked) $("#lock-box button.btn:not(.primary)")?.focus();
}

$("#committee").addEventListener("change", () => renderTopics($("#committee").value));
$("#delegate").addEventListener("change", delegateChanged);
$("#surprise").addEventListener("click", () => {
  const all = setup.committees.flatMap((c) => c.topics.map((t) => ({ c: c.id, t })));
  if (!all.length) return;
  const pick = all[Math.floor(Math.random() * all.length)];
  $("#committee").value = pick.c;
  renderTopics(pick.c, pick.t);
  $("#topic-custom").value = "";
});
$("#setup").addEventListener("submit", (e) => { e.preventDefault(); start(); });
init();
