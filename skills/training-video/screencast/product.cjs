// The product side of a "by code" video: its adapter, its roles and who a chapter is recorded as.
//
// <repo>/.training-video/adapter.cjs — module.exports = (env) => ({ base, login(ctx, who, rt), roles, check(),
//   describe(who), path(p, rt), helpers(rt, h), locale }). See reference/code.md.
// roles — { <id>: { label, as, home, screens: [paths it reaches], denied: [paths it must not reach] } }:
// what each role of the app sees, taken from the code (guards, menus), not guessed.
const path = require('path');
const fs = require('fs');

function adapterOf(cfg, dir) {
  if (!cfg.product) throw new Error('video.json: set "product" — the folder of the app repo with .training-video/adapter.cjs');
  const repo = path.resolve(dir, cfg.product);   // relative to the video folder, or absolute
  const file = path.join(repo, '.training-video', 'adapter.cjs');
  if (!fs.existsSync(file)) throw new Error(`no ${file} — write the product profile first (reference/code.md)`);
  const env = { ...process.env, ...(cfg.app || {}), REPO: repo };
  const a = require(file)(env);
  for (const k of ['base', 'login']) if (!a[k]) throw new Error(`adapter.cjs: "${k}" is missing`);
  const host = new URL(a.base).hostname;
  // recordings change data; they only ever talk to an app on this machine
  if (!['localhost', '127.0.0.1'].includes(host)) throw new Error(`adapter base must be localhost, got ${a.base}`);
  if (a.check) a.check();
  return a;
}

function role(adapter, id) {
  if (!id) return null;
  const roles = adapter.roles || {};
  if (!roles[id]) throw new Error(`no role "${id}" in adapter.cjs roles (${Object.keys(roles).join(', ') || 'none'})`);
  return { id, ...roles[id] };
}

// Who a chapter is recorded as: its own "as" or "role", else the video's; an explicit "as" wins over a role.
function whoFor(adapter, cfg, ch = {}) {
  if (ch.as) return ch.as;
  if (ch.role) return role(adapter, ch.role).as;
  if (cfg.as) return cfg.as;
  if (cfg.role) return role(adapter, cfg.role).as;
  return null;
}

function describe(adapter, who) {
  return adapter.describe ? adapter.describe(who) : who;
}

module.exports = { adapterOf, role, whoFor, describe };
