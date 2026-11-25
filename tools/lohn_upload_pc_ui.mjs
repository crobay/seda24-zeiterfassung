// NUR DEV: Monatsabschluss Schritt 3 - Anzeige "Upload-PC zuletzt gemeldet" (Drazen 26.11.2026 00:41).
// Aufruf: CK_TOKEN=... CK_ERWARTET=ok|still|nie [CK_MONAT=2026-10] node lohn_upload_pc_ui.mjs <ordner>
import path from 'path';
import fs from 'fs';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const BASE = 'https://dev.seda.de';
const SOLL = process.env.CK_ERWARTET || 'ok';
const MONAT = process.env.CK_MONAT || '2026-10';
fs.mkdirSync(OUT, { recursive: true });
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const browser = await chromium.launch();
const jsFehler = [];
try {
  for (const mobil of [false, true]) {
    console.log(mobil ? 'Handy' : 'PC');
    const p = await (await browser.newContext(mobil ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 1000 } })).newPage();
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.goto(`${BASE}/login`);
    await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); }, process.env.CK_TOKEN);
    await p.goto(`${BASE}/cockpit/abschluss?monat=${MONAT}`);
    await p.waitForSelector('[data-schritt="upload"]', { timeout: 15000 });
    await p.locator('[data-schritt="upload"]').click();
    const box = p.locator('[data-upload-pc]');
    await box.waitFor({ timeout: 10000 });
    const art = await box.getAttribute('data-upload-pc');
    const txt = (await box.textContent()).replace(/\s+/g, ' ');
    ok(`Hinweis Upload-PC sichtbar (${art})`, art === SOLL, txt);
    if (SOLL === 'ok') ok('Rechner + "zuletzt gemeldet" + Ordner', /Upload-PC TESTPC-LINUX zuletzt gemeldet: heute \d\d:\d\d/.test(txt) && /Lexware-Ordner: 10\/2026: Ordner fehlt · 11\/2026: 2 Dateien/.test(txt), txt);
    if (SOLL === 'ok') ok('letzter Fehler angezeigt', await p.locator('[data-upload-pc-fehler]').count() === 1);
    if (SOLL === 'still') ok('Stille-Text', /seit \d+ Std\. ohne Meldung \(Grenze 24 Std\., es zählen nur Werktage\)/.test(txt), txt);
    if (SOLL === 'nie') ok('Nie-Text', /noch nicht gemeldet/.test(txt), txt);
    ok('kein Querscrollen', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await box.scrollIntoViewIfNeeded();
    await p.screenshot({ path: path.join(OUT, `pc_${SOLL}_${mobil ? 'handy' : 'pc'}.png`) });
  }
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} catch (e) {
  ok('Ablauf', false, e.message.split('\n')[0]);
} finally { await browser.close(); }
console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
