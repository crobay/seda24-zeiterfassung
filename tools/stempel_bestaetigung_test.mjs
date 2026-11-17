// NUR DEV: Server-Bestaetigung der Stempeluhr mit simuliertem Captive Portal (iPhone 15, T9999, TEST BrowserStack).
// Je Fall wird die Stempel-Anfrage abgefangen (HTML-200, 302 auf Anmeldeseite, 511, 403, fremdes 400, Timeout):
// erwartet ⏳ innerhalb ~5 s, Warteschlange 1, nichts in der DB; danach Netz frei -> automatisch gesendet, ✓,
// DB-Zeit = Zeit des Tippens. Dazu: echte Fehlermeldung unseres Servers (nicht in die Warteschlange) und
// Neu laden waehrend ⏳ (Server meldet noch "eingestempelt", App zeigt trotzdem das gespeicherte Gehen).
// Am Ende werden die Testeintraege von T9999 in dev_cockpit geloescht.
// Aufruf: CK_TOKEN=$(./venv/bin/python ../tools/dev_token.py <mail>) CK_EMAIL=<mail> node stempel_bestaetigung_test.mjs <ordner>
import path from 'path';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const { CK_TOKEN: TOKEN, CK_EMAIL: EMAIL } = process.env;
const BASE = 'https://dev.seda.de';

const sql = (q) => execFileSync('psql', ['-h', 'localhost', '-U', 'seda24_user', 'dev_cockpit', '-X', '-tA', '-F', '|', '-c', q],
  { env: { ...process.env, PGPASSWORD: 'SedaDev2025' } }).toString().trim();
const EMP = sql("SELECT id FROM employees WHERE personal_nr = 'T9999'");
const eintraege = () => sql(`SELECT id, to_char(check_in,'HH24:MI:SS'), coalesce(to_char(check_out,'HH24:MI:SS'),'') FROM time_entries
                             WHERE employee_id = ${EMP} AND check_in::date = current_date ORDER BY id`).split('\n').filter(Boolean);
const START_IDS = sql(`SELECT coalesce(max(id),0) FROM time_entries`);

let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const hhmmss = (d) => d.toLocaleTimeString('de-DE', { timeZone: 'Europe/Berlin', hour12: false });

if (sql(`SELECT count(*) FROM time_entries WHERE employee_id = ${EMP} AND check_out IS NULL`) !== '0') { console.log('T9999 ist eingestempelt - Abbruch'); process.exit(1); }

const PORTAL_HTML = '<!doctype html><html><body><h1>Lidl WLAN</h1><form>Passwort <input name=pw></form></body></html>';
const FAELLE = [
  ['HTML-200 (Anmeldeseite statt JSON)', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: PORTAL_HTML })],
  ['302 auf Anmeldeseite', (r) => r.fulfill({ status: 302, headers: { location: BASE + '/portal-login.html' } })],
  ['511 Network Authentication Required', (r) => r.fulfill({ status: 511, contentType: 'text/html', body: PORTAL_HTML })],
  ['403 vom Portal', (r) => r.fulfill({ status: 403, contentType: 'text/html', body: PORTAL_HTML })],
  ['fremdes 400 mit JSON ohne Server-Kennung', (r) => r.fulfill({ status: 400, contentType: 'application/json', body: '{"detail":"portal"}' })],
  ['Timeout (keine Antwort)', () => new Promise(() => {})],
];

const { defaultBrowserType: _d, ...iphone } = devices['iPhone 15'];
const browser = await chromium.launch();
const ctx = await browser.newContext({ ...iphone, locale: 'de-DE', timezoneId: 'Europe/Berlin', serviceWorkers: 'block' });
const page = await ctx.newPage();
page.setDefaultTimeout(20000);
page.on('pageerror', (e) => ok('kein JS-Fehler', false, e.message));
await page.route('**/portal-login.html', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: PORTAL_HTML }));

const queue = () => page.evaluate(() => JSON.parse(localStorage.getItem('bie2_offline_queue') || '[]').filter((i) => i.status !== 'synced'));
const status = () => page.locator('[data-stempel-status]').first().getAttribute('data-stempel-status').catch(() => null);
const shot = (n) => page.screenshot({ path: path.join(OUT, `15_${n}.png`), fullPage: false });
const zumStatus = () => page.locator('[data-stempel-status]').first().evaluate((el) => el.scrollIntoView({ block: 'center' })).catch(() => {});

try {
  await page.goto(BASE + '/login');
  await page.evaluate(([tk, em]) => {
    localStorage.clear();
    localStorage.setItem('token', tk); localStorage.setItem('userEmail', em); localStorage.setItem('userRole', 'mitarbeiter');
  }, [TOKEN, EMAIL]);
  await page.goto(BASE + '/dashboard');
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).waitFor();
  const opt = page.locator('select').filter({ hasText: 'TEST BrowserStack' }).first();
  if (await opt.count()) await opt.selectOption({ label: 'TEST BrowserStack' });
  console.log(`Server-Bestaetigung DEV ${hhmmss(new Date())} (T9999, iPhone 15)`);

  let n = 0;
  for (const [name, simulation] of FAELLE) {
    n++;
    const knopf = n % 2 ? 'KOMMEN' : 'GEHEN';
    const api = n % 2 ? '**/api/v1/time-entries/check-in' : '**/api/v1/time-entries/check-out';
    console.log(`Fall ${n}: ${knopf} bei ${name}`);
    const vorher = eintraege();
    await page.route(api, simulation);
    const t0 = Date.now();
    await page.getByRole('button', { name: knopf, exact: true }).click();
    await page.locator('[data-stempel-status="wartet"]').waitFor({ timeout: 9000 }).catch(() => {});
    const dauer = (Date.now() - t0) / 1000;
    const q = await queue();
    ok('⏳ angezeigt', (await status()) === 'wartet', `nach ${dauer.toFixed(1)} s`);
    ok('höchstens ~5 s bis ⏳', dauer <= 6.5);
    ok('Hinweistext sichtbar', await page.getByText('Kein Problem – dein Stempel ist sicher gespeichert.').isVisible());
    ok('Stempel in der Warteschlange', q.length === 1, q.map((i) => `${i.action} ${i.status}`).join(', '));
    ok('nicht als erledigt verworfen, nichts Neues in der DB', JSON.stringify(eintraege()) === JSON.stringify(vorher));
    const getippt = q[0] ? new Date(q[0].timestamp) : null;
    if (n === 1) { await zumStatus(); await shot('iphone_wartet_kommen'); }
    if (knopf === 'GEHEN' && n === 2) {
      // Neu laden waehrend ⏳: Server meldet noch "eingestempelt", App bleibt beim gespeicherten Gehen
      await page.reload();
      await page.locator('[data-stempel-status="wartet"]').waitFor();
      ok('nach Neu laden: weiter ⏳, nicht "eingestempelt"', await page.getByRole('button', { name: 'KOMMEN', exact: true }).isVisible());
      await zumStatus(); await shot('iphone_wartet_gehen_nach_neuladen');
    }
    // Netz wieder da: Abfangen weg, App meldet "online" -> automatisch gesendet
    await page.unroute(api);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.locator('[data-stempel-status="ok"]').waitFor({ timeout: 15000 }).catch(() => {});
    ok('danach automatisch gesendet: ✓', (await status()) === 'ok');
    ok('Warteschlange leer', (await queue()).length === 0);
    const nachher = eintraege();
    const letzte = nachher[nachher.length - 1] || '';
    const dbZeit = knopf === 'KOMMEN' ? letzte.split('|')[1] : letzte.split('|')[2];
    ok('in der DB mit der Zeit des Tippens', getippt && dbZeit === hhmmss(getippt), `${knopf} ${dbZeit} (getippt ${getippt && hhmmss(getippt)})`);
    if (n === 1) { await zumStatus(); await shot('iphone_uebertragen_kommen'); }
    if (n === 2) { await zumStatus(); await shot('iphone_uebertragen_gehen'); }
    await page.getByRole('button', { name: n % 2 ? 'GEHEN' : 'KOMMEN', exact: true }).waitFor();
  }

  // Echte Fehlermeldung unseres Servers (JSON + Kennung): Meldung anzeigen, NICHT in die Warteschlange
  console.log('Fall 7: KOMMEN, echte Fehlermeldung unseres Servers');
  await page.route('**/api/v1/time-entries/check-in', (r) => r.fulfill({ status: 400, contentType: 'application/json',
    headers: { 'X-Seda24': '1' }, body: JSON.stringify({ detail: 'Test: Kommen abgelehnt' }) }));
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).click();
  ok('Fehlermeldung angezeigt', await page.getByText('Test: Kommen abgelehnt').waitFor({ timeout: 8000 }).then(() => true, () => false));
  ok('nicht in der Warteschlange', (await queue()).length === 0);
  ok('kein ⏳', (await status()) !== 'wartet');
  await page.unroute('**/api/v1/time-entries/check-in');

  // Direkt online ohne Stoerung: sofort ✓
  console.log('Fall 8: KOMMEN und GEHEN normal online');
  for (const [knopf, name, spalte] of [['KOMMEN', 'Kommen', 1], ['GEHEN', 'Gehen', 2]]) {
    const t0 = Date.now();
    await page.getByRole('button', { name: knopf, exact: true }).click();
    const hm = hhmmss(new Date(t0)).slice(0, 5);
    const ziel = page.locator('[data-stempel-status="ok"]').filter({ hasText: `${name} ${hm}` });
    const da = await ziel.waitFor({ timeout: 6000 }).then(() => true, () => false);
    const db = (eintraege().pop() || '').split('|')[spalte] || '';
    ok(`${knopf}: ✓ "${name} ${hm}" direkt`, da && (await queue()).length === 0 && db.startsWith(hm), `${((Date.now() - t0) / 1000).toFixed(1)} s, DB ${db}`);
    if (knopf === 'GEHEN') { await zumStatus(); await shot('iphone_uebertragen_online'); }
  }

  // Laras Ablauf: Kommen online, dann Gast-WLAN mit Anmeldeseite (JEDE Anfrage liefert HTML), Gehen,
  // Historie, Neu laden im Portal, spaeter mit Netz oeffnen
  console.log('Fall 9: Laras Ablauf - Gast-WLAN mit Anmeldeseite');
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).click();
  await page.locator('[data-stempel-status="ok"]').filter({ hasText: `Kommen ${hhmmss(new Date()).slice(0, 5)} übertragen` }).waitFor();
  await page.getByRole('button', { name: 'Historie' }).click();                     // online: Historie wird gespeichert
  await page.getByText('Arbeitshistorie').waitFor();
  await page.getByRole('button', { name: 'Stempel' }).click();
  await page.getByRole('button', { name: 'GEHEN', exact: true }).waitFor();
  await page.route('**/api/v1/**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: PORTAL_HTML }));
  const kein = await page.getByText('Kein Internet').waitFor({ timeout: 15000 }).then(() => true, () => false);
  ok('Anzeige "Kein Internet" trotz WLAN (echte Erreichbarkeit)', kein);
  const t0 = Date.now();
  await page.getByRole('button', { name: 'GEHEN', exact: true }).click();
  const hmGehen = hhmmss(new Date(t0)).slice(0, 5);
  const sofort = await page.locator('[data-stempel-status="wartet"]').filter({ hasText: `Gehen ${hmGehen} gespeichert – wird übertragen` })
    .waitFor({ timeout: 1500 }).then(() => true, () => false);
  ok(`sofort "⏳ Gehen ${hmGehen} gespeichert – wird übertragen"`, sofort, `${((Date.now() - t0) / 1000).toFixed(1)} s`);
  ok('Zähler gestoppt (keine laufende Arbeitszeit)', !(await page.getByText('Arbeitszeit läuft').isVisible()));
  await zumStatus(); await shot('iphone_gastwlan_gehen_gespeichert');
  await page.getByRole('button', { name: 'Historie' }).click();
  const stand = await page.locator('[data-historie-stand]').waitFor({ timeout: 12000 }).then(() => true, () => false);
  ok('Historie ohne Netz: "Stand von HH:MM"', stand, stand ? await page.locator('[data-historie-stand]').innerText() : '');
  ok('Historie: ausstehendes Gehen mit ⏳', await page.locator('[data-historie-ausstehend]').filter({ hasText: `Gehen ${hmGehen}` }).isVisible());
  await page.screenshot({ path: path.join(OUT, '15_iphone_historie_ohne_netz.png') });
  await page.getByRole('button', { name: 'Stempel' }).click();
  await page.reload();
  await page.locator('[data-stempel-status="wartet"]').waitFor();
  ok('Neu laden im Portal: weiter ⏳, nicht eingestempelt', await page.getByRole('button', { name: 'KOMMEN', exact: true }).isVisible()
     && !(await page.getByText('Arbeitszeit läuft').isVisible()));
  ok('Gehen noch nicht in der DB', !(eintraege().pop() || '').split('|')[2]);
  // Spaeter mit Netz oeffnen: erst Warteschlange, dann Server-Stand
  await page.unroute('**/api/v1/**');
  await page.reload();
  const toastDa = await page.locator('[data-toast]').filter({ hasText: `Gehen ${hmGehen} übertragen` }).waitFor({ timeout: 15000 }).then(() => true, () => false);
  ok(`Toast "Gehen ${hmGehen} übertragen"`, toastDa);
  await page.screenshot({ path: path.join(OUT, '15_iphone_toast_uebertragen.png') });
  ok(`✓ "Gehen ${hmGehen} übertragen"`, await page.locator('[data-stempel-status="ok"]').filter({ hasText: `Gehen ${hmGehen} übertragen` }).isVisible());
  ok('Zähler läuft nicht wieder an', !(await page.getByText('Arbeitszeit läuft').isVisible()) && (await queue()).length === 0);
  const g = (eintraege().pop() || '').split('|')[2] || '';
  ok('Gehen in der DB mit getippter Zeit', g.startsWith(hmGehen), `DB ${g}`);
  await zumStatus(); await shot('iphone_spaeter_uebertragen');

  // Eingestempelt (vom Server bestaetigt), dann Gast-WLAN + Neu laden: bleibt "eingestempelt"
  console.log('Fall 10: eingestempelt, Gast-WLAN, Neu laden');
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).click();
  await page.locator('[data-stempel-status="ok"]').filter({ hasText: `Kommen ${hhmmss(new Date()).slice(0, 5)} übertragen` }).waitFor();
  await page.route('**/api/v1/**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: PORTAL_HTML }));
  await page.reload();
  const laeuft = await page.getByText('Arbeitszeit läuft').waitFor({ timeout: 15000 }).then(() => true, () => false);
  ok('nach Neu laden im Portal weiter eingestempelt (GEHEN-Knopf, Zähler)', laeuft && await page.getByRole('button', { name: 'GEHEN', exact: true }).isVisible());
  if (!laeuft) {
    console.log('    Zustand:', await page.evaluate(() => [localStorage.getItem('bie2_offline_state'), localStorage.getItem('bie2_offline_queue')].join(' | ')));
    await page.screenshot({ path: path.join(OUT, 'fehler_fall10.png') });
  }
  await page.unroute('**/api/v1/**');
  await page.reload();
  await page.getByRole('button', { name: 'GEHEN', exact: true }).click();
  ok('danach GEHEN online: ✓', await page.locator('[data-stempel-status="ok"]').filter({ hasText: `Gehen ${hhmmss(new Date()).slice(0, 5)} übertragen` }).waitFor({ timeout: 8000 }).then(() => true, () => false));
} finally {
  const neu = sql(`SELECT string_agg(id::text, ',') FROM time_entries WHERE employee_id = ${EMP} AND id > ${START_IDS}`);
  if (neu) {
    sql(`DELETE FROM break_entries WHERE time_entry_id IN (${neu}); UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN (${neu});
         DELETE FROM km_daily_entries WHERE employee_id = ${EMP} AND time_entry_id IS NULL AND date = current_date;
         UPDATE pending_bookings SET related_time_entry_id = NULL WHERE related_time_entry_id IN (${neu});
         DELETE FROM time_entries WHERE id IN (${neu})`);
    console.log(`Testeintraege geloescht: ${neu}`);
  }
  await browser.close();
}
console.log(fehler ? `=== ${fehler} Fehler ===` : '=== alles OK ===');
process.exit(fehler ? 1 : 0);
