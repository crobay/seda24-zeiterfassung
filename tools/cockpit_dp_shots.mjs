// Screenshots Dienstplan (nur DEV, speichert nichts): Tage/Mitarbeiter-Ansicht, Ziehen in Arbeit, Kopier-Vorschau.
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2); const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de';
const { defaultBrowserType: _a, ...ipad } = devices['iPad (gen 7)'];
const { defaultBrowserType: _b, ...iphone } = devices['iPhone 15'];
const profile = { pc: { viewport: { width: 1440, height: 900 } }, tablet: ipad, handy: iphone };
const browser = await chromium.launch();
for (const [name, prof] of Object.entries(profile)) {
  for (const ansicht of ['tage', 'ma']) {
    const ctx = await browser.newContext({ ...prof, locale: 'de-DE', timezoneId: 'Europe/Berlin' });
    const page = await ctx.newPage(); page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
    await page.goto(`${BASE}/login`);
    await page.evaluate(([tk, a]) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_theme_v2', 'light'); localStorage.setItem('ck_dp_ansicht', a); }, [TOKEN, ansicht]);
    await page.goto(`${BASE}/cockpit/dienstplan`); await page.waitForLoadState('networkidle'); await page.waitForTimeout(800);
    const f = (x) => path.join(OUT, `11_dienstplan_${ansicht === 'ma' ? 'mitarbeiter' : 'tage'}${x}_${name}.png`);
    await page.screenshot({ path: f('') });
    // Ziehen in Arbeit (wird mit Esc abgebrochen, nichts gespeichert)
    const chip = page.locator('.ck-drag').nth(1); await chip.scrollIntoViewIfNeeded();
    const a = await chip.boundingBox();
    if (name === 'pc') {
      await page.mouse.move(a.x + 30, a.y + a.height / 2); await page.mouse.down();
      await page.mouse.move(a.x + 60, a.y + 20, { steps: 3 }); await page.keyboard.down('Control');
      await page.mouse.move(a.x + (ansicht === 'ma' ? 140 : 210), a.y + (ansicht === 'ma' ? 70 : 60), { steps: 10 }); await page.waitForTimeout(250);
      await page.screenshot({ path: f('_ziehen') });
      await page.keyboard.press('Escape'); await page.keyboard.up('Control'); await page.mouse.up();
    } else {
      const cdp = await ctx.newCDPSession(page);
      const T = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchCancel' || type === 'touchEnd' ? [] : [{ x, y }] });
      await T('touchStart', a.x + 30, a.y + 15); await page.waitForTimeout(500);
      for (let i = 1; i <= 6; i++) { await T('touchMove', a.x + 30 + i * 12, a.y + 15 + i * 14); await page.waitForTimeout(30); }
      await page.waitForTimeout(200); await page.screenshot({ path: f('_ziehen') });
      await T('touchCancel');
    }
    await page.waitForTimeout(400);
    if (ansicht === 'tage') {  // Kopier-Vorschau: diese Woche -> naechste Woche (nur Vorschau)
      await page.reload(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500);
      await page.getByRole('button', { name: 'Woche kopieren' }).click(); await page.waitForTimeout(300);
      await page.getByRole('button', { name: 'Vorschau anzeigen' }).click(); await page.waitForTimeout(1300);
      await page.screenshot({ path: path.join(OUT, `11_dienstplan_kopie_vorschau_${name}.png`) });
    }
    console.log(name, ansicht);
    await ctx.close();
  }
}
await browser.close();
