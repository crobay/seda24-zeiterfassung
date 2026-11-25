// NUR DEV/LIVE-Smoke: Cockpit › Einstellungen › E-Mail-Versand (Microsoft 365). Speichert nichts, testet keine Verbindung.
// Aufruf: CK_TOKEN=... [CK_TOKEN_OL=...] [CK_BASE=https://app.seda.de] node mailversand_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const BASE = process.env.CK_BASE || 'https://dev.seda.de';
fs.mkdirSync(OUT, { recursive: true });
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const browser = await chromium.launch();
const jsFehler = [];
async function seite(tk, mobil) {
  const p = await (await browser.newContext(mobil ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 1000 } })).newPage();
  p.on('pageerror', (e) => jsFehler.push(e.message));
  await p.goto(`${BASE}/login`);
  await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); }, tk);
  return p;
}
try {
  for (const mobil of [false, true]) {
    console.log(mobil ? 'Handy' : 'PC');
    const p = await seite(process.env.CK_TOKEN, mobil);
    await p.goto(`${BASE}/cockpit/einstellungen?tab=mail`);
    await p.waitForSelector('[data-mailversand]', { timeout: 10000 });
    ok('Reiter "E-Mail-Versand" sichtbar', await p.getByRole('button', { name: 'E-Mail-Versand' }).count() === 1);
    ok('Mandant vorbelegt', await p.locator('[data-mail-tenant]').inputValue() === '49ade56b-d15a-4fdf-a72e-a03c13331855');
    ok('Client-ID vorbelegt', await p.locator('[data-mail-client]').inputValue() === '6d6bf952-dd2e-4588-91f5-4e5928c1ef04');
    const sec = p.locator('[data-mail-secret]');
    ok('Geheimnis-Feld leer + verdeckt', await sec.inputValue() === '' && await sec.getAttribute('type') === 'password');
    const da = /gespeichert/.test(await sec.getAttribute('placeholder') || '');
    ok(`Speichern ${da ? 'frei (Geheimnis gespeichert)' : 'gesperrt ohne Geheimnis'}`, (await p.locator('[data-mail-speichern]').isDisabled()) === !da);
    ok('Verbindung testen nur wenn eingerichtet', (await p.locator('[data-mail-test]').isDisabled()) === !da);
    const txt = await p.locator('[data-mailversand]').textContent();
    ok('Absender Lohn + Material angezeigt', /lohn@seda\.de/.test(txt) && /SEDA24 Objektbetreuung.*material@seda24\.de/.test(txt));
    ok('beide im Testmodus', (txt.match(/Testmodus – alles an/g) || []).length === 2);
    ok('kein Querscrollen', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await p.screenshot({ path: path.join(OUT, mobil ? 'mail_handy.png' : 'mail_pc.png'), fullPage: true });
  }
  if (process.env.CK_TOKEN_OL) {
    console.log('Objektleitung');
    const p = await seite(process.env.CK_TOKEN_OL, false);
    await p.goto(`${BASE}/cockpit/einstellungen?tab=mail`);
    await p.waitForSelector('.ck-page-head', { timeout: 10000 });
    await p.waitForTimeout(800);
    ok('OL sieht den Reiter nicht', await p.getByRole('button', { name: 'E-Mail-Versand' }).count() === 0 && await p.locator('[data-mailversand]').count() === 0);
  }
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} catch (e) {
  ok('Ablauf', false, e.message.split('\n')[0]);
} finally { await browser.close(); }
console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
