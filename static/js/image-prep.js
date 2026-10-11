// Cleans up a photo or drawing in the browser before upload (section 6.2 A):
// crop, shrink so the long side is <= 1280 px, re-encode as JPEG 0.85 (this also strips
// EXIF and GPS data), and optionally boost light pencil lines. The server checks again.

export const MAX_INPUT_BYTES = 15 * 1024 * 1024;
const MAX_SIDE = 1280;

// source: an <img>, <video>, or <canvas>. crop: {x, y, w, h} in the source's own pixels.
export async function prepareImage(source, { crop = null, boost = true, mirror = false } = {}) {
  const sw = source.videoWidth || source.naturalWidth || source.width;
  const sh = source.videoHeight || source.naturalHeight || source.height;
  const c = crop || { x: 0, y: 0, w: sw, h: sh };
  const scale = Math.min(1, MAX_SIDE / Math.max(c.w, c.h));
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(c.w * scale));
  out.height = Math.max(1, Math.round(c.h * scale));
  const ctx = out.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, out.width, out.height);
  if (mirror) { ctx.translate(out.width, 0); ctx.scale(-1, 1); }
  ctx.drawImage(source, c.x, c.y, c.w, c.h, 0, 0, out.width, out.height);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (boost) autoContrast(ctx, out.width, out.height);
  const blob = await new Promise((res) => out.toBlob(res, "image/jpeg", 0.85));
  if (!blob) throw new Error("Could not prepare the image.");
  return { blob, width: out.width, height: out.height, dataUrl: out.toDataURL("image/jpeg", 0.85) };
}

// Mild auto-contrast: stretch the darkest 2% to near-black and the lightest 2% to white.
export function autoContrast(ctx, w, h) {
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  const hist = new Uint32Array(256);
  for (let i = 0; i < d.length; i += 4) hist[(d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000 | 0]++;
  const total = w * h;
  let lo = 0, hi = 255, acc = 0;
  for (; lo < 255; lo++) { acc += hist[lo]; if (acc > total * 0.02) break; }
  acc = 0;
  for (; hi > 0; hi--) { acc += hist[hi]; if (acc > total * 0.02) break; }
  if (hi - lo < 30) return; // nearly blank or already flat: leave it alone
  const range = hi - lo;
  for (let i = 0; i < d.length; i += 4) {
    for (let k = 0; k < 3; k++) {
      const v = ((d[i + k] - lo) * 255) / range;
      d[i + k] = v < 0 ? 0 : v > 255 ? 255 : v;
    }
  }
  ctx.putImageData(img, 0, 0);
}

export function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ img, url });
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });
}

export function dataUrlToBlob(dataUrl) {
  const [head, b64] = dataUrl.split(",");
  const mime = (head.match(/data:(.*?);/) || [])[1] || "image/jpeg";
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: mime });
}
