// Types text into a node one character at a time (instant with reduced motion).
import { reducedMotion, sleep } from "./ui.js";

export async function typeText(node, text, { cps = 45, skip = () => false } = {}) {
  node.textContent = "";
  if (reducedMotion()) { node.textContent = text; return; }
  node.classList.add("caret");
  const delay = 1000 / cps;
  for (let i = 0; i < text.length; i++) {
    if (skip()) { node.textContent = text; break; }
    node.textContent = text.slice(0, i + 1);
    await sleep(text[i] === "." || text[i] === "?" || text[i] === "!" ? delay * 6 : delay);
  }
  node.classList.remove("caret");
}
