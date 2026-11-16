// Screenshots Cockpit auf dev.seda.de. Aufruf: node cockpit_shots.mjs <outdir> <prefix> <who:admin|ol> <pfad,pfad,...> [dark]
import fs from 'fs'; import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT, PREFIX, WHO = 'admin', PATHS = '/cockpit', DARK] = process.argv.slice(2);
const env = Object.fromEntries(fs.readFileSync(new URL('./cockpit_dev.env', import.meta.url), 'utf8').split('\n').filter(l => l.includes('='))
  .map(l => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
const email = WHO === 'ol' ? env.OL_EMAIL : env.ADMIN_EMAIL, pw = WHO === 'ol' ? env.OL_PASSWORD : env.ADMIN_PASSWORD;
const browser = await chromium.launch();
const { defaultBrowserType, ...iphone } = devices['iPhone 15'];
const profiles = { desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 }, handy: { ...iphone, viewport: { width: 393, height: 852 }, deviceScaleFactor: 2 } };
for (const [pname, prof] of Object.entries(profiles)) {
  const ctx = await browser.newContext({ ...prof, locale: 'de-DE', timezoneId: 'Europe/Berlin', colorScheme: DARK ? 'dark' : 'light' });
  const page = await ctx.newPage(); page.setDefaultTimeout(20000);
  page.on('pageerror', e => console.log('PAGEERROR', e.message));
  await page.goto('https://dev.seda.de/login');
  await page.fill('input[name=email]', email); await page.fill('input[name=password]', pw);
  await page.click('button[type=submit]'); await page.waitForURL(/\/(admin|dashboard)/);
  await page.evaluate((d) => localStorage.setItem('ck_theme', d ? 'dark' : 'light'), !!DARK);
  for (const p of PATHS.split(',')) {
    const [url, action] = p.split('|');
    await page.goto('https://dev.seda.de' + url); await page.waitForLoadState('networkidle'); await page.waitForTimeout(900);
    if (action === 'cmdk') { await page.keyboard.press('Control+k'); await page.waitForTimeout(400); await page.keyboard.type('le'); await page.waitForTimeout(500); }
    if (action === 'assignkm') { await page.getByRole('button', { name: /Objekt zuteilen/ }).first().click(); await page.waitForTimeout(500); const sel = page.locator('.ck-dialog select').first(); const opts = await sel.locator('option').allTextContents(); await sel.selectOption({ index: 1 }); await page.locator('.ck-dialog-foot .ck-btn-primary').click(); await page.waitForTimeout(800); }
    if (action === 'assign') { await page.getByRole('button', { name: /Objekt zuteilen/ }).first().click(); await page.waitForTimeout(500); }
    const name = `${PREFIX}_${(url.replace(/^\/cockpit\/?/, '') || 'heute').replace(/[\/#]/g, '-')}${action ? '_' + action : ''}_${pname}${DARK ? '_dunkel' : ''}.png`;
    await page.screenshot({ path: path.join(OUT, name), fullPage: false });
    if (process.env.TALL && !action) {  // Gesamtansicht: Seitenleiste/Navigationsleiste statisch, ganze Seite
      await page.addStyleTag({ content: '.ck-sidebar{position:static!important;height:auto!important;min-height:100%}.ck-bottomnav{position:static!important}.ck-topbar{position:static!important}' });
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(OUT, name.replace('.png', '_gesamt.png')), fullPage: true });
    }
    if (pname === 'handy' && !action) { await page.evaluate(() => window.scrollBy(0, 700)); await page.waitForTimeout(300); await page.screenshot({ path: path.join(OUT, name.replace('_handy', '_handy_2')) }); }
    console.log(name);
  }
  await ctx.close();
}
await browser.close();
