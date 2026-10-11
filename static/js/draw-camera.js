// "This laptop's camera" tab (section 6.2 A). The preview may be mirrored so it feels
// natural, but the captured image is NEVER mirrored, so writing in the drawing reads correctly.
import { prepareImage } from "./image-prep.js";
import { copy, el, reducedMotion, sleep } from "./ui.js";

const PAPER_ASPECT = 0.77; // a sheet of paper held up (portrait)

export function createCamera(container, { onCapture, onUnavailable, onUseUpload, getBoost }) {
  let stream = null;
  let mirrored = true;
  const video = el("video", { autoplay: true, playsinline: true, muted: true, class: "cam-video", "aria-label": "Camera preview" });
  const guide = el("div", { class: "cam-guide", "aria-hidden": "true" }, el("span", { text: "Hold your drawing inside the box." }));
  const countdown = el("div", { class: "cam-countdown", "aria-live": "assertive" });
  const stage = el("div", { class: "cam-stage", hidden: true }, video, guide, countdown);
  const status = el("p", { class: "cam-status", role: "status" });
  const startBtn = el("button", { type: "button", class: "btn primary big", text: "📷 Turn on the camera" });
  const snapBtn = el("button", { type: "button", class: "btn primary big", text: "Snap", hidden: true });
  const timerBtn = el("button", { type: "button", class: "btn big", text: "⏱ 3-2-1 timer", hidden: true });
  const uploadInstead = el("button", { type: "button", class: "btn ghost", text: "Upload a photo instead", hidden: true, on: { click: () => onUseUpload && onUseUpload() } });
  container.append(stage, status, el("div", { class: "btn-row" }, startBtn, snapBtn, timerBtn, uploadInstead));

  function guideBox() {
    const vw = video.videoWidth, vh = video.videoHeight;
    const gh = vh * 0.86;
    const gw = Math.min(vw * 0.9, gh * PAPER_ASPECT);
    return { x: (vw - gw) / 2, y: (vh - gh) / 2, w: gw, h: gh, vw, vh };
  }
  function placeGuide() {
    if (!video.videoWidth) return;
    const g = guideBox();
    Object.assign(guide.style, { left: `${(g.x / g.vw) * 100}%`, top: `${(g.y / g.vh) * 100}%`, width: `${(g.w / g.vw) * 100}%`, height: `${(g.h / g.vh) * 100}%` });
  }

  async function start() {
    status.textContent = "Asking for the camera…";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      onUnavailable && onUnavailable("none");
      return;
    }
    try {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "environment" }, audio: false });
      } catch (e) {
        if (e && (e.name === "NotAllowedError" || e.name === "SecurityError")) throw e;
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false }); // any camera
      }
    } catch (e) {
      if (e && (e.name === "NotFoundError" || e.name === "OverconstrainedError" || e.name === "NotReadableError")) {
        status.textContent = "No camera found here. Let's upload a photo instead.";
        onUnavailable && onUnavailable("none");
        return;
      }
      status.textContent = copy("error.camera");
      uploadInstead.hidden = false;
      return;
    }
    const settings = stream.getVideoTracks()[0]?.getSettings?.() || {};
    mirrored = settings.facingMode !== "environment"; // back cameras aren't mirrored
    video.classList.toggle("mirrored", mirrored);
    video.srcObject = stream;
    await video.play().catch(() => {});
    if (!video.videoWidth) await new Promise((r) => video.addEventListener("loadedmetadata", r, { once: true }));
    stage.hidden = false;
    placeGuide();
    status.textContent = "Hold your drawing inside the box, then press Snap.";
    startBtn.hidden = true;
    snapBtn.hidden = false;
    timerBtn.hidden = false;
    uploadInstead.hidden = false;
    snapBtn.focus();
  }

  async function snap() {
    if (!video.videoWidth) return;
    const g = guideBox();
    // mirror: false - the saved photo is exactly what the camera saw, so words read correctly.
    const result = await prepareImage(video, { crop: { x: g.x, y: g.y, w: g.w, h: g.h }, boost: getBoost ? getBoost() : true, mirror: false });
    stop();
    onCapture && onCapture(result);
  }

  async function countdownSnap() {
    snapBtn.disabled = timerBtn.disabled = true;
    for (const n of ["3", "2", "1"]) {
      countdown.textContent = n;
      await sleep(reducedMotion() ? 700 : 1000);
    }
    countdown.textContent = "";
    snapBtn.disabled = timerBtn.disabled = false;
    await snap();
  }

  function stop() {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    stage.hidden = true;
    startBtn.hidden = false;
    snapBtn.hidden = timerBtn.hidden = true;
    status.textContent = "";
  }

  startBtn.addEventListener("click", start);
  snapBtn.addEventListener("click", snap);
  timerBtn.addEventListener("click", countdownSnap);
  window.addEventListener("resize", placeGuide);
  return { start, stop, isOn: () => !!stream };
}
