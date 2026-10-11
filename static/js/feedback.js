// Strength-first feedback (section 6.7): Your strength -> Use it to fix -> Skills -> Fear meter -> Continue.
import { get } from "./api.js";
import { $, confetti, copy, el, fearMeter, friendly, pageData, reducedMotion, sleep } from "./ui.js";

const roundId = pageData().round_id;
const root = $("#feedback-root");
const SKILL_NAMES = { clarity: "Clarity", evidence: "Evidence", answering: "Answering the question", diplomacy: "Diplomacy", listening: "Listening", perspective: "Perspective" };

function dots(n) {
  const box = el("span", { class: "score-dots", "aria-hidden": "true" });
  for (let i = 1; i <= 5; i++) box.append(el("i", { class: i <= n ? "on" : "" }));
  return box;
}

async function load() {
  let r;
  try { r = await get(`/api/rounds/${roundId}`); } catch (e) { root.textContent = friendly(e); return; }
  const fb = r.feedback;
  if (!fb) { window.location.href = `/practice/${roundId}`; return; }
  root.textContent = "";
  const maxHeat = Math.max(...(r.heat_trace || [r.heat]));
  root.append(el("h1", { text: "Your feedback" }),
    el("p", { class: "muted", text: `${r.settings.format_name} · ${r.settings.topic} · vs ${r.delegate.name}` + (maxHeat >= 4 ? ` · You pushed the heat to ${maxHeat}! 🔥` : "") }));
  if (fb.fallback) root.append(el("p", { class: "callout note", text: "The AI coach is on a break, so this is quick feedback from your round. It still counts!" }));

  root.append(el("section", { class: "panel fb-card" },
    el("h2", { class: "hand", text: `💪 ${copy("feedback.strength")}` }),
    el("blockquote", { class: "strength-quote", text: `“${fb.strength_quote}”` }),
    el("p", { text: fb.strength_why })));

  root.append(el("section", { class: "panel fb-card" },
    el("h2", { class: "hand", text: `🔧 ${copy("feedback.fix")}: ${fb.fix_focus}` }),
    el("p", { text: fb.fix_how }),
    el("div", { class: "sticky", style: { "--tilt": "-0.6deg" } }, el("strong", { text: `${copy("feedback.try")}: ` }), fb.try_next_time)));

  const skills = el("div", { class: "skills" });
  for (const [key, name] of Object.entries(SKILL_NAMES)) {
    const s = fb.scores[key];
    if (!s) continue;
    skills.append(el("div", { class: "skill" }, el("div", {}, el("strong", { text: name }), " ", el("span", { class: "score", text: `${s.score}/5` }), dots(s.score)),
      el("p", { class: "small", text: s.reason })));
  }
  root.append(el("section", { class: "panel fb-card" }, el("h2", { class: "hand", text: "📊 Skills" }),
    el("p", { class: "small muted", text: "Scores are about this round only. Hints never lower them." }), skills));

  const f = r.fear_change;
  if (f) {
    const meter = fearMeter(f.before);
    const card = el("section", { class: "panel fb-card" }, el("h2", { class: "hand", text: "😱 Fear meter" }),
      el("p", { text: `${f.name}: ${f.before}% → ${f.after}% scary` }), meter);
    root.append(card);
    await sleep(reducedMotion() ? 0 : 400);
    meter.setValue(f.after);
    if (f.befriended) {
      const next = el("div", { class: "befriend" }, el("p", { class: "hand", text: `🤝 ${f.message || copy("befriended", { name: f.name })}` }),
        el("p", { text: copy("next_nightmare") }),
        el("div", { class: "btn-row", style: { justifyContent: "center" } },
          ...(f.next_nightmares || []).map((n) => el("a", { class: "btn", href: n.url, text: `Next: ${n.name}` })),
          el("a", { class: "btn", href: "/blank", text: "Build one in The Blank" })));
      card.append(next);
      if (f.newly_befriended) confetti();
    }
  } else if (!pageData().logged_in) {
    root.append(el("p", { class: "callout note", text: "Join the club to track your fear meter and see your growth." }));
  }

  const cont = el("a", { class: "btn primary big", href: `/human?round=${encodeURIComponent(roundId)}`, text: "Continue" });
  root.append(el("p", { class: "center hand", text: fb.encouragement }), el("div", { class: "btn-row continue-row" }, cont));
  cont.focus({ preventScroll: true });
}
load();
