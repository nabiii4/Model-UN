// The taped paper card used on the Wall and the Welcome page (section 6.3).
import { post } from "./api.js";
import { createPuppet } from "./puppet.js";
import { el, friendly, modal, pips, toast } from "./ui.js";

export function reportDelegate(id, name) {
  const reason = el("textarea", { id: "report-reason", maxlength: "300", rows: "3" });
  return modal({
    title: `Report “${name}”?`,
    body: el("div", {}, el("p", { text: "It will be hidden from the Wall until an editor looks at it." }),
      el("label", { for: "report-reason", text: "What's wrong? (optional)" }), reason),
    actions: [{ label: "Cancel", value: false }, { label: "Report", primary: true, value: true, onClick: async () => {
      try { const r = await post(`/api/delegates/${encodeURIComponent(id)}/report`, { reason: reason.value }); toast(r.message); return true; }
      catch (e) { toast(friendly(e), { error: true }); return false; }
    } }],
  });
}

export function practiceUrl(item) {
  return item.opens_blank ? "/blank" : `/practice/new?delegate=${encodeURIComponent(item.id)}`;
}

export function wallCard(item, { onRemoved } = {}) {
  const pic = el("div", { class: "card-pic" });
  if (item.image_url) {
    pic.append(el("img", { src: item.image_url, alt: item.alt_text || item.name, loading: "lazy", width: "300", height: "300" }));
  } else {
    const p = el("div", { class: "puppet" });
    pic.append(p);
    createPuppet(p, item.look, { label: item.alt_text || item.name });
  }
  const card = el("article", { class: "taped wall-card", style: { "--tilt": `${item.rotation || 0}deg` }, "aria-label": item.name },
    item.is_example ? el("span", { class: "example-ribbon", text: "Example" }) : null,
    el("a", { href: `/d/${encodeURIComponent(item.id)}`, class: "card-link", "aria-label": `Open ${item.name}` }, pic),
    el("h3", { class: "card-name" }, el("a", { href: `/d/${encodeURIComponent(item.id)}`, text: item.name })),
    el("div", { class: "card-meta" }, pips(item.difficulty), item.befriended ? el("span", { class: "tag", text: "🤝 Befriended" }) : null),
    el("div", {}, ...(item.tags || []).map((t) => el("span", { class: "tag", text: t }))),
    el("p", { class: "small muted card-credit", text: `By ${item.credit}` }),
    el("div", { class: "btn-row card-actions" },
      el("a", { class: "btn small primary", href: practiceUrl(item), text: item.opens_blank ? "Build it" : "Practice" }),
      el("button", { class: "icon-btn", type: "button", "aria-label": `Report ${item.name}`, title: "Report",
        text: "⚑", on: { click: async () => { const done = await reportDelegate(item.id, item.name); if (done) { card.remove(); onRemoved && onRemoved(); } } } })));
  return card;
}
