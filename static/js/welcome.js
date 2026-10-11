// Welcome page: returning-member strip, the three doors, the demo round, Club Pulse, Wall preview.
import { get } from "./api.js";
import { wallCard } from "./cards.js";
import { createPuppet } from "./puppet.js";
import { typeText } from "./typewriter.js";
import { $, copy, el, pageData, sleep } from "./ui.js";

const data = pageData();

// ----- returning member -----
if (data.returning) {
  const r = data.returning;
  const box = $("#returning");
  const n = r.nightmare;
  box.append(
    el("div", { class: "grow" },
      el("h2", { class: "hand", text: copy("welcome.back", { name: r.name }) }),
      n ? el("p", {}, "Your nightmare: ", el("a", { href: `/d/${encodeURIComponent(n.id)}`, text: n.name }), ` — ${n.fear}% scary.`)
        : el("p", { text: "You haven't drawn a nightmare yet. The first thing you get is a blank sheet." })),
    el("div", { class: "btn-row" },
      r.has_last_settings ? el("a", { class: "btn primary", href: "/practice/new?quick=1", text: "Practice again" })
        : n ? el("a", { class: "btn primary", href: `/practice/new?delegate=${encodeURIComponent(n.id)}`, text: "Practice again" }) : null,
      el("a", { class: "btn", href: "/wall", text: "Pick a new nightmare" })));
  box.hidden = false;
}

// ----- Club Pulse (anonymous totals, never names) -----
get("/api/stats/club").then(({ week }) => {
  const t = $("#pulse-text");
  t.textContent = "";
  const part = (n, label) => [el("strong", { text: String(n) }), ` ${label}`];
  t.append("This week: ", ...part(week.rounds, "rounds"), " · ", ...part(week.human_rounds, "human rounds"), " · ",
    ...part(week.befriended, "nightmares befriended"), " · ", ...part(week.offday_rounds, "rounds on non-meeting days"), ".");
}).catch(() => { $("#pulse-text").textContent = "Club Pulse is taking a nap. Check back soon."; });

// ----- Wall preview: 6 random drawings -----
async function loadPreview() {
  const grid = $("#wall-preview");
  try {
    const res = await get("/api/delegates?sort=random&limit=6");
    grid.textContent = "";
    if (!res.items.length) grid.append(el("p", { text: res.empty_message }));
    res.items.forEach((item) => grid.append(wallCard(item)));
  } catch {
    grid.textContent = "The Wall is hiding. Try the Wall page.";
  }
}
loadPreview();

// ----- "Just sit": the scripted demo round (no AI calls) -----
let skipping = false;
let puppet = null;
async function playDemo() {
  const section = $("#demo");
  section.hidden = false;
  section.scrollIntoView({ behavior: "smooth", block: "start" });
  $("#demo-title").focus?.();
  skipping = false;
  const transcript = $("#demo-transcript");
  transcript.textContent = "";
  $("#demo-end").hidden = true;
  let demo;
  try { demo = await get("/api/demo-round"); } catch { transcript.textContent = "The demo got stage fright. Try again?"; return; }
  $("#demo-sub").textContent = `${demo.committee} · ${demo.topic} · You: ${demo.student_country} · ${demo.delegate.name}: ${demo.delegate_country}`;
  $("#demo-placard").textContent = demo.delegate_country;
  puppet?.destroy();
  puppet = createPuppet($("#demo-puppet"), demo.delegate.look, { quirks: demo.delegate.quirks, label: `${demo.delegate.name}'s face` });
  for (const line of demo.lines) {
    const isDelegate = line.role === "delegate";
    const textNode = el("span");
    const bubble = el("div", { class: `bubble ${isDelegate ? "delegate" : "student"}` },
      el("span", { class: "who", text: isDelegate ? `${demo.delegate.name} (${demo.delegate_country})` : `Student (${demo.student_country})` }), textNode);
    transcript.append(bubble);
    if (isDelegate) { puppet.setExpression(line.expression, line.eyebrows); puppet.talk(true); }
    await typeText(textNode, line.text, { skip: () => skipping });
    if (isDelegate) puppet.talk(false);
    if (!skipping) await sleep(500);
  }
  const end = $("#demo-end");
  end.textContent = "";
  end.append(
    el("h3", { class: "hand", text: copy("round.complete") }),
    el("div", { class: "sticky", style: { "--tilt": "-1deg", maxWidth: "520px" } },
      el("strong", { text: `${copy("feedback.strength")}: ` }), `“${demo.feedback.strength_quote}” — ${demo.feedback.strength_why}`),
    el("div", { class: "demo-handoff" },
      el("p", { class: "hand handoff-mini", text: copy("handoff.text") }),
      el("a", { class: "btn primary big", href: "/draw", text: copy("welcome.demo_ready") }),
      el("a", { class: "btn", href: "/wall", text: "Look at the Wall" })));
  end.hidden = false;
  if (!skipping) end.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
$("#door-sit").addEventListener("click", playDemo);
$("#demo-skip").addEventListener("click", () => { skipping = true; });
$("#demo-close").addEventListener("click", () => { skipping = true; $("#demo").hidden = true; puppet?.destroy(); $("#door-sit").focus(); });
