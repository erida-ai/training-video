// Records one chapter of a "by code" video: node record.cjs <video dir> <chapter id>
//
// The video folder: video.json {name, lang, theme, product: "<repo of the app>", app: {…options for the adapter}},
// script.json (chapters: {id, title, subtitle, card, part, role, as, caption_top, caption_left, beats}),
// chapters.cjs — module.exports = (h) => ({ async <chapter id>() { /* setup, off camera */ return async () => {
//   await h.beat('<line id>', async () => { /* actions while that line sounds */ }) } } }),
// audio/<line id>.wav — the narration (or placeholder silence).
// The product: <repo>/.training-video/adapter.cjs — see product.cjs and reference/code.md.
// Recorded as: the chapter's "as" or "role", else video.json "as" or "role" (a role of the adapter).
// Output: raw/<chapter>/ — the video, timeline.json (line start times, errors), error.png if the chapter stopped.
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { playwright, load, readJson } = require('../deck/render.cjs');
const helpers = require('./helpers.cjs');
const { partNumbers } = require('./cards.cjs');
const { adapterOf, whoFor, describe } = require('./product.cjs');

const W = 1280, H = 720;
const [dirArg, chapter] = process.argv.slice(2);
if (!dirArg || !chapter) { console.error('usage: node record.cjs <video dir> <chapter id>'); process.exit(2); }
const v = load(path.resolve(dirArg));

function durations() {
  const dur = {};
  for (const ch of v.chapters) for (const b of ch.beats) {
    const f = path.join(v.dir, 'audio', b.id + '.wav');
    if (fs.existsSync(f)) dur[b.id] = parseFloat(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
  }
  return dur;
}

// First line id → the title shown inside the page, for chapters without a title card.
function captions() {
  const parts = partNumbers(v.chapters); const out = {};
  // `continues: true` — the same chapter as the one before, recorded as another role: no title on screen
  for (const ch of v.chapters) if (ch.card === false && !ch.continues)
    out[ch.beats[0].id] = { title: ch.title, subtitle: ch.subtitle, part: parts[ch.id], top: ch.caption_top, left: ch.caption_left };
  return out;
}

const pause = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const ch = v.chapters.find(c => c.id === chapter);
  if (!ch) throw new Error(`no chapter "${chapter}" in script.json`);
  const adapter = adapterOf(v.cfg, v.dir);
  const who = whoFor(adapter, v.cfg, ch);
  const chaptersFile = path.join(v.dir, 'chapters.cjs');
  const dir = path.join(v.dir, 'raw', chapter);
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const t = v.theme;
  const themeInit = `window.__tvTheme = ${JSON.stringify({ dark: t.colors.dark, primary: t.colors.primary, accent: t.colors.accent,
    font: `${t.fonts?.heading?.family || 'system-ui'}, system-ui, sans-serif`, partLabel: (t.part_label || {})[v.cfg.lang] || '' })};`;

  const { chromium } = playwright();
  const browser = await chromium.launch();
  // every context logs in on its own: headers, cookies and storage are per context
  async function context(person, options = {}) {
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, locale: adapter.locale || 'bg-BG', ...options });
    await ctx.addInitScript({ content: themeInit });
    await ctx.addInitScript({ path: path.join(__dirname, 'overlay.js') });
    if (person) await adapter.login(ctx, person, rt);
    return ctx;
  }
  const rt = { dir: v.dir, base: adapter.base.replace(/\/$/, ''), who, adapter, dur: durations(), captions: captions(), log: [], browser,
    newContext: other => context(other || who) };
  const ctx = await context(who, { recordVideo: { dir, size: { width: W, height: H } } });
  rt.page = await ctx.newPage();
  rt.t0 = Date.now();   // the video file starts about here: line times are positions in it
  const errors = [];
  rt.page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
  rt.page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.request().method()} ${r.url()}`); });

  let err = null;
  try {
    delete require.cache[require.resolve(chaptersFile)];
    const chapters = require(chaptersFile)(helpers(rt));
    if (!chapters[chapter]) throw new Error(`no chapter "${chapter}" in chapters.cjs`);
    const run = await chapters[chapter]();      // setup, off camera (still recorded; assemble cuts it)
    await pause(600);
    await run();
    await pause(800);
  } catch (e) {
    err = e;
    console.log('ERROR', String(e.message || e).split('\n')[0]);
    await rt.page.screenshot({ path: path.join(dir, 'error.png') }).catch(() => {});
  }
  const end = (Date.now() - rt.t0) / 1000;
  const video = rt.page.video();
  await ctx.close(); await browser.close();
  const vpath = await video.path();
  fs.writeFileSync(path.join(dir, 'timeline.json'), JSON.stringify({ video: vpath, end, beats: rt.log, errors }, null, 1));
  console.log(JSON.stringify({ chapter, as: describe(adapter, who), seconds: +end.toFixed(1), lines: rt.log.length, errors }, null, 1));
  if (err) process.exit(1);
})().catch(e => { console.error(e.message || e); process.exit(1); });
