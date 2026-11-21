// <Product> — adapter for the training-video plugin (mode „by code“). Copy to <repo>/.training-video/adapter.cjs.
// env: video.json "app" + process env; REPO = the repo folder. Keep everything about this product here and in profile.md.
module.exports = (env) => {
  const base = `http://localhost:${env.DEMO_WEB || 3000}`;   // the DEMO instance, never someone's dev or prod
  return {
    base,
    locale: 'bg-BG',
    // throw when the environment is not safe or not ready (wrong instance, stack not up, missing demo data)
    check() {},
    // who = the "as" of the role (or an explicit "as" in script.json / video.json); log the Playwright context in:
    // set a cookie / header / storageState, or call the app's dev-login endpoint with ctx.request
    async login(ctx, who, rt) {
      // await ctx.request.post(`${base}/api/dev/login`, { data: { email: who.user } });
    },
    // the roles of the app, read from the code (auth guards, menus, seed users) — reference/code.md
    // home: where the role starts; screens: what it reaches; denied: what it must not reach (survey.cjs checks it).
    // Give a role its demo user inside login() (idempotent: API or SQL on the demo instance), so recordings repeat.
    roles: {
      // viewer: { label: 'Viewer', as: { user: 'viewer.demo@example.com', role: 'viewer' },
      //           home: '/dashboard', screens: ['/reports'], denied: ['/admin'] },
    },
    describe: who => JSON.stringify(who),
    path: p => p,                         // expand placeholders in paths if the app has them
    // own helpers for chapters.cjs: data setup off camera, resets that make a chapter repeatable, test data lookups
    helpers(rt, h) {
      return {};
    },
  };
};
