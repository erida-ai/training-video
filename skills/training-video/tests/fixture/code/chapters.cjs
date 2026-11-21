module.exports = (h) => ({
  async c1() {
    await h.open('/');
    return async () => {
      await h.beat('c1_00', async () => {});
      await h.beat('c1_01', async () => {
        await h.click(h.page.locator('#go'));
        await h.skip(() => h.page.getByText('Отчетът е готов').waitFor({ timeout: 20000 }), 'около 4 секунди по-късно');
      });
      await h.beat('c1_02', async () => { await h.spot(h.page.locator('#out')); });
    };
  },
  async c2() { await h.open('/'); return async () => { await h.beat('c2_00', async () => {}); }; },
});
