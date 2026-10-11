// The drawing pad (section 6.2 B). Pointer Events, so mouse, touch, and stylus all work.
import { confirmDialog, el, lsGet, lsRemove, lsSet } from "./ui.js";

const W = 1200, H = 900; // 4:3, scaled to fit the screen with CSS
const COLORS = { black: "#23262B", red: "#D64545", blue: "#2B6CB0", green: "#2F9E67", yellow: "#E8B800" };
const STORE_KEY = "nd-drawing";

export function createDrawingPad(container, { onDirty } = {}) {
  const canvas = el("canvas", { width: W, height: H, class: "pad-canvas", "aria-label": "Drawing pad. Draw with a mouse, finger, or stylus.", role: "img" });
  const ctx = canvas.getContext("2d", { willReadFrequently: true }); // undo snapshots read pixels often
  const undo = [], redo = [];
  let tool = "pencil", size = 4, color = COLORS.black, drawing = false, last = null, dirty = false;

  function clearCanvas() {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, W, H);
  }
  clearCanvas();

  function snapshot() {
    try {
      undo.push(ctx.getImageData(0, 0, W, H));
      if (undo.length > 20) undo.shift(); // 20 steps
      redo.length = 0;
    } catch { /* ignore */ }
    updateButtons();
  }
  function restore(stackFrom, stackTo) {
    if (!stackFrom.length) return;
    stackTo.push(ctx.getImageData(0, 0, W, H));
    ctx.putImageData(stackFrom.pop(), 0, 0);
    markDirty();
    updateButtons();
  }
  function markDirty() { dirty = true; onDirty && onDirty(); }

  function pos(e) {
    const r = canvas.getBoundingClientRect();
    return { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H };
  }
  function strokeWidth(e) {
    const pressure = e.pointerType === "pen" && e.pressure > 0 ? e.pressure * 2 : 1;
    const base = tool === "eraser" ? 26 : tool === "marker" ? 10 : size;
    return base * pressure;
  }

  canvas.addEventListener("pointerdown", (e) => {
    if (tool === "text") { placeBubble(pos(e)); return; }
    e.preventDefault();
    canvas.setPointerCapture(e.pointerId);
    snapshot();
    drawing = true;
    last = pos(e);
    ctx.beginPath();
    ctx.arc(last.x, last.y, strokeWidth(e) / 2, 0, Math.PI * 2);
    ctx.fillStyle = tool === "eraser" ? "#ffffff" : color;
    ctx.fill();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drawing) return;
    const p = pos(e);
    ctx.strokeStyle = tool === "eraser" ? "#ffffff" : color;
    ctx.globalAlpha = tool === "marker" ? 0.9 : 1;
    ctx.lineWidth = strokeWidth(e);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    ctx.globalAlpha = 1;
    last = p;
  });
  const stop = () => { if (drawing) { drawing = false; markDirty(); } };
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
  canvas.addEventListener("pointerleave", stop);

  // Speech-bubble text tool: click where the bubble goes, then type.
  function placeBubble(p) {
    const wrap = container.querySelector(".pad-wrap");
    const input = el("input", { type: "text", maxlength: "40", class: "bubble-input", "aria-label": "Speech bubble text. Press Enter to place it." });
    const r = canvas.getBoundingClientRect();
    input.style.left = `${(p.x / W) * r.width}px`;
    input.style.top = `${(p.y / H) * r.height}px`;
    wrap.append(input);
    input.focus();
    const done = (commit) => {
      const text = input.value.trim();
      input.remove();
      if (!commit || !text) return;
      snapshot();
      ctx.font = "bold 34px 'Patrick Hand', 'Comic Sans MS', cursive";
      const tw = ctx.measureText(text).width;
      const bw = tw + 40, bh = 64;
      const x = Math.min(Math.max(p.x, 10), W - bw - 10), y = Math.min(Math.max(p.y, 10), H - bh - 40);
      ctx.fillStyle = "#ffffff"; ctx.strokeStyle = COLORS.black; ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, y, bw, bh, 26) : ctx.rect(x, y, bw, bh);
      ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x + 30, y + bh); ctx.lineTo(x + 18, y + bh + 30); ctx.lineTo(x + 52, y + bh); ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = COLORS.black;
      ctx.fillText(text, x + 20, y + 44);
      markDirty();
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); done(true); }
      if (e.key === "Escape") { e.preventDefault(); done(false); }
    });
    input.addEventListener("blur", () => done(true));
  }

  // ----- toolbar -----
  const toolButtons = [];
  function toolBtn(id, label, onPick) {
    const b = el("button", { type: "button", class: "chip", "aria-pressed": "false", text: label,
      on: { click: () => { toolButtons.forEach((x) => x.setAttribute("aria-pressed", "false")); b.setAttribute("aria-pressed", "true"); onPick(); } } });
    b.dataset.tool = id;
    toolButtons.push(b);
    return b;
  }
  const undoBtn = el("button", { type: "button", class: "btn small", text: "↶ Undo", on: { click: () => restore(undo, redo) } });
  const redoBtn = el("button", { type: "button", class: "btn small", text: "↷ Redo", on: { click: () => restore(redo, undo) } });
  const clearBtn = el("button", { type: "button", class: "btn small danger", text: "Clear", on: { click: async () => {
    const ok = await confirmDialog("Clear the whole drawing? You can still undo it.", { title: "Clear the drawing?", ok: "Clear it", danger: true });
    if (!ok) return;
    snapshot(); clearCanvas(); markDirty();
  } } });
  function updateButtons() { undoBtn.disabled = !undo.length; redoBtn.disabled = !redo.length; }

  const toolbar = el("div", { class: "pad-toolbar", role: "toolbar", "aria-label": "Drawing tools" },
    toolBtn("pencil-thin", "✏️ Thin pencil", () => { tool = "pencil"; size = 4; color = COLORS.black; }),
    toolBtn("pencil-thick", "✏️ Thick pencil", () => { tool = "pencil"; size = 9; color = COLORS.black; }),
    ...Object.entries(COLORS).map(([name, c]) => toolBtn(`marker-${name}`, `🖍️ ${name[0].toUpperCase() + name.slice(1)}`, () => { tool = "marker"; color = c; })),
    toolBtn("eraser", "🧽 Eraser", () => { tool = "eraser"; }),
    toolBtn("text", "💬 Speech bubble", () => { tool = "text"; }),
    undoBtn, redoBtn, clearBtn);
  toolButtons[0].setAttribute("aria-pressed", "true");
  updateButtons();

  container.textContent = "";
  container.append(toolbar, el("div", { class: "pad-wrap" }, canvas));

  // ----- autosave every 5 seconds so a closed tab doesn't lose it -----
  const timer = setInterval(() => {
    if (!dirty) return;
    lsSet(STORE_KEY, { at: Date.now(), data: canvas.toDataURL("image/png") });
  }, 5000);

  return {
    canvas,
    hasDrawing: () => dirty,
    restoreSaved() {
      const saved = lsGet(STORE_KEY);
      if (!saved || !saved.data) return Promise.resolve(false);
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => { ctx.drawImage(img, 0, 0, W, H); dirty = true; resolve(true); };
        img.onerror = () => resolve(false);
        img.src = saved.data;
      });
    },
    hasSaved: () => !!(lsGet(STORE_KEY) || {}).data,
    forgetSaved: () => lsRemove(STORE_KEY),
    stop: () => clearInterval(timer),
  };
}
