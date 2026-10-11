// The face puppet (section 16.5): one SVG assembled from a persona's `look`.
// Look options only change how it looks, never personality or difficulty.
import { reducedMotion } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const INK = "#23262B";
const PAPER = "#FFFFFF";
const SKIN = { sketch: null, tone_1: "#F9DCC4", tone_2: "#F1C7A5", tone_3: "#E0AC84", tone_4: "#C98E64", tone_5: "#A86F4A", tone_6: "#8A5536", tone_7: "#6B3F26", tone_8: "#4A2B1A" };
const PALETTES = { pencil: ["#5B616B", "#C9CED6"], ink: ["#23262B", "#8B93A1"], blue: ["#2B6CB0", "#9CC3EC"], highlighter: ["#C9A400", "#FFE45C"], chalkboard: ["#2F4F3E", "#9DC5A6"], sunset: ["#D64545", "#F6A96B"], mint: ["#2F9E67", "#A8E6C8"], grape: ["#6B4FA0", "#C9B6EC"] };

function node(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, String(v));
  if (parent) parent.append(n);
  return n;
}

const MOUTHS = {
  smile: "M80 132 Q100 150 120 132",
  smirk: "M84 138 Q104 142 121 129",
  frown: "M82 143 Q100 128 118 143",
  flat: "M84 138 L116 138",
  toothy_grin: "M78 130 Q100 156 122 130 Z",
  small_smile: "M88 136 Q100 144 112 136",
};

// Brows: [x1, y1, x2, y2] for left and right, before the eyebrows (-2..2) nudge.
const BROWS = {
  flat: [[68, 62, 90, 62], [110, 62, 132, 62]],
  stern: [[68, 57, 91, 67], [109, 67, 132, 57]],
  raised: [[68, 53, 90, 52], [110, 52, 132, 53]],
  skeptical: [[68, 52, 90, 55], [110, 63, 132, 63]],
  relaxed: [[68, 59, 90, 57], [110, 57, 132, 59]],
  smug: [[68, 55, 90, 58], [110, 60, 132, 56]],
  thinking: [[68, 60, 90, 58], [110, 56, 132, 60]],
};
const EXPRESSIONS = {
  neutral: { brows: "flat", mouth: null },
  skeptical: { brows: "skeptical", mouth: "smirk" },
  stern: { brows: "stern", mouth: "flat" },
  impressed: { brows: "raised", mouth: "small_smile" },
  amused: { brows: "relaxed", mouth: "smile" },
  annoyed: { brows: "stern", mouth: "frown" },
  thinking: { brows: "thinking", mouth: "o_shape", gaze: [-4, -4] },
  smug: { brows: "smug", mouth: "smirk" },
};

export function createPuppet(container, look = {}, { quirks = [], label = "The delegate's face" } = {}) {
  const L = Object.assign({ style: "sketch", hair: "side_part", eyebrows: "flat", eyes: "round", glasses: "none", mouth: "flat", facial_hair: "none", headwear: "none", outfit: "navy_suit", accessory: "none", skin_tone: "sketch", palette: "pencil" }, look || {});
  const [dark, light] = PALETTES[L.palette] || PALETTES.pencil;
  const colored = L.style !== "sketch";
  const skin = (L.style === "colored" && SKIN[L.skin_tone]) || PAPER;
  const sw = L.style === "marker" ? 3.5 : 2.5;
  const line = { stroke: INK, "stroke-width": sw, "stroke-linecap": "round", "stroke-linejoin": "round" };
  const fillOr = (c) => (colored ? c : PAPER);

  const root = node("svg", { viewBox: "0 0 200 220", role: "img", "aria-label": label });
  const defs = node("defs", {}, root);
  const filter = node("filter", { id: "wobble-" + Math.random().toString(36).slice(2), x: "-5%", y: "-5%", width: "110%", height: "110%" }, defs);
  node("feTurbulence", { type: "fractalNoise", baseFrequency: "0.04", numOctaves: "2", seed: "3" }, filter);
  node("feDisplacementMap", { in: "SourceGraphic", scale: "2.2" }, filter);
  const body = node("g", { class: reducedMotion() ? "" : "breathe", filter: L.style === "sketch" ? `url(#${filter.id})` : null }, root);
  const head = node("g", { class: "head" }, body);

  // --- outfit (shoulders) ---
  const outfitColors = {
    navy_suit: ["#1F2F4F", "#fff"], black_tuxedo: ["#15171C", "#fff"], tweed_jacket: ["#8A6A45", "#F1E6D2"], blazer_blouse: [dark, "#fff"],
    sweater_vest: [dark, "#fff"], cardigan: [light, "#fff"], power_suit: [dark, "#fff"], dress_shirt_tie: ["#fff", "#fff"],
    bow_tie_vest: ["#4A4F58", "#fff"], lab_coat_silly: ["#fff", "#fff"],
  };
  const [coat, shirt] = outfitColors[L.outfit] || outfitColors.navy_suit;
  node("path", { d: "M30 220 Q36 172 74 162 L126 162 Q164 172 170 220 Z", fill: fillOr(coat), ...line }, body);
  node("path", { d: "M84 162 L100 196 L116 162 Z", fill: shirt, ...line }, body);
  if (["navy_suit", "power_suit", "blazer_blouse", "black_tuxedo", "tweed_jacket", "lab_coat_silly"].includes(L.outfit)) {
    node("path", { d: "M74 162 L92 200 M126 162 L108 200", fill: "none", ...line }, body);
  }
  if (["navy_suit", "power_suit", "dress_shirt_tie"].includes(L.outfit)) {
    node("path", { d: "M96 170 L104 170 L107 198 L100 206 L93 198 Z", fill: colored ? "#D64545" : INK, ...line }, body);
  }
  if (["black_tuxedo", "bow_tie_vest"].includes(L.outfit)) {
    node("path", { d: "M88 168 L100 174 L112 168 L112 180 L100 174 L88 180 Z", fill: colored ? dark : INK, ...line }, body);
  }
  if (L.outfit === "sweater_vest") node("path", { d: "M60 192 L140 192 M56 204 L144 204", fill: "none", ...line }, body);
  if (L.outfit === "cardigan") for (const y of [178, 192, 206]) node("circle", { cx: 120, cy: y, r: 2.5, fill: INK }, body);
  if (L.outfit === "tweed_jacket") for (let i = 0; i < 10; i++) node("circle", { cx: 50 + (i % 5) * 9, cy: 190 + Math.floor(i / 5) * 10, r: 1.2, fill: INK }, body);
  if (L.outfit === "lab_coat_silly") node("rect", { x: 128, y: 184, width: 16, height: 10, fill: "none", ...line }, body);

  // --- neck + head ---
  node("path", { d: "M88 146 L88 164 L112 164 L112 146", fill: skin, ...line }, head);
  const backHair = node("g", {}, head);
  node("ellipse", { cx: 50, cy: 98, rx: 7, ry: 11, fill: skin, ...line }, head);
  node("ellipse", { cx: 150, cy: 98, rx: 7, ry: 11, fill: skin, ...line }, head);
  node("ellipse", { cx: 100, cy: 96, rx: 50, ry: 58, fill: skin, ...line }, head);

  // --- hair ---
  const hairFill = colored ? dark : INK;
  const hair = node("g", {}, head);
  const cap = "M50 92 Q48 40 100 36 Q152 40 150 92 Q140 62 100 58 Q60 62 50 92 Z";
  const H = L.headwear === "hijab" ? "hidden" : L.hair;
  switch (H) {
    case "bald": node("path", { d: "M120 50 Q130 54 134 62", fill: "none", ...line }, hair); break;
    case "slicked_back": node("path", { d: cap, fill: hairFill, ...line }, hair); node("path", { d: "M70 50 Q100 44 130 52 M66 58 Q100 50 134 60", stroke: PAPER, "stroke-width": 1.5, fill: "none" }, hair); break;
    case "wild": node("path", { d: "M46 96 L30 80 L48 74 L34 54 L58 56 L56 32 L78 44 L86 22 L100 40 L114 20 L122 44 L144 30 L142 56 L166 52 L152 74 L170 80 L154 96 Q146 60 100 56 Q56 60 46 96 Z", fill: colored ? light : PAPER, ...line }, hair); break;
    case "curly": for (let i = 0; i < 9; i++) node("circle", { cx: 56 + i * 11, cy: 52 - Math.sin((i / 8) * Math.PI) * 14, r: 10, fill: hairFill, ...line }, hair); break;
    case "coily": for (let i = 0; i < 14; i++) node("circle", { cx: 52 + (i % 7) * 16, cy: 46 + Math.floor(i / 7) * 12 - Math.sin(((i % 7) / 6) * Math.PI) * 10, r: 8, fill: hairFill, ...line }, hair); break;
    case "buzz": node("path", { d: cap, fill: colored ? light : PAPER, ...line, "stroke-dasharray": "2 4" }, hair); break;
    case "bun": node("path", { d: cap, fill: hairFill, ...line }, hair); node("circle", { cx: 100, cy: 30, r: 14, fill: hairFill, ...line }, hair); break;
    case "ponytail": node("path", { d: cap, fill: hairFill, ...line }, hair); node("path", { d: "M146 70 Q176 90 160 132 Q156 104 144 86 Z", fill: hairFill, ...line }, backHair); break;
    case "braids": node("path", { d: cap, fill: hairFill, ...line }, hair); for (const x of [50, 150]) for (let j = 0; j < 4; j++) node("ellipse", { cx: x, cy: 112 + j * 14, rx: 7, ry: 8, fill: hairFill, ...line }, backHair); break;
    case "afro": node("circle", { cx: 100, cy: 74, r: 66, fill: hairFill, ...line }, backHair); break;
    case "long_straight": node("path", { d: "M50 92 Q46 40 100 36 Q154 40 150 92 L156 160 L138 160 L140 96 Q130 64 100 60 Q70 64 60 96 L62 160 L44 160 Z", fill: hairFill, ...line }, backHair); node("path", { d: cap, fill: hairFill, ...line }, hair); break;
    case "locs": node("path", { d: cap, fill: hairFill, ...line }, hair); for (let i = 0; i < 6; i++) node("path", { d: `M${52 + i * 19} 70 Q${48 + i * 19} 120 ${54 + i * 19} 150`, fill: "none", stroke: hairFill, "stroke-width": 7, "stroke-linecap": "round" }, backHair); break;
    case "bob": node("path", { d: "M48 120 Q40 40 100 36 Q160 40 152 120 L138 120 Q140 66 100 60 Q60 66 62 120 Z", fill: hairFill, ...line }, hair); break;
    case "spiky": node("path", { d: "M50 90 L52 52 L64 64 L70 34 L84 56 L94 26 L104 54 L118 28 L124 58 L138 38 L140 64 L150 54 L150 90 Q140 62 100 58 Q60 62 50 90 Z", fill: hairFill, ...line }, hair); break;
    case "mohawk": node("path", { d: "M90 60 L84 20 L96 30 L100 14 L106 30 L118 20 L110 60 Z", fill: colored ? dark : INK, ...line }, hair); break;
    case "hidden": break;
    default: node("path", { d: cap, fill: hairFill, ...line }, hair); node("path", { d: "M84 40 Q80 52 70 60", fill: "none", stroke: PAPER, "stroke-width": 2 }, hair);
  }

  // --- headwear (religious and cultural headwear always shown with respect) ---
  const hw = node("g", {}, head);
  switch (L.headwear) {
    case "hijab": node("path", { d: "M100 28 Q36 30 40 110 Q44 160 100 168 Q156 160 160 110 Q164 30 100 28 Z M100 46 Q58 50 58 100 Q60 146 100 150 Q140 146 142 100 Q142 50 100 46 Z", "fill-rule": "evenodd", fill: colored ? dark : "#E9ECF1", ...line }, hw); break;
    case "turban": node("path", { d: "M48 78 Q46 26 100 22 Q154 26 152 78 Q130 58 100 60 Q70 58 48 78 Z", fill: colored ? light : PAPER, ...line }, hw); node("path", { d: "M58 60 Q100 30 146 64 M54 70 Q100 44 150 72", fill: "none", ...line }, hw); break;
    case "kippah": node("path", { d: "M80 44 Q100 30 120 44 Z", fill: colored ? dark : INK, ...line }, hw); break;
    case "headband": node("path", { d: "M52 70 Q100 46 148 70", fill: "none", stroke: colored ? dark : INK, "stroke-width": 8, "stroke-linecap": "round" }, hw); break;
    case "beret": node("ellipse", { cx: 92, cy: 44, rx: 50, ry: 14, fill: colored ? dark : INK, ...line, transform: "rotate(-10 92 44)" }, hw); break;
    case "top_hat_silly": node("rect", { x: 66, y: -6, width: 68, height: 50, fill: INK, ...line }, hw); node("rect", { x: 52, y: 40, width: 96, height: 8, rx: 3, fill: INK, ...line }, hw); break;
    default: break;
  }

  // --- face ---
  const browG = node("g", { class: "brows" }, head);
  const browW = { bushy: 6, thin: 1.6, unibrow: 4.5 }[L.eyebrows] || 3.5;
  const browL = node("path", { class: "brow", fill: "none", stroke: INK, "stroke-width": browW, "stroke-linecap": "round" }, browG);
  const browR = node("path", { class: "brow", fill: "none", stroke: INK, "stroke-width": browW, "stroke-linecap": "round" }, browG);
  const uni = L.eyebrows === "unibrow" ? node("path", { d: "M90 62 L110 62", stroke: INK, "stroke-width": browW, "stroke-linecap": "round" }, browG) : null;

  const eyesG = node("g", { class: "eyes" }, head);
  const eyeCfg = { round: [10, 10, 4], narrow: [11, 4.5, 3.5], wide_unblinking: [14, 14, 4], sleepy: [10, 6, 4], sparkly: [10, 10, 5], dots: [0, 0, 4.5], hidden_by_glasses: [10, 10, 4] }[L.eyes] || [10, 10, 4];
  const pupils = [];
  for (const cx of [79, 121]) {
    if (eyeCfg[0]) node("ellipse", { cx, cy: 84, rx: eyeCfg[0], ry: eyeCfg[1], fill: PAPER, ...line }, eyesG);
    const p = node("circle", { class: "pupil", cx, cy: 84, r: eyeCfg[2], fill: INK }, eyesG);
    pupils.push(p);
    if (L.eyes === "sparkly") node("circle", { cx: cx + 2, cy: 82, r: 1.6, fill: PAPER }, eyesG);
    if (L.eyes === "sleepy") node("path", { d: `M${cx - 11} 81 L${cx + 11} 81`, ...line }, eyesG);
  }
  const eyesBaseY = 84;

  const glasses = node("g", {}, head);
  const gStroke = { ...line, fill: "none" };
  switch (L.glasses) {
    case "round": node("circle", { cx: 79, cy: 84, r: 15, ...gStroke }, glasses); node("circle", { cx: 121, cy: 84, r: 15, ...gStroke }, glasses); node("path", { d: "M94 84 Q100 79 106 84", ...gStroke }, glasses); break;
    case "square": node("rect", { x: 63, y: 72, width: 32, height: 24, rx: 3, ...gStroke }, glasses); node("rect", { x: 105, y: 72, width: 32, height: 24, rx: 3, ...gStroke }, glasses); node("path", { d: "M95 82 L105 82", ...gStroke }, glasses); break;
    case "monocle": node("circle", { cx: 121, cy: 84, r: 15, ...gStroke }, glasses); node("path", { d: "M134 92 Q140 120 128 150", ...gStroke, "stroke-width": 1.5 }, glasses); break;
    case "sunglasses": node("path", { d: "M62 76 L96 76 L92 94 Q78 100 66 92 Z M104 76 L138 76 L134 92 Q122 100 108 94 Z", fill: INK, ...line }, glasses); node("path", { d: "M96 79 L104 79", ...gStroke }, glasses); break;
    case "half_moon": node("path", { d: "M64 86 Q79 100 94 86 Z M106 86 Q121 100 136 86 Z", ...gStroke }, glasses); break;
    default: break;
  }

  node("path", { d: "M100 92 Q94 108 100 114 Q104 116 106 112", fill: "none", ...line }, head); // nose

  const mouthG = node("g", { class: "mouth" }, head);
  const mouthPath = node("path", { class: "mouth-path", fill: "none", ...line, "stroke-width": sw + 0.5 }, mouthG);
  const mouthOpen = node("ellipse", { cx: 100, cy: 137, rx: 14, ry: 2, fill: INK, opacity: 0 }, mouthG);

  const fh = node("g", {}, head);
  switch (L.facial_hair) {
    case "mustache": node("path", { d: "M78 124 Q90 114 100 122 Q110 114 122 124 Q110 128 100 125 Q90 128 78 124 Z", fill: colored ? dark : (L.hair === "wild" ? PAPER : INK), ...line }, fh); break;
    case "beard": node("path", { d: "M54 110 Q60 160 100 164 Q140 160 146 110 Q130 140 100 146 Q70 140 54 110 Z", fill: hairFill, ...line }, fh); break;
    case "goatee": node("path", { d: "M90 148 Q100 162 110 148 Z", fill: hairFill, ...line }, fh); break;
    case "stubble": for (let i = 0; i < 14; i++) node("circle", { cx: 72 + (i % 7) * 9, cy: 146 + Math.floor(i / 7) * 6, r: 0.9, fill: INK }, fh); break;
    default: break;
  }

  // --- accessory, held at the bottom edge ---
  const acc = node("g", {}, body);
  switch (L.accessory) {
    case "placard": node("rect", { x: 132, y: 168, width: 60, height: 34, fill: PAPER, ...line, transform: "rotate(6 162 185)" }, acc); node("path", { d: "M160 202 L160 220", ...line }, acc); break;
    case "pen": node("path", { d: "M150 214 L178 176", stroke: colored ? dark : INK, "stroke-width": 6, "stroke-linecap": "round" }, acc); break;
    case "paper_stack": for (let i = 0; i < 4; i++) node("rect", { x: 136, y: 196 - i * 8, width: 52, height: 8, fill: PAPER, ...line }, acc); break;
    case "laptop": node("path", { d: "M128 178 L180 178 L186 212 L122 212 Z", fill: colored ? light : PAPER, ...line }, acc); break;
    case "gavel": node("rect", { x: 150, y: 170, width: 34, height: 16, rx: 3, fill: colored ? "#8A6A45" : PAPER, ...line, transform: "rotate(-20 167 178)" }, acc); node("path", { d: "M164 184 L150 216", ...line, "stroke-width": 5 }, acc); break;
    case "briefcase": node("rect", { x: 134, y: 184, width: 52, height: 34, rx: 4, fill: colored ? "#5B3A22" : PAPER, ...line }, acc); node("path", { d: "M150 184 L150 176 L170 176 L170 184", fill: "none", ...line }, acc); break;
    case "stopwatch": node("circle", { cx: 164, cy: 196, r: 16, fill: PAPER, ...line }, acc); node("path", { d: "M164 196 L164 186 M164 180 L164 176", ...line }, acc); break;
    case "chalk": node("rect", { x: 152, y: 186, width: 26, height: 8, rx: 2, fill: PAPER, ...line, transform: "rotate(-30 165 190)" }, acc); break;
    case "coffee_mug": node("rect", { x: 144, y: 184, width: 30, height: 32, rx: 4, fill: colored ? light : PAPER, ...line }, acc); node("path", { d: "M174 192 Q186 198 174 208", fill: "none", ...line }, acc); break;
    case "clipboard": node("rect", { x: 136, y: 170, width: 46, height: 50, rx: 4, fill: colored ? "#C9A27E" : PAPER, ...line }, acc); node("path", { d: "M146 186 L172 186 M146 196 L172 196 M146 206 L164 206", ...line, "stroke-width": 1.5 }, acc); break;
    case "microphone": node("circle", { cx: 164, cy: 178, r: 10, fill: INK, ...line }, acc); node("path", { d: "M164 188 L160 218", ...line, "stroke-width": 5 }, acc); break;
    default: break;
  }

  const steam = node("path", { d: "M84 22 q4 -8 0 -14 q-4 -6 0 -12 M100 18 q4 -8 0 -14 q-4 -6 0 -12 M116 22 q4 -8 0 -14 q-4 -6 0 -12", fill: "none", stroke: "#D64545", "stroke-width": 2.5, "stroke-linecap": "round", opacity: 0 }, root);

  container.textContent = "";
  container.append(root);

  // ---------------------------------------------------------------- behavior
  const neverBlinks = quirks.includes("never_blinks");
  let state = { expression: "neutral", eyebrows: 0, gaze: [0, 0], talking: false };
  let blinkTimer = null;
  let flapTimer = null;

  function browPath([x1, y1, x2, y2], v, side) {
    // eyebrows: -2 pulled down and in ... +2 raised high
    const lift = -v * 3;
    const innerDrop = v < 0 ? -v * 2 : 0;
    const ax1 = side === "L" ? 0 : innerDrop, ax2 = side === "L" ? innerDrop : 0;
    const p1 = [x1, y1 + lift + ax1], p2 = [x2, y2 + lift + ax2];
    const arch = L.eyebrows === "arched" ? -6 : L.eyebrows === "raised" ? -3 : 0;
    const cx = (p1[0] + p2[0]) / 2, cy = (p1[1] + p2[1]) / 2 + arch;
    return `M${p1[0]} ${p1[1]} Q${cx} ${cy} ${p2[0]} ${p2[1]}`;
  }

  function render() {
    const ex = EXPRESSIONS[state.expression] || EXPRESSIONS.neutral;
    let base = ex.brows;
    if (state.expression === "neutral" && L.eyebrows === "pulled_in") base = "stern";
    const [bl, br] = BROWS[base] || BROWS.flat;
    browL.setAttribute("d", browPath(bl, state.eyebrows, "L"));
    browR.setAttribute("d", browPath(br, state.eyebrows, "R"));
    if (uni) uni.setAttribute("d", `M90 ${bl[3] + -state.eyebrows * 3} L110 ${br[1] + -state.eyebrows * 3}`);
    const mouth = ex.mouth || L.mouth;
    const talkingOpen = state.talking;
    if (mouth === "shouting" || mouth === "o_shape") {
      mouthPath.setAttribute("d", "");
      mouthOpen.setAttribute("opacity", "1");
      mouthOpen.setAttribute("rx", mouth === "shouting" ? "16" : "7");
      mouthOpen.setAttribute("ry", mouth === "shouting" ? "12" : "7");
    } else {
      mouthPath.setAttribute("d", MOUTHS[mouth] || MOUTHS.flat);
      mouthPath.setAttribute("fill", mouth === "toothy_grin" ? PAPER : "none");
      if (!talkingOpen) mouthOpen.setAttribute("opacity", "0");
    }
    const gaze = ex.gaze || state.gaze;
    pupils.forEach((p, i) => {
      p.setAttribute("cx", String((i === 0 ? 79 : 121) + gaze[0]));
      p.setAttribute("cy", String(eyesBaseY + gaze[1]));
    });
  }

  function blink() {
    if (neverBlinks || reducedMotion()) return;
    eyesG.style.transformOrigin = "100px 84px";
    eyesG.style.transform = "scaleY(0.1)";
    setTimeout(() => { eyesG.style.transform = ""; }, 120);
    blinkTimer = setTimeout(blink, 3000 + Math.random() * 3000);
  }
  if (!neverBlinks && !reducedMotion()) blinkTimer = setTimeout(blink, 2000 + Math.random() * 3000);
  render();

  return {
    svg: root,
    setExpression(expression = "neutral", eyebrows = 0) {
      state.expression = EXPRESSIONS[expression] ? expression : "neutral";
      state.eyebrows = Math.max(-2, Math.min(2, Number(eyebrows) || 0));
      render();
    },
    setHeat(heat) {
      steam.setAttribute("opacity", heat >= 5 ? "1" : "0");
    },
    lookAt(dx = 0, dy = 0) {
      state.gaze = [Math.max(-5, Math.min(5, dx)), Math.max(-4, Math.min(4, dy))];
      render();
    },
    setMouthOpen(v) {
      mouthOpen.setAttribute("opacity", v > 0.05 ? "1" : "0");
      mouthOpen.setAttribute("ry", String(2 + 10 * Math.max(0, Math.min(1, v))));
      mouthOpen.setAttribute("rx", "13");
    },
    talk(on) {
      state.talking = !!on;
      clearInterval(flapTimer);
      if (on && !reducedMotion()) {
        let open = false;
        flapTimer = setInterval(() => { open = !open; this.setMouthOpen(open ? 0.6 : 0.1); }, 125); // ~8 Hz
      } else {
        this.setMouthOpen(0);
        render();
      }
    },
    destroy() { clearTimeout(blinkTimer); clearInterval(flapTimer); },
    // Exports the puppet as a PNG (The Blank uses this as its "drawing").
    async toPNG(size = 600) {
      const clone = root.cloneNode(true);
      clone.setAttribute("xmlns", NS);
      clone.setAttribute("width", String(size));
      clone.setAttribute("height", String(Math.round(size * 1.1)));
      clone.querySelectorAll("[filter]").forEach((n) => n.removeAttribute("filter"));
      const xml = new XMLSerializer().serializeToString(clone);
      const url = URL.createObjectURL(new Blob([xml], { type: "image/svg+xml" }));
      try {
        const img = new Image();
        await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url; });
        const c = document.createElement("canvas");
        c.width = size; c.height = Math.round(size * 1.1);
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#FBF8F1";
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        return await new Promise((res) => c.toBlob(res, "image/png"));
      } finally {
        URL.revokeObjectURL(url);
      }
    },
  };
}
