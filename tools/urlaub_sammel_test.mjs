// NUR DEV: Cockpit "Zu erledigen" zeigt offene Urlaubsantraege nur als eine Zeile "Urlaubsanträge (N)" (Drazen 25.11.2026 20:25).
// Aufruf: CK_TOKEN=... CK_N=<offene Antraege> [CK_BASE=https://dev.seda.de] node urlaub_sammel_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const BASE = process.env.CK_BASE || 'https://dev.seda.de';
const N = Number(process.env.CK_N);
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
    await p.goto(`${BASE}/cockpit`);
    await p.waitForSelector('#todo .ck-list, #todo .ck-empty', { timeout: 15000 });
    const zeilen = p.locator('[data-urlaub-sammel]');
    ok('genau eine Zeile fuer Urlaubsantraege', await zeilen.count() === 1);
    ok(`Titel "Urlaubsanträge (${N})"`, (await zeilen.locator('.ck-row-title').textContent()).trim() === `Urlaubsanträge (${N})`);
    const einzeln = await p.locator('#todo .ck-row .ck-tag', { hasText: /^Urlaubsantrag$/ }).count();
    ok('keine einzelnen Urlaubsantraege mehr in der Liste', einzeln === 0, `${einzeln}`);
    ok('kein Genehmigen/Ablehnen-Knopf an der Urlaubszeile', await zeilen.locator('button').count() === 0);
    ok('kein Querscrollen', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await p.screenshot({ path: path.join(OUT, mobil ? 'todo_handy.png' : 'todo_pc.png'), fullPage: false });
    await p.locator('[data-urlaub-sammel-link]').click();
    await p.waitForURL(/tab=urlaub/, { timeout: 10000 });
    ok('Klick fuehrt zur Antragsliste (offene)', /tab=urlaub&status=pending/.test(p.url()), p.url());
    await p.getByText('24.05.2027 - 28.05.2027').first().waitFor({ timeout: 15000 }).catch(() => {});
    const offen = await p.getByText('24.05.2027 - 28.05.2027').count() + await p.getByText('02.08.2027 - 06.08.2027').count();
    ok('Antragsliste zeigt beide offenen Antraege von T9999 (2027, nicht auf 2026 gefiltert)', offen === 2, `${offen}`);
    await p.screenshot({ path: path.join(OUT, mobil ? 'liste_handy.png' : 'liste_pc.png'), fullPage: false });
  }
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.join(' | '));
} finally { await browser.close(); }
console.log(fehler ? `${fehler} Fehler` : 'alles OK');
process.exit(fehler ? 1 : 0);
