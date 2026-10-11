// Runs on every page: Night mode, log out, "Suggest a change", keyboard shortcut help, feature health.
import { get, post } from "./api.js";
import { $, $$, copy, el, friendly, lsGet, lsRemove, lsSet, modal, pageData, toast } from "./ui.js";

// ----- Night mode (respects the system setting until you choose) -----
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "dark" || theme === "light") root.dataset.theme = theme;
  else delete root.dataset.theme;
  const btn = $("#theme-btn");
  if (btn) {
    const dark = theme === "dark" || (!theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
    btn.title = dark ? "Turn off Night mode" : "Night mode";
  }
}
applyTheme(lsGet("nd-theme"));
$("#theme-btn")?.addEventListener("click", () => {
  const root = document.documentElement;
  const isDark = root.dataset.theme === "dark" || (!root.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const next = isDark ? "light" : "dark";
  lsSet("nd-theme", next);
  applyTheme(next);
});

// ----- Log out (shared Chromebooks: also clears any in-progress drawing) -----
$("#logout-btn")?.addEventListener("click", async () => {
  try { await post("/api/auth/logout", {}); } catch { /* go home anyway */ }
  lsRemove("nd-drawing");
  lsRemove("nd-draft");
  window.location.href = "/";
});

// ----- Feature health: read once per page load; pages hide features that are off. -----
window.ndHealth = get("/api/health").catch(() => ({ mock: false, features: {} }));

// ----- Suggest a change (floating button on every page) -----
async function openSuggest(extra = {}) {
  const loggedIn = !!pageData().logged_in;
  const kindIdea = el("input", { type: "radio", name: "kind", value: "idea", checked: true, id: "k-idea" });
  const kindBug = el("input", { type: "radio", name: "kind", value: "bug", id: "k-bug" });
  const what = el("textarea", { id: "s-what", maxlength: "1000", rows: "3" });
  const should = el("textarea", { id: "s-should", maxlength: "1000", rows: "3" });
  const anon = el("input", { type: "checkbox", id: "s-anon" });
  const credit = el("input", { type: "checkbox", id: "s-credit" });
  const err = el("p", { class: "error-text", role: "alert" });
  const body = el("div", {},
    extra.intro ? el("p", { text: extra.intro }) : null,
    el("fieldset", {}, el("legend", { text: "Is it an idea or a bug?" }),
      el("label", { class: "check", for: "k-idea" }, kindIdea, "💡 An idea"),
      el("label", { class: "check", for: "k-bug" }, kindBug, "🐛 Something broke")),
    el("div", { class: "field" }, el("label", { for: "s-what", text: "What happened?" }), what),
    el("div", { class: "field" }, el("label", { for: "s-should", text: "What should happen?" }), should),
    el("p", { class: "small muted", text: `Page: ${extra.page || window.location.pathname}` }),
    loggedIn ? el("label", { class: "check", for: "s-anon" }, anon, "Send it anonymously") : el("p", { class: "small muted", text: "You're not logged in, so this is anonymous." }),
    loggedIn ? el("label", { class: "check", for: "s-credit" }, credit, "List me in Credits as someone who helped fix the website") : null,
    err);
  await modal({
    title: extra.title || "Suggest a change",
    body,
    actions: [
      { label: "Cancel", value: false },
      { label: "Send", primary: true, value: true, onClick: async () => {
        err.textContent = "";
        if (what.value.trim().length < 2 && should.value.trim().length < 2) { err.textContent = "Write a few words first."; return false; }
        try {
          const res = await post("/api/requests", {
            kind: kindBug.checked ? "bug" : "idea", what_happened: what.value, what_should_happen: should.value,
            page: extra.page || window.location.pathname, credit: anon.checked ? "anonymous" : "name",
            credit_opt_in: credit.checked, delegate_id: extra.delegate_id || null,
          });
          toast(res.message || copy("suggest.thanks"));
          return true;
        } catch (e) { err.textContent = friendly(e); return false; }
      } },
    ],
  });
}
window.ndSuggest = openSuggest;
$$("[data-suggest]").forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); openSuggest(); }));

// ----- Keyboard shortcuts help -----
function shortcutsHelp() {
  const rows = [["Ctrl + Enter", "Send your answer"], ["H", "Hint (in a round)"], ["B", "Take a breath"], ["E", "End the round"],
    ["Space (hold)", "Talk, when the mic button is focused (coming in Phase 2)"], ["Tab / Shift + Tab", "Move around the page"], ["Esc", "Close a pop-up"]];
  const list = el("dl", { style: { display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 14px" } });
  for (const [k, v] of rows) list.append(el("dt", {}, el("kbd", { text: k })), el("dd", { style: { margin: 0 }, text: v }));
  modal({ title: "Keyboard shortcuts", body: el("div", {}, el("p", { class: "muted", text: "Everything also works with the mouse or touch." }), list) });
}
$("#shortcuts-btn")?.addEventListener("click", shortcutsHelp);
document.addEventListener("keydown", (e) => {
  const t = e.target;
  const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  if (!typing && e.key === "?" && !document.querySelector(".modal")) { e.preventDefault(); shortcutsHelp(); }
});
