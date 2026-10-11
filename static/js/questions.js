// The 3 optional questions (section 6.2 C). Tap chips, or "Other…" (100 characters max).
import { el } from "./ui.js";

export const QUESTIONS = [
  { key: "nervous", title: "What makes you nervous?",
    options: ["Being interrupted", "Silence", "Someone staring at me", "Fast talkers", "Big words", "Being asked for proof", "Forgetting my point", "Everyone watching", "Not knowing the rules"] },
  { key: "comfortable", title: "What would make you feel comfortable?",
    options: ["Typing first", "Short rounds", "Hints", "No timer", "Kind feedback", "A slower opponent", "Practicing alone first"] },
  { key: "try_again", title: "What would make you want to try again?",
    options: ["Seeing that I improved", "Laughing about it", "A friend trying my nightmare", "Beating it once"] },
];

export function renderQuestions(container, initial = {}) {
  const state = {};
  container.textContent = "";
  QUESTIONS.forEach((q, qi) => {
    state[q.key] = new Set(initial[q.key] || []);
    const otherId = `q-other-${q.key}`;
    const other = el("input", { type: "text", id: otherId, maxlength: "100", placeholder: "Something else? (optional)", value: initial[`${q.key}_other`] || "" });
    const chips = el("div", { class: "chips", role: "group", "aria-labelledby": `q-title-${q.key}` });
    for (const opt of q.options) {
      const pressed = state[q.key].has(opt);
      chips.append(el("button", { type: "button", class: "chip", "aria-pressed": pressed ? "true" : "false", text: opt, on: { click: (e) => {
        const b = e.currentTarget;
        const on = b.getAttribute("aria-pressed") !== "true";
        b.setAttribute("aria-pressed", on ? "true" : "false");
        if (on) state[q.key].add(opt); else state[q.key].delete(opt);
      } } }));
    }
    container.append(el("fieldset", { class: "question" },
      el("legend", { id: `q-title-${q.key}`, class: "hand q-title", text: `${qi + 1}. ${q.title}` }),
      chips,
      el("label", { for: otherId, class: "sr-only", text: `${q.title} Other answer` }),
      el("div", { class: "q-other" }, el("span", { "aria-hidden": "true", text: "Other… " }), other)));
    state[`${q.key}_input`] = other;
  });
  return {
    getAnswers() {
      const out = {};
      for (const q of QUESTIONS) {
        out[q.key] = Array.from(state[q.key]);
        out[`${q.key}_other`] = state[`${q.key}_input`].value.trim().slice(0, 100);
      }
      return out;
    },
  };
}
