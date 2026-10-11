// A delegate's page (section 6.4): the drawing, the persona card, the story, how to beat it.
import { del, get, patch } from "./api.js";
import { reportDelegate } from "./cards.js";
import { renderPersonaCard } from "./persona-card.js";
import { createPuppet } from "./puppet.js";
import { $, confirmDialog, el, fearMeter, friendly, pageData, pips, setBusy, toast } from "./ui.js";

const id = pageData().delegate_id;
const root = $("#delegate-root");

async function load() {
  let d;
  try {
    d = await get(`/api/delegates/${encodeURIComponent(id)}`);
  } catch (e) {
    root.textContent = "";
    root.append(el("div", { class: "panel" }, el("h1", { text: "Nightmare not found" }), el("p", { text: friendly(e) }),
      el("a", { class: "btn primary", href: "/wall", text: "Back to the Wall" })));
    return;
  }
  document.title = `${d.name} · Nightmare Delegate`;
  render(d);
}

function render(d) {
  root.textContent = "";
  const p = d.persona;
  const pic = el("div", { class: "drawing-frame big-drawing" });
  if (d.image_url) pic.append(el("img", { src: d.image_url, alt: p.alt_text || d.name }));
  else { const pp = el("div", { class: "puppet" }); pic.append(pp); createPuppet(pp, p.look, { quirks: p.quirks, label: p.alt_text || d.name }); }

  const badges = el("p", { class: "muted small" },
    d.is_example ? "Example — replace with your club's real drawings · " : "",
    `By ${d.credit} · `, `Trained ${d.trained_count} time${d.trained_count === 1 ? "" : "s"} · v${d.version}`,
    d.visibility === "private" ? " · 🔒 Private" : "", d.status !== "active" ? ` · Status: ${d.status}` : "");

  const actions = el("div", { class: "btn-row" },
    el("a", { class: "btn primary big", href: d.opens_blank ? "/blank" : `/practice/new?delegate=${encodeURIComponent(d.id)}`, text: d.opens_blank ? "Build it in The Blank" : "Practice" }),
    d.can_edit ? el("a", { class: "btn", href: `/d/${encodeURIComponent(d.id)}/train`, text: "Train" }) : null,
    d.can_edit ? el("button", { class: "btn", type: "button", text: "Edit", on: { click: () => editMode(d) } }) : null,
    !d.can_edit ? el("button", { class: "btn", type: "button", text: "Suggest a change to this nightmare",
      on: { click: () => window.ndSuggest && window.ndSuggest({ title: `Suggest a change to ${d.name}`, delegate_id: d.id, page: `/d/${d.id}`,
        intro: "Your idea goes to the person who drew it." }) } }) : null,
    el("button", { class: "btn ghost", type: "button", text: "⚑ Report", on: { click: async () => { if (await reportDelegate(d.id, d.name)) window.location.href = "/wall"; } } }));

  const cardBox = el("div", { class: "panel" });
  const right = el("div", { class: "meet-right" },
    el("h1", { text: d.name }), p.nickname ? el("p", { class: "hand nick-big", text: `“${p.nickname}”` }) : null,
    el("div", {}, pips(p.base_difficulty), ` Difficulty ${p.base_difficulty}/5`), badges, actions);

  if (d.fear) {
    const fm = fearMeter(d.fear.value);
    right.append(el("section", { class: "panel fear-panel" }, el("h2", { class: "hand", text: "My fear meter" }), fm,
      d.fear.befriended ? el("p", { class: "callout", text: `🤝 You befriended ${d.name}. It's officially not scary anymore.` }) : null));
  }
  if (d.story) right.append(el("section", { class: "sticky story", style: { "--tilt": "1deg" } }, el("strong", { text: "Why this is a nightmare: " }), d.story));

  const beat = el("section", { class: "panel" }, el("h2", { class: "hand", text: "How to beat it" }),
    el("p", { text: p.weakness.description }), el("ul", {}, ...p.weakness.how_to_beat.map((h) => el("li", { text: h }))));
  if (d.tips.length) {
    beat.append(el("div", { class: "tips" }, ...d.tips.map((t, i) => el("div", { class: "sticky", style: { "--tilt": `${i % 2 ? 1.5 : -1.5}deg` } }, t.text, el("div", { class: "small", text: `— ${t.credit}` })))));
  } else {
    beat.append(el("p", { class: "muted small", text: "Member tips (sticky notes) arrive in Phase 2." }));
  }
  right.append(beat);
  right.append(el("h2", { class: "hand", text: "The persona" }), cardBox);
  renderPersonaCard(cardBox, p, { editable: false, showTitle: false, showWeakness: false });

  if (d.suggestions && d.suggestions.length) {
    right.append(el("section", { class: "panel" }, el("h2", { class: "hand", text: "Ideas from others" }),
      el("ul", {}, ...d.suggestions.map((s) => el("li", {}, el("strong", { text: `${s.from}: ` }), s.what, s.should ? ` → ${s.should}` : "")))));
  }
  if (d.is_owner || d.can_delete) {
    const owner = el("section", { class: "panel" }, el("h2", { class: "hand", text: "Owner tools" }));
    if (d.can_edit && !d.is_example) {
      owner.append(el("button", { class: "btn", type: "button", text: d.visibility === "public" ? "Make it private" : "Put it on the Wall", on: { click: async (e) => {
        setBusy(e.currentTarget, true);
        try { await patch(`/api/delegates/${encodeURIComponent(d.id)}`, { visibility: d.visibility === "public" ? "private" : "public" }); toast("Saved."); load(); }
        catch (err) { toast(friendly(err), { error: true }); setBusy(e.currentTarget, false); }
      } } }));
    }
    if (d.can_delete) {
      owner.append(" ", el("button", { class: "btn danger", type: "button", text: "Delete", on: { click: async () => {
        if (!(await confirmDialog(`Delete ${d.name}? This can't be undone.`, { title: "Delete this nightmare?", ok: "Delete", danger: true }))) return;
        try { await del(`/api/delegates/${encodeURIComponent(d.id)}`); toast("Deleted."); window.location.href = "/wall"; }
        catch (err) { toast(friendly(err), { error: true }); }
      } } }));
    }
    right.append(owner);
  }
  root.append(el("div", { class: "meet-grid" }, el("div", { class: "meet-left" }, pic), right));
}

async function editMode(d) {
  root.textContent = "";
  const box = el("div", { class: "panel" });
  const story = el("textarea", { id: "edit-story", maxlength: "280", rows: "3" });
  story.value = d.story || "";
  const saveBtn = el("button", { class: "btn primary big", type: "button", text: "Save changes" });
  root.append(el("h1", { text: `Edit ${d.name}` }), el("p", { class: "muted", text: "Every save makes a new version, so you can always go back." }), box,
    el("div", { class: "panel" }, el("label", { for: "edit-story", text: "The story (optional)" }), story),
    el("div", { class: "btn-row step-nav" }, saveBtn, el("button", { class: "btn", type: "button", text: "Cancel", on: { click: () => render(d) } })));
  const card = await renderPersonaCard(box, d.persona, { editable: true });
  saveBtn.addEventListener("click", async () => {
    setBusy(saveBtn, true, "Saving…");
    try {
      const res = await patch(`/api/delegates/${encodeURIComponent(d.id)}`, { persona: card.getPersona(), story: story.value, summary: "Edited on its page" });
      toast(`Saved as v${res.delegate.version}.`);
      render(res.delegate);
    } catch (e) { toast(friendly(e), { error: true }); setBusy(saveBtn, false); }
  });
}

load();
