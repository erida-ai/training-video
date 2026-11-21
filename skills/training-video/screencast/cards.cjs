// Title cards (1920×1080 PNG, in the theme) for the chapters of a "by code" video: node cards.cjs <video dir>
// A chapter gets a card unless "card": false (then its title shows inside the page while its first line sounds).
// The first and the last chapter with one line are the intro and the end: a card alone, no part number.
const fs = require('fs'); const path = require('path');
const { playwright, load, buildTheme, esc } = require('../deck/render.cjs');
const { pathToFileURL } = require('url');

// Part numbers shared with record.cjs: every chapter with recorded lines counts, unless "part" says otherwise.
function partNumbers(chapters) {
  let part = 0; const out = {};
  for (const ch of chapters) {
    if (ch.card !== false && ch.beats.length < 2) { out[ch.id] = null; continue; }
    out[ch.id] = ch.part === false || ch.continues ? null : (ch.part ?? ++part);
    if (typeof ch.part === 'number') part = ch.part;
  }
  return out;
}

async function cards(dir) {
  const v = load(path.resolve(dir));
  const files = buildTheme(v);
  const parts = partNumbers(v.chapters);
  const label = (v.theme.part_label || {})[v.cfg.lang] || '';
  const out = path.join(v.dir, 'build', 'cards'); fs.mkdirSync(out, { recursive: true });
  fs.copyFileSync(path.join(__dirname, '..', 'deck', 'base.css'), path.join(v.dir, 'build', 'base.css'));
  const { chromium } = playwright();
  const browser = await chromium.launch(); const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const made = [];
  for (const ch of v.chapters.filter(c => c.card !== false)) {
    const n = parts[ch.id];
    const logo = files.logo_on_dark || files.logo_on_light;
    const html = `<!doctype html><html><head><meta charset="utf-8"><base href="${pathToFileURL(v.dir).href}/">
<link rel="stylesheet" href="build/theme/theme.css"><link rel="stylesheet" href="build/base.css"></head><body>
<section class="slide title" style="visibility:visible">
${files.title_image ? `<div class="bg"><img src="${files.title_image}"></div><div class="shade"></div>` : ''}
<div class="title-wrap">
${logo ? `<div class="title-logo${files.logo_on_dark ? ' on-dark' : ''}"><img src="${logo}"></div>` : ''}
${n != null && label ? `<div class="pill" style="margin:0 0 40px;background:var(--tv-accent);color:#fff">${esc(label)} ${n}</div>` : ''}
<div class="t1">${esc(ch.title || '')}</div>
${ch.subtitle ? `<div class="t2">${esc(ch.subtitle)}</div>` : ''}
</div>
${v.theme.footer ? `<div class="footer" style="color:rgba(255,255,255,.7)">${esc(v.theme.footer)}</div>` : ''}
</section></body></html>`;
    const f = path.join(v.dir, 'build', `card-${ch.id}.html`); fs.writeFileSync(f, html);
    await page.goto(pathToFileURL(f).href); await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(150);
    const png = path.join(out, `${ch.id}.png`); await page.screenshot({ path: png }); made.push(png);
  }
  await browser.close();
  console.log(made.join('\n'));
}

module.exports = { partNumbers };
if (require.main === module) cards(process.argv[2] || '.').catch(e => { console.error(e.message || e); process.exit(1); });
