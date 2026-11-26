// NUR DEV: Anwesend-Blatt im Cockpit "Heute" (Drazen 26.11.2026 18:21, fuer Rosi/Objektleitung).
// Die Liste /heute wird im Browser mit festen Testzeilen ersetzt (alle vier Gruppen), damit der Test zu jeder Uhrzeit laeuft.
// Aufruf: CK_TOKEN=... [CK_ROLLE=objektleiter] node anwesend_ui.mjs <ordner>
import path from 'path';
import fs from 'fs';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const BASE = 'https://dev.seda.de';
fs.mkdirSync(OUT, { recursive: true });
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const z = (o) => ({ schicht_id: o.id, employee_id: o.e, name: o.n, personal_nr: o.p, objekt: 'Lidl Bie2', object_id: 20, beginn: o.b, ende: o.en,
  kategorie: o.k || 'C', status: o.s, status_text: o.t || '', eintrag_id: o.kommen ? 900 + o.id : null, kommen: o.kommen || null, gehen: o.gehen || null,
  fehlt_min: o.fm ?? null, telefon: o.tel || null, evtl_offline: o.off || false, letzte_meldung: o.off ? '25.11. 13:00' : null });
const TEST = [
  z({ id: 1, e: 33, n: 'Helena Martin', p: 'D0039', b: '12:55', en: '16:25', s: 'da', kommen: '12:54' }),
  z({ id: 2, e: 31, n: 'Zyumbyul Kurd', p: 'D0038', b: '13:00', en: '16:00', s: 'fehlt', fm: 25, off: true, tel: '+49 171 1234567', t: 'Fehlt – seit 25 min' }),
  z({ id: 3, e: 34, n: 'Lara Hardt-Fabrizis', p: 'D0040', b: '12:55', en: '15:55', s: 'fehlt', fm: 30, t: 'Fehlt – seit 30 min' }),
  z({ id: 4, e: 4, n: 'Ruzica Sertic', p: 'D0002', b: '08:00', en: '09:30', s: 'fertig', kommen: '07:58', gehen: '09:31', k: 'A' }),
  z({ id: 5, e: 4, n: 'Ruzica Sertic', p: 'D0002', b: '17:00', en: '20:30', s: 'kommt', t: 'Kommt um 17:00' }),
];
const browser = await chromium.launch();
const jsFehler = [];
try {
  for (const mobil of [false, true]) {
    console.log(mobil ? 'Handy' : 'PC');
    const p = await (await browser.newContext(mobil ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 1000 } })).newPage();
    p.on('pageerror', (e) => jsFehler.push(e.message));
    await p.route('**/api/v1/cockpit/heute', async (route) => {
      const r = await route.fetch(); const d = await r.json();
      d.schichten = TEST; d.ohne_schicht = [{ employee_id: 36, name: 'Azra Brguljak', personal_nr: 'D0036', objekt: 'Geiger Malsch', seit: '14:02', eintrag_id: 999, status: 'da' }];
      d.kennzahlen = { ...d.kennzahlen, anwesend: 2, fertig: 1, fehlt: 2, kommt: 1, geplant: 5 };
      await route.fulfill({ response: r, json: d });
    });
    await p.goto(`${BASE}/login`);
    await p.evaluate(([x, rolle]) => { localStorage.setItem('token', x); localStorage.setItem('userRole', rolle); }, [process.env.CK_TOKEN, process.env.CK_ROLLE || 'objektleiter']);
    await p.goto(`${BASE}/cockpit`);
    const kachel = p.locator('[data-anwesend-kachel]');
    await kachel.waitFor({ timeout: 15000 });
    await p.waitForFunction(() => /da ·/.test(document.querySelector('[data-anwesend-kachel]')?.textContent || ''), null, { timeout: 15000 });
    const kt = (await kachel.textContent()).replace(/\s+/g, ' ');
    ok('Kachel-Untertitel "2 da · 1 fertig · 2 fehlt von 5"', kt.includes('2 da · 1 fertig · 2 fehlt von 5'), kt);
    await p.screenshot({ path: path.join(OUT, `kachel_${mobil ? 'handy' : 'pc'}.png`) });
    await kachel.click();
    const blatt = p.locator('[data-anwesend-blatt] .ck-sheet');
    await blatt.waitFor({ timeout: 5000 });
    await p.waitForTimeout(400);
    const g = async (k) => (await p.locator(`[data-anw-gruppe="${k}"]`).textContent()).replace(/\s+/g, ' ');
    const da = await g('da'), fe = await g('fehlt'), fi = await g('fertig'), ko = await g('kommt');
    ok('Da: Helena seit 12:54 + Azra ohne Schicht', /Helena Martin.*seit 12:54/.test(da) && /Azra Brguljak.*ohne Schicht.*seit 14:02/.test(da), da);
    ok('Fehlt: seit 25 Min. + evtl. offline + Anrufen (tel:)', /Zyumbyul Kurd.*evtl\. offline – letzte Handymeldung \(25\.11\. 13:00\) kam ohne Netz.*seit 25 Min\./.test(fe)
      && (await p.locator('[data-anw-ma="D0038"] [data-anw-anrufen]').getAttribute('href')) === 'tel:+491711234567', fe);
    ok('Fehlt ohne Nummer: Knopf "Nummer?" zum Stammblatt, kein offline', await p.locator('[data-anw-ma="D0040"] [data-anw-keine-nummer]').count() === 1
      && await p.locator('[data-anw-ma="D0040"] [data-anw-offline]').count() === 0);
    ok('Fertig: von–bis', /Ruzica Sertic.*07:58–09:31/.test(fi), fi);
    ok('Kommt noch: um 17:00', /Ruzica Sertic.*um 17:00/.test(ko), ko);
    const box = await blatt.boundingBox(); const vp = p.viewportSize();
    if (mobil) ok('Handy: Blatt unten angedockt, volle Breite', Math.abs(box.y + box.height - vp.height) < 2 && box.width >= vp.width - 1, JSON.stringify(box));
    else ok('PC: Blatt mittig', Math.abs(box.x + box.width / 2 - vp.width / 2) < 3 && box.y > 20, JSON.stringify(box));
    ok('kein Querscrollen', await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await p.screenshot({ path: path.join(OUT, `blatt_${mobil ? 'handy' : 'pc'}.png`) });
    if (mobil) { await p.mouse.click(vp.width / 2, 20); } else { await p.keyboard.press('Escape'); }
    await p.waitForTimeout(300);
    ok(mobil ? 'schliesst bei Tipp daneben' : 'schliesst mit Esc', await p.locator('[data-anwesend-blatt]').count() === 0);
  }
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} finally { await browser.close(); }
console.log(fehler ? `${fehler} FEHLER` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
