// Monatsabschluss Schritt 1 aufgeraeumt (Drazen 28.11.2026 09:28): Absender-Status, rote Hinweise sichtbar, graue hinter "i",
// "kommt noch", abgehakte MA blass + am Ende, Umschalter "Nur offene"/"Alle" gemerkt. Schreibt nichts (Nicht-GET blockiert);
// zwei MA werden im Browser als abgehakt simuliert. Aufruf: CK_TOKEN=... node abschluss_schritt1_ui.mjs <ordner> [BASE] [monat]
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT, BASE = 'https://dev.seda.de', MONAT = '2026-11', MOCK = 'mock'] = process.argv.slice(2);
let fehler = 0; const blockiert = [], js = [];
const ok = (n, c, i = '') => { console.log(`  [${c ? 'OK ' : 'XX '}] ${n}${i ? ' - ' + i : ''}`); if (!c) fehler++; };
const b = await chromium.launch();
for (const [name, w, h, touch] of [['pc', 1600, 1000, false], ['tablet', 1280, 800, true], ['handy', 390, 844, true]]) {
  console.log(name);
  const p = await (await b.newContext({ viewport: { width: w, height: h }, isMobile: touch && w < 900, hasTouch: touch })).newPage();
  p.on('pageerror', (e) => js.push(e.message));
  let fertigNr = [];
  await p.route('**/api/**', async (r) => {
    const q = r.request();
    if (q.method() !== 'GET' && !q.url().endsWith('/auth/refresh')) { blockiert.push(q.method() + ' ' + q.url()); return r.abort(); }
    if (MOCK === 'mock' && q.url().endsWith(`/abschluss/${MONAT}`)) {
      const res = await r.fetch(); const d = await res.json();
      d.pruefliste.mitarbeiter.slice(0, 2).forEach((x) => { x.haken_stunden = x.haken_km = true; fertigNr.push(x.personal_nr); });
      return r.fulfill({ response: res, json: d });
    }
    return r.continue();
  });
  await p.goto(`${BASE}/login`);
  await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); localStorage.removeItem('ck_ab_ma_filter'); }, process.env.CK_TOKEN);
  await p.goto(`${BASE}/cockpit/abschluss?monat=${MONAT}`);
  await p.locator('[data-ma-liste] [data-ma]').first().waitFor({ timeout: 20000 });
  const vs = (await p.locator('[data-versand-status]').textContent()).replace(/\s+/g, ' ');
  ok('Gelber Kasten: Status je Absender (Lohn + Material)', /Lohn .*lohn@seda\.de.*: (Echter Versand aktiv|Testmodus – alles an \S+)/.test(vs) && /Material .*material@seda24\.de.*: (Echter Versand aktiv|Testmodus – alles an \S+)/.test(vs), vs.slice(0, 200));
  const sichtbarGrau = await p.locator('[data-ma-hinweis="info"]').count();
  ok('Graue Hinweise eingeklappt (hinter "i")', sichtbarGrau === 0 && await p.locator('[data-ma-info]').count() > 0, `${await p.locator('[data-ma-info]').count()} i-Knoepfe`);
  ok('Rote Hinweise sichtbar', await p.locator('[data-ma-hinweis="rot"]').count() > 0, `${await p.locator('[data-ma-hinweis="rot"]').count()} rot`);
  const iBtn = p.locator('[data-ma-info]').first();
  await iBtn.scrollIntoViewIfNeeded(); await iBtn.click();
  ok('"i" klappt graue Hinweise auf', await p.locator('[data-ma-hinweis="info"]').count() > 0);
  const kommt = await p.locator('[data-ma-kommt]').allTextContents();
  ok('"kommt noch (n)" grau statt rot', !(await p.locator('[data-ma-hinweis="rot"]').allTextContents()).some((x) => /kommt noch/.test(x)), kommt.join(' | ') || 'heute keine offenen Schichten');
  if (MOCK === 'mock') {
    const reihen = await p.$$eval('[data-ma-liste] tbody tr', (a) => a.map((tr) => ({ nr: tr.getAttribute('data-ma'), f: tr.getAttribute('data-ma-fertig'), op: getComputedStyle(tr.querySelector('td')).opacity })));
    const letzte = reihen.slice(-2);
    ok('Abgehakte MA am Ende und blass', letzte.every((r) => r.f === '1' && fertigNr.includes(r.nr) && Number(r.op) < 0.7) && reihen.slice(0, -2).every((r) => r.f === '0'), letzte.map((r) => `${r.nr} ${r.op}`).join(', '));
    await p.locator('[data-ma-filter-k="offen"]').click(); await p.waitForTimeout(200);
    ok('"Nur offene" blendet abgehakte aus', await p.locator('[data-ma-liste] tbody tr[data-ma-fertig="1"]').count() === 0 && await p.locator('[data-ma-liste] tbody tr').count() === reihen.length - 2);
    await p.screenshot({ path: path.join(OUT, `nur_offene_${name}.png`), fullPage: name !== 'pc' });
    await p.reload(); await p.locator('[data-ma-liste] [data-ma]').first().waitFor({ timeout: 20000 });
    ok('Zustand gemerkt (nach Neuladen "Nur offene")', await p.locator('[data-ma-filter-k="offen"]').getAttribute('aria-pressed') === 'true' && await p.locator('[data-ma-liste] tbody tr[data-ma-fertig="1"]').count() === 0);
    await p.locator('[data-ma-filter-k="alle"]').click(); await p.waitForTimeout(200);
  }
  ok('kein Querscrollen der Seite', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await p.screenshot({ path: path.join(OUT, `schritt1_${name}.png`), fullPage: name !== 'pc' });
}
ok('keine schreibenden Anfragen', blockiert.length === 0, blockiert.join(' | '));
ok('keine JS-Fehler', js.length === 0, js.slice(0, 2).join(' | '));
await b.close();
console.log(fehler ? `${fehler} FEHLER` : 'ALLES OK'); process.exit(fehler ? 1 : 0);
