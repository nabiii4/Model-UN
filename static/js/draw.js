// The Draw flow (section 6.2): Draw -> 3 questions -> Bring it to life -> Meet your nightmare -> Save.
import { api, post } from "./api.js";
import { createCamera } from "./draw-camera.js";
import { createDrawingPad } from "./draw-canvas.js";
import { dataUrlToBlob, loadImageFromFile, MAX_INPUT_BYTES, prepareImage } from "./image-prep.js";
import { renderPersonaCard } from "./persona-card.js";
import { createPuppet } from "./puppet.js";
import { renderQuestions } from "./questions.js";
import { $, $$, confirmDialog, copy, el, friendly, lsGet, lsRemove, lsSet, pageData, reducedMotion, setBusy, sleep, toast } from "./ui.js";

const page = pageData();
const params = new URLSearchParams(window.location.search);
const DRAFT_KEY = "nd-draft";
const state = { image: null, source: null, answers: {}, draft: null, tempImageId: null, note: null, card: null };

// ---------------------------------------------------------------- steps
function showStep(i) {
  $$(".step").forEach((s) => { s.hidden = s.id !== `step-${i}`; });
  $$("#steps li").forEach((li) => {
    const n = Number(li.dataset.i);
    li.className = n < i ? "done" : n === i ? "current" : "";
    if (n === i) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  });
  const h = $(`#h-${i}`);
  if (h) { h.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" }); }
}

function saveDraftLocally() {
  // An in-progress drawing is the only thing kept on the device (cleared on save or logout).
  lsSet(DRAFT_KEY, { at: Date.now(), source: state.source, answers: state.answers, draft: state.draft,
    tempImageId: state.tempImageId, note: state.note, imageDataUrl: state.image ? state.image.dataUrl : null });
}

// ---------------------------------------------------------------- step 1: draw
let camera = null;
let pad = null;
const boost = () => $("#boost")?.checked !== false;

function useImage(result, source) {
  state.image = result;
  state.source = source;
  $("#captured-img").src = result.dataUrl;
  $("#paper-path").hidden = true;
  $("#canvas-path").hidden = true;
  $("#captured").hidden = false;
  $("#use-photo").focus();
}

function selectTab(name) {
  const cam = name === "camera";
  $("#tab-btn-camera").setAttribute("aria-selected", String(cam));
  $("#tab-btn-upload").setAttribute("aria-selected", String(!cam));
  $("#tab-camera").hidden = !cam;
  $("#tab-upload").hidden = cam;
  if (!cam && camera && camera.isOn()) camera.stop();
}

function setupPaper() {
  $("#paper-path").hidden = false;
  $("#link-paper").hidden = true;
  camera = createCamera($("#tab-camera"), {
    getBoost: boost,
    onCapture: (res) => useImage(res, "photo"),
    onUnavailable: () => { $("#tab-btn-camera").hidden = true; selectTab("upload"); },
    onUseUpload: () => selectTab("upload"),
  });
  $("#tab-btn-camera").addEventListener("click", () => selectTab("camera"));
  $("#tab-btn-upload").addEventListener("click", () => selectTab("upload"));
  $$('[role="tab"]').forEach((t) => t.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); const other = t.id === "tab-btn-camera" ? "upload" : "camera"; selectTab(other); $(`#tab-btn-${other}`).focus(); }
  }));
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { $("#tab-btn-camera").hidden = true; selectTab("upload"); }
  setupUpload();
}

// Upload + a simple crop box
let cropImg = null;
let crop = null;
function setupUpload() {
  const input = $("#file-input");
  const zone = $("#dropzone");
  input.addEventListener("change", () => input.files[0] && handleFile(input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (e) => { const f = e.dataTransfer?.files?.[0]; if (f) handleFile(f); });
  $("#crop-cancel").addEventListener("click", () => { $("#crop-area").hidden = true; zone.hidden = false; input.value = ""; });
  $("#crop-use").addEventListener("click", async () => {
    const btn = $("#crop-use");
    setBusy(btn, true, "Cleaning it up…");
    try {
      const img = $("#crop-img");
      const sx = cropImg.naturalWidth / img.clientWidth, sy = cropImg.naturalHeight / img.clientHeight;
      const res = await prepareImage(cropImg, { crop: { x: crop.x * sx, y: crop.y * sy, w: crop.w * sx, h: crop.h * sy }, boost: boost() });
      useImage(res, "photo");
    } catch { toast(copy("error.bad_image"), { error: true }); }
    setBusy(btn, false);
  });
  setupCropDrag();
}

async function handleFile(file) {
  if (file.size > MAX_INPUT_BYTES) { toast(copy("error.big_file"), { error: true, ms: 6000 }); return; }
  if (!/^image\//.test(file.type || "image/")) { toast(copy("error.bad_image"), { error: true }); return; }
  try {
    const { img, url } = await loadImageFromFile(file);
    cropImg = img;
    const shown = $("#crop-img");
    shown.src = url;
    await new Promise((r) => (shown.complete ? r() : shown.addEventListener("load", r, { once: true })));
    $("#dropzone").hidden = true;
    $("#crop-area").hidden = false;
    const w = shown.clientWidth, h = shown.clientHeight;
    crop = { x: w * 0.02, y: h * 0.02, w: w * 0.96, h: h * 0.96 };
    drawCrop();
    $("#crop-use").focus();
  } catch {
    toast(copy("error.bad_image"), { error: true });
  }
}

function drawCrop() {
  const box = $("#crop-box");
  Object.assign(box.style, { left: `${crop.x}px`, top: `${crop.y}px`, width: `${crop.w}px`, height: `${crop.h}px` });
}

function setupCropDrag() {
  const box = $("#crop-box");
  const handle = $("#crop-handle");
  let mode = null, start = null;
  const bounds = () => { const i = $("#crop-img"); return { w: i.clientWidth, h: i.clientHeight }; };
  const clamp = () => {
    const b = bounds();
    crop.w = Math.max(40, Math.min(crop.w, b.w)); crop.h = Math.max(40, Math.min(crop.h, b.h));
    crop.x = Math.max(0, Math.min(crop.x, b.w - crop.w)); crop.y = Math.max(0, Math.min(crop.y, b.h - crop.h));
    drawCrop();
  };
  const down = (m) => (e) => { e.preventDefault(); e.stopPropagation(); mode = m; start = { x: e.clientX, y: e.clientY, crop: { ...crop } }; e.target.setPointerCapture(e.pointerId); };
  box.addEventListener("pointerdown", down("move"));
  handle.addEventListener("pointerdown", down("resize"));
  const move = (e) => {
    if (!mode) return;
    const dx = e.clientX - start.x, dy = e.clientY - start.y;
    if (mode === "move") { crop.x = start.crop.x + dx; crop.y = start.crop.y + dy; }
    else { crop.w = start.crop.w + dx; crop.h = start.crop.h + dy; }
    clamp();
  };
  box.addEventListener("pointermove", move);
  handle.addEventListener("pointermove", move);
  const up = () => { mode = null; };
  box.addEventListener("pointerup", up);
  handle.addEventListener("pointerup", up);
  box.addEventListener("keydown", (e) => {
    const step = 10;
    const keys = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (!keys[e.key]) return;
    e.preventDefault();
    const [dx, dy] = keys[e.key];
    if (e.shiftKey) { crop.w += dx; crop.h += dy; } else { crop.x += dx; crop.y += dy; }
    clamp();
  });
}

async function setupCanvas() {
  $("#canvas-path").hidden = false;
  $("#link-canvas").hidden = true;
  pad = createDrawingPad($("#pad"));
  if (pad.hasSaved()) {
    const keep = await confirmDialog("We found your drawing from before. Keep going with it?", { title: "Welcome back!", ok: "Keep going", cancel: "Start over" });
    if (keep) await pad.restoreSaved(); else pad.forgetSaved();
  }
  $("#done-drawing").addEventListener("click", async () => {
    if (!pad.hasDrawing()) {
      const go = await confirmDialog("Your sheet is still blank. Use it anyway?", { title: "Blank sheet?", ok: "Use it", cancel: "Keep drawing" });
      if (!go) return;
    }
    const btn = $("#done-drawing");
    setBusy(btn, true, "Saving your drawing…");
    try {
      const res = await prepareImage(pad.canvas, { boost: false });
      useImage(res, "canvas");
    } catch { toast(copy("error.generic"), { error: true }); }
    setBusy(btn, false);
  });
}

$("#use-photo").addEventListener("click", () => {
  if (camera && camera.isOn()) camera.stop();
  saveDraftLocally();
  showStep(1);
});
$("#retake").addEventListener("click", () => {
  state.image = null;
  $("#captured").hidden = true;
  if (state.source === "canvas") $("#canvas-path").hidden = false;
  else { $("#paper-path").hidden = false; $("#crop-area").hidden = true; $("#dropzone").hidden = false; $("#file-input").value = ""; }
});
$("#describe-instead").addEventListener("click", () => {
  state.image = null;
  state.source = "description";
  if (camera && camera.isOn()) camera.stop();
  showStep(1);
});

// ---------------------------------------------------------------- step 2: questions
const questions = renderQuestions($("#questions"), page.answers || {});
async function afterQuestions(skip) {
  state.answers = skip ? {} : questions.getAnswers();
  try { await post("/api/me/answers", { answers: state.answers }); } catch { /* not required to continue */ }
  saveDraftLocally();
  bringToLife();
}
$("#q-continue").addEventListener("click", () => afterQuestions(false));
$("#q-skip").addEventListener("click", () => afterQuestions(true));

// ---------------------------------------------------------------- step 3: bring it to life
let loadingTimer = null;
function startLoading() {
  const lines = [1, 2, 3, 4, 5].map((n) => copy(`draw.loading_${n}`));
  let i = 0;
  $("#life-loading").hidden = false;
  $("#loading-line").textContent = lines[0];
  clearInterval(loadingTimer);
  loadingTimer = setInterval(() => { i = (i + 1) % lines.length; $("#loading-line").textContent = lines[i]; }, 2600);
}
function stopLoading() { clearInterval(loadingTimer); $("#life-loading").hidden = true; }

function lifeMessage(text, actions = [], { tone = "note" } = {}) {
  const box = $("#life-message");
  box.textContent = "";
  box.append(el("p", { class: `callout ${tone}`, role: "alert", text }), el("div", { class: "btn-row" }, ...actions));
  box.hidden = false;
}

function joinPrompt() {
  saveDraftLocally();
  const next = encodeURIComponent("/draw?resume=1");
  lifeMessage(copy("error.guest_ai_off"), [
    el("a", { class: "btn primary", href: `/join?next=${next}`, text: "Join the club" }),
    el("a", { class: "btn", href: `/login?next=${next}`, text: "Log in" }),
    el("a", { class: "btn ghost", href: "/", text: "Watch the demo round" }),
  ]);
  $("#h-2").textContent = "Almost there!";
}

function showDescribe(promptText) {
  $("#describe-label").textContent = promptText || copy("error.vision_fallback");
  $("#life-describe").hidden = false;
  $("#describe-text").focus();
}

async function bringToLife() {
  showStep(2);
  $("#h-2").textContent = "Bringing it to life…";
  $("#life-message").hidden = true;
  $("#life-describe").hidden = true;
  $("#reveal").hidden = true;
  if (page.guest && !page.guest_ai) { joinPrompt(); return; }
  if (!state.image) { showDescribe("Tell me about your nightmare in one sentence."); return; }
  startLoading();
  const fd = new FormData();
  fd.append("image", state.image.blob || dataUrlToBlob(state.image.dataUrl), "drawing.jpg");
  fd.append("answers", JSON.stringify(state.answers || {}));
  let res;
  try {
    res = await api("/api/delegates/draft-from-image", { method: "POST", form: fd, timeout: 45000 });
  } catch (e) {
    stopLoading();
    if (e.code === "guest_ai_off") { joinPrompt(); return; }
    if (e.data?.temp_image_id) state.tempImageId = e.data.temp_image_id;
    if (e.status === 429 || e.code === "slow_down") {
      lifeMessage(e.message, [el("a", { class: "btn", href: "/human", text: "Start a Human Round" })], { tone: "warn" });
      return;
    }
    if (e.status === 400) { // the photo itself was the problem (too big, wrong type)
      lifeMessage(e.message, [el("button", { class: "btn primary", type: "button", text: "Try another photo", on: { click: restart } })], { tone: "warn" });
      return;
    }
    // Timeout or AI trouble: always a way forward (describe it, or a Human Round).
    $("#h-2").textContent = "Let's try it with words";
    showDescribe(copy("error.vision_fallback"));
    return;
  }
  stopLoading();
  handleDraft(res);
}

async function describeGo() {
  const text = $("#describe-text").value.trim();
  if (text.length < 3) { toast("Tell me a little about it first.", { error: true }); return; }
  const btn = $("#describe-go");
  setBusy(btn, true, "Reading your words…");
  $("#life-message").hidden = true;
  startLoading();
  try {
    const res = await post("/api/delegates/draft-from-text", { description: text, answers: state.answers, temp_image_id: state.tempImageId }, { timeout: 50000 });
    stopLoading();
    $("#life-describe").hidden = true;
    if (!state.image && state.source !== "description") state.source = "description";
    handleDraft(res);
  } catch (e) {
    stopLoading();
    if (e.code === "guest_ai_off") { joinPrompt(); return; }
    lifeMessage(friendly(e), [el("a", { class: "btn", href: "/human", text: "Start a Human Round" })], { tone: "warn" });
  } finally { setBusy(btn, false); }
}
$("#describe-go").addEventListener("click", describeGo);
$("#describe-text").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); describeGo(); } });

function restart() {
  lsRemove(DRAFT_KEY);
  window.location.href = `/draw${page.path ? `?path=${page.path}` : ""}`;
}

async function handleDraft(res) {
  if (!res.ok) {
    $("#h-2").textContent = "Hmm…";
    const tryAgain = el("button", { class: "btn primary", type: "button", text: res.safety?.status === "unsafe" ? "Try another drawing" : "Try another photo", on: { click: restart } });
    const describe = el("button", { class: "btn", type: "button", text: "Describe it instead", on: { click: () => { $("#life-message").hidden = true; showDescribe("Tell me about your drawing in one sentence."); } } });
    lifeMessage(res.message, res.safety?.status === "unsafe" ? [tryAgain] : [tryAgain, describe], { tone: "warn" });
    return;
  }
  state.draft = res.draft;
  state.tempImageId = res.temp_image_id || state.tempImageId;
  state.note = res.note || null;
  saveDraftLocally();
  $("#h-2").textContent = "It's alive!";
  const list = $("#clue-list");
  list.textContent = "";
  $("#reveal").hidden = false;
  for (const c of state.draft.clues || []) {
    list.append(el("li", {}, el("strong", { text: c.saw }), " → ", c.means));
    await sleep(reducedMotion() ? 50 : 900);
  }
  $("#to-meet").hidden = false;
  $("#to-meet").focus();
}
$("#to-meet").addEventListener("click", () => showMeet());

// ---------------------------------------------------------------- step 4: meet your nightmare
async function showMeet() {
  showStep(3);
  const frame = $("#meet-drawing");
  frame.textContent = "";
  if (state.image?.dataUrl) {
    frame.append(el("img", { src: state.image.dataUrl, alt: state.draft.alt_text || "Your drawing" }));
  } else {
    const p = el("div", { class: "puppet" });
    frame.append(p);
    createPuppet(p, state.draft.look, { quirks: state.draft.quirks, label: state.draft.alt_text || state.draft.name });
  }
  const note = $("#real-person-note");
  note.hidden = !state.note;
  note.textContent = state.note || "";
  state.card = await renderPersonaCard($("#persona-card"), state.draft, { editable: true, onChange: (p) => { state.draft = p; saveDraftLocally(); } });
  const flip = $("#meet-flip");
  flip.classList.remove("flipped");
  void flip.offsetWidth;
  flip.classList.add("flipped");
}

let proposal = null;
$("#revise-go").addEventListener("click", async () => {
  const text = $("#revise-text").value.trim();
  if (text.length < 2) { toast("Tell it what to change first.", { error: true }); return; }
  const btn = $("#revise-go");
  setBusy(btn, true, "Changing…");
  const out = $("#revise-result");
  try {
    const res = await post("/api/delegates/revise-draft", { persona: state.card.getPersona(), instruction: text }, { timeout: 50000 });
    proposal = res.persona;
    out.textContent = "";
    out.append(el("p", { class: "callout note", text: res.summary }));
    if (res.changes.length) {
      out.append(el("ul", { class: "diff-list" }, ...res.changes.map((c) => el("li", {},
        el("strong", { text: `${c.label}: ` }), el("span", { class: "diff-before", text: c.before }), " → ", el("span", { class: "diff-after", text: c.after }),
        c.why ? el("div", { class: "small muted", text: c.why }) : null))));
      out.append(el("div", { class: "btn-row" },
        el("button", { class: "btn primary", type: "button", text: "Accept", on: { click: async () => {
          state.draft = proposal; proposal = null; out.hidden = true; $("#revise-text").value = "";
          state.card = await renderPersonaCard($("#persona-card"), state.draft, { editable: true, onChange: (p) => { state.draft = p; saveDraftLocally(); } });
          saveDraftLocally(); toast("Changed!");
        } } }),
        el("button", { class: "btn", type: "button", text: "Undo", on: { click: () => { proposal = null; out.hidden = true; } } })));
    }
    out.hidden = false;
  } catch (e) {
    out.textContent = "";
    out.append(el("p", { class: "callout warn", text: friendly(e) + " You can still edit the card yourself." }));
    out.hidden = false;
  } finally { setBusy(btn, false); }
});
$("#revise-text").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#revise-go").click(); } });

$("#to-save").addEventListener("click", () => {
  state.draft = state.card.getPersona();
  if (!state.draft.name.trim()) { toast("Give your nightmare a name first.", { error: true }); return; }
  saveDraftLocally();
  showStep(4);
  if (page.guest) {
    $("#vis-field").hidden = true;
    $("#credit-field").hidden = true;
    $("#save-btn").textContent = "Save it on this device";
  }
});

// ---------------------------------------------------------------- step 5: save
$("#story").addEventListener("input", () => { $("#story-count").textContent = String($("#story").value.length); });
$("#save-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#save-btn");
  $("#save-error").textContent = "";
  if (page.guest) { saveOnDevice(); return; }
  setBusy(btn, true, "Taping it to the Wall…");
  try {
    const form = new FormData($("#save-form"));
    const res = await post("/api/delegates", {
      persona: state.draft, temp_image_id: state.tempImageId, visibility: form.get("visibility"),
      credit: form.get("credit"), story: $("#story").value, source: state.source || "photo",
    });
    lsRemove(DRAFT_KEY);
    lsRemove("nd-drawing");
    pad?.stop();
    showSaved(res);
  } catch (err) {
    $("#save-error").textContent = friendly(err);
  } finally { setBusy(btn, false); }
});

function showSaved(res) {
  $("#save-form").hidden = true;
  const box = $("#saved");
  box.textContent = "";
  box.append(
    el("h3", { class: "hand", text: "Saved! 🎉" }),
    el("p", { text: res.message || (res.status === "active" ? "Your nightmare is ready." : "") }),
    el("div", { class: "btn-row", style: { justifyContent: "center" } },
      el("a", { class: "btn primary big", href: `/practice/new?delegate=${encodeURIComponent(res.id)}`, text: "Practice against it now" }),
      el("a", { class: "btn", href: `/d/${encodeURIComponent(res.id)}`, text: "See it on the Wall" })));
  box.hidden = false;
  box.classList.add("slap");
  box.querySelector(".btn.primary").focus();
}

function saveOnDevice() {
  const list = lsGet("nd-guest-nightmares", []) || [];
  list.unshift({ id: `local-${Date.now()}`, persona: state.draft, image: state.image?.dataUrl || null, at: Date.now() });
  const ok = lsSet("nd-guest-nightmares", list.slice(0, 5));
  $("#save-form").hidden = true;
  const box = $("#saved");
  box.textContent = "";
  box.append(el("h3", { class: "hand", text: ok ? "Saved on this device" : "Couldn't save on this device" }),
    el("p", { text: copy("draw.guest_saved") }),
    el("div", { class: "btn-row", style: { justifyContent: "center" } },
      page.guest_ai ? el("button", { class: "btn primary big", type: "button", text: "Practice against it now", on: { click: guestPractice } }) : null,
      el("a", { class: "btn", href: `/join?next=${encodeURIComponent("/draw?resume=1")}`, text: "Join the club" })));
  box.hidden = false;
}

async function guestPractice(e) {
  const btn = e.currentTarget;
  setBusy(btn, true, "Setting up…");
  try {
    const res = await post("/api/rounds", { guest_persona: state.draft, format: "rebuttal_duel", length: "quick" });
    window.location.href = res.url;
  } catch (err) {
    toast(friendly(err), { error: true, ms: 6000 });
    setBusy(btn, false);
  }
}

// ---------------------------------------------------------------- start
async function init() {
  const saved = lsGet(DRAFT_KEY);
  if (params.get("resume") && saved) {
    Object.assign(state, { source: saved.source, answers: saved.answers || {}, draft: saved.draft, tempImageId: saved.tempImageId, note: saved.note });
    if (saved.imageDataUrl) state.image = { dataUrl: saved.imageDataUrl, blob: dataUrlToBlob(saved.imageDataUrl) };
    if (state.draft && !page.guest) { showMeet(); return; }
    if (state.image || state.source === "description") { bringToLife(); return; }
  }
  showStep(0);
  if (page.path === "paper") setupPaper();
  else if (page.path === "canvas") setupCanvas();
  else { $("#path-choice").hidden = false; $(".alt-paths").hidden = true; }
}
init();
