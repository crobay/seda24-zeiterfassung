// NUR DEV: Cockpit > Zeiten, Spalte "Satz" (Drazen 28.11.2026 08:46). Aendert Saetze von DEV-Buchungen und setzt sie am Ende zurueck.
// Aufruf: CK_TOKEN=... node zeiten_satz_ui.mjs <ordner> <sonder-id> <unterhalt-id> <gesperrt-id>
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT, SONDER, UNTER, ZU] = process.argv.slice(2);
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1/cockpit`;
const H = { Authorization: `Bearer ${process.env.CK_TOKEN}`, 'Content-Type': 'application/json' };
let fehler = 0;
const ok = (n, c, i = '') => { console.log(`  [${c ? 'OK ' : 'XX '}] ${n}${i ? ' - ' + i : ''}`); if (!c) fehler++; };
const get = async (id) => (await (await fetch(`${API}/zeiten/${id}`, { headers: H })).json());
const alt = { [SONDER]: (await get(SONDER)).hourly_rate, [UNTER]: (await get(UNTER)).hourly_rate };
const b = await chromium.launch();
const js = [];
try {
  for (const [name, w, h, mobil] of [['pc', 1600, 1000, false], ['handy', 390, 844, true]]) {
    console.log(name);
    const p = await (await b.newContext({ viewport: { width: w, height: h }, isMobile: mobil, hasTouch: mobil })).newPage();
    p.on('pageerror', (e) => js.push(e.message));
    await p.goto(`${BASE}/login`);
    await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); }, process.env.CK_TOKEN);
    await p.goto(`${BASE}/cockpit/zeiten?monat=2026-11&range=month`);
    const zelle = (id) => p.locator(`[data-satz="${id}"]`);
    await zelle(SONDER).waitFor({ timeout: 20000 });
    const kopf = await p.$$eval('.ck-table thead th', (a) => a.map((x) => x.textContent.trim()));
    ok('Spalte "Satz" direkt neben "Std."', kopf.indexOf('Satz') === kopf.findIndex((x) => /^Std/.test(x)) + 1, kopf.join(' | '));
    ok('Satz angezeigt', (await zelle(SONDER).textContent()).includes('€'), (await zelle(SONDER).textContent()).trim());
    await zelle(SONDER).scrollIntoViewIfNeeded();
    // Esc bricht ab
    await zelle(SONDER).locator('[data-satz-knopf]').click();
    const ein = zelle(SONDER).locator('[data-satz-eingabe]');
    ok('Klick -> Eingabefeld, Dialog geht nicht auf', await ein.isVisible() && await p.locator('[role="dialog"]').count() === 0);
    const vorEsc = (await get(SONDER)).hourly_rate;
    await ein.fill('99'); await ein.press('Escape'); await p.waitForTimeout(300);
    ok('Esc bricht ab (nichts gespeichert)', (await get(SONDER)).hourly_rate === vorEsc && await ein.count() === 0);
    if (name === 'pc') {
      // Enter speichert (Sonder)
      await zelle(SONDER).locator('[data-satz-knopf]').click();
      await p.screenshot({ path: path.join(OUT, `eingabe_${name}.png`) });
      await zelle(SONDER).locator('[data-satz-eingabe]').fill('22,50'); await zelle(SONDER).locator('[data-satz-eingabe]').press('Enter');
      await p.waitForTimeout(900);
      ok('Enter speichert (Fensterreinigung 20,00 -> 22,50)', (await get(SONDER)).hourly_rate === 22.5);
      ok('Zelle zeigt neuen Satz', (await zelle(SONDER).textContent()).includes('22,50'));
      ok('Hinweis mit alt -> neu', /20,00 € → 22,50 €/.test(await p.locator('.ck-toast').first().textContent()));
      await p.screenshot({ path: path.join(OUT, `gespeichert_${name}.png`) });
      // Unterhalt: Hinweis im Feld
      await zelle(UNTER).scrollIntoViewIfNeeded();
      await zelle(UNTER).locator('[data-satz-knopf]').click();
      ok('Unterhalt: Hinweis "Lohn rechnet mit Stundenlohn aus dem Stammblatt"', await zelle(UNTER).locator('[data-satz-hinweis]').isVisible());
      await p.screenshot({ path: path.join(OUT, `unterhalt_hinweis_${name}.png`) });
      await zelle(UNTER).locator('[data-satz-eingabe]').fill('18'); await zelle(UNTER).locator('[data-satz-eingabe]').press('Enter'); await p.waitForTimeout(900);
      ok('Unterhalt gespeichert (-> 18,00)', (await get(UNTER)).hourly_rate === 18);
      // ungueltig
      await zelle(UNTER).locator('[data-satz-knopf]').click();
      await zelle(UNTER).locator('[data-satz-eingabe]').fill('abc'); await zelle(UNTER).locator('[data-satz-eingabe]').press('Enter'); await p.waitForTimeout(500);
      ok('Ungueltige Eingabe wird nicht gespeichert', (await get(UNTER)).hourly_rate === 18);
      await zelle(UNTER).locator('[data-satz-eingabe]').press('Escape');
      // gesperrter Monat (Oktober)
      await p.goto(`${BASE}/cockpit/zeiten?monat=2026-10&range=month`);
      await zelle(ZU).waitFor({ timeout: 20000 }); await zelle(ZU).scrollIntoViewIfNeeded();
      await zelle(ZU).locator('[data-satz-knopf]').click(); await p.waitForTimeout(400);
      ok('Oktober (abgeschlossen): kein Eingabefeld, Hinweis Super-PIN', await zelle(ZU).locator('[data-satz-eingabe]').count() === 0 && /Super-PIN/.test(await p.locator('.ck-toast').first().textContent()));
      await p.screenshot({ path: path.join(OUT, `gesperrt_${name}.png`) });
    } else await p.screenshot({ path: path.join(OUT, `zeiten_${name}.png`), fullPage: false });
    ok('kein Querscrollen der Seite', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  }
  const r = await fetch(`${API}/zeiten/${ZU}/satz`, { method: 'PUT', headers: H, body: JSON.stringify({ stundensatz: '30' }) });
  ok('Server: gesperrter Monat -> 423', r.status === 423, `${r.status} ${(await r.json()).detail || ''}`);
  ok('keine JS-Fehler', js.length === 0, js.slice(0, 2).join(' | '));
} finally {
  await b.close();
  for (const [id, v] of Object.entries(alt)) await fetch(`${API}/zeiten/${id}/satz`, { method: 'PUT', headers: H, body: JSON.stringify({ stundensatz: v }) });
  console.log(`Saetze zurueckgesetzt: ${JSON.stringify(alt)}`);
}
console.log(fehler ? `${fehler} FEHLER` : 'ALLES OK'); process.exit(fehler ? 1 : 0);
