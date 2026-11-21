// Paints the frame at moment t (seconds): which slide is visible, which elements have appeared, the motions.
// T(t) returns 'dyn' while the frame moves, else a key of the state — the same key means the same frame,
// so the renderer can reuse the previous screenshot.
//
// In a slide:  data-b="N"  appears at the start of line N of that slide;  data-d="0.5" — seconds later;
//              data-fx="up|fade|pop|left|right" (up by default);  data-hl="N" data-hl-end="M" — sets --h 0→1
//              between lines N and M (style it, e.g. a ring);  .kb img — slow zoom;  .bob — gentle float.
// Own motions: window.TV_CUSTOM = { "<slide id>": ctx => ({dyn, key}) } in the video's custom.js,
//              ctx = {t, local, len, slide, beatStart(n)}.
let TL, FADE, slides, items, hls, kbs, bobs;
const cl = x => Math.max(0, Math.min(1, x));
const easeOut = p => 1 - Math.pow(1 - p, 3);
const backOut = p => { const c = 1.6; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
const DUR = 0.55;

window.setup = (tl, fade) => {
  TL = tl; FADE = fade;
  slides = [...document.querySelectorAll('.slide')];
  const at = (i, b) => { const x = TL[i].beats[+b]; if (!x) throw new Error(`${TL[i].id}: no line ${b} (data-b/data-hl)`); return x.start; };
  items = slides.map((sl, i) => [...sl.querySelectorAll('[data-b]')].map(el => ({ el, at: at(i, el.dataset.b) + (+el.dataset.d || 0), fx: el.dataset.fx || 'up' })));
  hls = slides.map((sl, i) => [...sl.querySelectorAll('[data-hl]')].map(el => ({ el, a: at(i, el.dataset.hl), b: el.dataset.hlEnd != null ? at(i, el.dataset.hlEnd) : 1e9 })));
  kbs = slides.map(sl => [...sl.querySelectorAll('.kb img')]);
  bobs = slides.map(sl => [...sl.querySelectorAll('.bob')]);
};

function paint(i, t) {
  let dyn = false, done = 0;
  for (const it of items[i]) {
    const p = cl((t - it.at) / DUR);
    if (p > 0 && p < 1) dyn = true; else if (p === 1) done++;
    const e = easeOut(p), s = it.el.style;
    s.opacity = it.fx === 'pop' ? Math.min(1, p * 2.5) : e;
    s.transform = it.fx === 'pop' ? `scale(${0.75 + 0.25 * backOut(p)})`
      : it.fx === 'left' ? `translateX(${(1 - e) * -60}px)` : it.fx === 'right' ? `translateX(${(1 - e) * 60}px)`
      : it.fx === 'fade' ? '' : `translateY(${(1 - e) * 40}px)`;
  }
  let hk = '';
  for (const h of hls[i]) {
    const v = cl((t - h.a) / 0.4) * (1 - cl((t - h.b) / 0.4));
    if (v > 0 && v < 1) dyn = true; hk += v === 1 ? '1' : '0';
    h.el.style.setProperty('--h', v);
  }
  const local = t - TL[i].start, len = TL[i].end - TL[i].start;
  for (const img of kbs[i]) { img.style.scale = 1.12 + 0.08 * local / len; dyn = true; }
  for (const b of bobs[i]) { b.style.translate = `0 ${Math.sin(local * 1.3) * 14}px`; b.style.rotate = `${Math.sin(local * 0.9) * 1.5}deg`; dyn = true; }
  let ck = '';
  const custom = (window.TV_CUSTOM || {})[TL[i].id];
  if (custom) {
    const r = custom({ t, local, len, slide: slides[i], beatStart: n => TL[i].beats[n].start }) || {};
    dyn = dyn || !!r.dyn; ck = r.key || '';
  }
  return { dyn, key: `${done}.${hk}.${ck}` };
}

window.T = t => {
  let cur = TL.findIndex(s => t < s.end); if (cur < 0) cur = TL.length - 1;
  let dyn = false; const keys = [];
  slides.forEach((sl, i) => {
    let op = 0, z = 0;
    if (i === cur) { op = i === 0 ? 1 : cl((t - TL[i].start) / FADE); z = 2; if (op < 1) dyn = true; }
    else if (i === cur - 1 && t - TL[cur].start < FADE) { op = 1; z = 1; }
    sl.style.opacity = op; sl.style.zIndex = z; sl.style.visibility = op > 0 ? 'visible' : 'hidden';
    if (op > 0) { const r = paint(i, t); dyn = dyn || r.dyn; keys.push(i + ':' + r.key); }
  });
  return dyn ? 'dyn' : keys.join('|');
};
