// Join (club code + first name + PIN) and log in. No outside accounts, no emails.
import { post } from "./api.js";
import { $, friendly, pageData, setBusy } from "./ui.js";

const next = pageData().next || "/";
const go = () => { window.location.href = next; };

$("#join-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#join-btn");
  $("#join-error").textContent = "";
  const pin = $("#pin").value.trim();
  if (!/^\d{4}$/.test(pin)) { $("#join-error").textContent = "Your PIN is 4 numbers, like 2580."; $("#pin").focus(); return; }
  setBusy(btn, true, "Joining…");
  try {
    await post("/api/auth/join", { club_code: $("#club-code").value, name: $("#name").value, pin, shared_device: $("#shared").checked });
    go();
  } catch (err) { $("#join-error").textContent = friendly(err); setBusy(btn, false); }
});

$("#login-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-btn");
  $("#login-error").textContent = "";
  setBusy(btn, true, "Logging in…");
  try {
    await post("/api/auth/login", { name: $("#name").value, pin: $("#pin").value.trim(), shared_device: $("#shared").checked });
    go();
  } catch (err) { $("#login-error").textContent = friendly(err); setBusy(btn, false); }
});
