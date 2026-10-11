// The Blank, basic version (section 6.12): build your own nightmare without drawing.
// The rendered avatar becomes the "drawing". Look options never change personality or difficulty.
import { api, post } from "./api.js";
import { loadTraits } from "./persona-card.js";
import { createPuppet } from "./puppet.js";
import { $, el, friendly, setBusy } from "./ui.js";

const LOOK_SLOTS = ["style", "hair", "eyebrows", "eyes", "glasses", "mouth", "facial_hair", "headwear", "outfit", "accessory", "skin_tone", "palette"];
const DEFAULT_TACTICS = ["demands_evidence", "interrupts", "pins_down_dodges", "so_what", "yes_no_traps"];
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
let traits, puppet;
const state = { name: "", temperament: "calm", tactics: DEFAULT_TACTICS.map((id, i) => ({ id, intensity: [3, 2, 3, 2, 1][i] })), difficulty: 2, voice: "alloy",
  weakness: "real_examples", look: { style: "sketch", hair: "side_part", eyebrows: "flat", eyes: "round", glasses: "none", mouth: "flat", facial_hair: "none", headwear: "none", outfit: "navy_suit", accessory: "placard", skin_tone: "sketch", palette: "pencil" } };

const label = (cat, id) => ((traits.by_category[cat] || []).find((t) => t.id === id) || {}).label || id.replaceAll("_", " ");
const describe = (cat, id) => ((traits.by_category[cat] || []).find((t) => t.id === id) || {}).description || "";

function oneLiner() {
  const top = [...state.tactics].sort((a, b) => b.intensity - a.intensity)[0];
  const d = describe("tactic", top.id).replace(/\.$/, "");
  return `A ${label("temperament", state.temperament).toLowerCase()} opponent who ${d.charAt(0).toLowerCase()}${d.slice(1)}.`.slice(0, 140);
}

function refreshPreview() {
  puppet?.destroy();
  puppet = createPuppet($("#blank-puppet"), state.look, { label: "Your nightmare's face" });
  puppet.setExpression(state.difficulty >= 4 ? "stern" : state.difficulty <= 1 ? "amused" : "skeptical", state.difficulty >= 4 ? -1 : 0);
  $("#preview-name").textContent = state.name || "?";
  $("#preview-liner").textContent = oneLiner();
}

function select(id, options, value, onChange) {
  const s = $(id);
  s.textContent = "";
  options.forEach(([v, t]) => s.append(el("option", { value: v, text: t, selected: v === value })));
  s.onchange = () => { onChange(s.value); refreshPreview(); };
}

function renderTactics() {
  const box = $("#b-tactics");
  box.textContent = "";
  state.tactics.forEach((t, i) => {
    const sid = `bt-${i}`, rid = `br-${i}`;
    const s = el("select", { id: sid, "aria-label": `Tactic ${i + 1}` }, ...traits.by_category.tactic.map((o) => el("option", { value: o.id, text: o.label, selected: o.id === t.id })));
    const out = el("output", { for: rid, text: String(t.intensity) });
    const r = el("input", { type: "range", id: rid, min: "0", max: "5", value: String(t.intensity), "aria-label": `Tactic ${i + 1} intensity` });
    s.addEventListener("change", () => { t.id = s.value; refreshPreview(); });
    r.addEventListener("input", () => { t.intensity = Number(r.value); out.textContent = r.value; refreshPreview(); });
    box.append(el("div", { class: "tactic-row" }, s, r, out));
  });
}

function renderDifficulty() {
  const box = $("#b-difficulty");
  box.textContent = "";
  for (let i = 1; i <= 5; i++) box.append(el("button", { type: "button", "aria-pressed": String(i === state.difficulty), "aria-label": `Difficulty ${i}`, text: String(i),
    on: { click: () => { state.difficulty = i; renderDifficulty(); refreshPreview(); } } }));
}

function renderLook() {
  const box = $("#b-look");
  box.textContent = "";
  for (const slot of LOOK_SLOTS) {
    const id = `look-${slot}`;
    const s = el("select", { id }, ...(traits.look_by_slot[slot] || []).map((v) => el("option", { value: v, text: v.replaceAll("_", " "), selected: v === state.look[slot] })));
    s.addEventListener("change", () => { state.look[slot] = s.value; refreshPreview(); });
    box.append(el("div", { class: "field" }, el("label", { for: id, class: "small", text: slot.replace("_", " ") }), s));
  }
}

function renderAll() {
  $("#b-name").value = state.name;
  select("#b-temperament", traits.by_category.temperament.map((t) => [t.id, t.label]), state.temperament, (v) => { state.temperament = v; });
  select("#b-voice", traits.voices.map((v) => [v, v[0].toUpperCase() + v.slice(1)]), state.voice, (v) => { state.voice = v; });
  select("#b-weakness", traits.by_category.weakness.map((t) => [t.id, t.label]), state.weakness, (v) => { state.weakness = v; });
  renderTactics();
  renderDifficulty();
  renderLook();
  refreshPreview();
}

function randomize() {
  const adjectives = ["Midnight", "Velvet", "Thunder", "Paper", "Silent", "Turbo", "Glitter", "Iron", "Polite", "Quantum"];
  const nouns = ["Moderator", "Chair", "Delegate", "Diplomat", "Envoy", "Ambassador", "Questioner", "Negotiator"];
  state.name = `The ${pick(adjectives)} ${pick(nouns)}`;
  state.temperament = pick(traits.by_category.temperament).id;
  const ids = [...traits.by_category.tactic].sort(() => Math.random() - 0.5).slice(0, 5).map((t) => t.id);
  state.tactics = ids.map((id) => ({ id, intensity: Math.floor(Math.random() * 6) }));
  state.difficulty = 1 + Math.floor(Math.random() * 5);
  state.voice = pick(traits.voices);
  state.weakness = pick(traits.by_category.weakness).id;
  for (const slot of LOOK_SLOTS) state.look[slot] = pick(traits.look_by_slot[slot]);
  renderAll();
}

function persona() {
  const tactics = state.tactics.filter((t) => t.intensity > 0);
  const uniq = [];
  for (const t of tactics) if (!uniq.some((u) => u.id === t.id)) uniq.push(t);
  const top = [...uniq].sort((a, b) => b.intensity - a.intensity);
  const w = (traits.by_category.weakness || []).find((x) => x.id === state.weakness);
  return {
    name: state.name.trim() || "The Blank Nightmare", nickname: "", alt_text: `A face built in The Blank: ${state.look.hair.replace("_", " ")} hair, ${state.look.outfit.replaceAll("_", " ")}.`,
    clues: [{ saw: "Built in The Blank", means: "Every choice was yours" }, { saw: label("tactic", (top[0] || state.tactics[0]).id), means: describe("tactic", (top[0] || state.tactics[0]).id) }],
    one_liner: oneLiner(), temperament: [state.temperament], quirks: [],
    catchphrases: ["Interesting point, delegate.", "Let's see you prove it."],
    tactics: (uniq.length >= 2 ? uniq : state.tactics.slice(0, 2).map((t) => ({ ...t, intensity: Math.max(1, t.intensity) }))).slice(0, 5),
    interrupt_level: Math.min(5, (uniq.find((t) => t.id === "interrupts") || { intensity: 1 }).intensity),
    silence_seconds: uniq.some((t) => t.id === "silent_treatment") ? 3 : 0,
    base_difficulty: state.difficulty,
    voice: { tts_voice: state.voice, pace: "normal", energy: 3, tone: `Sounds ${label("temperament", state.temperament).toLowerCase()}.` },
    look: { ...state.look, summary: `Built in The Blank.` },
    weakness: { description: w ? w.description : "Has one weak spot. Find it.", how_to_beat: ["Stay calm and keep going", "Use one clear example"] },
  };
}

$("#randomize").addEventListener("click", randomize);
$("#b-name").addEventListener("input", (e) => { state.name = e.target.value; $("#preview-name").textContent = state.name || "?"; });
$("#blank-form").addEventListener("submit", (e) => {
  e.preventDefault();
  if (!state.name.trim()) { $("#blank-error").textContent = "Give your nightmare a name first."; $("#b-name").focus(); return; }
  $("#blank-error").textContent = "";
  $("#blank-builder").hidden = true;
  $("#blank-save").hidden = false;
  $("#bs-title").focus();
});
$("#blank-back").addEventListener("click", () => { $("#blank-save").hidden = true; $("#blank-builder").hidden = false; });
$("#blank-save-btn").addEventListener("click", async () => {
  const btn = $("#blank-save-btn");
  $("#bs-error").textContent = "";
  setBusy(btn, true, "Saving…");
  try {
    let tempImageId = null;
    try {
      const png = await puppet.toPNG(600);
      if (png) {
        const fd = new FormData();
        fd.append("image", png, "blank.png");
        tempImageId = (await api("/api/images/temp", { method: "POST", form: fd })).temp_image_id;
      }
    } catch { /* the puppet still shows without a picture */ }
    const res = await post("/api/delegates", { persona: persona(), temp_image_id: tempImageId, source: "blank",
      visibility: document.querySelector('input[name="b-vis"]:checked').value, credit: document.querySelector('input[name="b-credit"]:checked').value,
      story: $("#b-story").value });
    $("#blank-save").hidden = true;
    const box = $("#blank-saved");
    box.append(el("h3", { class: "hand", text: "Saved! 🎉" }), res.message ? el("p", { text: res.message }) : null,
      el("div", { class: "btn-row", style: { justifyContent: "center" } },
        el("a", { class: "btn primary big", href: `/practice/new?delegate=${encodeURIComponent(res.id)}`, text: "Practice against it now" }),
        el("a", { class: "btn", href: `/d/${encodeURIComponent(res.id)}`, text: "See it on the Wall" })));
    box.hidden = false;
    box.classList.add("slap");
    box.querySelector(".btn.primary").focus();
  } catch (e) {
    $("#bs-error").textContent = friendly(e);
  } finally { setBusy(btn, false); }
});

loadTraits().then((t) => { traits = t; renderAll(); });
