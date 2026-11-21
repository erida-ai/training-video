// Slides → video, synchronised by the length of every narration line.
//
//   node render.cjs <video dir> silence            placeholder silence for lines without a wav (drafts only)
//   node render.cjs <video dir> timeline           timeline.json + audio/full.wav from audio/<id>.wav
//   node render.cjs <video dir> stills [ids] [--beats]   build/stills/<slide>.jpg (end of each slide, or after each line)
//   node render.cjs <video dir> render             final/<name>.mp4 (frame by frame, loudness -16 LUFS)
//   node render.cjs <video dir> all                timeline + render
//   node render.cjs --catalog <theme>              every component in that theme → stills, for approving a theme
//
// The video folder: video.json {name, lang, theme}, script.json {chapters: [{id, title, part, layout, header, beats}]},
// slides/<chapter id>.html (the body of each slide; data-b etc. — see deck.js), optional custom.css / custom.js,
// any images next to them (paths relative to the video folder). Theme: <video>/theme/ if present, else
// <plugin>/themes/<theme>/. In slide HTML, {{logo_on_dark}}, {{logo_on_light}}, {{title_image}} become theme files (hidden when the theme has none).
const fs = require('fs'); const path = require('path'); const os = require('os');
const { spawn, execFileSync } = require('child_process');
const { pathToFileURL } = require('url');

const DECK = __dirname;
const SKILL = path.resolve(DECK, '..');
const PLUGIN = path.resolve(SKILL, '../..');
const TV_HOME = process.env.TV_HOME || path.join(os.homedir(), '.training-video');
const W = 1920, H = 1080, FPS = 25, RATE = 24000;
const LEAD0 = 1.2, LEAD = 0.75, GAP = 0.5, TAIL = 1.1, FADE = 0.5;

function playwright() {
  for (const dir of [PLUGIN, TV_HOME]) {
    try { return require(require.resolve('playwright', { paths: [dir] })); } catch (e) { /* next */ }
  }
  throw new Error('Playwright is missing: run `npm ci` in the plugin folder (or npm i playwright@1.63.0 in ' + TV_HOME +
    '), then `npx playwright install chromium`');
}

const readJson = f => JSON.parse(fs.readFileSync(f, 'utf8'));
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

function load(dir) {
  const cfg = { lang: 'bg', theme: 'neutral', ...readJson(path.join(dir, 'video.json')) };
  if (!cfg.name) throw new Error('video.json: set "name" (the file name of the output)');
  const script = readJson(path.join(dir, 'script.json'));
  const lang = readJson(path.join(SKILL, 'languages', cfg.lang + '.json'));
  const own = path.join(dir, 'theme');
  const themeDir = fs.existsSync(path.join(own, 'theme.json')) ? own : path.join(PLUGIN, 'themes', cfg.theme);
  if (!fs.existsSync(path.join(themeDir, 'theme.json'))) throw new Error(`no theme "${cfg.theme}" (${themeDir})`);
  return { dir, cfg, lang, chapters: script.chapters, theme: readJson(path.join(themeDir, 'theme.json')), themeDir };
}

// theme.json → build/theme/ (theme.css + the files it names)
function buildTheme(v) {
  const out = path.join(v.dir, 'build', 'theme'); fs.mkdirSync(out, { recursive: true });
  const t = v.theme, copy = rel => {
    if (!rel) return null;
    const src = path.join(v.themeDir, rel);
    if (!fs.existsSync(src)) throw new Error(`theme "${t.name}": missing ${rel}`);
    fs.mkdirSync(path.dirname(path.join(out, rel)), { recursive: true }); fs.copyFileSync(src, path.join(out, rel));
    return 'build/theme/' + rel;
  };
  const faces = [], fam = {};
  for (const [role, f] of Object.entries(t.fonts || {})) {
    fam[role] = `'${f.family}'`;
    const rel = copy(f.file);
    faces.push(`@font-face { font-family: '${f.family}'; src: url('${rel.replace('build/theme/', '')}'); font-weight: ${f.range || '100 900'}; }`);
  }
  const c = t.colors;
  const vars = ['dark', 'primary', 'accent', 'background', 'surface', 'ink', 'muted'].map(k => {
    if (!c[k]) throw new Error(`theme "${t.name}": colors.${k} is missing`); return `--tv-${k}: ${c[k]};`; });
  const css = [...new Set(faces)].join('\n') + `\n:root { ${vars.join(' ')}\n  --tv-font-heading: ${fam.heading || 'system-ui'}, system-ui, sans-serif;` +
    ` --tv-font-body: ${fam.body || 'system-ui'}, system-ui, sans-serif; --tv-heading-weight: ${(t.fonts?.heading?.weight) || 700}; }\n`;
  fs.writeFileSync(path.join(out, 'theme.css'), css);
  return { logo_on_light: copy(t.logo?.on_light), logo_on_dark: copy(t.logo?.on_dark), title_image: copy(t.title_image) };
}

function slideHtml(v, files) {
  let part = 0;
  return v.chapters.map((ch, i) => {
    const layout = ch.layout || 'content';
    const src = path.join(v.dir, ch.slide || `slides/${ch.id}.html`);
    if (!fs.existsSync(src)) throw new Error(`no slide for chapter ${ch.id}: ${path.relative(v.dir, src)}`);
    let body = fs.readFileSync(src, 'utf8').replace(/\{\{(logo_on_dark|logo_on_light|title_image)\}\}/g, (m, k) => {
      // a theme without that file: an empty image, hidden by base.css (with its frame)
      return files[k] || (k === 'logo_on_dark' && files.logo_on_light) || 'data:,'; });
    let head = '';
    if (layout === 'content' && ch.header !== false) {
      const n = ch.part === false ? null : (ch.part ?? ++part);
      if (typeof ch.part === 'number') part = ch.part;
      const label = (v.theme.part_label || {})[v.cfg.lang] ?? '';
      head = `<div class="hd" data-b="0" data-fx="left">${n != null && label ? `<div class="kick">${esc(label)} ${n}</div>` : ''}<h1>${esc(ch.title || '')}</h1></div>`;
      if (files.logo_on_light) head += `<div class="logo"><img src="${files.logo_on_light}"></div>`;
      if (v.theme.footer) body += `<div class="footer">${esc(v.theme.footer)}</div>`;
    }
    return `<section class="slide ${layout} ${ch.cls || ''}" id="${ch.id}" data-i="${i}">${head}${body}</section>`;
  }).join('\n');
}

function deck(v) {
  const build = path.join(v.dir, 'build'); fs.mkdirSync(build, { recursive: true });
  const files = buildTheme(v);
  fs.copyFileSync(path.join(DECK, 'base.css'), path.join(build, 'base.css'));
  fs.copyFileSync(path.join(DECK, 'deck.js'), path.join(build, 'deck.js'));
  const has = f => fs.existsSync(path.join(v.dir, f));
  const html = `<!doctype html><html lang="${v.cfg.lang}"><head><meta charset="utf-8"><base href="${pathToFileURL(v.dir).href}/">
<link rel="stylesheet" href="build/theme/theme.css"><link rel="stylesheet" href="build/base.css">${has('custom.css') ? '<link rel="stylesheet" href="custom.css">' : ''}
</head><body>
${slideHtml(v, files)}
<script src="build/deck.js"></script>${has('custom.js') ? '<script src="custom.js"></script>' : ''}</body></html>`;
  const out = path.join(build, 'deck.html'); fs.writeFileSync(out, html); return out;
}

function wavPcm(f) {
  const buf = fs.readFileSync(f); let o = 12;
  while (o < buf.length) { const id = buf.toString('ascii', o, o + 4), n = buf.readUInt32LE(o + 4); if (id === 'data') return buf.subarray(o + 8, o + 8 + n); o += 8 + n + (n % 2); }
  throw new Error('no data chunk: ' + f);
}
const wav = (v, id) => path.join(v.dir, 'audio', id + '.wav');

function timeline(v) {
  let t = 0; const out = [];
  v.chapters.forEach((ch, ci) => {
    const start = t; t += ci === 0 ? LEAD0 : LEAD; const beats = [];
    for (const b of ch.beats) {
      if (!fs.existsSync(wav(v, b.id))) throw new Error(`no audio for ${b.id} — narrate.py first (or "silence" for a draft)`);
      const dur = wavPcm(wav(v, b.id)).length / 2 / RATE; beats.push({ id: b.id, start: +t.toFixed(3), dur: +dur.toFixed(3) }); t += dur + GAP;
    }
    t += TAIL - GAP; out.push({ id: ch.id, start: +start.toFixed(3), end: +t.toFixed(3), beats });
  });
  fs.writeFileSync(path.join(v.dir, 'timeline.json'), JSON.stringify(out, null, 1));
  return out;
}

function fullAudio(v, tl) {
  const total = Math.ceil(tl.at(-1).end * RATE) * 2; const pcm = Buffer.alloc(total);
  for (const s of tl) for (const b of s.beats) wavPcm(wav(v, b.id)).copy(pcm, Math.round(b.start * RATE) * 2);
  const h = Buffer.alloc(44); h.write('RIFF', 0); h.writeUInt32LE(36 + total, 4); h.write('WAVEfmt ', 8); h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(RATE, 24); h.writeUInt32LE(RATE * 2, 28); h.writeUInt16LE(2, 32);
  h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(total, 40);
  fs.writeFileSync(path.join(v.dir, 'audio', 'full.wav'), Buffer.concat([h, pcm]));
}

async function open(v, tl) {
  const { chromium } = playwright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  const errors = [];
  page.on('console', m => m.type() === 'error' && errors.push(m.text()));
  page.on('pageerror', e => errors.push(String(e)));
  page.on('requestfailed', r => errors.push('missing file: ' + r.url()));
  await page.goto(pathToFileURL(deck(v)).href);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(([tl, f]) => window.setup(tl, f), [tl, FADE]);
  await page.waitForTimeout(300);
  if (errors.length) { await browser.close(); throw new Error('slide errors:\n' + errors.join('\n')); }
  return { browser, page };
}

async function stills(v, tl, only, perBeat) {
  const { browser, page } = await open(v, tl); const out = path.join(v.dir, 'build', 'stills');
  fs.mkdirSync(out, { recursive: true }); const made = [];
  const overflow = [];
  for (const s of tl) {
    if (only.length && !only.includes(s.id)) continue;
    const pts = perBeat ? s.beats.map(b => b.start + Math.min(b.dur, 3) + 0.6) : [s.end - 0.05];
    for (const [k, t] of pts.entries()) {
      await page.evaluate(t => window.T(t), t);
      const f = path.join(out, `${s.id}${pts.length > 1 ? '_' + k : ''}.jpg`);
      await page.screenshot({ path: f, type: 'jpeg', quality: 85 }); made.push(f);
    }
    // the most common layout fault: an element that ends outside the visible slide (checked with everything shown)
    await page.evaluate(t => window.T(t), s.end - 0.05);
    const bad = await page.evaluate(id => {
      const sl = document.getElementById(id), r = sl.getBoundingClientRect();
      return [...new Set([...sl.querySelectorAll('*')].filter(e => !e.closest('.bg, .kb, .bob') && e.getClientRects().length && (q =>
        q.bottom > r.bottom + 2 || q.right > r.right + 2 || q.left < r.left - 2)(e.getBoundingClientRect()))
        .map(e => e.tagName.toLowerCase() + (e.classList.length ? '.' + [...e.classList].join('.') : '')))].slice(0, 3);
    }, s.id);
    if (bad.length) overflow.push(`${s.id} (${bad.join(', ')})`);
  }
  await browser.close();
  console.log(made.join('\n'));
  if (overflow.length) console.log('OVERFLOW (cut off at the edge of the slide): ' + overflow.join('; '));
}

async function render(v, tl) {
  const { browser, page } = await open(v, tl);
  const total = Math.ceil(tl.at(-1).end * FPS); const silent = path.join(v.dir, 'build', 'video-silent.mp4');
  const ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', String(FPS), silent], { stdio: ['pipe', 'inherit', 'inherit'] });
  let prevKey = null, prev = null, shots = 0; const t0 = Date.now();
  for (let f = 0; f < total; f++) {
    const key = await page.evaluate(t => window.T(t), f / FPS);
    if (key === 'dyn' || key !== prevKey || !prev) { prev = await page.screenshot({ type: 'jpeg', quality: 93 }); shots++; }
    prevKey = key;
    if (!ff.stdin.write(prev)) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 1000 === 0) console.log(`frame ${f}/${total} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end(); await new Promise((r, j) => ff.on('close', c => c ? j(new Error('ffmpeg ' + c)) : r()));
  await browser.close();
  fs.mkdirSync(path.join(v.dir, 'final'), { recursive: true });
  const out = path.join(v.dir, 'final', v.cfg.name + '.mp4');
  execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', silent, '-i', path.join(v.dir, 'audio', 'full.wav'), '-c:v', 'copy',
    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', '48000', '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', out]);
  console.log(`done: ${out} — ${(total / FPS / 60).toFixed(1)} min, ${shots} screenshots for ${total} frames`);
}

function silence(v) {
  fs.mkdirSync(path.join(v.dir, 'audio'), { recursive: true });
  for (const ch of v.chapters) for (const b of ch.beats) {
    if (fs.existsSync(wav(v, b.id))) continue;
    const secs = Math.max(1.5, (b.say || b.text).length * v.lang.pace).toFixed(2);
    execFileSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', `anullsrc=r=${RATE}:cl=mono`, '-t', secs, '-c:a', 'pcm_s16le', wav(v, b.id)]);
  }
}

async function catalog(theme) {
  const dir = path.join(TV_HOME, 'catalog', theme);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.cpSync(path.join(DECK, 'catalog'), dir, { recursive: true });
  const cfg = readJson(path.join(dir, 'video.json')); cfg.theme = theme;
  fs.writeFileSync(path.join(dir, 'video.json'), JSON.stringify(cfg, null, 1));
  const v = load(dir); silence(v); await stills(v, timeline(v), [], false);
}

module.exports = { playwright, load, buildTheme, timeline, readJson, esc, TV_HOME, SKILL, PLUGIN };

if (require.main === module) (async () => {
  const [a, cmd, ...rest] = process.argv.slice(2);
  if (a === '--catalog') return catalog(cmd || 'neutral');
  if (!a || !cmd) { console.error(fs.readFileSync(__filename, 'utf8').split('\n').slice(0, 9).join('\n')); process.exit(2); }
  const v = load(path.resolve(a));
  if (cmd === 'silence') return silence(v);
  const tl = timeline(v);
  console.log(`timeline: ${tl.length} slides, ${(tl.at(-1).end / 60).toFixed(1)} min`);
  if (cmd === 'timeline' || cmd === 'all' || cmd === 'render') fullAudio(v, tl);
  if (cmd === 'stills') return stills(v, tl, rest.filter(x => !x.startsWith('--')), rest.includes('--beats'));
  if (cmd === 'render' || cmd === 'all') return render(v, tl);
})().catch(e => { console.error(e.message || e); process.exit(1); });
