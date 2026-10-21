'use strict';
// MagicPath — 15s motion showreel. Every frame is a pure function of time `t`,
// so the same code drives the live preview and the frame-exact video render.

const W = 1920, H = 1080, FPS = 60, DUR = 15;
const SHUTTER = 0.5;            // fraction of a frame the virtual shutter stays open
const cv = document.getElementById('c');
const ctx = cv.getContext('2d');

// ---------------------------------------------------------------- math ----
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, k) => a + (b - a) * k;
const expLerp = (a, b, k) => a * Math.pow(b / a, k);
const prog = (t, a, b) => clamp((t - a) / (b - a));
const ease = {
  inOut: x => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
  out: x => 1 - Math.pow(1 - x, 3),
  out5: x => 1 - Math.pow(1 - x, 5),
  in: x => x * x * x,
  inExpo: x => x <= 0 ? 0 : Math.pow(2, 10 * x - 10),
  back: x => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
};
// damped spring: dt seconds after release -> 0..1 with overshoot
const spring = (dt, freq = 14, damp = 7) => dt <= 0 ? 0 : 1 - Math.exp(-damp * dt) * Math.cos(freq * dt);
function rng(seed) {
  return () => {
    seed = seed + 0x6D2B79F5 | 0;
    let r = Math.imul(seed ^ seed >>> 15, 1 | seed);
    r = r + Math.imul(r ^ r >>> 7, 61 | r) ^ r;
    return ((r ^ r >>> 14) >>> 0) / 4294967296;
  };
}

// --------------------------------------------------------------- style ----
const C = {
  bg: '#06050B', violet: '#7C5CFF', magenta: '#FF4FD8', cyan: '#3BE8FF', gold: '#FFC85C',
};
const F = (w, s, fam = 'Inter Display') => `${w} ${s}px "${fam}"`;
const MONO = (w, s) => F(w, s, 'JetBrains Mono');
function brandGrad(x0, y0, x1, y1) {
  const g = ctx.createLinearGradient(x0, y0, x1, y1);
  g.addColorStop(0, C.cyan); g.addColorStop(0.5, C.violet); g.addColorStop(1, C.magenta);
  return g;
}
const hueColor = h => h < 0.33 ? C.cyan : h < 0.66 ? C.violet : C.magenta;

// global alpha multiplier so nested elements can fade as a group
let GA = 1;
const setA = a => { ctx.globalAlpha = clamp(a * GA); };

function rr(x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); }

function sparkle(x, y, r, rot = 0) {
  ctx.beginPath();
  for (let i = 0; i <= 4; i++) {
    const a = rot + i * Math.PI / 2;
    const px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
    if (i === 0) ctx.moveTo(px, py); else ctx.quadraticCurveTo(x, y, px, py);
  }
  ctx.closePath();
}

// ---------------------------------------------------------------- paths ---
function catmull(p0, p1, p2, p3, u) {
  const u2 = u * u, u3 = u2 * u;
  return [0, 1].map(k => 0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * u +
    (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u3));
}
function withLengths(pts) {
  const L = [0];
  for (let i = 1; i < pts.length; i++) L.push(L[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return { pts, L, total: L[L.length - 1] };
}
function splinePath(ctrl, per = 90) {
  const P = [ctrl[0], ...ctrl, ctrl[ctrl.length - 1]], out = [];
  for (let i = 1; i < P.length - 2; i++)
    for (let j = 0; j < per; j++) out.push(catmull(P[i - 1], P[i], P[i + 1], P[i + 2], j / per));
  out.push(ctrl[ctrl.length - 1]);
  return withLengths(out);
}
function pathAt(path, f) {
  const d = clamp(f) * path.total;
  let lo = 0, hi = path.L.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (path.L[m] < d) lo = m; else hi = m; }
  const seg = path.L[hi] - path.L[lo] || 1, k = clamp((d - path.L[lo]) / seg);
  const a = path.pts[lo], b = path.pts[hi];
  return [lerp(a[0], b[0], k), lerp(a[1], b[1], k)];
}
function strokeSub(path, f0, f1) {
  const d0 = f0 * path.total, d1 = f1 * path.total;
  const a = pathAt(path, f0), b = pathAt(path, f1);
  ctx.beginPath(); ctx.moveTo(a[0], a[1]);
  for (let i = 0; i < path.pts.length; i++)
    if (path.L[i] > d0 && path.L[i] < d1) ctx.lineTo(path.pts[i][0], path.pts[i][1]);
  ctx.lineTo(b[0], b[1]); ctx.stroke();
}
// tapered neon trail: thin tail, fat bright head
function strokeTrail(path, f0, f1, w, alpha = 1) {
  if (f1 - f0 < 1e-4) return;
  ctx.save();
  ctx.lineCap = 'butt'; ctx.lineJoin = 'round'; ctx.globalCompositeOperation = 'lighter';
  const g = brandGrad(0, 0, W, 0), N = 16;
  for (let pass = 0; pass < 3; pass++) {
    for (let i = 0; i < N; i++) {
      const k = (i + 1) / N;
      if (pass === 0) { ctx.strokeStyle = g; ctx.globalAlpha = 0.14 * alpha * k; ctx.lineWidth = w * 5 * k; }
      else if (pass === 1) { ctx.strokeStyle = g; ctx.globalAlpha = 0.95 * alpha * k; ctx.lineWidth = w * k; }
      else { ctx.strokeStyle = '#fff'; ctx.globalAlpha = 0.9 * alpha * k * k; ctx.lineWidth = w * 0.32 * k; }
      strokeSub(path, lerp(f0, f1, i / N), lerp(f0, f1, k));
    }
  }
  ctx.restore();
}

// ------------------------------------------------------------- effects ----
function flare(x, y, s, t, alpha = 1, streak = 300) {
  if (alpha <= 0) return;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = alpha;
  let g = ctx.createRadialGradient(x, y, 0, x, y, 70 * s);
  g.addColorStop(0, 'rgba(255,255,255,0.95)'); g.addColorStop(0.25, 'rgba(160,140,255,0.45)'); g.addColorStop(1, 'rgba(124,92,255,0)');
  ctx.fillStyle = g; ctx.fillRect(x - 70 * s, y - 70 * s, 140 * s, 140 * s);
  g = ctx.createLinearGradient(x - streak * s, 0, x + streak * s, 0);
  g.addColorStop(0, 'rgba(59,232,255,0)'); g.addColorStop(0.5, 'rgba(180,245,255,0.85)'); g.addColorStop(1, 'rgba(59,232,255,0)');
  ctx.fillStyle = g; ctx.fillRect(x - streak * s, y - 1.6 * s, streak * 2 * s, 3.2 * s);
  ctx.fillStyle = '#fff'; sparkle(x, y, 24 * s, t * 2.4); ctx.fill();
  ctx.restore();
}
function ring(x, y, t, t0, maxR, dur, width, color, alpha = 1) {
  const p = prog(t, t0, t0 + dur);
  if (p <= 0 || p >= 1) return;
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  ctx.globalAlpha = (1 - p) * alpha; ctx.strokeStyle = color; ctx.lineWidth = width * (1 - p) + 0.5;
  ctx.beginPath(); ctx.arc(x, y, ease.out(p) * maxR, 0, Math.PI * 2); ctx.stroke();
  ctx.restore();
}
const BURSTS = {};
function burst(x, y, t, t0, seed, n = 120, speed = 900) {
  const age = t - t0;
  if (age < 0 || age > 1.6) return;
  const ps = BURSTS[seed] || (BURSTS[seed] = (() => {
    const r = rng(seed);
    return Array.from({ length: n }, () => ({ a: r() * Math.PI * 2, v: speed * (0.2 + r() * 0.8), life: 0.5 + r() * 1.0, s: 1 + r() * 3.2, h: r(), star: r() < 0.18 }));
  })());
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  for (const p of ps) {
    if (age > p.life) continue;
    const d = p.v * (1 - Math.exp(-3.2 * age)) / 3.2;
    const px = x + Math.cos(p.a) * d, py = y + Math.sin(p.a) * d + 30 * age * age;
    const k = 1 - age / p.life;
    ctx.globalAlpha = k; ctx.fillStyle = hueColor(p.h);
    if (p.star) { sparkle(px, py, p.s * 3.2 * k, age * 4); ctx.fill(); }
    else { ctx.beginPath(); ctx.arc(px, py, p.s * k, 0, Math.PI * 2); ctx.fill(); }
  }
  ctx.restore();
}
const IMPACTS = [[2.0, 10], [6.0, 6], [12.55, 12], [13.27, 6]];
function shake(t) {
  let x = 0, y = 0;
  for (const [t0, a] of IMPACTS) {
    const d = t - t0; if (d < 0 || d > 0.6) continue;
    const e = a * Math.exp(-d * 9);
    x += e * Math.sin(d * 71); y += e * Math.cos(d * 53);
  }
  return [x, y];
}

// ------------------------------------------------------- background -------
const tile = document.createElement('canvas'); tile.width = tile.height = 40;
{ const c = tile.getContext('2d'); c.fillStyle = '#fff'; c.beginPath(); c.arc(20, 20, 1.5, 0, Math.PI * 2); c.fill(); }
const gridPat = ctx.createPattern(tile, 'repeat');
function grid(alpha, s = 1, ox = 960, oy = 540) {
  if (alpha <= 0) return;
  gridPat.setTransform(new DOMMatrix().translateSelf(ox - 20 * s, oy - 20 * s).scaleSelf(s, s));
  ctx.save(); ctx.globalAlpha = alpha; ctx.fillStyle = gridPat; ctx.fillRect(0, 0, W, H); ctx.restore();
}
function blob(x, y, r, color, a) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, color); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.globalAlpha = a; ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
}
function background(t) {
  ctx.save();
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  const I = 0.55 + 0.45 * prog(t, 3.8, 4.4) - 0.25 * prog(t, 6.5, 7.2) + 0.5 * prog(t, 12.4, 13.4);
  ctx.globalCompositeOperation = 'lighter';
  blob(960 + 420 * Math.sin(t * 0.33), 280 + 120 * Math.cos(t * 0.41), 950, C.violet, 0.2 * I);
  blob(380 + 160 * Math.cos(t * 0.27), 860, 760, C.magenta, 0.11 * I);
  blob(1560, 760 + 90 * Math.sin(t * 0.5), 700, C.cyan, 0.08 * I);
  ctx.restore();
  // dot grid for the "canvas" scenes (scene 4 draws its own world-space grid)
  const ga = 0.09 * (prog(t, 4.0, 4.6) * (1 - prog(t, 6.45, 6.55)) + prog(t, 10.1, 10.6) * (1 - prog(t, 12.2, 12.5)));
  grid(ga);
}

const GRAIN = [0, 1, 2].map(seed => {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const x = c.getContext('2d'), img = x.createImageData(256, 256), r = rng(seed + 99);
  for (let i = 0; i < img.data.length; i += 4) { const v = r() * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
  x.putImageData(img, 0, 0); return c;
});
function post(t, f) {
  ctx.save();
  const v = ctx.createRadialGradient(960, 540, 420, 960, 540, 1150);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.6)');
  ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
  const r = rng(f * 7 + 3);
  const pat = ctx.createPattern(GRAIN[f % 3], 'repeat');
  pat.setTransform(new DOMMatrix().translateSelf(r() * 256, r() * 256));
  ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = 0.07; ctx.fillStyle = pat; ctx.fillRect(0, 0, W, H);
  ctx.restore();
  hud(t);
}

// ------------------------------------------------------------- HUD --------
const SECTIONS = [[0, '01', 'PATH'], [2, '02', 'IDENTITY'], [4, '03', 'PROMPT'], [6.5, '04', 'GENERATE'], [10, '05', 'CODE'], [12.5, '06', 'SIGNATURE']];
function hud(t) {
  const a = ease.out(prog(t, 0.25, 0.9)) * (1 - 0.65 * prog(t, 13.3, 13.9));
  if (a <= 0) return;
  ctx.save();
  ctx.globalAlpha = a; ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1.5;
  for (const [x, y, dx, dy] of [[36, 36, 1, 1], [W - 36, 36, -1, 1], [36, H - 36, 1, -1], [W - 36, H - 36, -1, -1]]) {
    ctx.beginPath(); ctx.moveTo(x, y + dy * 22); ctx.lineTo(x, y); ctx.lineTo(x + dx * 22, y); ctx.stroke();
  }
  ctx.font = MONO(500, 15); ctx.letterSpacing = '3px'; ctx.textBaseline = 'middle';
  ctx.fillStyle = Math.floor(t * 2) % 2 ? 'rgba(255,79,216,0.35)' : '#FF4FD8';
  ctx.beginPath(); ctx.arc(66, 66, 5, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.fillText('AK DAVID — MOTION REEL', 82, 67);
  const fr = Math.min(Math.round(t * FPS), DUR * FPS - 1);
  const tc = `00:00:${String(Math.floor(fr / FPS)).padStart(2, '0')}:${String(fr % FPS).padStart(2, '0')}`;
  ctx.textAlign = 'right'; ctx.fillText(tc, W - 62, 67);
  ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.fillText('MAGICPATH · CONCEPT FILM', W - 62, H - 72);
  // section label with slot-machine roll on change
  ctx.textAlign = 'left';
  let idx = 0; for (let i = 0; i < SECTIONS.length; i++) if (t >= SECTIONS[i][0]) idx = i;
  const roll = ease.out5(prog(t, SECTIONS[idx][0], SECTIONS[idx][0] + 0.45));
  ctx.save(); ctx.beginPath(); ctx.rect(56, H - 92, 400, 40); ctx.clip();
  const drawSec = (s, dy, al) => {
    ctx.globalAlpha = a * al; ctx.fillStyle = C.violet; ctx.fillText(s[1], 62, H - 72 + dy);
    ctx.fillStyle = 'rgba(255,255,255,0.75)'; ctx.fillText('/  ' + s[2], 100, H - 72 + dy);
  };
  if (idx > 0 && roll < 1) drawSec(SECTIONS[idx - 1], -roll * 30, 1 - roll);
  drawSec(SECTIONS[idx], (1 - roll) * 30, roll);
  ctx.restore();
  ctx.globalAlpha = a;
  ctx.fillStyle = 'rgba(255,255,255,0.12)'; ctx.fillRect(62, H - 46, W - 124, 2);
  ctx.fillStyle = brandGrad(62, 0, W - 62, 0); ctx.fillRect(62, H - 46, (W - 124) * clamp(t / DUR), 2);
  ctx.restore();
}

// ---------------------------------------------------------- wordmark ------
const WORD = 'magicpath';
let WM2, WMLK, path1, path6, TITTLE;
// find where Inter draws the dot of an "i" so our animated dot sits exactly there
function measureTittle() {
  const c = document.createElement('canvas'); c.width = 400; c.height = 400;
  const x = c.getContext('2d'); x.font = F(800, 200); x.fillStyle = '#fff'; x.fillText('i', 100, 300);
  const d = x.getImageData(0, 0, 400, 400).data, ink = y => { for (let i = 0; i < 400; i++) if (d[(y * 400 + i) * 4 + 3] > 128) return true; return false; };
  let top = 0; while (!ink(top)) top++;
  let bot = top; while (ink(bot)) bot++;
  let l = 400, r = 0;
  for (let y = top; y < bot; y++) for (let i = 0; i < 400; i++) if (d[(y * 400 + i) * 4 + 3] > 128) { l = Math.min(l, i); r = Math.max(r, i); }
  return { cx: ((l + r) / 2 - 100) / 200, cy: (300 - (top + bot) / 2) / 200, r: (bot - top) / 2 / 200 };
}
function layoutWord(size, x0c, cy) {
  ctx.font = F(800, size);
  const track = -0.025 * size;
  let x = 0; const letters = [];
  for (const ch of WORD) {
    const g = ch === 'i' ? 'ı' : ch, w = ctx.measureText(g).width;
    letters.push({ ch: g, x, w }); x += w + track;
  }
  const width = x - track, base = cy + 0.273 * size;
  const x0 = x0c === null ? 960 - width / 2 : x0c;
  const li = letters[3];
  return { size, letters, width, x0, base, idot: { x: x0 + li.x + TITTLE.cx * size, y: base - TITTLE.cy * size, r: TITTLE.r * size } };
}
function drawLetters(L, t, t0, { stagger = 0.045, dur = 0.7, alpha = 1, slideX = 0, clipX = -1e9 } = {}) {
  ctx.save();
  ctx.font = F(800, L.size); ctx.fillStyle = '#fff'; ctx.textBaseline = 'alphabetic';
  ctx.beginPath(); ctx.rect(Math.max(clipX, -1e4), L.base - L.size * 1.2, 2e4, L.size * 1.5); ctx.clip();
  L.letters.forEach((l, i) => {
    const e = ease.out5(prog(t, t0 + i * stagger, t0 + i * stagger + dur));
    if (e <= 0) return;
    ctx.globalAlpha = alpha * clamp(e * 1.6);
    const dy = slideX ? 0 : (1 - e) * L.size, dx = slideX ? -(1 - e) * slideX : 0;
    ctx.fillText(l.ch, L.x0 + l.x + dx, L.base + dy);
  });
  ctx.restore();
}
function drawIDot(d, scale, alpha = 1) {
  if (scale <= 0) return;
  const r = d.r * scale;
  ctx.save(); ctx.globalAlpha = alpha;
  ctx.shadowColor = 'rgba(124,92,255,0.9)'; ctx.shadowBlur = 30;
  const g = ctx.createRadialGradient(d.x - r * 0.35, d.y - r * 0.35, 0, d.x, d.y, r);
  g.addColorStop(0, '#D6CCFF'); g.addColorStop(0.55, C.violet); g.addColorStop(1, '#6A44FF');
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(d.x, d.y, r, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}

// ========================================================== SCENE 1+2 ======
// A neon path writes itself across the screen and lands as the dot of the "i".
const P1 = (() => { const r = rng(7); return Array.from({ length: 240 }, (_, i) => ({ t0: 0.15 + 1.85 * (i / 240), vx: (r() - 0.5) * 170, vy: (r() - 0.5) * 170 - 25, life: 0.5 + r() * 0.9, s: 0.8 + r() * 2.8, h: r() })); })();
const h1 = t => ease.inOut(prog(t, 0.15, 2.0));
function scene12(t) {
  const L = WM2, dot = L.idot;
  const z = ease.inExpo(prog(t, 3.6, 4.05));
  const S = Math.exp(z * Math.log(95));
  ctx.save();
  ctx.translate(dot.x, dot.y); ctx.scale(S, S); ctx.translate(-dot.x, -dot.y);

  // ghost echoes + main trail
  const h = h1(t), tl = ease.inOut(prog(t, 0.5, 2.02));
  if (h > 0 && t < 2.1) {
    for (const [dy, delay, al] of [[46, 0.12, 0.25], [-58, 0.22, 0.18]]) {
      ctx.save(); ctx.translate(0, dy * (1 - h));
      strokeTrail(path1, ease.inOut(prog(t, 0.5 + delay, 2.0)) * 0.98, h1(t - delay) * 0.98, 3, al * (1 - prog(t, 1.6, 2.0)));
      ctx.restore();
    }
    strokeTrail(path1, tl, h, 7);
  }
  // trail particles
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  for (const p of P1) {
    const age = t - p.t0; if (age < 0 || age > p.life) continue;
    const b = pathAt(path1, h1(p.t0)), k = 1 - age / p.life;
    ctx.globalAlpha = k; ctx.fillStyle = hueColor(p.h);
    ctx.beginPath(); ctx.arc(b[0] + p.vx * age, b[1] + p.vy * age + 40 * age * age, p.s * k, 0, Math.PI * 2); ctx.fill();
  }
  ctx.restore();
  if (h > 0 && t < 2.05) { const p = pathAt(path1, h); flare(p[0], p[1], 1, t, 1 - prog(t, 1.95, 2.05)); }

  // impact
  ring(dot.x, dot.y, t, 2.0, 1100, 1.0, 10, C.violet);
  ring(dot.x, dot.y, t, 2.08, 700, 0.8, 4, C.cyan);
  burst(dot.x, dot.y, t, 2.0, 11, 140, 1100);
  if (t > 1.98) {
    const fl = 1 - prog(t, 2.0, 2.35);
    if (fl > 0 && fl < 1) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; blob(dot.x, dot.y, 900, 'rgba(200,190,255,1)', 0.5 * fl); ctx.restore(); }
    const la = 1 - z;
    drawLetters(L, t, 2.03, { alpha: la });
    // eyebrow + tagline
    ctx.save(); ctx.textAlign = 'center';
    const e1 = ease.out5(prog(t, 2.55, 3.2));
    ctx.globalAlpha = e1 * la; ctx.font = MONO(500, 18); ctx.letterSpacing = '8px';
    ctx.fillStyle = 'rgba(255,255,255,0.55)'; ctx.fillText('AI-NATIVE DESIGN CANVAS', 960, L.base - L.size * 1.05 - (1 - e1) * 20);
    ctx.letterSpacing = '0px'; ctx.font = F(500, 42);
    const words = 'Design at the speed of thought.'.split(' ');
    ctx.textAlign = 'left';
    const sp = ctx.measureText(' ').width, widths = words.map(w => ctx.measureText(w).width);
    let x = 960 - (widths.reduce((a, b) => a + b, 0) + sp * (words.length - 1)) / 2;
    ctx.beginPath(); ctx.rect(0, L.base + 70, W, 70); ctx.clip();
    words.forEach((w, i) => {
      const e = ease.out5(prog(t, 2.75 + i * 0.06, 3.35 + i * 0.06));
      ctx.globalAlpha = la * e; ctx.fillStyle = i === words.length - 1 ? brandGrad(x, 0, x + widths[i], 0) : 'rgba(255,255,255,0.7)';
      ctx.fillText(w, x, L.base + 122 + (1 - e) * 60); x += widths[i] + sp;
    });
    ctx.restore();
  }
  drawIDot(dot, t < 1.97 ? 0 : spring(t - 1.97, 16, 7) + 0.25 * z);
  ctx.restore();
}

// ============================================================ SCENE 3 ======
// Prompt bar: a brief gets typed, enter is hit, and the bar morphs into a frame.
const PROMPT_A = 'Pricing page for a ', PROMPT_B = 'Mars', PROMPT_C = ' travel startup';
const PROMPT = PROMPT_A + PROMPT_B + PROMPT_C;
const charTime = i => 4.45 + 1.3 * (i + 0.3 * Math.sin(i * 2.7)) / PROMPT.length;
const BOX = { x: 360, y: 476, w: 1200, h: 128 };
const FRAME_SCREEN = { x: 360, y: 165, w: 1200, h: 750 };
function scene3(t) {
  if (t > 6.56) return;
  const intro = ease.out5(prog(t, 4.02, 4.6));
  const morph = ease.inOut(prog(t, 6.05, 6.55));
  const content = 1 - prog(t, 6.02, 6.2);
  ctx.save();
  // question
  ctx.textAlign = 'center'; ctx.font = F(600, 52);
  ctx.globalAlpha = intro * content; ctx.fillStyle = '#fff';
  ctx.fillText('What should we design today?', 960, 410 + (1 - intro) * 40);
  // box
  const pop = lerp(0.82, 1, ease.back(prog(t, 4.02, 4.55)));
  const bx = lerp(BOX.x, FRAME_SCREEN.x, morph), by = lerp(BOX.y, FRAME_SCREEN.y, morph);
  const bw = lerp(BOX.w, FRAME_SCREEN.w, morph), bh = lerp(BOX.h, FRAME_SCREEN.h, morph), br = lerp(64, 18, morph);
  ctx.translate(960, 540); ctx.scale(pop, pop); ctx.translate(-960, -540);
  ctx.globalAlpha = intro;
  ctx.shadowColor = 'rgba(124,92,255,0.55)'; ctx.shadowBlur = 50 + 40 * Math.sin(t * 3) ** 2;
  rr(bx, by, bw, bh, br); ctx.fillStyle = 'rgba(22,18,40,0.92)'; ctx.fill();
  ctx.shadowBlur = 0;
  ctx.globalAlpha = intro * morph; ctx.fillStyle = '#0F0D1A'; ctx.fill();
  const cg = ctx.createConicGradient(t * 2.2, bx + bw / 2, by + bh / 2);
  cg.addColorStop(0, C.cyan); cg.addColorStop(0.33, C.violet); cg.addColorStop(0.66, C.magenta); cg.addColorStop(1, C.cyan);
  ctx.globalAlpha = intro * lerp(1, 0.25, morph); ctx.strokeStyle = cg; ctx.lineWidth = 2.5; rr(bx, by, bw, bh, br); ctx.stroke();

  // contents
  ctx.globalAlpha = intro * content;
  ctx.textAlign = 'left';
  const cy = 540, spin = t * 1.2 + 6 * ease.inOut(prog(t, 5.95, 6.3));
  ctx.fillStyle = brandGrad(400, 520, 440, 560); sparkle(422, cy, 22, spin); ctx.fill();
  ctx.font = F(500, 44, 'Inter');
  let n = 0; for (let i = 0; i < PROMPT.length; i++) if (charTime(i) <= t) n++;
  if (n === 0) { ctx.fillStyle = 'rgba(255,255,255,0.3)'; ctx.fillText('Describe anything you want to make…', 470, cy + 15); }
  const typed = PROMPT.slice(0, n);
  const marsLit = ease.out(prog(t, 5.85, 6.05));
  let x = 470;
  const seg = (s, style) => { ctx.fillStyle = style; ctx.fillText(s, x, cy + 15); x += ctx.measureText(s).width; };
  seg(typed.slice(0, PROMPT_A.length), '#fff');
  if (n > PROMPT_A.length) {
    const s = typed.slice(PROMPT_A.length, PROMPT_A.length + PROMPT_B.length), w = ctx.measureText(s).width;
    seg(s, marsLit > 0 ? brandGrad(x, 0, x + w, 0) : '#fff');
    if (marsLit > 0) { ctx.fillStyle = brandGrad(x - w, 0, x, 0); ctx.globalAlpha = intro * content * marsLit; ctx.fillRect(x - w, cy + 30, w * marsLit, 3); ctx.globalAlpha = intro * content; }
  }
  if (n > PROMPT_A.length + PROMPT_B.length) seg(typed.slice(PROMPT_A.length + PROMPT_B.length), '#fff');
  if (t < 5.85 || Math.floor(t * 4) % 2 === 0) { ctx.fillStyle = brandGrad(0, cy - 26, 0, cy + 26); ctx.fillRect(x + 4, cy - 26, 3, 52); }
  // send button
  const press = 1 - 0.18 * Math.sin(Math.PI * prog(t, 5.94, 6.12));
  const ready = prog(t, charTime(0), charTime(0) + 0.2);
  ctx.save(); ctx.translate(1490, cy); ctx.scale(press, press);
  ctx.fillStyle = `rgba(255,255,255,${0.12 + 0.88 * ready})`; ctx.beginPath(); ctx.arc(0, 0, 38, 0, Math.PI * 2); ctx.fill();
  ctx.strokeStyle = ready > 0.5 ? '#0F0D1A' : 'rgba(255,255,255,0.6)'; ctx.lineWidth = 4.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(0, 14); ctx.lineTo(0, -13); ctx.moveTo(-11, -2); ctx.lineTo(0, -13); ctx.lineTo(11, -2); ctx.stroke();
  ctx.restore();
  ring(1490, cy, t, 6.0, 260, 0.6, 8, C.magenta);
  // suggestion chips
  const chips = ['Landing page', 'Dashboard', 'Pricing page', 'Mobile app'];
  ctx.font = F(500, 22, 'Inter');
  const cw = chips.map(c => ctx.measureText(c).width + 56);
  let cx = 960 - (cw.reduce((a, b) => a + b, 0) + 16 * (chips.length - 1)) / 2;
  chips.forEach((c, i) => {
    const e = spring(t - 4.3 - i * 0.07, 15, 8), out = 1 - prog(t, 4.75 + i * 0.05, 5.05 + i * 0.05);
    if (e <= 0) return;
    ctx.globalAlpha = intro * clamp(e) * out;
    const y = 652 + (1 - e) * 30;
    rr(cx, y, cw[i], 46, 23); ctx.fillStyle = 'rgba(255,255,255,0.06)'; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,0.14)'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = i === 2 ? '#C9BCFF' : 'rgba(255,255,255,0.7)'; ctx.fillText(c, cx + 28, y + 31);
    cx += cw[i] + 16;
  });
  ctx.restore();
  // color flash handed over from the zoom into the dot
  const fl = 1 - ease.out(prog(t, 4.0, 4.45));
  if (fl > 0) { ctx.save(); ctx.globalAlpha = fl; ctx.fillStyle = C.violet; ctx.fillRect(-50, -50, W + 100, H + 100); ctx.restore(); }
}

// ============================================================ SCENE 4 ======
// Infinite canvas: the page generates element by element, plus two variations.
const THEMES = {
  midnight: { name: 'v1 — Midnight', bg: '#0F0D1A', fg: '#FFFFFF', sub: 'rgba(255,255,255,0.55)', card: '#181530', line: 'rgba(255,255,255,0.09)', accent: '#7C5CFF', accent2: '#FF4FD8', btnFg: '#FFFFFF', skel: 'rgba(255,255,255,0.07)', glow: 'rgba(124,92,255,0.6)' },
  light: { name: 'v2 — Daylight', bg: '#F5F3FF', fg: '#15121F', sub: 'rgba(21,18,31,0.55)', card: '#FFFFFF', line: 'rgba(21,18,31,0.1)', accent: '#5B3DF5', accent2: '#00B3D6', btnFg: '#FFFFFF', skel: 'rgba(21,18,31,0.07)', glow: 'rgba(91,61,245,0.35)' },
  ember: { name: 'v3 — Ember', bg: '#170D09', fg: '#FFF1E6', sub: 'rgba(255,241,230,0.55)', card: '#25150E', line: 'rgba(255,241,230,0.1)', accent: '#FF6B2C', accent2: '#FFC85C', btnFg: '#170D09', skel: 'rgba(255,241,230,0.07)', glow: 'rgba(255,107,44,0.55)' },
};
const PLANS = [
  { name: 'Scout', price: '$0', blurb: 'For weekend orbiters', perks: ['1 seat on the shuttle', 'Low-orbit views', 'Freeze-dried snacks'], cta: 'Start free' },
  { name: 'Pioneer', price: '$29', blurb: 'For serious explorers', perks: ['Priority boarding', 'Mars surface walk', 'Zero-g lounge'], cta: 'Launch now', popular: true },
  { name: 'Colony', price: '$99', blurb: 'For whole crews', perks: ['Private habitat', 'Unlimited rovers', 'Dedicated pilot'], cta: 'Talk to us' },
];
const CARD_ANCHORS = { badge: [306, 36], name: [118, 50], price: [150, 135], perks: [230, 254], button: [302, 335] };
const reveal = (a, d = 0.3) => ({ al: clamp(a / d), dy: (1 - spring(a, 16, 9)) * 18 });

function skeleton(x, y, w, h, th, t, r = 8) {
  rr(x, y, w, h, r); ctx.fillStyle = th.skel; ctx.fill();
  ctx.save(); ctx.clip();
  const sx = x + ((t * 1100) % (w + 400)) - 200;
  const g = ctx.createLinearGradient(sx - 120, 0, sx + 120, 0);
  g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, th.skel); g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g; ctx.fillRect(x, y, w, h); ctx.restore();
}
function el(t, t0, x, y, w, h, th, fn) {
  const a = t - t0;
  if (a < 0) { skeleton(x, y, w, h, th, t); return; }
  const r = reveal(a);
  if (r.al < 1) { const g = GA; GA *= 1 - r.al; setA(1); skeleton(x, y, w, h, th, t); GA = g; }
  ctx.save(); setA(r.al); ctx.translate(0, r.dy); fn(); ctx.restore();
}
function drawCard(th, plan, x, y, t, t0, o = {}) {
  const a = t - t0;
  if (a < 0) { setA(1); skeleton(x, y, 330, 380, th, t, 18); return; }
  const r = reveal(a, 0.3), lift = o.lift || 1, g0 = GA;
  if (r.al < 1) { GA = g0 * (1 - r.al); setA(1); skeleton(x, y, 330, 380, th, t, 18); GA = g0; }
  ctx.save();
  ctx.translate(x + 165, y + 190); const s = lift * lerp(0.94, 1, spring(a, 15, 8)); ctx.scale(s, s); ctx.translate(-165, -190);
  GA = g0 * r.al;
  setA(1);
  if (plan.popular) { ctx.shadowColor = th.glow; ctx.shadowBlur = 50 * (o.glow || 1); }
  rr(0, 0, 330, 380, 18); ctx.fillStyle = th.card; ctx.fill(); ctx.shadowBlur = 0; ctx.shadowColor = 'transparent';
  ctx.lineWidth = plan.popular ? 2.5 : 1.5;
  ctx.strokeStyle = plan.popular ? (() => { const g = ctx.createLinearGradient(0, 0, 330, 380); g.addColorStop(0, th.accent); g.addColorStop(1, th.accent2); return g; })() : th.line;
  ctx.stroke();
  const sub = (off, fn) => { const q = reveal(a - off, 0.25); if (q.al <= 0) return; ctx.save(); setA(q.al); ctx.translate(0, q.dy * 0.6); fn(); ctx.restore(); };
  const accentGrad = () => { const g = ctx.createLinearGradient(0, 0, 330, 0); g.addColorStop(0, th.accent); g.addColorStop(1, th.accent2); return g; };
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  if (plan.popular) sub(0.1, () => {
    rr(194, 22, 116, 28, 14); ctx.fillStyle = accentGrad(); ctx.fill();
    ctx.font = F(700, 13, 'Inter'); ctx.fillStyle = th.btnFg; ctx.textAlign = 'center'; ctx.fillText('Most popular', 252, 41);
  });
  sub(0.12, () => { ctx.font = F(700, 24, 'Inter'); ctx.fillStyle = th.fg; ctx.fillText(plan.name, 28, 58); });
  sub(0.18, () => { ctx.font = F(400, 15, 'Inter'); ctx.fillStyle = th.sub; ctx.fillText(plan.blurb, 28, 84); });
  sub(0.24, () => {
    ctx.font = F(800, 64); ctx.fillStyle = th.fg; ctx.fillText(plan.price, 26, 158);
    const w = ctx.measureText(plan.price).width;
    ctx.font = F(500, 18, 'Inter'); ctx.fillStyle = th.sub; ctx.fillText('/ month', 34 + w, 156);
  });
  sub(0.3, () => { ctx.fillStyle = th.line; ctx.fillRect(28, 184, 274, 1.5); });
  plan.perks.forEach((p, j) => sub(0.34 + j * 0.06, () => {
    const y = 222 + j * 34;
    ctx.fillStyle = th.accent; ctx.globalAlpha *= 0.22; ctx.beginPath(); ctx.arc(38, y - 6, 11, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha /= 0.22;
    ctx.strokeStyle = th.accent; ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(33, y - 6); ctx.lineTo(37, y - 2); ctx.lineTo(44, y - 11); ctx.stroke();
    ctx.font = F(500, 16, 'Inter'); ctx.fillStyle = th.fg; ctx.fillText(p, 60, y);
  }));
  sub(0.55, () => {
    rr(28, 312, 274, 46, 12); ctx.fillStyle = plan.popular ? accentGrad() : th.line; ctx.fill();
    ctx.font = F(700, 17, 'Inter'); ctx.fillStyle = plan.popular ? th.btnFg : th.fg; ctx.textAlign = 'center'; ctx.fillText(plan.cta, 165, 341);
  });
  GA = g0;
  ctx.restore();
}
function drawFrame(th, x0, y0, t, t0, o = {}) {
  const a = t - t0;
  if (a < 0) return;
  const pop = o.main ? 1 : ease.out5(clamp(a / 0.45)), g0 = GA;
  GA = pop;
  ctx.save();
  ctx.translate(x0 + 600, y0 + 375); const sc = o.main ? 1 : lerp(0.9, 1, pop); ctx.scale(sc, sc); ctx.translate(-600, -375);
  setA(clamp(a / 0.3)); ctx.font = F(600, 24, 'Inter'); ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.textAlign = 'left';
  ctx.fillText(th.name, 4, -22);
  setA(1);
  ctx.shadowColor = 'rgba(0,0,0,0.55)'; ctx.shadowBlur = 70; ctx.shadowOffsetY = 24;
  rr(0, 0, 1200, 750, 18); ctx.fillStyle = th.bg; ctx.fill();
  ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.save(); rr(0, 0, 1200, 750, 18); ctx.clip();
  setA(clamp(a / 0.6));
  blob(600, -60, 700, th.accent, 0.22 * GA);
  setA(1);
  el(t, t0 + 0.05, 40, 30, 120, 36, th, () => {
    const g = ctx.createLinearGradient(46, 36, 70, 60); g.addColorStop(0, th.accent); g.addColorStop(1, th.accent2);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(58, 48, 12, 0, Math.PI * 2); ctx.fill();
    ctx.font = F(800, 26); ctx.fillStyle = th.fg; ctx.textAlign = 'left'; ctx.fillText('Ares', 80, 57);
  });
  el(t, t0 + 0.1, 455, 36, 290, 24, th, () => {
    ctx.font = F(500, 18, 'Inter'); ctx.fillStyle = th.sub; ctx.textAlign = 'center'; ctx.fillText('Flights      Pricing      Habitats', 600, 55);
  });
  el(t, t0 + 0.15, 1040, 28, 124, 40, th, () => {
    rr(1040, 28, 124, 40, 20); ctx.strokeStyle = th.line; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.font = F(600, 16, 'Inter'); ctx.fillStyle = th.fg; ctx.textAlign = 'center'; ctx.fillText('Sign in', 1102, 54);
  });
  el(t, t0 + 0.25, 260, 122, 680, 62, th, () => {
    ctx.font = F(800, 58); ctx.fillStyle = th.fg; ctx.textAlign = 'center'; ctx.fillText('Pricing for the red planet.', 600, 172);
  });
  el(t, t0 + 0.38, 420, 200, 360, 26, th, () => {
    ctx.font = F(400, 21, 'Inter'); ctx.fillStyle = th.sub; ctx.textAlign = 'center'; ctx.fillText('Simple plans. No oxygen fees. Cancel anytime.', 600, 220);
  });
  PLANS.forEach((p, i) => {
    if (o.hideCard === i) return;
    drawCard(th, p, 75 + i * 360, 280, t, t0 + 0.5 + i * 0.16, i === 1 ? { lift: o.lift } : {});
  });
  ctx.restore(); ctx.restore();
  GA = g0;
}
function cam4(t) {
  let s = expLerp(1, 0.45, ease.inOut(prog(t, 7.0, 8.4)));
  s *= lerp(1, 1.08, ease.inOut(prog(t, 8.4, 9.2)));
  const z = ease.inOut(prog(t, 9.2, 10.0));
  s = expLerp(s, 1.7, z);
  const drift = prog(t, 6.6, 7.6) * (1 - z);
  return { s, cx: Math.sin(t * 0.7) * 30 * drift, cy: lerp(0, 95, z) + Math.cos(t * 0.5) * 12 * drift };
}
function keyframes(t, ks) {
  if (t <= ks[0][0]) return ks[0][1];
  for (let i = 1; i < ks.length; i++) if (t <= ks[i][0]) {
    const k = ease.inOut(prog(t, ks[i - 1][0], ks[i][0]));
    return [lerp(ks[i - 1][1][0], ks[i][1][0], k), lerp(ks[i - 1][1][1], ks[i][1][1], k)];
  }
  return ks[ks.length - 1][1];
}
function cursor(x, y, s, color, label, alpha, press = 1) {
  if (alpha <= 0) return;
  ctx.save(); ctx.globalAlpha = alpha; ctx.translate(x, y); ctx.scale(press / s, press / s);
  ctx.shadowColor = 'rgba(0,0,0,0.4)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 4;
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, 30); ctx.lineTo(8, 23); ctx.lineTo(14, 36); ctx.lineTo(20, 33); ctx.lineTo(14, 21); ctx.lineTo(24, 21); ctx.closePath();
  ctx.fillStyle = color; ctx.fill(); ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
  ctx.font = F(600, 16, 'Inter'); const w = ctx.measureText(label).width + 24;
  rr(20, 36, w, 30, 15); ctx.fillStyle = color; ctx.fill();
  ctx.fillStyle = '#fff'; ctx.textAlign = 'left'; ctx.fillText(label, 32, 57);
  ctx.restore();
}
function scene4(t) {
  const cam = cam4(t);
  ctx.save();
  grid(0.09 * prog(t, 6.5, 6.6) + 0.06 * prog(t, 7.0, 8.0), cam.s, 960 - cam.cx * cam.s, 540 - cam.cy * cam.s);
  ctx.translate(960, 540); ctx.scale(cam.s, cam.s); ctx.translate(-cam.cx, -cam.cy);
  const lift = 1 + 0.04 * ease.out(prog(t, 9.15, 9.4));
  drawFrame(THEMES.light, -1920, -375, t, 7.3);
  drawFrame(THEMES.ember, 720, -375, t, 7.48);
  drawFrame(THEMES.midnight, -600, -375, t, 6.55, { main: true, lift, hideCard: t >= 10.0 ? 1 : -1 });
  // selection on the Pioneer card
  const sel = ease.out(prog(t, 9.15, 9.3)) * (1 - prog(t, 9.6, 9.9));
  if (sel > 0) {
    ctx.save(); ctx.globalAlpha = sel; ctx.translate(0, 95); ctx.scale(lift, lift);
    ctx.strokeStyle = C.cyan; ctx.lineWidth = 2 / cam.s; ctx.strokeRect(-171, -196, 342, 392);
    ctx.fillStyle = '#fff';
    for (const [hx, hy] of [[-171, -196], [171, -196], [-171, 196], [171, 196]]) {
      const hs = 10 / cam.s; ctx.fillRect(hx - hs / 2, hy - hs / 2, hs, hs); ctx.strokeRect(hx - hs / 2, hy - hs / 2, hs, hs);
    }
    ctx.scale(1 / cam.s, 1 / cam.s);
    ctx.font = F(600, 15, 'Inter'); ctx.textAlign = 'center';
    rr(-44, 206 * cam.s, 88, 26, 6); ctx.fillStyle = C.cyan; ctx.fill(); ctx.fillStyle = '#06050B'; ctx.fillText('330 × 380', 0, 206 * cam.s + 18);
    ctx.restore();
  }
  // cursors
  const ai = keyframes(t, [[6.55, [-100, -120]], [6.72, [-520, -320]], [6.98, [80, -200]], [7.25, [-330, -60]], [7.52, [40, -20]], [7.8, [380, -40]], [8.15, [1380, -220]], [8.55, [1320, 120]]]);
  cursor(ai[0], ai[1], cam.s, C.violet, '✦ magicpath', prog(t, 6.55, 6.7) * (1 - prog(t, 8.5, 8.8)));
  const me = keyframes(t, [[8.5, [760, 640]], [9.1, [95, 248]], [9.9, [110, 262]]]);
  const press = 1 - 0.2 * Math.sin(Math.PI * prog(t, 9.08, 9.22));
  cursor(me[0], me[1], cam.s, C.magenta, 'Ak David', prog(t, 8.5, 8.7) * (1 - prog(t, 9.55, 9.8)), press);
  ring(95, 248, t, 9.12, 60, 0.5, 4, C.magenta);
  ctx.restore();
  // status pill (screen space)
  const sa = ease.out5(prog(t, 6.6, 7.0)) * (1 - prog(t, 9.0, 9.3));
  if (sa > 0) {
    ctx.save(); ctx.globalAlpha = sa; ctx.textAlign = 'left'; ctx.font = F(600, 20, 'Inter');
    const sw = prog(t, 8.55, 8.75), labels = ['Generating 3 variations…', '3 variations · generated in 2.1s'];
    const w = lerp(ctx.measureText(labels[0]).width, ctx.measureText(labels[1]).width, ease.inOut(sw)) + 84, y = 96 - (1 - sa) * 30, lx = 960 - w / 2;
    rr(lx, y, w, 52, 26); ctx.fillStyle = 'rgba(20,17,36,0.85)'; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.save(); rr(lx, y, w, 52, 26); ctx.clip();
    ctx.globalAlpha = sa * (1 - sw);
    ctx.fillStyle = brandGrad(lx + 20, 0, lx + 48, 0); sparkle(lx + 34, y + 26 - sw * 30, 13, t * 5); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.fillText(labels[0], lx + 58, y + 33 - sw * 30);
    if (sw > 0) {
      ctx.globalAlpha = sa * sw; const dy = (1 - sw) * 30;
      ctx.fillStyle = '#3BE8A0'; ctx.beginPath(); ctx.arc(lx + 34, y + 26 + dy, 11, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#06050B'; ctx.lineWidth = 2.6; ctx.beginPath(); ctx.moveTo(lx + 29, y + 26 + dy); ctx.lineTo(lx + 33, y + 30 + dy); ctx.lineTo(lx + 40, y + 21 + dy); ctx.stroke();
      ctx.fillStyle = '#fff'; ctx.fillText(labels[1], lx + 58, y + 33 + dy);
    }
    ctx.restore();
    ctx.restore();
  }
  // fade the world out behind the hero card
  const f = ease.inOut(prog(t, 10.0, 10.4));
  if (f > 0) { ctx.save(); ctx.globalAlpha = f; ctx.fillStyle = C.bg; ctx.fillRect(-50, -50, W + 100, H + 100); ctx.restore(); }
}

// ============================================================ SCENE 5 ======
// The selected card becomes code. Wires connect each element to its JSX line.
const CODE = [
  'export function PlanCard() {',
  '  return (',
  '    <Card plan="pioneer" popular>',
  '      <Badge>Most popular</Badge>',
  '      <Title>Pioneer</Title>',
  '      <Price amount={29} per="month" />',
  '      <Perks items={perks} />',
  '      <Button glow>Launch now</Button>',
  '    </Card>',
  '  );',
  '}',
];
const LINKS = { 3: 'badge', 4: 'name', 5: 'price', 6: 'perks', 7: 'button' };
const TOK = /(\b(?:export|function|return)\b)|(<\/?[A-Za-z]+|\/?>)|("[^"]*")|(\{[^{}]*\})|([a-z]+(?==))|(\b(?:popular|glow)\b)|([A-Za-z]\w*(?=\())|(.)/g;
const TOK_COLORS = ['#B69CFF', '#5EE7FF', '#FFC85C', '#FF7AD9', '#9AF0C0', '#9AF0C0', '#FFFFFF', 'rgba(255,255,255,0.78)'];
const CODE_TOKENS = CODE.map(line => { const out = []; let m; TOK.lastIndex = 0; while ((m = TOK.exec(line))) { const g = m.slice(1).findIndex(Boolean); out.push([m[0], TOK_COLORS[g]]); } return out; });
const LINE_START = []; { let n = 0; for (const l of CODE) { LINE_START.push(n); n += l.length; } LINE_START.push(n); }
const CODE_T0 = 10.65, CODE_T1 = 12.0;
const PANEL = { x: 1010, y: 190, w: 790, h: 700 };
function bezierPartial(p, q, k) {
  const c1 = [p[0] + 150, p[1]], c2 = [q[0] - 150, q[1]];
  ctx.beginPath();
  for (let i = 0; i <= 40; i++) {
    const u = (i / 40) * k, v = 1 - u;
    const x = v * v * v * p[0] + 3 * v * v * u * c1[0] + 3 * v * u * u * c2[0] + u * u * u * q[0];
    const y = v * v * v * p[1] + 3 * v * v * u * c1[1] + 3 * v * u * u * c2[1] + u * u * u * q[1];
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  return ctx;
}
function scene5(t) {
  const m = ease.inOut(prog(t, 10.05, 10.65));
  const imp = ease.inExpo(prog(t, 12.2, 12.55));
  if (imp >= 1) return;
  let S = lerp(1.7 * 1.04, 1.4, m), cx = lerp(960, 560, m);
  const cy = 540;
  ctx.save();
  ctx.translate(960, 540); ctx.scale(1 - imp, 1 - imp); ctx.translate(-960, -540);
  ctx.globalAlpha = 1 - imp;
  // halo
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; blob(cx, cy, 520 * S / 1.4, C.violet, 0.25 * (1 - imp)); ctx.restore();
  // hero card
  ctx.save(); ctx.translate(cx, cy); ctx.scale(S, S); ctx.translate(-165, -190);
  GA = 1 - imp; drawCard(THEMES.midnight, PLANS[1], 0, 0, t, -10, { glow: 1.6 }); GA = 1;
  ctx.restore();
  // code panel
  const p = ease.out5(prog(t, 10.25, 10.85));
  const px = PANEL.x + (1 - p) * 180;
  ctx.globalAlpha = p * (1 - imp);
  ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 60; ctx.shadowOffsetY = 20;
  rr(px, PANEL.y, PANEL.w, PANEL.h, 20); ctx.fillStyle = 'rgba(16,14,28,0.94)'; ctx.fill();
  ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0; ctx.strokeStyle = 'rgba(255,255,255,0.12)'; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.04)'; ctx.fillRect(px + 1, PANEL.y + 60, PANEL.w - 2, 1.5);
  ['#FF5F57', '#FEBC2E', '#28C840'].forEach((c, i) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(px + 32 + i * 24, PANEL.y + 30, 7, 0, Math.PI * 2); ctx.fill(); });
  ctx.font = MONO(500, 17); ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.textAlign = 'left'; ctx.fillText('PlanCard.tsx', px + 120, PANEL.y + 36);
  ctx.font = F(600, 15, 'Inter'); const chip = 'React · Tailwind', cw = ctx.measureText(chip).width + 28;
  rr(px + PANEL.w - cw - 22, PANEL.y + 15, cw, 30, 15); ctx.fillStyle = 'rgba(124,92,255,0.2)'; ctx.fill();
  ctx.fillStyle = '#C9BCFF'; ctx.fillText(chip, px + PANEL.w - cw - 8, PANEL.y + 35);
  // typed code
  const shown = Math.floor(prog(t, CODE_T0, CODE_T1) * LINE_START[CODE.length]);
  ctx.font = MONO(500, 23); const chw = ctx.measureText('M').width;
  const ox = px + 82, oy = PANEL.y + 112, lh = 46;
  let caret = null;
  CODE_TOKENS.forEach((toks, li) => {
    const y = oy + li * lh;
    ctx.fillStyle = 'rgba(255,255,255,0.22)'; ctx.textAlign = 'right'; ctx.fillText(String(li + 1), px + 52, y); ctx.textAlign = 'left';
    const avail = shown - LINE_START[li];
    if (avail <= 0) { if (avail === 0 && !caret) caret = [ox, y]; return; }
    let col = 0;
    for (const [s, c] of toks) {
      if (col >= avail) break;
      const part = s.slice(0, avail - col);
      ctx.fillStyle = c; ctx.fillText(part, ox + col * chw, y); col += part.length;
    }
    if (avail < CODE[li].length) caret = [ox + col * chw, y];
  });
  if (caret && t < CODE_T1 + 0.05) { ctx.fillStyle = C.cyan; ctx.fillRect(caret[0] + 2, caret[1] - 22, 3, 30); }
  // wires
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round';
  for (const [li, key] of Object.entries(LINKS)) {
    const st = CODE_T0 + (LINE_START[li] / LINE_START[CODE.length]) * (CODE_T1 - CODE_T0);
    const k = ease.out(prog(t, st, st + 0.35));
    if (k <= 0) continue;
    const a = CARD_ANCHORS[key];
    const P = [cx + (a[0] - 165) * S, cy + (a[1] - 190) * S], Q = [ox - 30, oy + li * lh - 8];
    const g = ctx.createLinearGradient(P[0], 0, Q[0], 0); g.addColorStop(0, C.magenta); g.addColorStop(1, C.cyan);
    ctx.globalAlpha = 0.25 * p * (1 - imp); ctx.strokeStyle = g; ctx.lineWidth = 9; bezierPartial(P, Q, k).stroke();
    ctx.globalAlpha = 0.9 * p * (1 - imp); ctx.lineWidth = 2; bezierPartial(P, Q, k).stroke();
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(P[0], P[1], 5, 0, Math.PI * 2); ctx.fill();
    if (k >= 1) { ctx.beginPath(); ctx.arc(Q[0], Q[1], 4, 0, Math.PI * 2); ctx.fill(); }
    // pulse travelling down each wire
    const u = ((t - st) * 0.9) % 1, v = 1 - u;
    const c1 = [P[0] + 150, P[1]], c2 = [Q[0] - 150, Q[1]];
    const bx = v * v * v * P[0] + 3 * v * v * u * c1[0] + 3 * v * u * u * c2[0] + u * u * u * Q[0];
    const by = v * v * v * P[1] + 3 * v * v * u * c1[1] + 3 * v * u * u * c2[1] + u * u * u * Q[1];
    if (k >= 1) { ctx.globalAlpha = p * (1 - imp); blob(bx, by, 18, 'rgba(255,255,255,1)', ctx.globalAlpha); }
  }
  ctx.restore();
  // deploy toast
  const ta = spring(t - 12.0, 14, 8);
  if (ta > 0) {
    ctx.globalAlpha = clamp(ta) * (1 - imp);
    const tw = 330, tx = px + PANEL.w - tw - 28, ty = PANEL.y + PANEL.h - 80 + (1 - ta) * 30;
    rr(tx, ty, tw, 52, 14); ctx.fillStyle = 'rgba(59,232,160,0.14)'; ctx.fill(); ctx.strokeStyle = 'rgba(59,232,160,0.5)'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.fillStyle = '#3BE8A0'; ctx.font = F(600, 18, 'Inter'); ctx.fillText('✓  Shipped to ares.app', tx + 22, ty + 33);
  }
  // caption
  const ca = ease.out5(prog(t, 10.8, 11.4));
  ctx.globalAlpha = ca * (1 - imp); ctx.textAlign = 'center'; ctx.font = F(700, 34);
  ctx.textAlign = 'left';
  const c1 = 'Design in.  ', c2 = 'Production React out.', w1 = ctx.measureText(c1).width, w2 = ctx.measureText(c2).width, x1 = 960 - (w1 + w2) / 2;
  ctx.fillStyle = '#fff'; ctx.fillText(c1, x1, 990 - (1 - ca) * 20);
  ctx.fillStyle = brandGrad(x1 + w1, 0, x1 + w1 + w2, 0); ctx.fillText(c2, x1 + w1, 990 - (1 - ca) * 20);
  ctx.restore();
}

// ============================================================ SCENE 6 ======
// Everything implodes, the path loops an infinity sign and lands as the logo.
function drawMark(x, y, size, t, t0) {
  const s = spring(t - t0, 13, 7);
  if (s <= 0) return;
  ctx.save(); ctx.translate(x, y); ctx.rotate((1 - s) * -0.5); ctx.scale(s, s);
  ctx.shadowColor = 'rgba(124,92,255,0.8)'; ctx.shadowBlur = 70;
  const g = ctx.createLinearGradient(-size / 2, -size / 2, size / 2, size / 2);
  g.addColorStop(0, C.cyan); g.addColorStop(0.5, C.violet); g.addColorStop(1, C.magenta);
  rr(-size / 2, -size / 2, size, size, size * 0.28); ctx.fillStyle = g; ctx.fill();
  ctx.shadowBlur = 0;
  const hl = ctx.createLinearGradient(0, -size / 2, 0, size / 2); hl.addColorStop(0, 'rgba(255,255,255,0.35)'); hl.addColorStop(0.5, 'rgba(255,255,255,0)');
  ctx.fillStyle = hl; ctx.fill();
  const u = size;
  const d = ease.out(prog(t, t0 + 0.05, t0 + 0.55));
  ctx.strokeStyle = '#fff'; ctx.lineWidth = u * 0.085; ctx.lineCap = 'round';
  ctx.setLineDash([u * 1.1 * d, u * 2]);
  ctx.beginPath(); ctx.moveTo(-0.27 * u, 0.24 * u); ctx.bezierCurveTo(-0.24 * u, -0.32 * u, 0.04 * u, 0.36 * u, 0.13 * u, -0.1 * u); ctx.stroke();
  ctx.setLineDash([]);
  const st = spring(t - t0 - 0.4, 16, 7);
  if (st > 0) { ctx.fillStyle = '#fff'; sparkle(0.2 * u, -0.2 * u, 0.15 * u * st, (1 - st) * 2); ctx.fill(); }
  ctx.restore();
}
function scene6(t) {
  const O = { x: 960, y: 500 };
  // flash
  const fl = Math.exp(-Math.max(0, t - 12.55) * 7) * prog(t, 12.48, 12.55);
  if (fl > 0.01) { ctx.save(); ctx.globalCompositeOperation = 'lighter'; blob(O.x, O.y, 1300, 'rgba(230,225,255,1)', 0.85 * fl); ctx.restore(); }
  const h = ease.inOut(prog(t, 12.5, 13.22)), tl = ease.inOut(prog(t, 12.66, 13.28));
  if (h > 0 && t < 13.32) {
    strokeTrail(path6, tl, h, 7);
    const p = pathAt(path6, h); flare(p[0], p[1], 1, t, 1 - prog(t, 13.22, 13.3));
  }
  ring(O.x, O.y, t, 13.27, 900, 0.9, 8, C.violet);
  ring(O.x, O.y, t, 13.33, 600, 0.7, 3, C.cyan);
  burst(O.x, O.y, t, 13.27, 23, 110, 900);
  const LK = WMLK, M = 150;
  const slide = ease.inOut(prog(t, 13.62, 14.15));
  const mx = lerp(O.x, LK.markX, slide);
  if (t > 13.6) {
    drawLetters(LK, t, 13.72, { stagger: 0.035, dur: 0.6, slideX: 120, clipX: mx + M / 2 + 4 });
    drawIDot(LK.idot, spring(t - 14.0, 16, 7));
  }
  drawMark(mx, O.y, M, t, 13.26);
  // tagline
  ctx.save(); ctx.font = F(500, 38); ctx.textAlign = 'left';
  const words = ['Prompt it.', 'Design it.', 'Ship it.'], gap = 30, ws = words.map(w => ctx.measureText(w).width);
  let x = 960 - (ws.reduce((a, b) => a + b, 0) + gap * 2) / 2;
  ctx.beginPath(); ctx.rect(0, 610, W, 80); ctx.clip();
  words.forEach((w, i) => {
    const e = ease.out5(prog(t, 14.0 + i * 0.11, 14.55 + i * 0.11));
    ctx.globalAlpha = e; ctx.fillStyle = i === 2 ? brandGrad(x, 0, x + ws[i], 0) : 'rgba(255,255,255,0.75)';
    ctx.fillText(w, x, 668 + (1 - e) * 60); x += ws[i] + gap;
  });
  ctx.restore();
  // credit
  const ce = ease.out5(prog(t, 14.3, 14.85));
  if (ce > 0) {
    ctx.save(); ctx.textAlign = 'center'; ctx.globalAlpha = ce;
    ctx.font = MONO(600, 18); ctx.letterSpacing = '7px'; ctx.fillStyle = 'rgba(255,255,255,0.9)';
    const label = 'MOTION DESIGN BY AK DAVID', lw = ctx.measureText(label).width;
    ctx.fillText(label, 960 + 3.5, 812);
    ctx.font = MONO(500, 14); ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.fillText('SHOWREEL — 2026', 960 + 3.5, 846);
    const lg = 160 * ce;
    ctx.fillStyle = brandGrad(960 - lw / 2 - 30 - lg, 0, 960 + lw / 2 + 30 + lg, 0);
    ctx.fillRect(960 - lw / 2 - 30 - lg, 805, lg, 1.5); ctx.fillRect(960 + lw / 2 + 30, 805, lg, 1.5);
    ctx.restore();
  }
  // anamorphic light sweep across the lockup
  const sw = prog(t, 14.2, 14.9);
  if (sw > 0 && sw < 1) flare(lerp(LK.markX - 200, LK.x0 + LK.width + 200, ease.inOut(sw)), O.y, 0.7, t, Math.sin(Math.PI * sw) * 0.8, 700);
}

// ============================================================= render ======
function drawScene(t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  GA = 1;
  background(t);
  ctx.save();
  const sh = shake(t); ctx.translate(sh[0], sh[1]);
  if (t < 4.1) scene12(t);
  if (t >= 6.5 && t < 10.45) scene4(t);
  if (t >= 3.98 && t < 6.6) scene3(t);
  if (t >= 10.0 && t < 12.6) scene5(t);
  if (t >= 12.45) scene6(t);
  ctx.restore();
}
const acc = document.createElement('canvas'); acc.width = W; acc.height = H;
const actx = acc.getContext('2d');
function paintFrame(f, sub = 4) {
  if (sub <= 1) drawScene(f / FPS);
  else {
    for (let k = 0; k < sub; k++) {
      const t = (f + ((k + 0.5) / sub - 0.5) * SHUTTER) / FPS;
      drawScene(clamp(t, 0, DUR - 1e-4));
      actx.globalAlpha = 1 / (k + 1); actx.drawImage(cv, 0, 0);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'copy';
    ctx.drawImage(acc, 0, 0); ctx.globalCompositeOperation = 'source-over';
  }
  post(f / FPS, f);
}

async function init() {
  await Promise.all([F(800, 200), F(600, 52), F(500, 42), F(700, 34), F(500, 44, 'Inter'), F(400, 15, 'Inter'), F(600, 15, 'Inter'), F(700, 15, 'Inter'), MONO(500, 23), MONO(600, 18)].map(f => document.fonts.load(f)));
  TITTLE = measureTittle();
  WM2 = layoutWord(210, null, 520);
  const lk = layoutWord(150, 0, 500), M = 150, gap = 46, total = M + gap + lk.width;
  const markX = 960 - total / 2 + M / 2;
  WMLK = layoutWord(150, markX + M / 2 + gap, 500); WMLK.markX = markX;
  const d = WM2.idot;
  path1 = splinePath([[-160, 760], [240, 260], [600, 820], [960, 300], [1340, 860], [1760, 560], [1640, 170], [1240, 140], [d.x + 120, d.y - 90], [d.x, d.y]]);
  const lem = [];
  for (let i = 0; i <= 400; i++) {
    const th = Math.PI / 2 + (i / 400) * Math.PI * 2, s = Math.sin(th), c = Math.cos(th), den = 1 + s * s;
    lem.push([960 + 600 * c / den, 500 + 600 * s * c / den]);
  }
  path6 = withLengths(lem);
  window.reelReady = true;
}

window.renderFrame = (f, sub = 4, q = 0.95) => { paintFrame(f, sub); return cv.toDataURL('image/jpeg', q).split(',')[1]; };
window.renderPNG = (f, sub = 4) => { paintFrame(f, sub); return cv.toDataURL('image/png').split(',')[1]; };

init().then(() => {
  if (new URLSearchParams(location.search).has('render')) return;
  // live preview: space pauses, arrows scrub
  let t0 = performance.now(), paused = false, pt = 0;
  addEventListener('keydown', e => {
    if (e.code === 'Space') { paused = !paused; if (!paused) t0 = performance.now() - pt * 1000; }
    if (e.code === 'ArrowRight' || e.code === 'ArrowLeft') { pt = clamp(pt + (e.code === 'ArrowRight' ? 0.5 : -0.5), 0, DUR); t0 = performance.now() - pt * 1000; }
  });
  const loop = now => {
    if (!paused) pt = ((now - t0) / 1000) % DUR;
    paintFrame(Math.floor(pt * FPS), 1);
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
});
