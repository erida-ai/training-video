// Looks at the app as one role before the script is written: node survey.cjs <video dir> [--role <id>] [--crawl] [path…]
//
// Logs in through the product adapter as the role (video.json "role", or --role) and opens every screen the role
// reaches: its "home" and "screens" from adapter.cjs, the paths given, and with --crawl the links found on them
// (same site, two steps deep, at most 40 screens, two of each pattern such as /items/<n>; only page loads, nothing
// is clicked). Then it opens the role's
// "denied" screens and checks that the app really refuses them.
// Output: survey/<role>/ — NN.png (whole page), NN.txt (the page text), index.json (per screen: path, where it
// ended, headings, buttons, links, fields, refused requests) and summary.md — what the script may promise.
const path = require('path');
const fs = require('fs');
const { playwright, readJson } = require('../deck/render.cjs');
const { adapterOf, role: roleOf, whoFor, describe } = require('./product.cjs');

const W = 1280, H = 720, MAX = 40, DEPTH = 2;
const args = process.argv.slice(2);
const flag = n => { const i = args.indexOf(n); return i < 0 ? null : args.splice(i, 2)[1]; };
const roleArg = flag('--role');
const crawl = args.includes('--crawl') && args.splice(args.indexOf('--crawl'), 1);
const [dirArg, ...extra] = args;
if (!dirArg) { console.error('usage: node survey.cjs <video dir> [--role <id>] [--crawl] [path…]'); process.exit(2); }

const dir = path.resolve(dirArg);
const cfg = readJson(path.join(dir, 'video.json'));
const adapter = adapterOf(cfg, dir);
const r = roleOf(adapter, roleArg || cfg.role);
const who = r ? r.as : whoFor(adapter, cfg);
const out = path.join(dir, 'survey', r ? r.id : 'default');
const base = adapter.base.replace(/\/$/, '');
// links that end a session or act on data even as a page load
const SKIP = adapter.crawlSkip || /logout|sign-?out|изход|delete|remove|\.(pdf|csv|xlsx|zip)(\?|$)/i;
// /orders/25 and /orders/26 are the same screen with other data: two of each are enough
const pattern = p => p.split(/[?#]/)[0].replace(/\/\d+(?=\/|$)/g, '/<n>');
const PER_PATTERN = 2;

// What a screen offers, read from the page itself: the script names only what is here.
function read() {
  const txt = el => (el.getAttribute('aria-label') || el.innerText || el.value || '').replace(/\s+/g, ' ').trim();
  const shown = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const all = sel => [...document.querySelectorAll(sel)].filter(shown);
  const label = el => {
    const id = el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    const around = el.closest('label');
    return (id && txt(id)) || el.getAttribute('aria-label') || el.placeholder || (around && txt(around)) || el.name || el.type;
  };
  return {
    title: document.title,
    headings: all('h1,h2,h3').map(txt).filter(Boolean),
    buttons: [...new Set(all('button,[role=button],input[type=submit]').map(txt).filter(Boolean))],
    links: all('a[href]').map(a => ({ text: txt(a), href: a.getAttribute('href') })).filter(l => l.text),
    fields: all('input:not([type=hidden]):not([type=submit]),select,textarea').map(label).filter(Boolean),
  };
}

(async () => {
  fs.rmSync(out, { recursive: true, force: true }); fs.mkdirSync(out, { recursive: true });
  const { chromium } = playwright();
  const browser = await chromium.launch();
  const rt = { dir, base, who, adapter, browser, role: r };
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, locale: adapter.locale || 'bg-BG' });
  if (who) await adapter.login(ctx, who, rt);
  const page = await ctx.newPage();
  page.on('dialog', d => d.dismiss());   // nothing is confirmed while looking around
  const expand = p => (adapter.path ? adapter.path(p, rt) : p);

  async function visit(p, n) {
    const refused = [], errors = [];
    const onResp = res => { if (res.status() >= 400) refused.push(`${res.status()} ${res.request().method()} ${res.url().replace(base, '')}`); };
    const onCon = m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); };
    page.on('response', onResp); page.on('console', onCon);
    let failed = null;
    try {
      await page.goto(base + p, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(400);
    } catch (e) { failed = String(e.message || e).split('\n')[0]; }
    page.off('response', onResp); page.off('console', onCon);
    const id = String(n).padStart(2, '0');
    const info = failed ? {} : await page.evaluate(read);
    const at = page.url().replace(base, '');
    await page.screenshot({ path: path.join(out, id + '.png'), fullPage: true }).catch(() => {});
    fs.writeFileSync(path.join(out, id + '.txt'), failed ? failed : await page.evaluate(() => document.body.innerText));
    return { n: id, path: p, at, moved: at.split(/[?#]/)[0] !== p.split(/[?#]/)[0], refused, errors, failed, ...info };
  }

  const start = [r && r.home, ...((r && r.screens) || []), ...extra].filter(Boolean).map(expand);
  if (!start.length) start.push('/');
  const seen = new Set(), screens = [], perPattern = {};
  let queue = [...new Set(start)].map(p => [p, 0]);
  while (queue.length && screens.length < MAX) {
    const [p, depth] = queue.shift();
    if (seen.has(p)) continue;
    seen.add(p);
    perPattern[pattern(p)] = Math.max(perPattern[pattern(p)] || 0, 1);
    const s = await visit(p, screens.length + 1);
    screens.push(s);
    console.log(`${s.n} ${p}${s.moved ? ' → ' + s.at : ''}${s.refused.length ? '  (' + s.refused.length + ' refused)' : ''}`);
    if (!crawl || depth >= DEPTH || !s.links) continue;
    for (const l of s.links) {
      let u;
      try { u = new URL(l.href, base + s.at); } catch (e) { continue; }
      if (u.origin !== new URL(base).origin || SKIP.test(u.pathname + u.search)) continue;
      const next = u.pathname + u.search, key = pattern(next);
      if (seen.has(next) || queue.some(([q]) => q === next) || (perPattern[key] || 0) >= PER_PATTERN) continue;
      perPattern[key] = (perPattern[key] || 0) + 1;
      queue.push([next, depth + 1]);
    }
  }

  // The screens the role must not reach: refused by the server, or sent elsewhere.
  const denied = [];
  for (const p of ((r && r.denied) || []).map(expand)) {
    const s = await visit(p, 'x' + (denied.length + 1));
    s.blocked = s.moved || s.refused.some(x => /^40[13] /.test(x));
    denied.push(s);
    console.log(`${s.blocked ? 'refused ' : 'OPEN!   '} ${p}${s.moved ? ' → ' + s.at : ''}`);
  }
  await ctx.close(); await browser.close();

  const report = { role: r ? r.id : null, label: r ? r.label : null, as: describe(adapter, who), base, screens, denied };
  fs.writeFileSync(path.join(out, 'index.json'), JSON.stringify(report, null, 1));
  const md = [`# ${r ? `${r.label || r.id} (${r.id})` : 'без роля'} — ${report.as ? JSON.stringify(report.as) : ''}`, ''];
  for (const s of screens) {
    md.push(`## ${s.n} ${s.path}${s.moved ? ` → ${s.at}` : ''}`);
    if (s.failed) { md.push(`не се отвори: ${s.failed}`, ''); continue; }
    if (s.headings.length) md.push(`заглавия: ${s.headings.join(' · ')}`);
    if (s.buttons.length) md.push(`бутони: ${s.buttons.join(' · ')}`);
    if (s.fields.length) md.push(`полета: ${s.fields.join(' · ')}`);
    if (s.refused.length) md.push(`отказани заявки: ${s.refused.join('; ')}`);
    md.push('');
  }
  if (denied.length) {
    md.push('## Не бива да стига', '');
    for (const s of denied) md.push(`- ${s.path}: ${s.blocked ? 'отказано' : '**ОТВАРЯ СЕ**'}${s.moved ? ` (→ ${s.at})` : ''}`);
  }
  fs.writeFileSync(path.join(out, 'summary.md'), md.join('\n') + '\n');
  console.log(`\n${screens.length} screens → ${out}/summary.md`);
  if (denied.some(s => !s.blocked)) { console.log('WARN: a screen in "denied" opens for this role — check adapter.cjs roles and the app'); process.exit(1); }
})().catch(e => { console.error(e.message || e); process.exit(1); });
