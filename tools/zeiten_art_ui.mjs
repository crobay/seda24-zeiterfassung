// NUR DEV: Cockpit > Zeiten, Spalte "Art" + Satz grau bei Unterhalt (Drazen 28.11.2026 09:11).
// Phase "hin": Unterhalt -> Sonderreinigung (Satz vorbelegt, sofort editierbar, 21,00) + Pruefungen (grau, gesperrt, Urlaub, Handy).
// Phase "zurueck": Sonderreinigung -> Unterhalt (Satz = Stammblatt-Lohn, grau).
// Aufruf: CK_TOKEN=... node zeiten_art_ui.mjs <ordner> <hin|zurueck> <unterhalt-id> <gesperrt-id> <urlaub-id>
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT, PHASE, ID, ZU, URL] = process.argv.slice(2);
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1/cockpit`;
const H = { Authorization: `Bearer ${process.env.CK_TOKEN}`, 'Content-Type': 'application/json' };
let fehler = 0;
const ok = (n, c, i = '') => { console.log(`  [${c ? 'OK ' : 'XX '}] ${n}${i ? ' - ' + i : ''}`); if (!c) fehler++; };
const get = async (id) => (await (await fetch(`${API}/zeiten/${id}`, { headers: H })).json());
const b = await chromium.launch();
const js = [];
const seite = async (w, h, mobil, monat = '2026-11') => {
  const p = await (await b.newContext({ viewport: { width: w, height: h }, isMobile: mobil, hasTouch: mobil })).newPage();
  p.on('pageerror', (e) => js.push(e.message));
  await p.goto(`${BASE}/login`);
  await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); }, process.env.CK_TOKEN);
  await p.goto(`${BASE}/cockpit/zeiten?monat=${monat}&range=month`);
  return p;
};
try {
  if (PHASE === 'hin') {
    console.log('PC');
    const p = await seite(1600, 1000, false);
    const art = p.locator(`[data-art="${ID}"]`), satz = p.locator(`[data-satz="${ID}"]`);
    await art.waitFor({ timeout: 20000 }); await art.scrollIntoViewIfNeeded();
    const kopf = await p.$$eval('.ck-table thead th', (a) => a.map((x) => x.textContent.trim()));
    ok('Spalte "Art" vor "Satz"', kopf.indexOf('Art') + 1 === kopf.indexOf('Satz'), kopf.join(' | '));
    ok('Unterhalt: Satz grau, nicht editierbar, Tooltip', await satz.getAttribute('data-satz-grau') === '' && await satz.locator('button, input').count() === 0
      && await satz.getAttribute('title') === 'Lohn aus Stammblatt (Lexware)', (await satz.textContent()).trim());
    const r400 = await fetch(`${API}/zeiten/${ID}/satz`, { method: 'PUT', headers: H, body: JSON.stringify({ stundensatz: '25' }) });
    ok('Server: Satz bei Unterhalt abgelehnt (400)', r400.status === 400);
    await p.screenshot({ path: path.join(OUT, 'unterhalt_grau_pc.png') });
    await art.locator('[data-art-knopf]').click();
    ok('Klick auf Art -> Auswahl mit 4 Arten', (await art.locator('option').allTextContents()).join('|') === 'Unterhaltsreinigung|Grundreinigung|Sonderreinigung|Fensterreinigung');
    await p.screenshot({ path: path.join(OUT, 'art_auswahl_pc.png') });
    await art.locator('[data-art-auswahl]').selectOption('Sonderreinigung');
    await satz.locator('[data-satz-eingabe]').waitFor({ timeout: 5000 });
    const e = await get(ID);
    ok('Art gespeichert, Satz mit Sondersatz vorbelegt', e.service_type === 'Sonderreinigung' && e.hourly_rate === 20, `${e.service_type} ${e.hourly_rate}`);
    ok('Satz sofort editierbar (Feld offen, vorbelegt 20,00)', await satz.locator('[data-satz-eingabe]').inputValue() === '20,00');
    await p.screenshot({ path: path.join(OUT, 'sonder_satz_offen_pc.png') });
    await satz.locator('[data-satz-eingabe]').fill('21'); await satz.locator('[data-satz-eingabe]').press('Enter'); await p.waitForTimeout(900);
    ok('Satz 21,00 gespeichert', (await get(ID)).hourly_rate === 21);
    // gesperrter Monat
    const q = await seite(1600, 1000, false, '2026-10');
    await q.locator(`[data-art="${ZU}"] [data-art-knopf]`).waitFor({ timeout: 20000 });
    await q.locator(`[data-art="${ZU}"] [data-art-knopf]`).scrollIntoViewIfNeeded(); await q.locator(`[data-art="${ZU}"] [data-art-knopf]`).click(); await q.waitForTimeout(400);
    ok('Oktober gesperrt: keine Auswahl, Hinweis Super-PIN', await q.locator(`[data-art="${ZU}"] [data-art-auswahl]`).count() === 0 && /Super-PIN/.test(await q.locator('.ck-toast').first().textContent()));
    const r423 = await fetch(`${API}/zeiten/${ZU}/art`, { method: 'PUT', headers: H, body: JSON.stringify({ art: 'Grundreinigung' }) });
    ok('Server: gesperrter Monat -> 423', r423.status === 423);
    // Urlaub
    const ru = await fetch(`${API}/zeiten/${URL}/art`, { method: 'PUT', headers: H, body: JSON.stringify({ art: 'Grundreinigung' }) });
    ok('Urlaub: Art nicht aenderbar (Server 400)', ru.status === 400);
    const u = p.locator(`[data-art="${URL}"]`);
    if (await u.count()) ok('Urlaub: Zelle ohne Knopf', await u.locator('button').count() === 0, (await u.textContent()).trim());
    console.log('Handy');
    const m = await seite(390, 844, true);
    const ma = m.locator(`[data-art="${ID}"]`);
    await ma.waitFor({ timeout: 20000 }); await ma.scrollIntoViewIfNeeded();
    ok('Handy: Art "Sonder" + Satz 21,00 € editierbar', (await ma.textContent()).includes('Sonder') && (await m.locator(`[data-satz="${ID}"]`).textContent()).includes('21,00')
      && await m.locator(`[data-satz="${ID}"] [data-satz-knopf]`).count() === 1);
    await ma.locator('[data-art-knopf]').click();
    ok('Handy: Auswahl geht auf', await ma.locator('[data-art-auswahl]').isVisible());
    await m.screenshot({ path: path.join(OUT, 'art_auswahl_handy.png') });
    await ma.locator('[data-art-auswahl]').press('Escape');
    ok('kein Querscrollen der Seite (Handy)', await m.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  } else {
    const p = await seite(1600, 1000, false);
    const art = p.locator(`[data-art="${ID}"]`), satz = p.locator(`[data-satz="${ID}"]`);
    await art.waitFor({ timeout: 20000 }); await art.scrollIntoViewIfNeeded();
    await art.locator('[data-art-knopf]').click();
    await art.locator('[data-art-auswahl]').selectOption('Unterhaltsreinigung'); await p.waitForTimeout(900);
    const e = await get(ID);
    ok('Zurueck auf Unterhalt: Satz = Stammblatt-Lohn, grau', e.service_type === 'Unterhaltsreinigung' && e.hourly_rate === 17 && await satz.getAttribute('data-satz-grau') === '', `${e.service_type} ${e.hourly_rate}`);
    await p.screenshot({ path: path.join(OUT, 'zurueck_unterhalt_pc.png') });
  }
  ok('keine JS-Fehler', js.length === 0, js.slice(0, 2).join(' | '));
} finally { await b.close(); }
console.log(fehler ? `${fehler} FEHLER` : 'ALLES OK'); process.exit(fehler ? 1 : 0);
