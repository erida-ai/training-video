// The smoke test's "product": a static page served by smoke.py on SMOKE_PORT; no login.
module.exports = (env) => ({
  base: `http://127.0.0.1:${env.SMOKE_PORT}`,
  async login() {},
  roles: { a: { label: 'Първа роля', as: { user: 'a' } }, b: { label: 'Втора роля', as: { user: 'b' } } },
});
