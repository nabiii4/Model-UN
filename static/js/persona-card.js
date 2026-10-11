// The persona card (section 6.2 E). Read-only for visitors; fully editable for the owner:
// rename, add/remove tags from the trait library, drag intensities, change difficulty, rewrite catchphrases.
import { get } from "./api.js";
import { el, pips } from "./ui.js";

let traitCache = null;
export async function loadTraits() {
  if (!traitCache) traitCache = get("/api/traits").catch(() => ({ by_category: {}, look_by_slot: {}, voices: [] }));
  return traitCache;
}

const clone = (o) => JSON.parse(JSON.stringify(o));

export async function renderPersonaCard(container, persona, { editable = false, onChange, showTitle = true, showWeakness = true } = {}) {
  const traits = await loadTraits();
  const cat = traits.by_category || {};
  const labelOf = (category, id) => ((cat[category] || []).find((t) => t.id === id) || {}).label || id.replaceAll("_", " ");
  let p = clone(persona);
  const changed = () => onChange && onChange(clone(p));

  function section(title, ...kids) {
    return el("section", {}, el("div", { class: "section-title", text: title }), ...kids);
  }

  function textField(label, value, { max, onInput, multiline = false, cls = "" }) {
    const id = "f-" + Math.random().toString(36).slice(2);
    const input = el(multiline ? "textarea" : "input", { id, class: `inline-edit ${cls}`, maxlength: String(max), rows: multiline ? "2" : null, type: multiline ? null : "text" });
    input.value = value || "";
    input.addEventListener("input", () => { onInput(input.value); changed(); });
    return el("div", { class: "field" }, el("label", { for: id, class: "small", text: label }), input);
  }

  function tagEditor(category, key, { min, max }) {
    const wrap = el("div");
    const draw = () => {
      wrap.textContent = "";
      const list = el("div");
      for (const id of p[key]) {
        list.append(el("span", { class: "tag" }, labelOf(category, id),
          editable && p[key].length > min ? el("button", { type: "button", "aria-label": `Remove ${labelOf(category, id)}`, text: "✕",
            on: { click: () => { p[key] = p[key].filter((x) => x !== id); draw(); changed(); } } }) : null));
      }
      wrap.append(list);
      if (editable && p[key].length < max) {
        const id = "add-" + key;
        const select = el("select", { id, class: "add-select" }, el("option", { value: "", text: `+ Add ${category}` }),
          ...(cat[category] || []).filter((t) => !p[key].includes(t.id)).map((t) => el("option", { value: t.id, text: t.label })));
        select.addEventListener("change", () => { if (select.value) { p[key] = [...p[key], select.value]; draw(); changed(); } });
        wrap.append(el("label", { for: id, class: "sr-only", text: `Add ${category}` }), select);
      }
    };
    draw();
    return wrap;
  }

  function slider(label, value, min, max, onSet, suffix = "") {
    const id = "s-" + Math.random().toString(36).slice(2);
    const out = el("output", { for: id, text: `${value}${suffix}` });
    const input = el("input", { type: "range", id, min: String(min), max: String(max), step: "1", value: String(value) });
    input.addEventListener("input", () => { out.textContent = `${input.value}${suffix}`; onSet(Number(input.value)); changed(); });
    return el("div", { class: "intensity-row" }, el("label", { for: id, text: label }), input, out, el("span"));
  }

  function tacticsEditor() {
    const wrap = el("div");
    const draw = () => {
      wrap.textContent = "";
      for (const t of p.tactics) {
        if (editable) {
          const row = slider(labelOf("tactic", t.id), t.intensity, 0, 5, (v) => { t.intensity = v; });
          if (p.tactics.length > 2) {
            row.lastChild.replaceWith(el("button", { type: "button", class: "icon-btn", "aria-label": `Remove ${labelOf("tactic", t.id)}`, text: "✕",
              on: { click: () => { p.tactics = p.tactics.filter((x) => x !== t); draw(); changed(); } } }));
          }
          wrap.append(row);
        } else {
          wrap.append(el("div", { class: "intensity-row" }, el("span", { text: labelOf("tactic", t.id) }),
            el("div", { class: "bar-static", role: "img", "aria-label": `${t.intensity} out of 5` }, el("span", { style: { width: `${t.intensity * 20}%` } })),
            el("span", { text: `${t.intensity}/5` }), el("span")));
        }
      }
      if (editable && p.tactics.length < 5) {
        const select = el("select", { id: "add-tactic", class: "add-select" }, el("option", { value: "", text: "+ Add a tactic" }),
          ...(cat.tactic || []).filter((t) => !p.tactics.some((x) => x.id === t.id)).map((t) => el("option", { value: t.id, text: t.label })));
        select.addEventListener("change", () => { if (select.value) { p.tactics.push({ id: select.value, intensity: 3 }); draw(); changed(); } });
        wrap.append(el("label", { for: "add-tactic", class: "sr-only", text: "Add a tactic" }), select);
      }
    };
    draw();
    return wrap;
  }

  function difficultyEditor() {
    if (!editable) return el("div", {}, pips(p.base_difficulty), ` ${p.base_difficulty}/5`);
    const group = el("div", { class: "pip-buttons", role: "group", "aria-label": "Base difficulty" });
    const draw = () => {
      group.textContent = "";
      for (let i = 1; i <= 5; i++) {
        group.append(el("button", { type: "button", "aria-pressed": String(i === p.base_difficulty), "aria-label": `Difficulty ${i}`, text: String(i),
          on: { click: () => { p.base_difficulty = i; draw(); changed(); } } }));
      }
    };
    draw();
    return group;
  }

  function build() {
    container.textContent = "";
    const card = el("div", { class: "persona-card" });
    if (editable) {
      card.append(
        textField("Name", p.name, { max: 40, onInput: (v) => { p.name = v; } }),
        textField("Placard nickname", p.nickname, { max: 40, onInput: (v) => { p.nickname = v; } }),
        textField("One-liner", p.one_liner, { max: 140, multiline: true, onInput: (v) => { p.one_liner = v; } }));
    } else {
      if (showTitle) card.append(el("h3", { text: p.name }), p.nickname ? el("div", { class: "nick", text: `“${p.nickname}”` }) : null);
      card.append(el("p", { class: "one-liner", text: p.one_liner }));
    }

    // Catchphrases
    const cp = el("div");
    if (editable) {
      p.catchphrases.forEach((c, i) => cp.append(textField(`Catchphrase ${i + 1}`, c, { max: 70, onInput: (v) => { p.catchphrases[i] = v; } })));
      if (p.catchphrases.length < 3) {
        cp.append(el("button", { type: "button", class: "btn small", text: "+ Add a catchphrase", on: { click: () => { p.catchphrases.push(""); build(); changed(); } } }));
      }
    } else {
      p.catchphrases.forEach((c) => cp.append(el("p", { class: "hand catch", text: `“${c}”` })));
    }
    card.append(section("Catchphrases", cp));

    card.append(section("Temperament", tagEditor("temperament", "temperament", { min: 1, max: 3 })));
    card.append(section("Quirks", tagEditor("quirk", "quirks", { min: 0, max: 3 })));
    card.append(section("Tactics (0 = never, 5 = all the time)", tacticsEditor()));

    const levels = el("div");
    if (editable) {
      levels.append(slider("Interrupt level", p.interrupt_level, 0, 5, (v) => { p.interrupt_level = v; }),
        slider("Dramatic silence", p.silence_seconds, 0, 6, (v) => { p.silence_seconds = v; }, " s"));
    } else {
      levels.append(el("p", { text: `Interrupt level: ${p.interrupt_level}/5 · Dramatic silence: ${p.silence_seconds} s` }));
    }
    card.append(section("Pressure", levels));
    card.append(section("Base difficulty", difficultyEditor()));

    // Weakness: every nightmare has one. (The delegate page shows it in its own box.)
    const weak = el("div");
    if (editable) {
      weak.append(textField("Its weakness", p.weakness.description, { max: 160, multiline: true, onInput: (v) => { p.weakness.description = v; } }));
      p.weakness.how_to_beat.forEach((h, i) => weak.append(textField(`How to beat it ${i + 1}`, h, { max: 80, onInput: (v) => { p.weakness.how_to_beat[i] = v; } })));
    } else {
      weak.append(el("p", { text: p.weakness.description }), el("ul", {}, ...p.weakness.how_to_beat.map((h) => el("li", { text: h }))));
    }
    if (editable || showWeakness) card.append(section("How to beat it", weak));

    // Voice (the "Hear it" button arrives with AI voice in Phase 2).
    const voices = traits.voices || [];
    if (editable && voices.length) {
      const id = "voice-pick";
      const select = el("select", { id }, ...voices.map((v) => el("option", { value: v, text: v[0].toUpperCase() + v.slice(1), selected: v === p.voice.tts_voice })));
      select.addEventListener("change", () => { p.voice.tts_voice = select.value; changed(); });
      const pace = el("select", { id: "pace-pick" }, ...["slow", "normal", "fast", "very_fast"].map((v) => el("option", { value: v, text: v.replace("_", " "), selected: v === p.voice.pace })));
      pace.addEventListener("change", () => { p.voice.pace = pace.value; changed(); });
      card.append(section("Voice", el("div", { class: "grid-2" },
        el("div", {}, el("label", { for: id, class: "small", text: "Voice" }), select),
        el("div", {}, el("label", { for: "pace-pick", class: "small", text: "Pace" }), pace))));
    } else {
      card.append(section("Voice", el("p", { text: `${p.voice.tts_voice} · ${String(p.voice.pace).replace("_", " ")} · ${p.voice.tone || ""}` })));
    }

    if (p.clues && p.clues.length) {
      card.append(section("Clues from the drawing", el("ul", { class: "clue-list" }, ...p.clues.map((c) => el("li", {}, el("strong", { text: c.saw }), " → ", c.means)))));
    }
    if ((p.training?.rules || []).length) {
      card.append(section("Trainer rules", el("ul", {}, ...p.training.rules.map((r) => el("li", { text: r })))));
    }
    container.append(card);
  }
  build();
  return { getPersona: () => clone(p) };
}
