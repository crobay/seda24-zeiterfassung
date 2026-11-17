// Browser-Test "Plan aus Vorlage" (nur DEV): Mitarbeiter aus der Seitenleiste auf eine Luecke ziehen (Maus + Touch),
// "+ einplanen" (2 Klicks), Woche aus Vorlage mit Vorschau + Rueckgaengig, Plan als fertig melden, Vorlage-Seite ziehen/kopieren,
// Kontingent-Karte, Leitstelle "Plan naechste Woche". Raeumt alle eigenen Testdaten wieder weg.
// Aufruf: CK_TOKEN=$(...dev_token.py admin@seda24.de) node cockpit_vorlage_test.mjs
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const TOKEN = process.env.CK_TOKEN;
if (!TOKEN) throw new Error('CK_TOKEN fehlt');
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1/cockpit`;
const H = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' };
const call = async (m, p, b) => { const r = await fetch(API + p, { method: m, headers: H, body: b ? JSON.stringify(b) : undefined }); return { s: r.status, j: await r.json().catch(() => null) }; };
const iso = (d) => d.toISOString().slice(0, 10);
const plus = (s, n) => { const d = new Date(s + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
let ok = 0, fail = 0;
const check = (c, msg) => { if (c) { ok++; console.log('  OK  ', msg); } else { fail++; console.log('  FEHLER', msg); } };

// Testwoche +12 (Feb. 2027: Festgehalt Ruzica aktiv), eigener Vorlage-Eintrag fuer MA A am Montag 06:00-07:30
const aus = (await call('GET', '/auswahl')).j;
const d0 = new Date(); d0.setUTCDate(d0.getUTCDate() + 84); d0.setUTCDate(d0.getUTCDate() - ((d0.getUTCDay() + 6) % 7));
const MO = iso(d0);
const [A, B] = aus.mitarbeiter.filter((m) => !['D0002', 'D0039', 'D0040', 'D0036', 'D0038'].includes(m.personal_nr)).slice(0, 2);
const OBJ = aus.objekte.find((o) => o.id !== 20).id;
const vlNeu = (await call('POST', '/vorlage', { employee_id: A.id, object_id: OBJ, wochentag: 0, beginn: '06:00', ende: '07:30' })).j;
const VL = vlNeu.id; const vlIds = new Set([VL]);
const schichtenVon = async (eid) => (await call('GET', `/dienstplan?start=${MO}`)).j.tage.flatMap((d) => d.schichten.filter((s) => s.employee_id === eid).map((s) => ({ ...s, datum: d.datum })));
const vorher = new Set((await call('GET', `/dienstplan?start=${MO}`)).j.tage.flatMap((d) => d.schichten.map((s) => s.id)));
console.log(`Testwoche ${MO}, Vorlage ${VL} (${A.name}), einplanen: ${B.name}`);

const browser = await chromium.launch();
async function seite(profil, pfad = `/cockpit/dienstplan?start=${MO}`, ansicht = 'tage') {
  const ctx = await browser.newContext({ ...profil, locale: 'de-DE', timezoneId: 'Europe/Berlin' });
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  if (process.env.DEBUG) { page.on('console', (m) => console.log('    console:', m.text())); await page.addInitScript((n) => { window.__dbg = 1; if (n) window.__noas = 1; }, !!process.env.NOAS); }
  await page.goto(`${BASE}/login`);
  await page.evaluate(([tk, a]) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_theme_v2', 'light'); localStorage.setItem('ck_dp_ansicht', a); localStorage.removeItem('ck_vl_obj'); }, [TOKEN, ansicht]);
  await page.goto(BASE + pfad); await page.waitForLoadState('networkidle'); await page.waitForTimeout(700);
  return { ctx, page };
}
const luecke = (page) => page.locator(`[data-luecke="${VL}|${MO}"]`);
const maItem = (page, id) => page.locator(`[data-ma="${id}"]`);
async function mausZiehen(page, von, nach, strg = false) {
  await nach.scrollIntoViewIfNeeded(); await von.scrollIntoViewIfNeeded(); await page.waitForTimeout(150);
  const a = await von.boundingBox(); const b = await nach.boundingBox();
  if (process.env.DEBUG) console.log('    ziehen', JSON.stringify(a), '->', JSON.stringify(b));
  await page.mouse.move(a.x + 30, a.y + a.height / 2);
  if (strg) await page.keyboard.down('Control');
  await page.mouse.down();
  await page.mouse.move(a.x + 40, a.y + a.height / 2 + 4, { steps: 3 });
  await page.mouse.move(b.x + b.width / 2, b.y + Math.min(20, b.height / 2), { steps: 14 });
  await page.waitForTimeout(150); await page.mouse.up();
  if (strg) await page.keyboard.up('Control');
  await page.waitForTimeout(900);
}
const cdps = new WeakMap();
async function touch(page, typ, x, y) {
  if (!cdps.has(page)) cdps.set(page, await page.context().newCDPSession(page));
  await cdps.get(page).send('Input.dispatchTouchEvent', { type: typ, touchPoints: typ === 'touchEnd' ? [] : [{ x, y }] });
}
async function touchZiehen(page, von, nach, halten = 500) {
  await nach.scrollIntoViewIfNeeded(); await von.scrollIntoViewIfNeeded(); await page.waitForTimeout(200);
  const a = await von.boundingBox(), b = await nach.boundingBox();
  const x0 = a.x + 30, y0 = a.y + a.height / 2, x1 = b.x + b.width / 2, y1 = b.y + Math.min(20, b.height / 2);
  await touch(page, 'touchStart', x0, y0); await page.waitForTimeout(halten);
  for (let i = 1; i <= 14; i++) { await touch(page, 'touchMove', x0 + (x1 - x0) * i / 14, y0 + (y1 - y0) * i / 14); await page.waitForTimeout(25); }
  await touch(page, 'touchEnd', x1, y1); await page.waitForTimeout(1200);
}
const dialogWerte = async (page) => {
  const d = page.getByRole('dialog');
  await d.waitFor({ timeout: 5000 });
  await page.waitForFunction(() => document.querySelectorAll('[role=dialog] select option').length > 4, null, { timeout: 8000 });
  return { ma: await d.locator('select').nth(0).inputValue(), obj: await d.locator('select').nth(1).inputValue(),
    datum: await d.locator('input[type=date]').inputValue(), b: await d.locator('input[type=time]').nth(0).inputValue(), e: await d.locator('input[type=time]').nth(1).inputValue() };
};

try {
  // 1) PC: Woche noch ungeplant -> Hinweis statt einzelner Luecken; Woche aus Vorlage (Vorschau -> anlegen)
  console.log('PC (Maus)');
  let { ctx, page } = await seite({ viewport: { width: 1440, height: 900 } });
  check(await page.locator('.ck-plan-status').getByText('noch nicht aus der Vorlage geplant').count() === 1 && await page.locator('.ck-gap').count() === 0,
    'Ungeplante Woche: ein Hinweis statt vieler Lücken');
  const vorWoche = (await call('GET', `/dienstplan?start=${MO}`)).j.tage.reduce((n, d) => n + d.schichten.length, 0);
  await page.locator('.ck-plan-status').getByRole('button', { name: 'Woche aus Vorlage erstellen' }).click(); await page.waitForTimeout(1500);
  const dlg = page.getByRole('dialog');
  const zeilen = await dlg.locator('.ck-kopie-row').count();
  check(zeilen > 0 && await dlg.getByText('Diese Woche').count() === 1, `Woche aus Vorlage: Vorschau mit ${zeilen} Zeilen`);
  await dlg.getByRole('button', { name: /anlegen/ }).click(); await page.waitForTimeout(1500);
  const nachWoche = (await call('GET', `/dienstplan?start=${MO}`)).j.tage.reduce((n, d) => n + d.schichten.length, 0);
  check(nachWoche - vorWoche === zeilen, `Woche aus Vorlage angelegt (+${nachWoche - vorWoche})`);
  await page.locator('.ck-callout-info').getByRole('button', { name: 'Ganze Kopie rückgängig' }).click(); await page.waitForTimeout(1500);
  check((await call('GET', `/dienstplan?start=${MO}`)).j.tage.reduce((n, d) => n + d.schichten.length, 0) === vorWoche, 'Ganzer Vorgang "Woche aus Vorlage" rückgängig');
  const KID = (await call('POST', '/dienstplan/aus-vorlage', { woche: MO, vorschau: false })).j.kopie_id;   // fuer die weiteren Schritte
  // A faellt am Montag aus -> offene Luecke
  const aMo = (await schichtenVon(A.id)).find((x) => x.datum === MO && x.beginn === '06:00');
  await call('DELETE', `/dienstplan/${aMo.id}`);
  await page.reload(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(800);
  check(await luecke(page).count() === 1, 'Fehlende Vorlage-Schicht erscheint als offene Lücke (gestrichelt, mit Grund)');
  // Mitarbeiter aus der Leiste auf die Luecke ziehen -> Dialog vorbelegt -> Speichern
  await mausZiehen(page, maItem(page, B.id), luecke(page));
  let w = await dialogWerte(page);
  check(w.ma === String(B.id) && w.obj === String(OBJ) && w.datum === MO && w.b === '06:00' && w.e === '07:30', 'Ziehen auf Lücke: Mitarbeiter, Objekt, Tag und Zeit vorbelegt');
  await page.getByRole('dialog').getByRole('button', { name: 'Speichern' }).click(); await page.waitForTimeout(1200);
  check((await schichtenVon(B.id)).some((x) => x.datum === MO && x.beginn === '06:00'), 'Nach "Speichern" eingeplant (Ziehen + 1 Klick)');
  check(await luecke(page).count() === 0, 'Lücke ist danach geschlossen');
  // "+ einplanen" = 1 Klick, danach Speichern
  await maItem(page, B.id).getByRole('button').click();
  w = await dialogWerte(page);
  check(w.ma === String(B.id) && w.datum >= MO && w.datum <= plus(MO, 6), '"+ einplanen" öffnet vorbelegten Dialog (2. Klick = Speichern)');
  await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
  // Plan als fertig melden / wieder oeffnen
  await page.locator('.ck-plan-status').getByRole('button', { name: 'Als fertig melden' }).click(); await page.waitForTimeout(900);
  check((await call('GET', `/dienstplan?start=${MO}`)).j.plan.fertig === true, 'Woche als fertig gemeldet');
  await page.locator('.ck-plan-status').getByRole('button', { name: 'Wieder öffnen' }).click(); await page.waitForTimeout(900);
  check((await call('GET', `/dienstplan?start=${MO}`)).j.plan.fertig === false, 'Woche wieder geöffnet');
  // Kontingent (Festgehalt Ruzica) + Rest verteilen (nur Vorschau)
  check(await page.locator('.ck-konto').count() >= 1, 'Kontingent-Karte (Soll/verplant/Rest) sichtbar');
  await page.locator('.ck-konto').getByRole('button', { name: 'Rest verteilen' }).click(); await page.waitForTimeout(1200);
  check(await page.getByRole('dialog').locator('.ck-kopie-row').count() > 0, 'Rest verteilen zeigt Vorschau je Werktag');
  await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
  // Rueckgaengig nimmt nur die Vorlage-Schichten weg, die von Hand eingeplante Schicht bleibt
  await call('DELETE', `/dienstplan/kopie/${KID}`);
  check((await call('GET', `/dienstplan?start=${MO}`)).j.tage.reduce((n, d) => n + d.schichten.length, 0) === vorWoche + 1, 'Rückgängig: nur Vorlage-Schichten weg, von Hand eingeplante bleibt');
  await ctx.close();

  // 2) iPad quer: Mitarbeiter per Touch (langes Druecken) auf einen Tag ziehen
  console.log('iPad (Touch)');
  ({ ctx, page } = await seite({ ...devices['iPad Pro 11 landscape'] }));
  await touchZiehen(page, maItem(page, A.id), page.locator(`[data-tag="${plus(MO, 2)}"]`));
  w = await dialogWerte(page).catch(() => ({}));
  check(w.ma === String(A.id) && w.datum === plus(MO, 2), `Touch: gedrückt halten + ziehen auf Mittwoch öffnet vorbelegten Dialog`);
  if (await page.getByRole('dialog').count()) await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
  await ctx.close();

  // 3) Handy: Leiste aufklappen, "+ einplanen", Speichern
  console.log('Handy');
  ({ ctx, page } = await seite({ ...devices['iPhone 13'] }));
  await maItem(page, A.id).getByRole('button').click();
  w = await dialogWerte(page);
  check(w.ma === String(A.id), `Handy: "+ einplanen" öffnet vorbelegten Dialog`);
  await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
  await ctx.close();

  // 4) Vorlage-Seite: Eintrag ziehen (Mo -> Di), Strg = kopieren (-> Mi)
  console.log('Vorlage-Seite');
  ({ ctx, page } = await seite({ viewport: { width: 1440, height: 900 } }, '/cockpit/vorlage'));
  await mausZiehen(page, page.locator(`[data-vorlage="${VL}"]`), page.locator(`[data-vzelle="${A.id}|1"]`));
  let v = (await call('GET', '/vorlage')).j.eintraege.find((e) => e.id === VL);
  check(v.wochentag === 1, 'Vorlage: Ziehen Mo -> Di verschiebt');
  await page.waitForTimeout(500);
  await mausZiehen(page, page.locator(`[data-vorlage="${VL}"]`), page.locator(`[data-vzelle="${A.id}|2"]`), true);
  const kop = (await call('GET', '/vorlage')).j.eintraege.filter((e) => e.employee_id === A.id && e.object_id === OBJ && e.beginn === '06:00');
  kop.forEach((e) => vlIds.add(e.id));
  check(kop.length === 2 && kop.some((e) => e.wochentag === 2), 'Vorlage: Strg + Ziehen kopiert auf Mittwoch');
  await ctx.close();

  // 5) Leitstelle: Karte "Plan naechste Woche"
  ({ ctx, page } = await seite({ viewport: { width: 1440, height: 900 } }, '/cockpit'));
  check(await page.locator('#plan-naechste-woche').getByText('Plan nächste Woche').count() === 1, 'Leitstelle: Karte "Plan nächste Woche" mit Status');
  await ctx.close();
} catch (e) {
  fail++; console.log('  FEHLER Ausnahme:', e.message.split('\n')[0]);
} finally {
  await browser.close();
  // Aufraeumen: neue Schichten der Testwoche, Test-Vorlage, Fertig-Markierung
  const jetzt = (await call('GET', `/dienstplan?start=${MO}`)).j.tage.flatMap((d) => d.schichten.map((s) => s.id));
  for (const id of jetzt) if (!vorher.has(id)) await call('DELETE', `/dienstplan/${id}`);
  for (const id of vlIds) await call('DELETE', `/vorlage/${id}`);
  await call('POST', '/dienstplan/fertig', { woche: MO, fertig: false });
  const rest = (await call('GET', `/dienstplan?start=${MO}`)).j.tage.flatMap((d) => d.schichten.map((s) => s.id)).filter((id) => !vorher.has(id));
  check(rest.length === 0 && !(await call('GET', '/vorlage')).j.eintraege.some((e) => vlIds.has(e.id)), 'Aufgeräumt');
  console.log(`=== ${ok} OK, ${fail} Fehler ===`);
}
