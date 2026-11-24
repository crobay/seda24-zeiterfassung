// Sackgassen-Pruefung: alle internen Cockpit-Links aufrufen (nur lesen, keine Klicks auf Aktionen)
import fs from 'fs'; import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const env = Object.fromEntries(fs.readFileSync(new URL('./cockpit_dev.env', import.meta.url), 'utf8').split('\n').filter(l => l.includes('=')).map(l => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
const WHO = process.argv[2] || 'admin';
const browser = await chromium.launch(); const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } }); const page = await ctx.newPage();
const errs = []; page.on('pageerror', (e) => errs.push(`${page.url()}: ${e.message}`));
page.on('response', (r) => { if (r.url().includes('/api/v1/cockpit') && r.status() >= 400 && r.status() !== 409) errs.push(`${page.url()} -> API ${r.status()} ${r.url().replace(/^.*\/api/, '/api')}`); });
await page.goto('https://dev.seda.de/login');
await page.fill('input[name=email]', WHO === 'ol' ? env.OL_EMAIL : env.ADMIN_EMAIL); await page.fill('input[name=password]', WHO === 'ol' ? env.OL_PASSWORD : env.ADMIN_PASSWORD);
await page.click('button[type=submit]'); await page.waitForURL(/\/(admin|dashboard|cockpit)/);
const seen = new Set(); const queue = ['/cockpit', '/cockpit/dienstplan', '/cockpit/mitarbeiter', '/cockpit/objekte', '/cockpit/zeiten', '/cockpit/abrechnung', '/cockpit/einstellungen'];
const bad = [];
while (queue.length && seen.size < 90) {
  const u = queue.shift(); const key = u.replace(/\/\d+/g, '/:id').replace(/#.*/, ''); if (seen.has(key)) continue; seen.add(key);
  await page.goto('https://dev.seda.de' + u); await page.waitForLoadState('networkidle'); await page.waitForTimeout(400);
  const now = new URL(page.url()).pathname + new URL(page.url()).search;
  if (u !== '/cockpit' && (now === '/cockpit' || now === '/cockpit/') && !u.startsWith('/cockpit#')) bad.push(`${u} -> umgeleitet auf /cockpit`);
  if (await page.getByText('Das hat nicht geklappt').count()) bad.push(`${u} -> Fehlerkasten`);
  for (const h of await page.$$eval('a[href^="/cockpit"]', (as) => as.map((a) => a.getAttribute('href')))) queue.push(h);
}
await browser.close();
console.log(`${WHO}: ${seen.size} Ziele geprueft`); console.log([...bad, ...errs].join('\n') || 'keine Sackgassen, keine Fehler');
