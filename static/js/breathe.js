// "Take a breath": 4-4-4-4 box breathing, two cycles (about 32 seconds), with Skip (section 6.6).
import { el, reducedMotion, sleep } from "./ui.js";

export function takeABreath() {
  return new Promise((resolve) => {
    const previous = document.activeElement;
    const square = el("div", { class: "breath-square" });
    const word = el("p", { class: "breath-word", "aria-live": "polite" });
    const count = el("p", { class: "muted" });
    let stopped = false;
    const done = () => { if (stopped) return; stopped = true; overlay.remove(); previous?.focus?.(); resolve(); };
    const skip = el("button", { class: "btn", type: "button", text: "Skip", on: { click: done } });
    const overlay = el("div", { class: "breath-overlay", role: "dialog", "aria-modal": "true", "aria-label": "Take a breath" },
      el("h2", { class: "hand", text: "Take a breath" }),
      el("div", { class: "breath-box" }, square), word, count, skip);
    overlay.addEventListener("keydown", (e) => { if (e.key === "Escape") done(); });
    document.body.append(overlay);
    skip.focus();
    (async () => {
      const phases = [["Breathe in", true], ["Hold", true], ["Breathe out", false], ["Hold", false]];
      for (let cycle = 1; cycle <= 2 && !stopped; cycle++) {
        count.textContent = `Round ${cycle} of 2`;
        for (const [label, big] of phases) {
          if (stopped) return;
          word.textContent = label;
          square.classList.toggle("big", big);
          for (let s = 4; s >= 1 && !stopped; s--) {
            if (reducedMotion()) word.textContent = `${label}… ${s}`;
            await sleep(1000);
          }
        }
      }
      if (!stopped) { word.textContent = "Nice. You're ready."; await sleep(1200); done(); }
    })();
  });
}
