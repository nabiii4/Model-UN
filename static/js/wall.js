// The Nightmare Wall (section 6.3). Sort is Random or Newest only: the Wall isn't a contest.
import { get } from "./api.js";
import { wallCard } from "./cards.js";
import { loadTraits } from "./persona-card.js";
import { $, el } from "./ui.js";

const grid = $("#wall-grid");
const traits = new Set();
let page = 1;
let seed = String(Math.random()).slice(2);
let timer = null;

function query() {
  const p = new URLSearchParams();
  const q = $("#q").value.trim();
  if (q) p.set("q", q);
  if ($("#difficulty").value) p.set("difficulty", $("#difficulty").value);
  if ($("#source").value) p.set("source", $("#source").value);
  if (traits.size) p.set("traits", [...traits].join(","));
  p.set("sort", $("#sort").value);
  if ($("#not-tried")?.checked) p.set("not_tried", "1");
  if ($("#befriended")?.checked) p.set("befriended", "1");
  p.set("seed", seed);
  p.set("page", String(page));
  return p.toString();
}

async function load(reset = true) {
  if (reset) { page = 1; grid.textContent = ""; }
  try {
    const res = await get(`/api/delegates?${query()}`);
    if (reset && !res.items.length) {
      grid.append(el("div", { class: "empty-wall panel" }, el("p", { class: "hand big-hand", text: res.empty_message }),
        el("a", { class: "btn primary", href: "/draw", text: "Draw one" })));
    }
    res.items.forEach((item) => grid.append(wallCard(item)));
    $("#wall-count").textContent = `${res.total} nightmare${res.total === 1 ? "" : "s"} on the Wall`;
    $("#more").hidden = res.page >= res.pages;
  } catch (e) {
    grid.textContent = "";
    grid.append(el("p", { class: "callout warn", text: e.message || "The Wall is hiding. Try again?" }));
  }
}

function drawTraitChips() {
  const box = $("#trait-chips");
  box.textContent = "";
  for (const t of traits) {
    box.append(el("span", { class: "tag" }, t.replaceAll("_", " "),
      el("button", { type: "button", "aria-label": `Remove filter ${t.replaceAll("_", " ")}`, text: "✕", on: { click: () => { traits.delete(t); drawTraitChips(); load(); } } })));
  }
}

loadTraits().then((lib) => {
  const sel = $("#trait");
  const groups = [["tactic", "Tactics"], ["temperament", "Temperament"], ["quirk", "Quirks"]];
  for (const [key, label] of groups) {
    const og = el("optgroup", { label });
    for (const t of lib.by_category?.[key] || []) og.append(el("option", { value: t.id, text: t.label }));
    sel.append(og);
  }
});
$("#trait").addEventListener("change", (e) => { if (e.target.value) { traits.add(e.target.value); e.target.value = ""; drawTraitChips(); load(); } });
$("#filters").addEventListener("change", (e) => { if (e.target.id !== "trait" && e.target.id !== "q") load(); });
$("#filters").addEventListener("submit", (e) => { e.preventDefault(); load(); });
$("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(), 300); });
$("#sort").addEventListener("change", () => { seed = String(Math.random()).slice(2); });
$("#more").addEventListener("click", () => { page += 1; load(false); });
load();
