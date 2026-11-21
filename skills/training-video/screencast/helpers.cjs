// What a chapter module (chapters.cjs of a video) can use: h = helpers(rt) + the product adapter's own helpers.
// rt is the recording state from record.cjs: page, browser, newContext, base, who, dur, captions, log, t0, adapter.
const fs = require('fs');
const path = require('path');

const sleep = ms => new Promise(r => setTimeout(r, ms));
const DIALOG = '[role=dialog],[role=alertdialog],dialog[open]';

function pointer(rt) {
  async function center(loc) {
    await loc.scrollIntoViewIfNeeded();
    const b = await loc.boundingBox();
    return { x: b.x + b.width / 2, y: b.y + b.height / 2, b };
  }
  // The cursor glides to the element (35 steps), so the viewer sees where the next action is.
  async function move(loc) {
    const { x, y } = await center(loc);
    await rt.page.mouse.move(x, y, { steps: 35 });
    await sleep(350);
  }
  async function click(loc) { await move(loc); await loc.click(); await sleep(600); }
  async function typeSlow(text, delay = 110) { await rt.page.keyboard.type(text, { delay }); }
  return { center, move, click, typeSlow };
}

function light(rt) {
  async function spotRect(r, pad = 8) {
    await rt.page.evaluate(([r, p]) => window.__demo.spot(r, p), [r, pad]);
    await sleep(500);
  }
  // Notices that appear above an element push it down; measuring a moment later keeps the ring on it.
  async function spot(loc, pad = 8) {
    if (loc) { await loc.waitFor(); await sleep(250); }
    await spotRect(loc ? await loc.boundingBox() : null, pad);
  }
  async function union(locs) {
    const bs = [];
    for (const l of locs) bs.push(await l.boundingBox());
    const x = Math.min(...bs.map(b => b.x)), y = Math.min(...bs.map(b => b.y));
    const x2 = Math.max(...bs.map(b => b.x + b.width)), y2 = Math.max(...bs.map(b => b.y + b.height));
    return { x, y, width: x2 - x, height: y2 - y };
  }
  async function zoom(loc, scale) {
    const b = loc ? await loc.boundingBox() : null;
    await rt.page.evaluate(([r, s]) => window.__demo.zoom(r, s), [b, scale]);
    await sleep(1000);
  }
  return { spot, spotRect, union, zoom };
}

function timing(rt) {
  const caption = c => rt.page.evaluate(x => window.__demo.caption(x), c);
  // Runs the actions of one narration line and waits until its audio has ended + 0.9 s:
  // the recording itself carries the sync. A chapter without a title card shows its title during its first line.
  async function beat(id, fn) {
    const start = Date.now();
    const entry = { id, t: (start - rt.t0) / 1000 };
    rt.log.push(entry);
    if (rt.dur[id] === undefined) throw new Error('no audio for ' + id + ' (narrate.py, or render.cjs silence for a draft)');
    const title = rt.captions[id];
    if (title) await caption(title);
    await fn();
    // the cut after the last line must not fall before its actions end
    entry.done = (Date.now() - rt.t0) / 1000;
    // time cut out by skip() does not count: the line still gets its full narration on screen
    const cut = (entry.cuts || []).reduce((s, [a, b]) => s + (b - a), 0) * 1000;
    const left = rt.dur[id] * 1000 + 900 - (Date.now() - start - cut);
    if (left > 0) await sleep(left);
    if (title) await caption(null);
  }
  // A slow wait inside a line (an AI call, a report): `fn` runs on camera but assemble.py cuts it out of the video,
  // and `note` (e.g. „около 30 секунди по-късно“) is shown for 2.5 s right after the cut, so the viewer knows time
  // passed. Use only for real waits the narration does not need; never to hide what the app does.
  async function skip(fn, note) {
    const entry = rt.log[rt.log.length - 1];
    if (!entry) throw new Error('skip() must be inside a beat');
    const from = (Date.now() - rt.t0) / 1000;
    await fn();
    const to = (Date.now() - rt.t0) / 1000;
    (entry.cuts = entry.cuts || []).push([+from.toFixed(3), +to.toFixed(3)]);
    if (note) {
      await caption({ title: note });
      await sleep(2500);
      await caption(rt.captions[entry.id] || null);   // back to the chapter title, if the line shows one
    }
  }
  return { beat, skip };
}

function controls(rt, { move, click }, { spot }) {
  // A native <select> never opens in a headless recording, so it is lit and changed in place.
  async function selectOption(loc, option) {
    await move(loc); await spot(loc, 6);
    await loc.selectOption(option); await sleep(900);
    await spot(null);
  }
  async function pressKey(loc, key, times = 1) {
    await move(loc); await loc.focus();
    for (let i = 0; i < times; i++) { await rt.page.keyboard.press(key); await sleep(900); }
  }
  // Text that arrives at once, then Enter — what a hand-held scanner or a paste does (headless has no camera).
  async function enter(input, value) {
    await click(input); await spot(input, 6);
    await input.fill(value); await sleep(500);
    await rt.page.keyboard.press('Enter'); await sleep(1200);
    await spot(null);
  }
  // A confirm() dialog would block the recording; accept (or dismiss) the next one.
  function nextConfirm(accept = true) {
    rt.page.once('dialog', d => (accept ? d.accept() : d.dismiss()));
  }
  return { selectOption, pressKey, enter, scan: enter, nextConfirm };
}

function nav(rt) {
  // Opens a path of the app (the adapter may expand placeholders, e.g. {org} → the demo organisation) and parks the cursor.
  async function open(p) {
    const full = rt.adapter.path ? rt.adapter.path(p, rt) : p;
    await rt.page.goto(rt.base + full);
    await rt.page.waitForLoadState('networkidle');
    const v = rt.page.viewportSize();
    await rt.page.mouse.move(v.width / 2, v.height * 0.55);
  }
  return { open };
}

module.exports = function helpers(rt) {
  const p = pointer(rt);
  const l = light(rt);
  const base = {
    get page() { return rt.page; },
    rt, sleep, fs, path, DIALOG,
    ...p, ...l, ...timing(rt), ...controls(rt, p, l), ...nav(rt),
  };
  const own = rt.adapter.helpers ? rt.adapter.helpers(rt, base) : {};
  return Object.assign(base, own);
};
