// Injected into every page of a recording: a visible cursor, a click ripple, a spotlight ring around the element
// being used, the chapter title inside the page, and a smooth zoom of the app root.
// Colours: window.__tvTheme = {dark, primary, accent, font, partLabel}, set by record.cjs before this script.
(() => {
  if (window.__demo) return;
  const th = Object.assign({ dark: '#1b2a41', primary: '#2d5be3', accent: '#0e9f8e', font: 'system-ui, sans-serif', partLabel: '' }, window.__tvTheme || {});
  const css = `
  #demo-cursor{position:fixed;left:0;top:0;width:34px;height:34px;z-index:2147483647;pointer-events:none;
    transform:translate(-4px,-3px);transition:none;filter:drop-shadow(0 2px 3px rgba(0,0,0,.45))}
  .demo-ripple{position:fixed;z-index:2147483646;pointer-events:none;width:20px;height:20px;border-radius:50%;
    border:4px solid ${th.accent};transform:translate(-50%,-50%) scale(.4);opacity:1;animation:demoRip .7s ease-out forwards}
  @keyframes demoRip{to{transform:translate(-50%,-50%) scale(3.2);opacity:0}}
  #demo-spot{position:fixed;z-index:2147483645;pointer-events:none;border:4px solid ${th.accent};border-radius:10px;
    box-shadow:0 0 0 9999px color-mix(in srgb, ${th.dark} 38%, transparent),0 0 18px 4px color-mix(in srgb, ${th.accent} 70%, transparent);
    opacity:0;transition:all .45s ease}
  .tv-zoom-root{transition:transform .9s ease-in-out}
  #demo-caption{position:fixed;left:var(--demo-caption-left,50%);top:var(--demo-caption-top,236px);z-index:2147483644;pointer-events:none;
    transform:translate(-50%,-8px);opacity:0;transition:opacity .45s ease,transform .45s ease;width:max-content;max-width:560px;
    background:#fff;border-left:8px solid ${th.dark};border-radius:8px;padding:12px 26px 14px;text-align:left;
    box-shadow:0 6px 24px color-mix(in srgb, ${th.dark} 25%, transparent);font-family:${th.font}}
  #demo-caption.on{opacity:1;transform:translate(-50%,0)}
  #demo-caption .n{font-weight:600;font-size:14px;letter-spacing:2px;color:${th.accent};text-transform:uppercase}
  #demo-caption .t{font-weight:700;font-size:30px;color:${th.dark};line-height:1.15}
  #demo-caption .s{font-size:17px;color:#334155;margin-top:4px}
  `;
  const svg = `<svg viewBox="0 0 24 24" width="34" height="34"><path d="M3 2 L3 19 L7.5 14.8 L10.6 21.6 L13.4 20.4 L10.4 13.8 L16.6 13.6 Z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
  function setup() {
    if (document.getElementById('demo-cursor')) return;
    const st = document.createElement('style'); st.textContent = css; document.documentElement.appendChild(st);
    const c = document.createElement('div'); c.id = 'demo-cursor'; c.innerHTML = svg; document.documentElement.appendChild(c);
    const s = document.createElement('div'); s.id = 'demo-spot'; document.documentElement.appendChild(s);
    const pos = window.__demoPos || { x: innerWidth / 2, y: innerHeight / 2 }; c.style.left = pos.x + 'px'; c.style.top = pos.y + 'px';
  }
  document.addEventListener('mousemove', e => {
    setup(); const c = document.getElementById('demo-cursor');
    c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px';
    window.__demoPos = { x: e.clientX, y: e.clientY };
  }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = 'demo-ripple';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.documentElement.appendChild(r); setTimeout(() => r.remove(), 800);
  }, true);
  // the element that zooms: #root (React), #app (Vue), else body
  const zoomRoot = () => document.getElementById('root') || document.getElementById('app') || document.body;
  window.__demo = {
    setup,
    spot(rect, pad = 8) {
      setup(); const s = document.getElementById('demo-spot');
      if (!rect) { s.style.opacity = '0'; return; }
      s.style.left = (rect.x - pad) + 'px'; s.style.top = (rect.y - pad) + 'px';
      s.style.width = (rect.width + 2 * pad) + 'px'; s.style.height = (rect.height + 2 * pad) + 'px'; s.style.opacity = '1';
    },
    // The chapter title inside the page, for chapters that stay on the same screen (no title card).
    caption(c) {
      setup(); let el = document.getElementById('demo-caption');
      if (!el) { el = document.createElement('div'); el.id = 'demo-caption'; document.documentElement.appendChild(el); }
      if (!c) { el.classList.remove('on'); return; }
      el.replaceChildren(...[[c.part != null && th.partLabel ? `${th.partLabel} ${c.part}` : '', 'n'], [c.title, 't'], [c.subtitle || '', 's']]
        .filter(([text]) => text).map(([text, cls]) => Object.assign(document.createElement('div'), { className: cls, textContent: text })));
      if (c.top) el.style.setProperty('--demo-caption-top', c.top + 'px');
      if (c.left) el.style.setProperty('--demo-caption-left', c.left + 'px');
      el.classList.add('on');
    },
    zoom(rect, scale) {
      const root = zoomRoot(); root.classList.add('tv-zoom-root');
      if (!rect) { root.style.transform = ''; return; }
      const cx = rect.x + rect.width / 2, cy = rect.y + rect.height / 2;
      root.style.transformOrigin = `${cx}px ${cy + window.scrollY}px`;
      root.style.transform = `scale(${scale})`;
    },
  };
  if (document.readyState !== 'loading') setup(); else document.addEventListener('DOMContentLoaded', setup);
})();
