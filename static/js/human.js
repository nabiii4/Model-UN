// "Now go find a human." (section 6.8). The laptop is where you start, not where you stay.
import { post } from "./api.js";
import { $, announce, confirmDialog, copy, el, friendly, pageData, reducedMotion, setBusy, toast } from "./ui.js";

const page = pageData();
const card = page.card;
const ho = page.handoff || {};

// ---------------------------------------------------------------- the Human Round card
const hc = $("#human-card");
if (card) {
  hc.append(el("p", {}, el("strong", { text: "Debate this with a person: " }), card.topic + "."),
    el("p", {}, el("strong", { text: "You: " }), card.my_country, " · ", el("strong", { text: "Them: " }), card.their_country),
    el("p", {}, el("strong", { text: "Start with: " }), card.question));
} else {
  hc.append(el("p", { text: "Pick any topic you both care about. One of you argues for it, one against. Then switch." }));
}

// ---------------------------------------------------------------- buttons depend on meeting time + handoff mode
const strictMeeting = ho.meeting && ho.mode === "strict";
let lockTimer = null;
function showLock() {
  const line = $("#lock-line");
  if (!ho.locked || !ho.lock_until) { line.hidden = true; return; }
  const until = new Date(ho.lock_until).getTime();
  const tick = () => {
    const left = Math.max(0, Math.ceil((until - Date.now()) / 60000));
    if (left <= 0) {
      line.textContent = "Your nightmare is awake again. You can practice another round.";
      clearInterval(lockTimer);
      ho.locked = false;
      return;
    }
    line.textContent = copy("handoff.lock", { n: left });
  };
  line.hidden = false;
  tick();
  lockTimer = setInterval(tick, 15000);
}

if (strictMeeting) {
  $("#odd-btn").hidden = !(ho.overtime_available || !ho.locked);
  showLock();
} else {
  const left = ho.home_rounds_left;
  const btn = $("#home-btn");
  btn.hidden = false;
  if (ho.meeting || ho.mode === "off") btn.textContent = "🤖 One more AI round";
  if (left !== null && left !== undefined && left <= 0) {
    btn.disabled = true;
    btn.textContent = `That's ${ho.home_cap} AI rounds today`;
  }
  $("#home-note").hidden = ho.meeting;
}

async function startAnother({ overtime = false } = {}) {
  const last = page.last_settings;
  if (!last || !last.delegate_id) { window.location.href = `/practice/new${overtime ? "?overtime=1" : ""}`; return; }
  const btn = overtime ? $("#odd-btn") : $("#home-btn");
  setBusy(btn, true, "Setting up…");
  try {
    const res = await post("/api/rounds", { ...last, overtime, confirm_overtime: overtime }, { timeout: 45000 });
    window.location.href = res.url;
  } catch (e) {
    setBusy(btn, false);
    if (e.status === 423) toast(e.message, { error: true, ms: 7000 });
    else if (e.status === 404 || e.code === "use_blank") window.location.href = "/practice/new";
    else toast(friendly(e), { error: true, ms: 7000 });
  }
}

$("#odd-btn").addEventListener("click", async () => {
  if (ho.locked && ho.overtime_needs_confirm) {
    const ok = await confirmDialog("Is everyone else paired up, and you have no partner right now? You get ONE overtime round with your nightmare. Next time, you get a human partner first.",
      { title: "Odd one out?", ok: "Yes, I'm the odd one out", cancel: "I'll find someone" });
    if (!ok) return;
  }
  startAnother({ overtime: ho.locked });
});
$("#home-btn").addEventListener("click", () => startAnother());

// ---------------------------------------------------------------- Human Round timer (no AI at all)
const DEFAULT_SEGMENTS = [["A", "Opening", 60], ["B", "Opening", 60], ["A", "Rebuttal", 30], ["B", "Rebuttal", 30]];
let segments = DEFAULT_SEGMENTS.map(([who, kind, secs]) => ({ who, kind, secs }));
let idx = 0, remaining = segments[0].secs, running = false, tick = null, totalSeconds = 0, finished = false;

function names() {
  return { A: $("#name-a").value.trim() || "Speaker A", B: $("#name-b").value.trim() || "Speaker B" };
}

function renderSegInputs() {
  const grid = $("#seg-grid");
  grid.textContent = "";
  segments.forEach((s, i) => {
    const id = `seg-${i}`;
    const input = el("input", { type: "number", id, min: "10", max: "600", step: "5", value: String(s.secs) });
    input.addEventListener("change", () => {
      s.secs = Math.max(10, Math.min(600, Number(input.value) || 30));
      input.value = String(s.secs);
      if (i === idx && !running) { remaining = s.secs; draw(); }
    });
    grid.append(el("div", { class: "field" }, el("label", { for: id, text: `${s.who === "A" ? "Speaker A" : "Speaker B"} ${s.kind} (seconds)` }), input));
  });
}

function fmt(sec) { return `${Math.floor(sec / 60)}:${String(Math.max(0, sec) % 60).padStart(2, "0")}`; }

function draw() {
  const n = names();
  const seg = segments[idx];
  $("#who-now").textContent = finished ? "Done!" : `${n[seg.who]} — ${seg.kind}`;
  const clock = $("#clock");
  clock.textContent = fmt(finished ? 0 : remaining);
  clock.classList.toggle("warn", !finished && remaining <= 10 && running);
  const dots = $("#seg-dots");
  dots.textContent = "";
  segments.forEach((s, i) => dots.append(el("span", { class: i === idx && !finished ? "now" : i < idx || finished ? "done" : "", text: `${n[s.who]} ${s.kind} ${fmt(s.secs)}` })));
  $("#start-pause").textContent = running ? "⏸ Pause" : finished ? "▶ Again" : "▶ Start";
}

function nextSegment() {
  if (idx < segments.length - 1) {
    idx += 1;
    remaining = segments[idx].secs;
    announce(`${names()[segments[idx].who]}, your turn: ${segments[idx].kind}.`);
  } else {
    finish();
  }
  draw();
}

function startStop() {
  if (finished) { reset(); return; }
  running = !running;
  clearInterval(tick);
  if (running) {
    tick = setInterval(() => {
      remaining -= 1;
      totalSeconds += 1;
      if (remaining === 10) announce("10 seconds left");
      if (remaining <= 0) nextSegment();
      draw();
    }, 1000);
  }
  draw();
}

function reset() {
  clearInterval(tick);
  running = false; finished = false; idx = 0; totalSeconds = 0;
  remaining = segments[0].secs;
  $("#hr-done").hidden = true;
  draw();
}

async function finish() {
  clearInterval(tick);
  running = false;
  finished = true;
  const done = $("#hr-done");
  done.textContent = "";
  done.append(el("p", { class: "hand done-line", text: copy("handoff.human_done") }));
  done.hidden = false;
  announce(copy("handoff.human_done"));
  if (page.logged_in) {
    try {
      await post("/api/human-rounds", { partner_name: $("#name-b").value.trim() || null, topic: card ? card.topic : "", seconds: totalSeconds, source_round_id: card ? card.round_id : null });
      done.append(el("p", { class: "muted", text: "Logged in your journey. Microphone stage unlocked!" }));
    } catch (e) {
      done.append(el("p", { class: "muted", text: `We couldn't log it (${friendly(e)}), but it still counts.` }));
    }
  }
  done.append(el("div", { class: "btn-row", style: { justifyContent: "center" } },
    el("a", { class: "btn primary", href: "/wall", text: "Pick your next nightmare" }), el("a", { class: "btn", href: "/", text: "Home" })));
}

$("#found-btn").addEventListener("click", () => {
  $("#human-round").hidden = false;
  $("#name-a").value = $("#name-a").value || (page.logged_in ? "Me" : "");
  renderSegInputs();
  reset();
  $("#human-round").scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth" });
  $("#start-pause").focus();
});
$("#start-pause").addEventListener("click", startStop);
$("#next-seg").addEventListener("click", () => { if (!finished) nextSegment(); });
$("#swap").addEventListener("click", () => { const a = $("#name-a").value; $("#name-a").value = $("#name-b").value; $("#name-b").value = a; draw(); });
$("#reset").addEventListener("click", reset);
$("#name-a").addEventListener("input", draw);
$("#name-b").addEventListener("input", draw);

// ---------------------------------------------------------------- idle dim ("the black glass became a mirror")
let idle = null;
function wake() {
  document.body.classList.remove("dimmed");
  clearTimeout(idle);
  idle = setTimeout(() => { if (!running) document.body.classList.add("dimmed"); }, 60000);
}
["pointermove", "keydown", "pointerdown", "scroll", "touchstart"].forEach((ev) => window.addEventListener(ev, wake, { passive: true }));
wake();
