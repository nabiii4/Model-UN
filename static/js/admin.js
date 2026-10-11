// Admin + maintainer dashboard (section 6.18, basic version).
import { del, get, patch, post } from "./api.js";
import { $, confirmDialog, el, friendly, pageData, setBusy, svg, toast } from "./ui.js";

const page = pageData();
const role = page.role;
const isEditor = role === "editor" || role === "maintainer";
const isMaintainer = role === "maintainer";
const panel = $("#admin-panel");

// ---------------------------------------------------------------- passcode
if (!isMaintainer) {
  $("#passcode-box").hidden = false;
  if (!page.passcode_set) $("#passcode-error").textContent = "The admin passcode isn't set yet. Add ADMIN_PASSCODE to .env and restart the app.";
}
$("#passcode-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#passcode-error").textContent = "";
  try { await post("/api/admin/login", { passcode: $("#passcode").value }); window.location.reload(); }
  catch (err) { $("#passcode-error").textContent = friendly(err); }
});

// ---------------------------------------------------------------- tabs
const TABS = [
  ["moderation", "Moderation", isEditor, moderation],
  ["requests", "Requests", isEditor, requestsTab],
  ["members", "Members", isEditor, members],
  ["copy", "Site text", isEditor, copyTab],
  ["committees", "Committees & topics", isEditor, committees],
  ["ai", "AI status", isEditor, aiStatus],
  ["usage", "Usage", isEditor, usage],
  ["settings", "Settings", isMaintainer, settingsTab],
  ["audit", "Audit log", isMaintainer, audit],
  ["backups", "Backups & handoff", isMaintainer, backups],
];
if (isEditor) {
  $("#admin-app").hidden = false;
  const bar = $("#admin-tabs");
  const visible = TABS.filter((t) => t[2]);
  visible.forEach(([id, label, , fn], i) => {
    const b = el("button", { class: "tab", role: "tab", id: `tab-${id}`, "aria-selected": "false", "aria-controls": "admin-panel", text: label,
      on: { click: () => open(id) } });
    b.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      e.preventDefault();
      const n = (i + (e.key === "ArrowRight" ? 1 : -1) + visible.length) % visible.length;
      $(`#tab-${visible[n][0]}`).focus();
      open(visible[n][0]);
    });
    bar.append(b);
  });
  open(location.hash.slice(1) && visible.some((t) => t[0] === location.hash.slice(1)) ? location.hash.slice(1) : visible[0][0]);
}

async function open(id) {
  document.querySelectorAll("#admin-tabs .tab").forEach((t) => t.setAttribute("aria-selected", String(t.id === `tab-${id}`)));
  panel.setAttribute("aria-labelledby", `tab-${id}`);
  history.replaceState(null, "", `#${id}`);
  panel.textContent = "Loading…";
  const tab = TABS.find((t) => t[0] === id);
  try { await tab[3](); } catch (e) { panel.textContent = ""; panel.append(el("p", { class: "callout warn", text: friendly(e) })); }
}

function table(headers, rows) {
  return el("div", { class: "table-wrap" }, el("table", { class: "admin-table" },
    el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", { scope: "col", text: h })))),
    el("tbody", {}, ...rows.map((r) => el("tr", {}, ...r.map((c) => el("td", {}, c ?? "")))))));
}

// ---------------------------------------------------------------- moderation
async function moderation() {
  const res = await get("/api/admin/moderation");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Moderation queue" }),
    el("p", { class: "muted", text: "Reported or waiting-for-approval items. Approve puts them back on the Wall. Hide keeps them off. Delete removes them." }));
  if (!res.items.length) { panel.append(el("p", { text: "Nothing waiting. 🎉" })); return; }
  for (const it of res.items) {
    const act = (action) => async () => {
      if (action === "delete" && !(await confirmDialog(`Delete “${it.name}” for good?`, { danger: true, ok: "Delete" }))) return;
      try { await patch(`/api/admin/moderation/${it.type}/${encodeURIComponent(it.id)}`, { action }); toast("Done."); moderation(); }
      catch (e) { toast(friendly(e), { error: true }); }
    };
    panel.append(el("div", { class: "mod-item" },
      it.image_url ? el("img", { src: it.image_url, alt: it.name }) : el("div"),
      el("div", {}, el("strong", { text: `${it.type === "delegate" ? "Nightmare" : "Tip"}: ${it.name}` }), el("span", { class: "tag", text: it.status }),
        it.one_liner ? el("p", { text: it.one_liner }) : null, it.story ? el("p", { class: "small", text: `Story: ${it.story}` }) : null,
        it.reports.length ? el("p", { class: "small" }, el("strong", { text: "Reports: " }), it.reports.join(" · ")) : null,
        it.type === "delegate" ? el("a", { href: `/d/${encodeURIComponent(it.id)}`, text: "Open" }) : null),
      el("div", { class: "btn-row" },
        el("button", { class: "btn small primary", type: "button", text: "Approve", on: { click: act("approve") } }),
        el("button", { class: "btn small", type: "button", text: "Hide", on: { click: act("hide") } }),
        el("button", { class: "btn small danger", type: "button", text: "Delete", on: { click: act("delete") } }))));
  }
}

// ---------------------------------------------------------------- requests
async function requestsTab() {
  const res = await get("/api/requests");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Suggest-a-change requests" }));
  if (!res.requests.length) { panel.append(el("p", { text: "No requests yet." })); return; }
  const STATUSES = [["new", "New"], ["planned", "Planned"], ["done", "Done"], ["wont_do", "Won't do"]];
  panel.append(table(["When", "Kind", "What happened", "What should happen", "Page", "From", "Status / reply"], res.requests.map((r) => {
    const sel = el("select", { "aria-label": "Status" }, ...STATUSES.map(([v, t]) => el("option", { value: v, text: t, selected: v === r.status })));
    const reply = el("input", { type: "text", maxlength: "500", placeholder: "Reply (optional)", "aria-label": "Reply", value: r.reply || "" });
    const save = el("button", { class: "btn small", type: "button", text: "Save", on: { click: async () => {
      try { await patch(`/api/requests/${r.id}`, { status: sel.value, reply: reply.value }); toast("Saved."); } catch (e) { toast(friendly(e), { error: true }); }
    } } });
    return [r.date.slice(0, 10), r.kind, r.what_happened, r.what_should_happen, r.delegate_id ? el("a", { href: `/d/${r.delegate_id}`, text: "a nightmare" }) : r.page, r.from, el("div", {}, sel, reply, save)];
  })));
}

// ---------------------------------------------------------------- members
async function members() {
  const res = await get("/api/admin/members");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Members" }), el("p", { class: "muted", text: "Editors can reset PINs. Maintainers can change roles." }));
  panel.append(table(["Name", "Role", "Stage", "Joined", "Actions"], res.members.map((m) => {
    const actions = el("div", { class: "btn-row" });
    actions.append(el("button", { class: "btn small", type: "button", text: "Reset PIN", on: { click: async () => {
      const pin = String(Math.floor(1000 + Math.random() * 9000));
      if (!(await confirmDialog(`Reset ${m.name}'s PIN to ${pin}? Tell them the new PIN in person.`, { ok: "Reset" }))) return;
      try { await patch(`/api/admin/members/${m.id}`, { pin }); toast(`New PIN for ${m.name}: ${pin}`, { ms: 12000 }); } catch (e) { toast(friendly(e), { error: true }); }
    } } }));
    let roleCell = m.role;
    if (isMaintainer) {
      const sel = el("select", { "aria-label": `Role for ${m.name}` }, ...["member", "editor", "maintainer"].map((r) => el("option", { value: r, text: r, selected: r === m.role })));
      sel.addEventListener("change", async () => {
        try { await patch(`/api/admin/members/${m.id}`, { role: sel.value }); toast("Role saved."); } catch (e) { toast(friendly(e), { error: true }); sel.value = m.role; }
      });
      roleCell = sel;
      actions.append(el("button", { class: "btn small danger", type: "button", text: "Remove", on: { click: async () => {
        if (!(await confirmDialog(`Remove ${m.name} and their data? Their public nightmares stay, anonymously.`, { danger: true, ok: "Remove" }))) return;
        try { await del(`/api/admin/members/${m.id}`, { public_delegates: "anonymize" }); toast("Removed."); members(); } catch (e) { toast(friendly(e), { error: true }); }
      } } }));
    }
    return [m.name, roleCell, m.stage, m.joined, actions];
  })));
}

// ---------------------------------------------------------------- site text
async function copyTab() {
  const res = await get("/api/admin/copy");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Site text" }), el("p", { class: "muted", text: "Change any line. Leave it the same (or empty) to use the original. {n} and {name} are filled in automatically." }));
  const inputs = {};
  for (const [key, def] of Object.entries(res.defaults)) {
    const id = `copy-${key}`;
    const input = el("textarea", { id, rows: def.length > 80 ? "2" : "1", maxlength: "400" });
    input.value = res.overrides[key] || def;
    inputs[key] = input;
    panel.append(el("div", { class: "copy-row" }, el("label", { for: id }, el("code", { text: key })), input));
  }
  const btn = el("button", { class: "btn primary", type: "button", text: "Save site text" });
  btn.addEventListener("click", async () => {
    setBusy(btn, true, "Saving…");
    const overrides = {};
    for (const [k, i] of Object.entries(inputs)) overrides[k] = i.value;
    try { const r = await patch("/api/admin/copy", { overrides }); toast(`Saved ${r.changed.length} change(s).`); } catch (e) { toast(friendly(e), { error: true }); }
    setBusy(btn, false);
  });
  panel.append(btn);
}

// ---------------------------------------------------------------- committees
async function committees() {
  const res = await get("/api/admin/committees");
  let list = res.committees;
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Committees & topics" }));
  const box = el("div");
  const draw = () => {
    box.textContent = "";
    list.forEach((c, i) => {
      const name = el("input", { type: "text", value: c.name, maxlength: "80", "aria-label": "Committee name" });
      name.addEventListener("input", () => { c.name = name.value; });
      const topics = el("textarea", { rows: "3", "aria-label": `Topics for ${c.name}, one per line` });
      topics.value = c.topics.join("\n");
      topics.addEventListener("input", () => { c.topics = topics.value.split("\n").map((t) => t.trim()).filter(Boolean); });
      box.append(el("div", { class: "committee-block" }, el("label", { text: "Committee" }), name, el("label", { text: "Topics (one per line)" }), topics,
        el("button", { class: "btn small danger", type: "button", text: "Remove committee", on: { click: () => { list.splice(i, 1); draw(); } } })));
    });
  };
  draw();
  panel.append(box, el("div", { class: "btn-row" },
    el("button", { class: "btn", type: "button", text: "+ Add committee", on: { click: () => { list.push({ name: "New committee", topics: [] }); draw(); } } }),
    el("button", { class: "btn primary", type: "button", text: "Save", on: { click: async () => {
      try { const r = await patch("/api/admin/committees", { committees: list }); list = r.committees; draw(); toast("Saved."); } catch (e) { toast(friendly(e), { error: true }); }
    } } })));
}

// ---------------------------------------------------------------- AI status
async function aiStatus() {
  const s = await get("/api/admin/ai-status");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "AI status" }),
    s.mock ? el("p", { class: "callout note", text: `Demo mode: the AI is pretend (${s.mock_reason}). Add real keys to .env, set MOCK_AI=0, and restart to use the real AI.` }) : null,
    el("p", { text: `AI calls today: ${s.calls_today_db} of ${s.cap} · Failovers today: ${s.failovers_today}` }),
    table(["Feature", "Resource", "Status", "Last check", "Last error"], s.rows.map((r) => [r.feature, r.resource,
      el("span", { class: /ok|mock/.test(r.status) ? "status-ok" : /error|rejected|404/.test(r.status) ? "status-bad" : "", text: r.status }), r.last_check || "—", r.last_error || "—"])),
    el("p", { class: "small muted", text: "Keys, endpoints, and deployment names are never shown here." }));
  if (isMaintainer) {
    const row = el("div", { class: "btn-row" });
    for (const f of ["chat", "vision"]) {
      row.append(el("button", { class: "btn", type: "button", text: `Test ${f} now`, on: { click: async (e) => {
        setBusy(e.currentTarget, true, "Testing…");
        try { const r = await post(`/api/admin/ai-test/${f}`, {}); toast(r.message || `${f}: ${r.status}`, { error: !r.ok }); aiStatus(); }
        catch (err) { toast(friendly(err), { error: true }); setBusy(e.currentTarget, false); }
      } } }));
    }
    panel.append(row);
  }
}

// ---------------------------------------------------------------- usage chart (inline SVG, no chart library)
async function usage() {
  const res = await get("/api/admin/usage");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Usage (last 30 days)" }), el("p", { class: "muted", text: "Club totals only — never who did what. Shaded days are meeting days." }));
  const days = res.days;
  const series = [["visits", "#2B6CB0"], ["rounds", "#D64545"], ["human_rounds", "#2F9E67"], ["delegates_created", "#C9A400"]];
  const max = Math.max(1, ...days.flatMap((d) => series.map(([k]) => d[k] || 0)));
  const W = 600, H = 200, bw = W / days.length;
  let marks = "";
  days.forEach((d, i) => { if (d.meeting_day) marks += `<rect x="${i * bw}" y="0" width="${bw}" height="${H}" fill="rgba(255,228,92,.25)"/>`; });
  for (const [k, color] of series) {
    const pts = days.map((d, i) => `${(i + 0.5) * bw},${H - ((d[k] || 0) / max) * (H - 10)}`).join(" ");
    marks += `<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.5"/>`;
  }
  panel.append(el("div", { class: "chart" }, svg(`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Usage chart">${marks}</svg>`)),
    el("p", { class: "small" }, ...series.map(([k, c]) => el("span", { style: { marginRight: "14px" } }, el("span", { style: { color: c }, text: "■ " }), k.replace("_", " ")))),
    table(["Date", "Meeting day", "Visits", "Rounds", "Human rounds", "New nightmares", "AI calls"], [...days].reverse().map((d) =>
      [d.date, d.meeting_day ? "yes" : "", d.visits || 0, d.rounds || 0, d.human_rounds || 0, d.delegates_created || 0, d.ai_calls || 0])));
}

// ---------------------------------------------------------------- settings (maintainers)
async function settingsTab() {
  const { settings: s, day_keys } = await get("/api/admin/settings");
  panel.textContent = "";
  const f = (id, label, input, hint) => el("div", { class: "field" }, el("label", { for: id, text: label }), input, hint ? el("p", { class: "hint-text", text: hint }) : null);
  const text = (id, value, max = 80) => { const i = el("input", { type: "text", id, maxlength: String(max) }); i.value = value ?? ""; return i; };
  const num = (id, value, min, max) => el("input", { type: "number", id, min: String(min), max: String(max), value: String(value) });
  const select = (id, value, opts) => el("select", { id }, ...opts.map(([v, t]) => el("option", { value: v, text: t, selected: v === value })));
  const days = el("div", { class: "days", role: "group", "aria-label": "Meeting days" }, ...day_keys.map((d) =>
    el("label", { class: "check" }, el("input", { type: "checkbox", value: d, checked: s.meeting_schedule.days.includes(d) }), d.toUpperCase())));
  const features = el("div", {}, ...Object.entries(s.features).map(([k, v]) => el("label", { class: "check" }, el("input", { type: "checkbox", "data-feature": k, checked: v }), k.replaceAll("_", " "))));
  const grid = el("div", { class: "settings-grid" },
    f("s-club-name", "Club name", text("s-club-name", s.club_name, 60)),
    f("s-club-code", "Club code (rotate it each year)", text("s-club-code", s.club_code, 40)),
    f("s-tz", "Time zone", text("s-tz", s.timezone, 60), "Example: America/New_York"),
    el("div", { class: "field" }, el("span", { class: "small", text: "Meeting days" }), days),
    f("s-start", "Meeting start", el("input", { type: "time", id: "s-start", value: s.meeting_schedule.start })),
    f("s-end", "Meeting end", el("input", { type: "time", id: "s-end", value: s.meeting_schedule.end })),
    f("s-mode", "Handoff mode", select("s-mode", s.handoff_mode, [["strict", "Strict (AI rests after each round in meetings)"], ["gentle", "Gentle (no lock, daily cap)"], ["off", "Off"]])),
    f("s-lock", "Lock minutes", num("s-lock", s.lock_minutes, 0, 60)),
    f("s-cap", "Home rounds per day", num("s-cap", s.home_cap, 0, 50)),
    f("s-htext", "Handoff text", text("s-htext", s.handoff_text)),
    f("s-hcredit", "Handoff credit line", text("s-hcredit", s.handoff_credit)),
    el("div", { class: "field" }, el("label", { class: "check" }, el("input", { type: "checkbox", id: "s-guest", checked: s.guest_ai.enabled }), "Guests can use AI")),
    f("s-guest-quota", "Guest AI calls per device per day", num("s-guest-quota", s.guest_ai.daily_quota, 1, 100)),
    f("s-aicap", "Whole-site AI calls per day", num("s-aicap", s.ai_daily_cap, 0, 100000)),
    f("s-mod", "Wall moderation", select("s-mod", s.wall_moderation, [["auto", "Auto (word filter + AI safety check)"], ["approval", "An editor approves first"]])),
    el("div", { class: "field" }, el("span", { class: "small", text: "Feature toggles (most arrive in later phases)" }), features));
  const save = el("button", { class: "btn primary big", type: "button", text: "Save settings" });
  const err = el("p", { class: "error-text", role: "alert" });
  save.addEventListener("click", async () => {
    err.textContent = "";
    const featureVals = {};
    features.querySelectorAll("input[data-feature]").forEach((i) => { featureVals[i.dataset.feature] = i.checked; });
    const body = {
      club_name: $("#s-club-name").value, club_code: $("#s-club-code").value, timezone: $("#s-tz").value,
      meeting_schedule: { days: [...days.querySelectorAll("input:checked")].map((i) => i.value), start: $("#s-start").value, end: $("#s-end").value },
      handoff_mode: $("#s-mode").value, lock_minutes: Number($("#s-lock").value), home_cap: Number($("#s-cap").value),
      handoff_text: $("#s-htext").value, handoff_credit: $("#s-hcredit").value,
      guest_ai: { enabled: $("#s-guest").checked, daily_quota: Number($("#s-guest-quota").value) },
      ai_daily_cap: Number($("#s-aicap").value), wall_moderation: $("#s-mod").value, features: featureVals,
    };
    setBusy(save, true, "Saving…");
    try { const r = await patch("/api/admin/settings", body); toast(r.changed.length ? `Saved: ${r.changed.join(", ")}` : "Nothing changed."); }
    catch (e) { err.textContent = friendly(e) + (e.data?.problems ? " " + Object.values(e.data.problems).join(" ") : ""); }
    setBusy(save, false);
  });
  panel.append(el("h2", { class: "hand", text: "Settings" }), grid, err, save);
}

// ---------------------------------------------------------------- audit + backups
async function audit() {
  const res = await get("/api/admin/audit");
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Audit log" }), el("p", { class: "muted", text: "Who changed roles or settings, and who deleted content." }),
    table(["When", "Who", "Action", "Target", "Detail"], res.entries.map((e) => [e.when.replace("T", " ").slice(0, 19), e.who, e.action, e.target_type ? `${e.target_type} ${e.target_id || ""}` : "", e.detail ? JSON.stringify(e.detail) : ""])));
}

async function backups() {
  panel.textContent = "";
  panel.append(el("h2", { class: "hand", text: "Backups & handoff" }),
    el("p", { text: "Export everything (members, nightmares, drawings, versions, settings) as one .zip. Do this weekly and keep it somewhere safe." }),
    el("a", { class: "btn primary", href: "/api/admin/export", text: "⬇ Export everything (.zip)" }),
    el("p", { class: "small muted", text: "To restore a backup, use: python scripts/backup.py import <file.zip> (see MAINTAINERS.md). A restore button arrives in Phase 3." }),
    el("h3", { class: "hand", text: "Graduation handoff checklist" }),
    el("ul", {}, ...["At least 2 maintainers added in Admin, and both can log in.", "GitHub repo transferred, or maintainers added as admins.",
      "Hosting and database access shared with the maintainers and the club advisor.", "ADMIN_PASSCODE changed and shared only with new maintainers and the advisor.",
      "Confirmed whose AI key the site uses and what happens when it expires.", "A fresh backup exported and stored with the advisor.",
      "Walked through MAINTAINERS.md together, start to finish."].map((t) => el("li", { text: `☐ ${t}` }))));
}
