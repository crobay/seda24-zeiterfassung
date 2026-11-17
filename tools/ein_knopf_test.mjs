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

  // ---------- Pause online ----------
  console.log('Pause online');
  ({ ctx, page } = await neueSeite(plus(S, -5)));
  await knopf(page, 'KOMMEN').click();
  await page.clock.runFor(3500);
  await knopf(page, 'GEHEN').waitFor();
  const pauseKnopf = page.getByRole('button', { name: 'Pause', exact: true });
  ok('eingestempelt: kleiner Knopf "Pause" unter GEHEN', await pauseKnopf.isVisible()
     && (await pauseKnopf.boundingBox()).y > (await knopf(page, 'GEHEN').boundingBox()).y
     && (await pauseKnopf.boundingBox()).height < 80);
  await springe(page, plus(S, 60));
  await pauseKnopf.click();
  const beenden = knopf(page, 'PAUSE BEENDEN');
  ok('Pause: gross nur "PAUSE BEENDEN"', await beenden.waitFor({ timeout: 6000 }).then(() => true, () => false)
     && !(await knopf(page, 'GEHEN').isVisible()) && !(await knopf(page, 'KOMMEN').isVisible()));
  ok('Pause: "Gehen" klein darunter', await page.getByRole('button', { name: 'Gehen', exact: true }).isVisible());
  await springe(page, plus(S, 72));
  await page.clock.runFor(1500);  // Sekundentakt der Anzeige nach dem Zeitsprung einmal laufen lassen
  const pauseTxt = (await page.locator('[data-ek-pause]').innerText().catch(() => '')).replace(/\s+/g, ' ');
  ok(`Pause: Anzeige "Pause seit ${hm(plus(S, 60))} · 12 Min"`, pauseTxt.includes(`Pause seit ${hm(plus(S, 60))} · 12 Min`), pauseTxt);
  await shot(page, 'pause_laeuft');
  await beenden.click();
  ok('Pause beendet: wieder Zähler + GEHEN', await knopf(page, 'GEHEN').waitFor({ timeout: 6000 }).then(() => true, () => false));
  const br = sql(`SELECT to_char(b.start_time,'HH24:MI'), to_char(b.end_time,'HH24:MI') FROM break_entries b JOIN time_entries t ON t.id = b.time_entry_id WHERE t.employee_id = ${EMP} AND t.id > ${MAX_TE} ORDER BY b.id`);
  ok('Pause in der DB (Server-Bestätigung)', br === `${hm(plus(S, 60))}|${hm(plus(S, 72))}`, br);
  // Gehen waehrend der Pause schliesst die Pause
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await beenden.waitFor();
  await springe(page, E);
  await page.getByRole('button', { name: 'Gehen', exact: true }).click();
  ok('Gehen während Pause: "Schicht erledigt"', await page.locator('[data-ek-zustand="erledigt"]').waitFor({ timeout: 8000 }).then(() => true, () => false));
  const br2 = sql(`SELECT count(*) FILTER (WHERE b.end_time IS NULL), count(*) FROM break_entries b JOIN time_entries t ON t.id = b.time_entry_id WHERE t.employee_id = ${EMP} AND t.id > ${MAX_TE}`);
  ok('Gehen schliesst die Pause (keine offene Pause)', br2 === '0|2', br2);
  await ctx.close();
  leeren();

  // ---------- Pause im Gast-WLAN ----------
  console.log('Pause im Gast-WLAN');
  ({ ctx, page } = await neueSeite(plus(S, -5)));
  await knopf(page, 'KOMMEN').click();
  await page.clock.runFor(3500);
  await knopf(page, 'GEHEN').waitFor();
  await page.route('**/api/v1/**', PORTAL);
  await springe(page, plus(S, 60));
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  ok('Gast-WLAN: Pause sofort, gross "PAUSE BEENDEN"', await knopf(page, 'PAUSE BEENDEN').waitFor({ timeout: 8000 }).then(() => true, () => false));
  ok(`Gast-WLAN: ⏳ "Pause ${hm(plus(S, 60))} gespeichert – wird übertragen"`,
     await page.locator('[data-stempel-status="wartet"]').filter({ hasText: `Pause ${hm(plus(S, 60))} gespeichert – wird übertragen` }).isVisible());
  await shot(page, 'pause_gastwlan');
  await page.reload();
  await page.locator('[data-ek-zustand]').first().waitFor();
  await page.waitForTimeout(1500);
  ok('Gast-WLAN: nach Neu laden weiter Pause', await knopf(page, 'PAUSE BEENDEN').isVisible());
  ok('Gast-WLAN: Pause noch nicht in der DB', sql(`SELECT count(*) FROM break_entries b JOIN time_entries t ON t.id = b.time_entry_id WHERE t.employee_id = ${EMP} AND t.id > ${MAX_TE}`) === '0');
  await page.unroute('**/api/v1/**');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  let br3 = '0';
  for (let i = 0; i < 15 && br3 === '0'; i++) { await new Promise((r) => setTimeout(r, 1000)); br3 = sql(`SELECT count(*) FROM break_entries b JOIN time_entries t ON t.id = b.time_entry_id WHERE t.employee_id = ${EMP} AND t.id > ${MAX_TE}`); }
  ok('mit Netz: Pause übertragen (Zeit des Tippens)', br3 === '1'
     && sql(`SELECT to_char(b.start_time,'HH24:MI') FROM break_entries b JOIN time_entries t ON t.id = b.time_entry_id WHERE t.employee_id = ${EMP} AND t.id > ${MAX_TE}`) === hm(plus(S, 60)));
  ok('mit Netz: weiter Pause (Server-Stand)', await knopf(page, 'PAUSE BEENDEN').isVisible());
  await knopf(page, 'PAUSE BEENDEN').click();
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'GEHEN', exact: true }).click();
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
