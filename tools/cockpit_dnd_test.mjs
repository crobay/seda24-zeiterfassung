// Browser-Test Dienstplan (nur DEV): Ziehen mit Maus, Strg-Kopieren, Mitarbeiter-Ansicht, Touch (langes Druecken),
// Wischen = Scrollen, Menue "Verschieben/Kopieren nach", Woche kopieren mit Vorschau + Rueckgaengig.
// Legt eigene Testschichten ~10 Wochen in der Zukunft an und raeumt am Ende alles wieder weg.
// Aufruf: CK_TOKEN=$(...dev_token.py admin@seda24.de) node cockpit_dnd_test.mjs [screenshot-ordner]
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const TOKEN = process.env.CK_TOKEN; const OUT = process.argv[2];
if (!TOKEN) throw new Error('CK_TOKEN fehlt');
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1/cockpit`;
const H = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' };
const call = async (m, p, b) => { const r = await fetch(API + p, { method: m, headers: H, body: b ? JSON.stringify(b) : undefined }); return { s: r.status, j: await r.json().catch(() => null) }; };
const iso = (d) => d.toISOString().slice(0, 10);
const plus = (s, n) => { const d = new Date(s + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
let ok = 0, fail = 0; const angelegt = new Set();
const check = (c, msg) => { if (c) { ok++; console.log('  OK  ', msg); } else { fail++; console.log('  FEHLER', msg); } };

// Testdaten: zwei MA, eine Montagsschicht in Woche +10
const aus = (await call('GET', '/auswahl')).j;
const d0 = new Date(); d0.setUTCDate(d0.getUTCDate() + 70); d0.setUTCDate(d0.getUTCDate() - ((d0.getUTCDay() + 6) % 7));
const MO = iso(d0);
const [A, B] = aus.mitarbeiter.filter((m) => m.personal_nr !== 'D0002').slice(0, 2);
const OBJ = aus.objekte[0].id;
const neu = async (eid, datum, b = '08:00', e = '10:00') => { const r = await call('POST', '/dienstplan', { employee_id: eid, object_id: OBJ, datum, beginn: b, ende: e }); angelegt.add(r.j.id); return r.j.id; };
const sid = await neu(A.id, MO);
const lese = async (id) => (await call('GET', `/schicht/${id}`)).j;
const woche = async () => (await call('GET', `/dienstplan?start=${MO}`)).j.tage.flatMap((d) => d.schichten.map((s) => ({ ...s, datum: d.datum })));
console.log(`Testwoche ${MO}, MA ${A.name} / ${B.name}, Schicht ${sid}`);

const browser = await chromium.launch();
async function seite(profil, ansicht = 'tage') {
  const ctx = await browser.newContext({ ...profil, locale: 'de-DE', timezoneId: 'Europe/Berlin' });
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  await page.goto(`${BASE}/login`);
  await page.evaluate(([tk, a]) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_theme_v2', 'light'); localStorage.setItem('ck_dp_ansicht', a); }, [TOKEN, ansicht]);
  await page.goto(`${BASE}/cockpit/dienstplan?start=${MO}`); await page.waitForLoadState('networkidle'); await page.waitForTimeout(600);
  return { ctx, page };
}
const chip = (page, id) => page.locator(`[data-schicht="${id}"]`);
const tag = (page, datum) => page.locator(`[data-tag="${datum}"]`);
async function mausZiehen(page, von, nach, strg = false) {
  const a = await von.boundingBox(), b = await nach.boundingBox();
  await page.mouse.move(a.x + 30, a.y + a.height / 2);
  if (strg) await page.keyboard.down('Control');
  await page.mouse.down();
  await page.mouse.move(a.x + 40, a.y + a.height / 2 + 4, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + 30, { steps: 12 });
  await page.waitForTimeout(150);
  await page.mouse.up();
  if (strg) await page.keyboard.up('Control');
  await page.waitForTimeout(1200);
}
const cdps = new WeakMap();
async function touch(page, typ, x, y) {
  if (!cdps.has(page)) cdps.set(page, await page.context().newCDPSession(page));
  const cdp = cdps.get(page);
  await cdp.send('Input.dispatchTouchEvent', { type: typ, touchPoints: typ === 'touchEnd' ? [] : [{ x, y }] });
}
async function touchZiehen(page, von, nach, halten = 500) {
  const a = await von.boundingBox(), b = await nach.boundingBox();
  const x0 = a.x + 30, y0 = a.y + a.height / 2, x1 = b.x + b.width / 2, y1 = b.y + 30;
  await touch(page, 'touchStart', x0, y0); await page.waitForTimeout(halten);
  for (let i = 1; i <= 12; i++) { await touch(page, 'touchMove', x0 + (x1 - x0) * i / 12, y0 + (y1 - y0) * i / 12); await page.waitForTimeout(25); }
  await touch(page, 'touchEnd', x1, y1); await page.waitForTimeout(1300);
}

try {
  // 1) PC: Maus ziehen Mo -> Di = verschieben
  console.log('PC (Maus)');
  let { ctx, page } = await seite({ viewport: { width: 1440, height: 900 } });
  await mausZiehen(page, chip(page, sid), tag(page, plus(MO, 1)));
  check((await lese(sid)).datum === plus(MO, 1), 'Ziehen Mo->Di verschiebt die Schicht');
  // Rueckgaengig ueber den Hinweis
  await page.getByRole('button', { name: 'Rückgängig' }).first().click(); await page.waitForTimeout(1000);
  check((await lese(sid)).datum === MO, 'Rückgängig nach Verschieben');
  await page.reload(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500);
  // Strg + ziehen Mo -> Mi = kopieren
  await mausZiehen(page, chip(page, sid), tag(page, plus(MO, 2)), true);
  let w = await woche();
  const kopie = w.find((s) => s.datum === plus(MO, 2) && s.employee_id === A.id);
  check(kopie && (await lese(sid)).datum === MO, 'Strg+Ziehen Mo->Mi kopiert (Original bleibt)');
  if (kopie) angelegt.add(kopie.id);
  await page.getByRole('button', { name: 'Ganze Kopie rückgängig' }).click(); await page.waitForTimeout(1000);
  w = await woche();
  check(!w.some((s) => s.datum === plus(MO, 2) && s.employee_id === A.id), 'Ganze Kopie rückgängig entfernt die Kopie');
  await ctx.close();

  // 2) PC Mitarbeiter-Ansicht: auf anderen MA ziehen
  ({ ctx, page } = await seite({ viewport: { width: 1440, height: 1800 } }, 'ma'));
  await mausZiehen(page, chip(page, sid), page.locator(`[data-zelle="${B.id}|${plus(MO, 1)}"]`));
  let s = await lese(sid);
  check(s.employee_id === B.id && s.datum === plus(MO, 1), `Mitarbeiter-Ansicht: Ziehen auf anderen MA + Tag (ist: MA ${s.employee_id}, ${s.datum})`);
  await call('PUT', `/dienstplan/${sid}`, { employee_id: A.id, object_id: OBJ, datum: MO, beginn: '08:00', ende: '10:00', fahrer: true });
  await ctx.close();

  // 3) Tablet (iPad): langes Druecken + ziehen
  console.log('Tablet (Touch)');
  const { defaultBrowserType: _a, ...ipad } = devices['iPad (gen 7)'];
  ({ ctx, page } = await seite(ipad));
  await touchZiehen(page, chip(page, sid), tag(page, plus(MO, 3)));
  check((await lese(sid)).datum === plus(MO, 3), 'iPad: gedrückt halten + ziehen verschiebt Mo->Do');
  // kurzes Wischen: scrollt, verschiebt nicht
  await page.reload(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(500);
  await chip(page, sid).scrollIntoViewIfNeeded();
  const vor = await page.evaluate(() => window.scrollY);
  const bb = await chip(page, sid).boundingBox();
  await touch(page, 'touchStart', bb.x + 30, bb.y + 20);
  for (let i = 1; i <= 8; i++) { await touch(page, 'touchMove', bb.x + 30, bb.y + 20 - i * 25); await page.waitForTimeout(16); }
  await touch(page, 'touchEnd', bb.x + 30, bb.y - 180); await page.waitForTimeout(900);
  const nach = await page.evaluate(() => window.scrollY);
  check((await lese(sid)).datum === plus(MO, 3), 'iPad: kurzes Wischen verschiebt nichts');
  check(nach !== vor, `iPad: kurzes Wischen scrollt die Seite (${vor} -> ${nach})`);
  await ctx.close();

  // 4) Handy: Menue "Verschieben/Kopieren nach ..." -> kopieren auf MA B
  console.log('Handy (Menü)');
  const { defaultBrowserType: _b, ...iphone } = devices['iPhone 15'];
  ({ ctx, page } = await seite(iphone));
  await chip(page, sid).locator('.ck-shift-more').tap(); await page.waitForTimeout(400);
  const dlg = page.getByRole('dialog');
  await dlg.getByRole('radio', { name: 'Kopieren' }).tap();
  await dlg.locator('input[type=date]').fill(plus(MO, 4));
  await dlg.locator('select').selectOption(String(B.id));
  if (OUT) await page.screenshot({ path: path.join(OUT, '11_dienstplan_menue_nach_handy.png') });
  await dlg.locator('.ck-dialog-foot .ck-btn-primary').tap(); await page.waitForTimeout(1300);
  w = await woche();
  const k2 = w.find((x) => x.datum === plus(MO, 4) && x.employee_id === B.id);
  check(!!k2, 'Handy-Menü: Kopieren nach Fr für anderen MA');
  if (k2) angelegt.add(k2.id);
  await ctx.close();

  // 5) Woche kopieren mit Vorschau (Konflikt: B hat in der Zielwoche Fr schon die gleiche Schicht -> "bereits vorhanden" nach Kopie)
  console.log('Woche kopieren');
  await neu(B.id, plus(MO, 7 + 4), '09:00', '11:00');   // Ziel-Fr: B belegt -> Doppelbelegung
  ({ ctx, page } = await seite({ viewport: { width: 1440, height: 900 } }));
  await page.getByRole('button', { name: 'Woche kopieren' }).click(); await page.waitForTimeout(300);
  await page.getByRole('button', { name: 'Vorschau anzeigen' }).click(); await page.waitForTimeout(1200);
  const txt = await page.getByRole('dialog').innerText();
  check(/werden angelegt/.test(txt) && /übersprungen – Doppelbelegung/.test(txt), 'Vorschau zeigt anzulegende und übersprungene (Doppelbelegung)');
  if (OUT) await page.screenshot({ path: path.join(OUT, '11_dienstplan_kopie_vorschau_desktop.png') });
  await page.locator('.ck-dialog-foot .ck-btn-primary').click(); await page.waitForTimeout(1500);
  let w2 = (await call('GET', `/dienstplan?start=${plus(MO, 7)}`)).j.tage.flatMap((d) => d.schichten.map((x) => ({ ...x, datum: d.datum })));
  check(w2.some((x) => x.datum === plus(MO, 10) && x.employee_id === A.id), 'Woche kopiert: Do-Schicht von A in der Folgewoche');
  await page.getByRole('button', { name: 'Ganze Kopie rückgängig' }).click(); await page.waitForTimeout(1200);
  w2 = (await call('GET', `/dienstplan?start=${plus(MO, 7)}`)).j.tage.flatMap((d) => d.schichten.map((x) => ({ ...x, datum: d.datum })));
  check(!w2.some((x) => x.datum === plus(MO, 10) && x.employee_id === A.id), 'Ganze Wochenkopie rückgängig');
  w2.filter((x) => x.employee_id === B.id && x.datum === plus(MO, 11)).forEach((x) => angelegt.add(x.id));
  await ctx.close();
} catch (e) { fail++; console.log('ABBRUCH', e.message.split('\n').slice(0, 6).join('\n')); } finally {
  for (const id of angelegt) await call('DELETE', `/dienstplan/${id}`);
  const rest = (await woche()).filter((s) => angelegt.has(s.id));
  console.log(`Aufgeräumt: ${angelegt.size} Testschichten gelöscht, Rest ${rest.length}`);
  await browser.close();
  console.log(`\n${ok} OK, ${fail} Fehler`);
  process.exit(fail ? 1 : 0);
}
