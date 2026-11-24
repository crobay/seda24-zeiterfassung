// NUR DEV: Zeichen 📶 "verspaetet uebertragen" (Drazen 24.11.2026) im Cockpit "Zeiten" und in der alten Journal-Ansicht.
// Liest nur (Monat November, offline nachgereichte App-Stempel aus der LIVE-Kopie).
// Aufruf: CK_TOKEN=$(./venv/bin/python ../tools/dev_token.py <admin-mail>) node versp_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de';
fs.mkdirSync(OUT, { recursive: true });
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const KURZ = /^📶 \+(\d+ Min|\d+:\d\d h) verspätet$/;
const kurzOk = async (pg) => pg.$$eval('[data-versp-kurz]', (els) => els.map((e) => ({ t: e.textContent, sichtbar: e.offsetParent !== null && e.getBoundingClientRect().height > 0,
  klein: parseFloat(getComputedStyle(e).fontSize) < parseFloat(getComputedStyle(e.parentElement).fontSize) })));
const MUSTER = /^📶 (\d+ Min|\d+:\d\d h) verspätet übertragen \(Handy \d\d:\d\d, Server (\d\d\.\d\d\. )?\d\d:\d\d\)$/;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const jsFehler = [];
page.on('pageerror', (e) => jsFehler.push(e.message));
try {
  await page.goto(`${BASE}/login`);
  await page.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);

  console.log('Cockpit Zeiten (Monat)');
  await page.goto(`${BASE}/cockpit/zeiten?range=month`);
  await page.waitForSelector('table.ck-table tbody tr');
  const zeichen = await page.$$eval('[data-versp]', (els) => els.map((e) => ({ art: e.dataset.versp, t: e.getAttribute('title') })));
  ok('Zeichen vorhanden', zeichen.length > 0, `${zeichen.length} Stück`);
  ok('Tooltip-Text wie vorgegeben', zeichen.every((z) => MUSTER.test(z.t)), zeichen[0]?.t);
  const alle = await page.$$eval('table.ck-table tbody tr', (r) => r.length);
  const sauber = await page.$$eval('table.ck-table tbody tr', (rs) => rs.filter((r) => !r.querySelector('[data-versp]')).length);
  ok('sauber gestempelte ohne Zeichen', sauber > 0 && sauber < alle, `${sauber} von ${alle}`);
  let k = await kurzOk(page);
  ok('Kurztext unter jeder Zeit mit Zeichen', k.length === zeichen.length && k.every((x) => KURZ.test(x.t) && x.sichtbar && x.klein), k[0]?.t);
  const z = page.locator('[data-versp]').first();
  await z.scrollIntoViewIfNeeded(); await z.hover();
  await page.screenshot({ path: path.join(OUT, 'zeiten_zeichen.png') });
  const vorher = page.url();
  await z.click();
  ok('Klick auf Zeichen öffnet nicht die Bearbeitung', !(await page.$('.ck-dialog, [role=dialog]')) && page.url() === vorher);

  console.log('Filter "Nur mit Hinweis"');
  await page.getByLabel(/Nur mit Hinweis/i).check().catch(async () => page.locator('label', { hasText: /Hinweis/ }).locator('input').check());
  await page.waitForTimeout(300);
  const gefiltert = await page.$$eval('table.ck-table tbody tr', (rs) => rs.map((r) => !!r.querySelector('[data-versp]') || /\S/.test(r.cells[7]?.textContent || '')));
  ok('alle Zeilen mit Zeichen bleiben drin', (await page.$$('[data-versp]')).length === zeichen.length);
  ok('jede gefilterte Zeile hat Zeichen oder Hinweis', gefiltert.length > 0 && gefiltert.every(Boolean), `${gefiltert.length} Zeilen`);
  await page.screenshot({ path: path.join(OUT, 'zeiten_filter.png') });

  console.log('Alte Journal-Ansicht');
  await page.goto(`${BASE}/admin?klassisch=1`);
  await page.locator('button', { hasText: /^\s*Journal\s*$/ }).first().click();
  await page.waitForSelector('[data-versp]', { timeout: 15000 }).catch(() => null);
  const alt = await page.$$eval('[data-versp]', (els) => els.map((e) => e.getAttribute('title')));
  ok('Zeichen im Journal', alt.length > 0, `${alt.length} Stück`);
  ok('Tooltip-Text im Journal', alt.length > 0 && alt.every((t) => MUSTER.test(t)), alt[0]);
  ok('altes Etikett "offline, … verspätet" weg', !(await page.content()).includes('🕓 offline'));
  await page.locator('[data-versp]').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, 'journal_zeichen.png') });
  k = await kurzOk(page);
  ok('Kurztext im Journal', k.length === alt.length && k.every((x) => KURZ.test(x.t) && x.sichtbar && x.klein), k[0]?.t);

  console.log('Handy (390 px, Touch)');
  const hctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  const h = await hctx.newPage();
  h.on('pageerror', (e) => jsFehler.push(e.message));
  await h.goto(`${BASE}/login`);
  await h.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);
  await h.goto(`${BASE}/cockpit/zeiten?range=month`);
  await h.waitForSelector('[data-versp-kurz]');
  k = await kurzOk(h);
  ok('Kurztext auf dem Handy sichtbar', k.length > 0 && k.every((x) => x.sichtbar && KURZ.test(x.t)), `${k.length} Stück`);
  await h.locator('[data-versp-kurz]').first().scrollIntoViewIfNeeded();
  await h.screenshot({ path: path.join(OUT, 'handy_zeiten.png') });
  await hctx.close();
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} catch (e) {
  ok('Ablauf', false, e.message.split('\n')[0]);
  await page.screenshot({ path: path.join(OUT, 'fehler.png') }).catch(() => {});
}
await browser.close();
console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
