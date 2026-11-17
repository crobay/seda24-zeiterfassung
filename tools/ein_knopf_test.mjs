// NUR DEV: Ein-Knopf-Ablauf der Stempeluhr (iPhone 15, T9999, Objekt TEST BrowserStack) mit gestellter Uhr im Browser.
// Schicht S..S+3h heute (S = jetzt, auf 5 Min gerundet) und morgen. Zustaende: 1) vor Beginn-10 grau "Kommen ab",
// 2) ab Beginn-10 nur KOMMEN, 3) Bestaetigung, dann Zaehler + nur GEHEN, 4) "Schicht erledigt S–E · 3:00 Std."
// ohne Knopf; dasselbe im Gast-WLAN (⏳); zweite Schicht am Tag; Schicht vorbei ohne Kommen; offener Eintrag von
// gestern; ohne Dienstplan. In jedem Schritt: nie KOMMEN und GEHEN gleichzeitig. Testdaten werden am Ende geloescht.
// Aufruf: CK_TOKEN=... CK_EMAIL=... node ein_knopf_test.mjs <ordner>
import path from 'path';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const { CK_TOKEN: TOKEN, CK_EMAIL: EMAIL } = process.env;
const BASE = 'https://dev.seda.de';
const OBJ = 25;

const sql = (q) => execFileSync('psql', ['-h', 'localhost', '-U', 'seda24_user', 'dev_cockpit', '-X', '-tA', '-F', '|', '-c', q],
  { env: { ...process.env, PGPASSWORD: 'SedaDev2025' } }).toString().trim();
const EMP = sql("SELECT id FROM employees WHERE personal_nr = 'T9999'");
const MAX_TE = sql('SELECT coalesce(max(id),0) FROM time_entries');
const MAX_S = sql('SELECT coalesce(max(id),0) FROM schedules');
if (sql(`SELECT count(*) FROM time_entries WHERE employee_id = ${EMP} AND (check_out IS NULL OR check_in >= current_date - 1)`) !== '0') { console.log('T9999 hat offene oder heutige Eintraege - Abbruch'); process.exit(1); }
if (sql(`SELECT count(*) FROM schedules WHERE employee_id = ${EMP} AND date BETWEEN current_date - 1 AND current_date + 1`) !== '0') { console.log('T9999 hat schon Schichten - Abbruch'); process.exit(1); }

let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const p2 = (n) => String(n).padStart(2, '0');
const hm = (d) => `${p2(d.getHours())}:${p2(d.getMinutes())}`;
const plus = (d, min) => new Date(d.getTime() + min * 60000);
const S = new Date(); S.setSeconds(0, 0); S.setMinutes(Math.floor(S.getMinutes() / 5) * 5);
const E = plus(S, 180);
if (E.getDate() !== S.getDate() || S.getHours() < 6) { console.log('Test braucht eine Schicht S..S+3h am selben Tag (06-21 Uhr)'); process.exit(1); }
const tag = (off) => sql(`SELECT (current_date + ${off})::text`);
const schicht = (datum, von, bis) => sql(`INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status)
  VALUES (${EMP}, ${OBJ}, '${datum}', extract(dow from date '${datum}')::int, '${von}', '${bis}', 3, 'normal') RETURNING id`);
const leeren = () => {
  const te = sql(`SELECT string_agg(id::text, ',') FROM time_entries WHERE employee_id = ${EMP} AND id > ${MAX_TE}`);
  if (te) sql(`DELETE FROM break_entries WHERE time_entry_id IN (${te}); UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN (${te});
               DELETE FROM km_daily_entries WHERE employee_id = ${EMP} AND time_entry_id IS NULL AND date >= current_date - 1;
               UPDATE pending_bookings SET related_time_entry_id = NULL WHERE related_time_entry_id IN (${te});
               DELETE FROM pending_bookings WHERE employee_id = ${EMP} AND id > 0 AND created_at > now() - interval '1 hour';
               DELETE FROM time_entries WHERE id IN (${te})`);
  const rest = sql(`SELECT count(*) FROM time_entries WHERE employee_id = ${EMP} AND id > ${MAX_TE}`);
  if (rest !== '0') { console.log(`  Aufraeumen unvollstaendig: ${rest} Eintraege`); fehler++; }
};
const schichtenWeg = () => sql(`UPDATE time_entries SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE employee_id = ${EMP} AND id > ${MAX_S});
  DELETE FROM push_notifications WHERE schedule_id IN (SELECT id FROM schedules WHERE employee_id = ${EMP} AND id > ${MAX_S});
  DELETE FROM schedules WHERE employee_id = ${EMP} AND id > ${MAX_S}`);

const { defaultBrowserType: _d, ...iphone } = devices['iPhone 15'];
const browser = await chromium.launch();
const PORTAL = (r) => r.fulfill({ status: 200, contentType: 'text/html', body: '<html><body>Lidl WLAN Anmeldung</body></html>' });

async function neueSeite(uhr) {
  const ctx = await browser.newContext({ ...iphone, locale: 'de-DE', timezoneId: 'Europe/Berlin', serviceWorkers: 'block' });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on('pageerror', (e) => ok('kein JS-Fehler', false, e.message));
  await page.clock.install({ time: uhr });
  await page.goto(BASE + '/login');
  await page.evaluate(([tk, em]) => {
    localStorage.clear();
    localStorage.setItem('token', tk); localStorage.setItem('userEmail', em); localStorage.setItem('userRole', 'mitarbeiter');
  }, [TOKEN, EMAIL]);
  await page.goto(BASE + '/dashboard');
  await page.locator('[data-ek-zustand]').first().waitFor();
  await page.waitForTimeout(800);
  return { ctx, page };
}
const knopf = (page, name) => page.getByRole('button', { name, exact: true });
async function nieBeide(page, wo) {
  const k = await knopf(page, 'KOMMEN').isVisible(), g = await knopf(page, 'GEHEN').isVisible();
  ok(`${wo}: nie KOMMEN und GEHEN gleichzeitig`, !(k && g), `KOMMEN ${k ? 'sichtbar' : '-'}, GEHEN ${g ? 'sichtbar' : '-'}`);
}
const shot = async (page, n) => {
  await page.locator('[data-ek-zustand]').first().evaluate((el) => el.scrollIntoView({ block: 'start' })).catch(() => {});
  await page.evaluate(() => window.scrollBy(0, -170));
  await page.screenshot({ path: path.join(OUT, `16_${n}.png`) });
};
const springe = async (page, d) => { await page.clock.setSystemTime(d); await page.waitForTimeout(1300); };

console.log(`Ein-Knopf-Test DEV (T9999, iPhone 15), Schicht ${hm(S)}–${hm(E)}`);
try {
  schicht(tag(0), hm(S), hm(E));
  schicht(tag(1), hm(S), hm(E));

  // ---------- 1-4 online ----------
  console.log('Zustand 1-4 online');
  let { ctx, page } = await neueSeite(plus(S, -20));
  const zust = async () => page.locator('[data-ek-zustand]').first().getAttribute('data-ek-zustand');
  ok('1) vor Beginn-10: Zustand "warten"', (await zust()) === 'warten');
  const grau = page.getByRole('button', { name: `Kommen ab ${hm(plus(S, -10))}` });
  ok(`1) grauer Knopf "Kommen ab ${hm(plus(S, -10))}", gesperrt`, await grau.isVisible() && await grau.isDisabled());
  ok('1) kein KOMMEN, kein GEHEN', !(await knopf(page, 'KOMMEN').isVisible()) && !(await knopf(page, 'GEHEN').isVisible()));
  ok('1) oben Objekt + Schichtzeit', await page.getByText(`Schicht ${hm(S)}–${hm(E)}`).first().isVisible());
  await shot(page, 'zustand1_kommen_ab');

  await springe(page, plus(S, -5));
  ok('2) ab Beginn-10: nur KOMMEN', (await zust()) === 'kommen' && await knopf(page, 'KOMMEN').isVisible());
  await nieBeide(page, '2)');
  const box = await knopf(page, 'KOMMEN').boundingBox();
  ok('2) KOMMEN-Knopf riesig (≥ 40 % Bildschirmhöhe)', box && box.height >= 0.4 * iphone.viewport.height, `${box && Math.round(box.height)} px von ${iphone.viewport.height}`);
  await shot(page, 'zustand2_kommen');

  await knopf(page, 'KOMMEN').click();
  const q = page.locator('[data-ek-quittung="ok"]');
  ok('3) Bestätigung "✓ Angekommen" mit Haken', await q.waitFor({ timeout: 6000 }).then(() => true, () => false));
  ok('3) während der Bestätigung kein GEHEN (kein Vertippen)', !(await knopf(page, 'GEHEN').isVisible()));
  await shot(page, 'zustand3a_bestaetigung');
  await page.clock.runFor(3500);
  await knopf(page, 'GEHEN').waitFor();
  ok('3) danach Zähler + nur GEHEN', await page.getByText('Arbeitszeit läuft').isVisible() && !(await knopf(page, 'KOMMEN').isVisible()));
  await nieBeide(page, '3)');
  await shot(page, 'zustand3_gehen');

  await springe(page, E);
  await knopf(page, 'GEHEN').click();
  const fertig = page.locator('[data-ek-zustand="erledigt"] [data-stempel-status="ok"]');
  ok('4) "Schicht erledigt"', await fertig.waitFor({ timeout: 8000 }).then(() => true, () => false));
  const txt = (await fertig.innerText().catch(() => '')).replace(/\s+/g, ' ');
  ok(`4) "${hm(S)}–${hm(E)} · 3:00 Std." + "Schönen Feierabend!"`, txt.includes(`${hm(S)}–${hm(E)} · 3:00 Std.`) && txt.includes('Schönen Feierabend!'), txt.slice(0, 120));
  await page.clock.runFor(3500);
  ok('4) kein Knopf mehr', !(await knopf(page, 'KOMMEN').isVisible()) && !(await knopf(page, 'GEHEN').isVisible()));
  ok('4) nächste Schicht klein darunter', await page.locator('[data-ek-naechste]').filter({ hasText: `morgen, ${hm(S)}–${hm(E)}` }).isVisible());
  const db = sql(`SELECT to_char(check_in,'HH24:MI'), to_char(check_out,'HH24:MI'), billed_hours FROM time_entries WHERE employee_id = ${EMP} AND id > ${MAX_TE} ORDER BY id DESC LIMIT 1`);
  ok('4) DB: Kommen/Gehen wie getippt, 3,0 Std.', db === `${hm(plus(S, -5))}|${hm(E)}|3`, db);
  await shot(page, 'zustand4_erledigt');
  await ctx.close();
  leeren();

  // ---------- dieselbe Schicht im Gast-WLAN ----------
  console.log('Gast-WLAN (Anmeldeseite)');
  ({ ctx, page } = await neueSeite(plus(S, -5)));
  await page.route('**/api/v1/**', PORTAL);
  await knopf(page, 'KOMMEN').click();
  ok('3) Bestätigung "⏳ Gespeichert"', await page.locator('[data-ek-quittung="wartet"]').waitFor({ timeout: 8000 }).then(() => true, () => false));
  await shot(page, 'zustand3a_gespeichert');
  await page.clock.runFor(3500);
  await knopf(page, 'GEHEN').waitFor();
  await nieBeide(page, '3) Gast-WLAN');
  await springe(page, E);
  await knopf(page, 'GEHEN').click();
  const wartet = page.locator('[data-ek-zustand="erledigt"] [data-stempel-status="wartet"]');
  ok('4) "Gezählt – wird übertragen" (gestrichelt)', await wartet.waitFor({ timeout: 8000 }).then(() => true, () => false));
  const wt = (await wartet.innerText().catch(() => '')).replace(/\s+/g, ' ');
  ok(`4) ⏳ mit ${hm(S)}–${hm(E)} · 3:00 Std. und "Gehen ${hm(E)} gespeichert"`, wt.includes(`${hm(S)}–${hm(E)} · 3:00 Std.`) && wt.includes(`Gehen ${hm(E)} gespeichert`), wt.slice(0, 140));
  ok('4) Gast-WLAN: kein Knopf', !(await knopf(page, 'KOMMEN').isVisible()) && !(await knopf(page, 'GEHEN').isVisible()));
  await shot(page, 'zustand4_wird_uebertragen');
  const vorSync = sql(`SELECT coalesce(max(id),0) FROM time_entries`);
  await page.unroute('**/api/v1/**');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  // Nach dem Zeitsprung wartet Playwright im Browser an der gestellten Uhr: hier Node-seitig abfragen
  const fertig2 = page.locator('[data-ek-zustand="erledigt"] [data-stempel-status="ok"]');
  let da = false;
  for (let i = 0; i < 15 && !da; i++) { await new Promise((r) => setTimeout(r, 1000)); da = await fertig2.isVisible(); }
  if (!ok('4) später mit Netz: "Schicht erledigt" (✓)', da)) {
    console.log('    Anzeige:', (await page.locator('[data-ek-zustand]').first().innerText()).replace(/\s+/g, ' ').slice(0, 300));
    console.log('    Speicher:', await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('bie2_heute') || k === 'bie2_offline_queue').map((k) => k + '=' + localStorage.getItem(k)).join(' ; ')));
    await page.screenshot({ path: path.join(OUT, 'fehler_portal_spaeter.png') });
  }
  const db2 = sql(`SELECT to_char(check_in,'HH24:MI'), to_char(check_out,'HH24:MI') FROM time_entries WHERE employee_id = ${EMP} AND id > ${vorSync} ORDER BY id DESC LIMIT 1`);
  ok('Gast-WLAN: DB mit getippten Zeiten', db2 === `${hm(plus(S, -5))}|${hm(E)}`, db2);
  await ctx.close();
  leeren();

  // ---------- zweite Schicht am Tag ----------
  console.log('Zweite Schicht am Tag');
  const A1 = plus(S, -300), A2 = plus(S, -180);
  if (A1.getDate() === S.getDate()) {
    schicht(tag(0), hm(A1), hm(A2));
    sql(`INSERT INTO time_entries (employee_id, object_id, check_in, check_out, billed_hours, created_at)
         VALUES (${EMP}, ${OBJ}, current_date + time '${hm(A1)}', current_date + time '${hm(A2)}', 2, now())`);
    ({ ctx, page } = await neueSeite(plus(S, -20)));
    ok('erste Schicht erledigt, nächste heute klein darunter', (await zust()) === 'erledigt'
       && await page.locator('[data-ek-naechste]').filter({ hasText: `heute, ${hm(S)}–${hm(E)}` }).isVisible());
    ok('dazwischen kein Knopf', !(await knopf(page, 'KOMMEN').isVisible()) && !(await knopf(page, 'GEHEN').isVisible()));
    await shot(page, 'zweite_schicht_dazwischen');
    await springe(page, plus(S, -5));
    ok('ab Beginn-10 der zweiten Schicht: nur KOMMEN', (await zust()) === 'kommen' && await knopf(page, 'KOMMEN').isVisible());
    await nieBeide(page, 'zweite Schicht');
    await ctx.close();
    leeren();

    // ---------- Schicht vorbei ohne Kommen ----------
    console.log('Schicht vorbei ohne Kommen');
    ({ ctx, page } = await neueSeite(plus(S, -20)));
    ok('"Nicht gestempelt" + ein Knopf "Zeit nachtragen", kein KOMMEN', (await zust()) === 'verpasst'
       && await page.getByRole('button', { name: 'Zeit nachtragen', exact: true }).isVisible() && !(await knopf(page, 'KOMMEN').isVisible()));
    await shot(page, 'schicht_verpasst');
    await ctx.close();
  } else {
    console.log('  (übersprungen: zu früh am Tag für eine Schicht 5 Std. vorher)');
  }
  schichtenWeg();

  // ---------- offener Eintrag von gestern ----------
  console.log('Offener Eintrag von gestern');
  sql(`INSERT INTO time_entries (employee_id, object_id, check_in, created_at) VALUES (${EMP}, ${OBJ}, current_date - 1 + time '12:55', now())`);
  ({ ctx, page } = await neueSeite(new Date()));
  ok('"Gehen fehlt noch" + ein Knopf "Gehen-Zeit eintragen"', (await zust()) === 'offen_gestern'
     && await page.getByRole('button', { name: 'Gehen-Zeit eintragen', exact: true }).isVisible());
  ok('kein KOMMEN, kein GEHEN', !(await knopf(page, 'KOMMEN').isVisible()) && !(await knopf(page, 'GEHEN').isVisible()));
  await shot(page, 'offen_von_gestern');
  await ctx.close();
  leeren();

  // ---------- ohne Dienstplan ----------
  console.log('Ohne Dienstplan');
  ({ ctx, page } = await neueSeite(new Date()));
  ok('ohne Plan: KOMMEN', (await zust()) === 'ohne_plan' && await knopf(page, 'KOMMEN').isVisible());
  await nieBeide(page, 'ohne Plan vor Kommen');
  await knopf(page, 'KOMMEN').click();
  await page.clock.runFor(3500);
  await knopf(page, 'GEHEN').waitFor();
  await nieBeide(page, 'ohne Plan eingestempelt');
  await knopf(page, 'GEHEN').click();
  ok('ohne Plan: "Erledigt"-Karte', await page.locator('[data-ek-zustand="ohne_plan"] [data-stempel-status="ok"]').waitFor({ timeout: 8000 }).then(() => true, () => false));
  ok('ohne Plan: 3 s kein Knopf nach Gehen (Doppeltipp)', !(await knopf(page, 'KOMMEN').isVisible()));
  await page.clock.runFor(3500);
  ok('ohne Plan: danach wieder KOMMEN', await knopf(page, 'KOMMEN').isVisible());
  await nieBeide(page, 'ohne Plan nach Gehen');
  await shot(page, 'ohne_plan_erledigt');
  await ctx.close();
} finally {
  leeren();
  schichtenWeg();
  await browser.close();
}
console.log(fehler ? `=== ${fehler} Fehler ===` : '=== alles OK ===');
process.exit(fehler ? 1 : 0);
