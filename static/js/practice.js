// The Practice Room (section 6.6): type, get answered, watch the heat, then feedback.
import { get, post } from "./api.js";
import { takeABreath } from "./breathe.js";
import { createPuppet } from "./puppet.js";
import { typeText } from "./typewriter.js";
import { $, announce, confirmDialog, copy, el, friendly, heatDial, modal, pageData, reducedMotion, setBusy, sleep, toast } from "./ui.js";

const page = pageData();
const roundId = page.round_id;
const params = new URLSearchParams(window.location.search);
let R = null;           // the round from the server
let puppet = null;
let dial = null;
let busy = false;
let timer = null;
let turnStarted = Date.now();
let switchedThisTurn = false;
const answer = $("#answer");

const words = (t) => (t.match(/[A-Za-zÀ-ÿ0-9']+/g) || []).length;

// ---------------------------------------------------------------- rendering
function topBar() {
  const s = R.settings;
  const info = $("#top-info");
  info.textContent = "";
  info.append(el("strong", { text: s.format_name }), el("span", { class: "sep", text: "·" }), el("span", { text: s.committee }),
    el("span", { class: "sep", text: "·" }), el("span", { text: s.topic }), el("span", { class: "sep", text: "·" }),
    el("span", {}, "You: ", el("span", { class: "placard small", text: s.my_country })));
  updateProgress();
}

function updateProgress() {
  const s = R.settings;
  let text = `Exchange ${Math.min(R.exchanges + 1, R.total_exchanges)} of ${R.total_exchanges}`;
  if (s.length === "timed" && s.timed_seconds) {
    const left = Math.max(0, s.timed_seconds - Math.floor((Date.now() - R._loadedAt) / 1000) - R.elapsed_seconds);
    text = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left`;
  }
  if (R.exchanges >= R.total_exchanges) text = copy("round.complete");
  $("#progress").textContent = text;
}

function stage() {
  const d = R.delegate;
  const drawing = $("#stage-drawing");
  drawing.textContent = "";
  if (d.image_url) drawing.append(el("img", { src: d.image_url, alt: d.alt_text || d.name }));
  puppet = createPuppet($("#puppet"), d.look, { quirks: d.quirks, label: `${d.name}'s face` });
  $("#stage-name").textContent = d.name;
  $("#stage-placard").textContent = R.settings.their_country;
  dial = heatDial(R.heat);
  $("#heat-dial").textContent = "";
  $("#heat-dial").append(dial);
  puppet.setHeat(R.heat);
  const lastDelegate = [...R.messages].reverse().find((m) => m.role === "delegate");
  if (lastDelegate) puppet.setExpression(lastDelegate.meta.expression, lastDelegate.meta.eyebrows);
}

function bubble(m) {
  const t = $("#transcript");
  if (m.role === "system") {
    const node = el("div", { class: "divider", role: "note", text: m.text });
    t.append(node);
    return node;
  }
  const isDel = m.role === "delegate";
  const care = isDel && m.meta?.break_character;
  const textNode = el("span", { class: "bubble-text", text: m.text });
  const node = el("div", { class: `bubble ${isDel ? "delegate" : "student"}${care ? " care" : ""}` },
    el("span", { class: "who", text: isDel ? (care ? "A real note from us" : `${R.delegate.name} (${R.settings.their_country})`) : "You" }), textNode);
  if (isDel && m.id && page.logged_in && !care) node.append(reactRow(m));
  t.append(node);
  t.scrollTop = t.scrollHeight;
  return node;
}

function reactRow(m) {
  const up = el("button", { type: "button", "aria-label": "Thumbs up", "aria-pressed": "false", text: "👍" });
  const down = el("button", { type: "button", "aria-label": "Thumbs down: suggest what it should have said", "aria-pressed": "false", text: "👎" });
  up.addEventListener("click", async () => {
    try { await post(`/api/messages/${m.id}/react`, { kind: "up" }); up.setAttribute("aria-pressed", "true"); toast("Thanks!"); } catch (e) { toast(friendly(e), { error: true }); }
  });
  down.addEventListener("click", async () => {
    const box = el("textarea", { id: "should-say", maxlength: "400", rows: "3" });
    await modal({ title: "What should it have said?", body: el("div", {}, el("p", { class: "muted", text: "Your idea helps train this nightmare. The owner approves it first." }),
      el("label", { for: "should-say", text: "A better reply" }), box),
      actions: [{ label: "Cancel", value: false }, { label: "Send", primary: true, value: true, onClick: async () => {
        try {
          const r = await post(`/api/messages/${m.id}/react`, { kind: "down", suggestion: box.value.trim() || null });
          down.setAttribute("aria-pressed", "true"); toast(r.message); return true;
        } catch (e) { toast(friendly(e), { error: true }); return false; }
      } }] });
  });
  return el("div", { class: "react-row" }, up, down);
}

// ---------------------------------------------------------------- timer
function stopTimer() { clearInterval(timer); timer = null; }
function chime() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = 660; g.gain.value = 0.06;
    o.connect(g); g.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.25);
    setTimeout(() => ctx.close(), 500);
  } catch { /* school policy may block audio; that's fine */ }
}
function startTimer() {
  stopTimer();
  turnStarted = Date.now();
  if (!R.settings.options?.timer) { $("#timer").hidden = true; return; }
  const limit = R.settings.turn_seconds || 60;
  const ring = $("#timer"), bar = ring.querySelector(".bar"), label = $("#timer-text");
  ring.hidden = false;
  ring.classList.remove("warn", "over");
  let warned = false, chimed = false;
  const tick = () => {
    const used = (Date.now() - turnStarted) / 1000;
    const left = Math.ceil(limit - used);
    bar.style.strokeDashoffset = String(175.9 * Math.min(1, used / limit));
    label.textContent = left >= 0 ? `${left}s` : `+${-left}s`;
    if (left <= 10 && left > 0 && !warned) { warned = true; ring.classList.add("warn"); announce("10 seconds left"); }
    if (left <= 0 && !chimed) {
      chimed = true;
      ring.classList.remove("warn"); ring.classList.add("over");
      chime();
      // Gentle mode never cuts anyone off. At heat 4+, the delegate calls time.
      if (!R.settings.gentle && R.heat >= 4 && answer.value.trim()) send({ timeUp: true });
    }
    updateProgress();
  };
  tick();
  timer = setInterval(tick, 500);
}

// ---------------------------------------------------------------- turns
function setInputEnabled(on) {
  answer.disabled = !on;
  for (const id of ["send-btn", "hint-btn", "switch-btn", "end-btn"]) $(`#${id}`).disabled = !on;
  if (on) {
    $("#hint-btn").disabled = !(R.settings.options?.hints) || R.hints_left <= 0;
    $("#switch-btn").disabled = R.switch_pending;
  }
}
function updateHints() {
  // The count lives in the button's own text, so busy states can't lose it.
  $("#hint-btn").textContent = R.settings.options?.hints ? `💡 Hint (${R.hints_left} left)` : "💡 Hints off";
}

async function delegateSays(text, meta, messageId, silence = 0) {
  if (silence > 0 && !reducedMotion()) {
    const thinking = el("div", { class: "bubble delegate thinking", text: "…" });
    $("#transcript").append(thinking);
    puppet.setExpression("neutral", 0);
    await sleep(silence * 1000);
    thinking.remove();
  }
  const node = bubble({ role: "delegate", text: "", meta, id: messageId });
  puppet.setExpression(meta.expression, meta.eyebrows);
  puppet.talk(true);
  await typeText(node.querySelector(".bubble-text"), text);
  puppet.talk(false);
  puppet.setExpression(meta.expression, meta.eyebrows);
  $("#transcript").scrollTop = $("#transcript").scrollHeight;
  announce(`${R.delegate.name} says: ${text}`);
}

async function send({ timeUp = false } = {}) {
  if (busy) return;
  const text = answer.value.trim();
  if (!text) { toast("Type your answer first — even one sentence is great.", { error: true }); answer.focus(); return; }
  busy = true;
  let keepLocked = false; // paused (care card) or finished: leave the inputs off afterwards
  stopTimer();
  setInputEnabled(false);
  setBusy($("#send-btn"), true, "Sending…");
  $("#hint-box").hidden = true;
  const studentNode = bubble({ role: "student", text });
  answer.value = "";
  updateWordCount();
  try {
    const res = await post(`/api/rounds/${roundId}/turn`, { text, expected_exchange: R.exchanges, seconds_used: Math.round((Date.now() - turnStarted) / 1000), time_up: timeUp, mode: "type" }, { timeout: 45000 });
    R.exchanges = res.exchange;
    await delegateSays(res.reply, { expression: res.expression, eyebrows: res.eyebrows, break_character: res.break_character }, res.message_id, res.silence_seconds || 0);
    if (res.switched_back) { bubble({ role: "system", text: "Back to your own side." }); R.switch_pending = false; }
    if (res.heat !== R.heat) {
      R.heat = res.heat;
      dial.setValue(res.heat);
      puppet.setHeat(res.heat);
      if (res.toast) toast(res.toast);
    }
    updateProgress();
    if (res.break_character) { keepLocked = true; showCare(); return; }
    if (res.done) { keepLocked = true; await roundComplete(); return; }
    setInputEnabled(true);
    answer.focus();
    startTimer();
  } catch (e) {
    studentNode.remove();
    answer.value = text; // never lose what they typed
    updateWordCount();
    if (e.status === 409 && e.data?.round) { window.location.reload(); return; }
    const box = el("div", { class: "callout warn", role: "alert" }, friendly(e), " ", el("a", { href: "/human", text: "Start a Human Round" }), " — or press Send to try again.");
    $("#transcript").append(box);
    $("#transcript").scrollTop = $("#transcript").scrollHeight;
    setInputEnabled(true);
    startTimer();
  } finally {
    setBusy($("#send-btn"), false);
    if (keepLocked) $("#send-btn").disabled = true;
    busy = false;
  }
}

function showCare() {
  stopTimer();
  setInputEnabled(false);
  const card = el("div", { class: "care-card", role: "alert" },
    el("p", { text: "We paused the round. Take your time." }),
    el("div", { class: "btn-row" },
      el("button", { class: "btn primary", type: "button", text: "Keep going", on: { click: async () => {
        try { await post(`/api/rounds/${roundId}/resume`, {}); } catch { /* fine */ }
        card.remove(); setInputEnabled(true); answer.focus(); startTimer();
      } } }),
      el("button", { class: "btn", type: "button", text: "End round", on: { click: () => endRound({ ask: false }) } })));
  $("#transcript").append(card);
  $("#transcript").scrollTop = $("#transcript").scrollHeight;
}

async function roundComplete() {
  stopTimer();
  setInputEnabled(false);
  const box = el("div", { class: "round-done", role: "status" }, el("p", { class: "hand", text: copy("round.complete") }), el("p", { class: "muted", text: "Getting your feedback…" }));
  $("#transcript").append(box);
  $("#transcript").scrollTop = $("#transcript").scrollHeight;
  announce(copy("round.complete"));
  await sleep(reducedMotion() ? 200 : 1200);
  await endRound({ ask: false });
}

async function endRound({ ask = true } = {}) {
  const noTurns = !R.messages.some((m) => m.role === "student") && R.exchanges === 0;
  if (ask) {
    const ok = noTurns
      ? await confirmDialog(copy("round.leave"), { title: "Leave this round?", ok: "Leave", cancel: "Stay" })
      : await confirmDialog("End the round now and see your feedback?", { title: "End the round?", ok: "End it", cancel: "Keep going" });
    if (!ok) return;
  }
  stopTimer();
  setInputEnabled(false);
  try {
    const res = await post(`/api/rounds/${roundId}/end`, {}, { timeout: 60000 });
    window.location.href = res.abandoned ? "/" : res.url;
  } catch (e) {
    toast(friendly(e), { error: true, ms: 6000 });
    setInputEnabled(true);
  }
}

async function exitRound() {
  if (!(await confirmDialog(copy("round.leave"), { title: "Leave this round?", ok: "Leave", cancel: "Stay" }))) return;
  try { await post(`/api/rounds/${roundId}/end`, { abandon: true }); } catch { /* leaving anyway */ }
  window.location.href = "/";
}

async function hint() {
  if ($("#hint-btn").disabled) return;
  const btn = $("#hint-btn");
  setBusy(btn, true, "Thinking…");
  try {
    const res = await post(`/api/rounds/${roundId}/hint`, {});
    R.hints_left = res.hints_left;
    const box = $("#hint-box");
    box.textContent = "";
    box.append(el("strong", { text: "💡 Idea: " }), res.idea, el("br"), el("strong", { text: "❓ Ask back: " }), res.ask_back);
    box.hidden = false;
    announce(`Hint: ${res.idea}. Ask back: ${res.ask_back}`);
  } catch (e) { toast(friendly(e), { error: true }); }
  setBusy(btn, false);
  updateHints();
  $("#hint-btn").disabled = R.hints_left <= 0 || !R.settings.options?.hints;
  answer.focus();
}

async function switchSides() {
  try {
    const res = await post(`/api/rounds/${roundId}/switch-sides`, {});
    R.switch_pending = true;
    bubble({ role: "system", text: `Switched sides: ${res.message}` });
    $("#switch-btn").disabled = true;
    toast(res.message);
    answer.focus();
  } catch (e) { toast(friendly(e), { error: true }); }
}

function updateWordCount() {
  const n = words(answer.value);
  const limit = R?.settings?.word_limit || 120;
  const wc = $("#word-count");
  wc.textContent = `${n} / ${limit} words`;
  wc.classList.toggle("over", n > limit);
}

// ---------------------------------------------------------------- setup
async function init() {
  try {
    R = await get(`/api/rounds/${roundId}`);
  } catch (e) {
    $("#top-info").textContent = friendly(e);
    return;
  }
  R._loadedAt = Date.now();
  if (R.completed) { window.location.href = `/practice/${roundId}/feedback`; return; }
  if (R.ended) { window.location.href = "/"; return; }
  topBar();
  stage();
  for (const m of R.messages) bubble(m);
  updateHints();
  updateWordCount();
  if (!R.messages.length && R.settings.who_starts === "student") {
    bubble({ role: "system", text: `Your opening speech — ${R.settings.turn_seconds} seconds. You go first!` });
  }
  if (R.paused) { showCare(); return; }
  if (R.exchanges >= R.total_exchanges) { await roundComplete(); return; }
  if (params.get("breath") === "1") { setInputEnabled(false); await takeABreath(); history.replaceState(null, "", window.location.pathname); }
  setInputEnabled(true);
  answer.focus();
  startTimer();
}

answer.addEventListener("input", updateWordCount);
answer.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
$("#send-btn").addEventListener("click", () => send());
$("#hint-btn").addEventListener("click", hint);
$("#switch-btn").addEventListener("click", switchSides);
$("#breath-btn").addEventListener("click", async () => { const wasTimer = !!timer; stopTimer(); await takeABreath(); if (wasTimer && !busy) startTimer(); answer.focus(); });
$("#end-btn").addEventListener("click", () => endRound());
$("#exit-btn").addEventListener("click", exitRound);
document.addEventListener("keydown", (e) => {
  const t = e.target;
  if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.tagName === "SELECT") || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector(".modal, .breath-overlay")) return;
  const k = e.key.toLowerCase();
  if (k === "h") { e.preventDefault(); hint(); }
  if (k === "b") { e.preventDefault(); $("#breath-btn").click(); }
  if (k === "e") { e.preventDefault(); endRound(); }
});
init();
