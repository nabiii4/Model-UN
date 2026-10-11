// My Journey (section 6.10, basic version): stage, Strength Journal, my nightmares, past rounds,
// comfort settings, my suggestions, and my data.
import { del, get, patch } from "./api.js";
import { $, el, fearMeter, friendly, modal, toast } from "./ui.js";

const STAGES = [["pockets", "🫥", "Pockets", "You joined. Welcome!"], ["keyboard", "⌨️", "Keyboard", "You finished a typed round."], ["microphone", "🎤", "Microphone", "You spoke out loud or did a human round."]];
const COMFORT = [
  ["gentle", "Gentle mode (difficulty never above 2, never cut off)", "bool"],
  ["timers", "Speech timers", "bool"],
  ["auto_hints", "Hints switched on", "bool"],
  ["dramatic_silence", "Dramatic silence before replies", "bool"],
  ["interruptions", "Interruptions (Phase 2)", "bool"],
  ["camera_off", "Camera off by default", "bool"],
  ["ai_voice", "AI voice (Phase 2)", "bool"],
  ["reduced_motion", "Reduce motion", "bool"],
  ["readable_font", "Readable font everywhere", "bool"],
  ["default_mode", "Default mode", [["type", "⌨️ Type"], ["speak", "🎤 Speak (Phase 2)"]]],
  ["default_length", "Default round length", [["quick", "Quick"], ["standard", "Standard"], ["timed", "Timed (4 min)"]]],
  ["text_size", "Text size", [["100", "100%"], ["115", "115%"], ["130", "130%"]]],
];

async function load() {
  let me;
  try { me = await get("/api/me"); } catch (e) { toast(friendly(e), { error: true }); return; }
  const stageIdx = STAGES.findIndex((s) => s[0] === me.member.stage);
  const path = $("#stage-path");
  STAGES.forEach(([key, icon, name, desc], i) => path.append(el("li", { class: `${i <= stageIdx ? "reached" : ""} ${i === stageIdx ? "current" : ""}`, "aria-current": i === stageIdx ? "step" : null },
    el("span", { class: "icon", "aria-hidden": "true", text: icon }), el("strong", { text: name }), el("div", { class: "small", text: desc }))));
  $("#show-up").textContent = `You showed up on ${me.member.show_up_days} day${me.member.show_up_days === 1 ? "" : "s"} · ${me.human_rounds} human round${me.human_rounds === 1 ? "" : "s"}. (Not a streak — it can't break.)`;

  const sj = $("#strengths");
  if (!me.strengths.length) sj.append(el("p", { class: "muted", text: "Finish a round and your first strength lands here." }));
  me.strengths.forEach((s, i) => sj.append(el("div", { class: "sticky", style: { "--tilt": `${i % 2 ? 0.6 : -0.6}deg` } }, `“${s.text}”`, el("div", { class: "small", text: s.date }))));

  const nm = $("#nightmares");
  if (!me.nightmares.length) nm.append(el("p", {}, "No nightmares yet. ", el("a", { href: "/draw", text: "Draw your first one" }), "."));
  else nm.append(el("ul", { class: "row-list" }, ...me.nightmares.map((n) => el("li", {}, el("a", { href: `/d/${encodeURIComponent(n.id)}`, text: n.name }),
    el("span", { class: "small muted", text: `${n.visibility === "private" ? "🔒 private" : "on the Wall"}${n.status !== "active" ? ` · ${n.status}` : ""}` })))));
  const fears = $("#fears");
  if (!me.fear.length) fears.append(el("p", { class: "muted small", text: "Practice against a nightmare to start its fear meter." }));
  me.fear.forEach((f) => fears.append(el("div", { class: "field" }, el("a", { href: `/d/${encodeURIComponent(f.delegate_id)}`, text: f.befriended ? `🤝 ${f.name}` : f.name }), fearMeter(f.value))));

  const rounds = $("#rounds");
  if (!me.rounds.length) rounds.append(el("p", { class: "muted", text: "No finished rounds yet." }));
  else rounds.append(el("ul", { class: "row-list" }, ...me.rounds.map((r) => el("li", {},
    el("span", {}, el("strong", { text: r.delegate }), ` · ${r.format || ""} · ${r.topic || ""}`), el("span", { class: "small muted", text: r.date }),
    el("a", { class: "btn small", href: `/practice/${encodeURIComponent(r.id)}/feedback`, text: "Feedback" })))));

  const form = $("#comfort-form");
  for (const [key, label, kind] of COMFORT) {
    const id = `c-${key}`;
    if (kind === "bool") {
      const box = el("input", { type: "checkbox", id, checked: !!me.member.comfort[key] });
      box.addEventListener("change", () => saveComfort({ [key]: box.checked }));
      form.append(el("label", { class: "check", for: id }, box, label));
    } else {
      const sel = el("select", { id }, ...kind.map(([v, t]) => el("option", { value: v, text: t, selected: String(me.member.comfort[key]) === v })));
      sel.addEventListener("change", () => saveComfort({ [key]: key === "text_size" ? Number(sel.value) : sel.value }));
      form.append(el("div", { class: "field" }, el("label", { for: id, text: label }), sel));
    }
  }

  const sugg = $("#suggestions");
  const STATUS = { new: "Sent", planned: "Planned!", done: "Done ✅", wont_do: "Not this time" };
  if (!me.suggestions.length) sugg.append(el("p", { class: "muted" }, "Nothing yet. See something confusing? Use “Suggest a change.”"));
  else sugg.append(el("ul", { class: "row-list" }, ...me.suggestions.map((s) => el("li", {}, el("span", { text: s.what }),
    el("strong", { text: STATUS[s.status] || s.status }), s.reply ? el("div", { class: "small muted", text: `Reply: ${s.reply}` }) : null))));
}

async function saveComfort(change) {
  try {
    const res = await patch("/api/me/comfort", change);
    const c = res.comfort;
    const root = document.documentElement;
    root.dataset.text = String(c.text_size);
    root.dataset.readable = c.readable_font ? "1" : "0";
    root.dataset.motion = c.reduced_motion ? "reduce" : "auto";
    $("#comfort-status").textContent = "Saved.";
  } catch (e) { toast(friendly(e), { error: true }); }
}

$("#delete-me").addEventListener("click", async () => {
  const anon = el("input", { type: "radio", name: "pub", value: "anonymize", id: "pub-anon", checked: true });
  const delAll = el("input", { type: "radio", name: "pub", value: "delete", id: "pub-del" });
  const ok = await modal({
    title: "Delete my data?",
    body: el("div", {}, el("p", { text: "This removes your account, rounds, strengths, and private nightmares. It can't be undone." }),
      el("fieldset", {}, el("legend", { text: "What about my nightmares on the Wall?" }),
        el("label", { class: "check", for: "pub-anon" }, anon, "Keep them, but make them anonymous"),
        el("label", { class: "check", for: "pub-del" }, delAll, "Delete them too"))),
    actions: [{ label: "Cancel", value: false }, { label: "Delete my data", danger: true, value: true }],
    dismissValue: false,
  });
  if (!ok) return;
  try {
    await del("/api/me", { public_delegates: delAll.checked ? "delete" : "anonymize" });
    window.location.href = "/";
  } catch (e) { toast(friendly(e), { error: true }); }
});

load();
