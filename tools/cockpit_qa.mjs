// NUR DEV: Komplette QA des Cockpits (dev.seda.de, DB dev_cockpit).
// 1) Rundgang: Admin + Objektleitung x Desktop/iPad/Handy x hell/dunkel - jede Seite/jeder Reiter oeffnen, pageerror,
//    console.error, API-Antworten >= 400 (409 = erwartete Rueckfrage), Fehlerkasten, waagerechtes Ueberlaufen, Navigation,
//    Strg+K. Screenshots je Seite.
// 2) Aktionen (Desktop, Admin und Objektleitung): Heute (genehmigen/ablehnen/erledigt+rueckgaengig/antworten/Urlaub),
//    Dienstplan (anlegen/bearbeiten+rueckgaengig/loeschen+rueckgaengig/Woche kopieren+ganze Kopie rueckgaengig/als fertig),
//    Mitarbeiter-Akte (Objekt zuteilen mit KM / Zuteilung beenden), KM-Strecke (+rueckgaengig), Objekt (bearbeiten
//    +rueckgaengig, deaktivieren+rueckgaengig), Zeiten (nachtragen/bearbeiten+rueckgaengig/loeschen+rueckgaengig),
//    Abrechnung (Monat, Reiter, PDF, Lexware), Einstellungen (Reiter, Branding speichern+rueckgaengig), Theme-Knopf.
// 3) Rechte: Objektleitung ohne Kunden-Umsaetze (UI + API 403), Mitarbeiter/ohne Anmeldung kein Cockpit.
// Testdaten: eigener Mitarbeiter "QA Cockpit-Test" (QA0001) + Objekt "QA-TEST Objekt"; am Ende komplett entfernt.
// Bestandsdaten: Pruefsumme vorher/nachher (alles ausser den QA-Testdaten) muss gleich bleiben.
// Aufruf: node cockpit_qa.mjs <ordner> [nur=rundgang|aktionen]
import fs from 'fs'; import path from 'path';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const env = Object.fromEntries(fs.readFileSync(new URL('./cockpit_dev.env', import.meta.url), 'utf8').split('\n').filter((l) => l.includes('='))
  .map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
const [OUT, NUR] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1`;

const sql = (q) => execFileSync('psql', ['-h', 'localhost', '-U', 'seda24_user', 'dev_cockpit', '-X', '-q', '-tA', '-F', '|', '-v', 'ON_ERROR_STOP=1', '-c', q],
  { env: { ...process.env, PGPASSWORD: 'SedaDev2025' } }).toString().trim();

const ergebnis = [];   // {bereich, funktion, ok, info}
const fehlerListe = [];
const ok = (bereich, funktion, cond, info = '') => {
  ergebnis.push({ bereich, funktion, ok: !!cond, info });
  console.log(`  [${cond ? 'OK ' : 'XX '}] ${bereich}: ${funktion}${info ? ' - ' + info : ''}`);
  return !!cond;
};

// ---------- Bestandsdaten-Pruefsumme (ohne QA-Testdaten) ----------
const QA_MAIL = 'qa-cockpit@seda.invalid', QA_NR = 'QA0001', QA_OBJ = 'QA-TEST Objekt';
const qaIds = () => ({
  emp: sql(`SELECT coalesce((SELECT id FROM employees WHERE personal_nr = '${QA_NR}'), -1)`),
  obj: sql(`SELECT coalesce((SELECT id FROM objects WHERE name = '${QA_OBJ}'), -1)`),
  usr: sql(`SELECT coalesce((SELECT id FROM users WHERE email = '${QA_MAIL}'), -1)`),
});
function pruefsumme() {
  const ids = qaIds();
  // T9999 ausnehmen: die Stempeluhr-Tests (ein_knopf_test, stempel_bestaetigung_test) laufen ggf. parallel auf DEV
  const t9 = sql(`SELECT coalesce((SELECT id FROM employees WHERE personal_nr = 'T9999'), -1)`);
  const emp = `${ids.emp}, ${t9}`, obj = ids.obj, usr = `${ids.usr}, coalesce((SELECT user_id FROM employees WHERE id = ${t9}), -1)`;
  const t = {
    employees: `SELECT md5(string_agg(t::text, ',' ORDER BY id)) FROM employees t WHERE id NOT IN (${emp})`,
    users: `SELECT md5(string_agg((id, email, role, is_active, category)::text, ',' ORDER BY id)) FROM users WHERE id NOT IN (${usr})`,
    objects: `SELECT md5(string_agg(t::text, ',' ORDER BY id)) FROM objects t WHERE id <> ${obj}`,
    schedules: `SELECT md5(string_agg((id, employee_id, object_id, date, start_time, end_time, status, planned_hours)::text, ',' ORDER BY id)) FROM schedules WHERE employee_id NOT IN (${emp}) AND coalesce(object_id,0) <> ${obj}`,
    time_entries: `SELECT md5(string_agg((id, employee_id, object_id, check_in, check_out, billed_hours, notes)::text, ',' ORDER BY id)) FROM time_entries WHERE employee_id NOT IN (${emp})`,
    pending_bookings: `SELECT md5(string_agg((id, employee_id, status, approved_hours)::text, ',' ORDER BY id)) FROM pending_bookings WHERE employee_id NOT IN (${emp})`,
    km_distances: `SELECT md5(string_agg(t::text, ',' ORDER BY id)) FROM km_distances t WHERE employee_id NOT IN (${emp}) AND object_id <> ${obj}`,
    assignments: `SELECT md5(string_agg((id, employee_id, object_id, is_active, tracking_category)::text, ',' ORDER BY id)) FROM employee_object_assignments WHERE employee_id NOT IN (${emp}) AND object_id <> ${obj}`,
    vorlage: `SELECT md5(string_agg(t::text, ',' ORDER BY id)) FROM schedule_template_items t WHERE employee_id NOT IN (${emp}) AND object_id <> ${obj}`,
    vacation: `SELECT md5(string_agg((id, employee_id, status)::text, ',' ORDER BY id)) FROM vacation_requests WHERE employee_id NOT IN (${emp})`,
    messages: `SELECT md5(string_agg((id, status, body)::text, ',' ORDER BY id)) FROM messages WHERE coalesce(sender_employee_id,0) NOT IN (${emp}) AND coalesce(parent_id,0) NOT IN (SELECT id FROM messages WHERE sender_employee_id IN (${emp}))`,
    app_settings: `SELECT md5(string_agg((key, value)::text, ',' ORDER BY key)) FROM app_settings`,
  };
  return Object.fromEntries(Object.entries(t).map(([k, q]) => [k, sql(q)]));
}

// ---------- QA-Testdaten ----------
function aufraeumen() {
  const { emp, obj, usr } = qaIds();
  if (emp === '-1' && obj === '-1' && usr === '-1') return;
  const E = emp, O = obj;
  sql(`
    DELETE FROM break_entries WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = ${E} OR object_id = ${O});
    UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = ${E} OR object_id = ${O});
    DELETE FROM km_daily_entries WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM correction_requests WHERE employee_id = ${E};
    UPDATE pending_bookings SET related_time_entry_id = NULL WHERE related_time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = ${E} OR object_id = ${O});
    DELETE FROM pending_bookings WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM time_entries WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM push_notifications WHERE employee_id = ${E} OR schedule_id IN (SELECT id FROM schedules WHERE employee_id = ${E} OR object_id = ${O});
    DELETE FROM schedules WHERE employee_id = ${E} OR object_id = ${O} OR replacement_for = ${E};
    DELETE FROM schedule_template_items WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM km_distances WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM employee_object_assignments WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM employee_object_hours WHERE employee_id = ${E} OR object_id = ${O};
    DELETE FROM messages WHERE parent_id IN (SELECT id FROM messages WHERE sender_employee_id = ${E});
    DELETE FROM messages WHERE sender_employee_id = ${E};
    DELETE FROM vacation_requests WHERE employee_id = ${E};
    DELETE FROM vacation_entitlements WHERE employee_id = ${E};
    DELETE FROM monthly_confirmations WHERE employee_id = ${E};
    DELETE FROM km_monthly_reports WHERE employee_id = ${E};
    DELETE FROM sick_notes WHERE employee_id = ${E};
    DELETE FROM audit_log WHERE employee_id = ${E};
    DELETE FROM object_standard_times WHERE object_id = ${O};
    DELETE FROM object_standard_times_v2 WHERE object_id = ${O};
    DELETE FROM user_object_assignments WHERE object_id = ${O} OR user_id = ${usr};
    DELETE FROM employees WHERE id = ${E};
    DELETE FROM users WHERE id = ${usr};
    DELETE FROM objects WHERE id = ${O};`);
}
function anlegen() {
  aufraeumen();
  const usr = sql(`INSERT INTO users (email, password_hash, role, is_active, category, must_change_password)
    VALUES ('${QA_MAIL}', 'x', 'MITARBEITER', true, 'B', false) RETURNING id`);
  const emp = sql(`INSERT INTO employees (user_id, personal_nr, first_name, last_name, is_active, is_test, tracking_mode, hourly_rate)
    VALUES (${usr}, '${QA_NR}', 'QA', 'Cockpit-Test', true, false, 'B', 15) RETURNING id`);
  const obj = sql(`INSERT INTO objects (name, address, is_active, is_test) VALUES ('${QA_OBJ}', 'Teststr. 1, Rastatt', true, false) RETURNING id`);
  sql(`INSERT INTO vacation_entitlements (employee_id, year, days_entitled) VALUES (${emp}, extract(year from current_date)::int, 20)`);
  const pb = (notiz) => sql(`INSERT INTO pending_bookings (employee_id, object_id, date, start_time, end_time, service_type, requested_hours,
      status, notes, created_at, reason, catch_up_type)
    VALUES (${emp}, ${obj}, current_date - 1, '08:00', '10:00', 'Unterhaltsreinigung', 2, 'offen', '${notiz}', now(), 'vergessen', 'beides_vergessen') RETURNING id`);
  const pb1 = pb('QA-TEST genehmigen'), pb2 = pb('QA-TEST ablehnen');
  const msg = sql(`INSERT INTO messages (sender_employee_id, category, subject, body, status, created_at)
    VALUES (${emp}, 'sonstiges', 'QA-TEST', 'QA-TEST Nachricht', 'neu', now()) RETURNING id`);
  const msg2 = sql(`INSERT INTO messages (sender_employee_id, category, subject, body, status, created_at)
    VALUES (${emp}, 'sonstiges', 'QA-TEST2', 'QA-TEST Nachricht 2', 'neu', now()) RETURNING id`);
  const vac = sql(`INSERT INTO vacation_requests (employee_id, start_date, end_date, working_days, status, requested_at, type)
    VALUES (${emp}, current_date + 60, current_date + 60, 1, 'pending', now(), 'urlaub') RETURNING id`);
  return { usr, emp, obj, pb1, pb2, msg, msg2, vac };
}

// ---------- Anmeldung ----------
// Kurzlebige Tokens ueber dev_token.py (nur DEV), ohne Passwoerter
const HIER = path.dirname(new URL(import.meta.url).pathname);
const token = (email) => execFileSync(path.join(HIER, '../backend/venv/bin/python'), [path.join(HIER, 'dev_token.py'), email]).toString().trim();
const ROLLEN = { admin: token(env.ADMIN_EMAIL), ol: token(env.OL_EMAIL) };
const { defaultBrowserType: _a, ...IPAD } = devices['iPad (gen 7)'];
const { defaultBrowserType: _b, ...HANDY } = devices['iPhone 15'];
const GERAETE = { desktop: { viewport: { width: 1440, height: 900 } }, ipad: IPAD, handy: HANDY };
const browser = await chromium.launch();

async function seite(rolle, geraet, theme) {
  const ctx = await browser.newContext({ ...GERAETE[geraet], locale: 'de-DE', timezoneId: 'Europe/Berlin', acceptDownloads: true });
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  page.fehler = [];
  page.on('pageerror', (e) => page.fehler.push(`JS: ${e.message.slice(0, 160)}`));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) page.fehler.push(`console: ${m.text().slice(0, 160)}`); });
  page.on('response', (r) => {
    const u = r.url();
    if (u.includes('/api/') && r.status() >= 400 && r.status() !== 409) page.fehler.push(`API ${r.status()} ${r.request().method()} ${u.replace(/^.*\/api/, '/api').slice(0, 110)}`);
  });
  await page.goto(BASE + '/login');
  await page.evaluate(([tk, th]) => {
    localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_theme_v2', th);
  }, [ROLLEN[rolle], theme]);
  return { ctx, page };
}
const geh = async (page, url) => {
  await page.goto(BASE + url); await page.waitForLoadState('networkidle').catch(() => {}); await page.waitForTimeout(500);
};
const fehlerkasten = (page) => page.getByText('Das hat nicht geklappt').count();
const ueberlauf = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
const toastDa = (page, txt) => page.locator('.ck-toast').filter({ hasText: txt }).first().waitFor({ timeout: 8000 }).then(() => true, () => false);
const undoKlick = async (page) => { await page.locator('.ck-toast button', { hasText: 'Rückgängig' }).last().click(); await page.waitForTimeout(1200); };
const warte = (ms) => new Promise((r) => setTimeout(r, ms));
const pollDb = async (q, erwartet, ms = 8000) => { const t0 = Date.now(); let v; do { v = sql(q); if (v === erwartet) return v; await warte(300); } while (Date.now() - t0 < ms); return v; };

// ================= 1) Rundgang =================
const SEITEN = [
  ['Heute', '/cockpit'], ['Dienstplan Tage', '/cockpit/dienstplan', { ck_dp_ansicht: 'tage' }], ['Dienstplan Mitarbeiter', '/cockpit/dienstplan', { ck_dp_ansicht: 'ma' }],
  ['Vorlage', '/cockpit/vorlage'], ['Mitarbeiter', '/cockpit/mitarbeiter'], ['Akte Ruzica', '/cockpit/mitarbeiter/4'],
  ['Objekte', '/cockpit/objekte'], ['Objekt-Detail Bie2', '/cockpit/objekte/20'], ['Zeiten 7 Tage', '/cockpit/zeiten'], ['Zeiten Monat', '/cockpit/zeiten?range=month'],
  ['Abrechnung Übersicht', '/cockpit/abrechnung'], ['Einstellungen Marke', '/cockpit/einstellungen?tab=brand'], ['Einstellungen KM', '/cockpit/einstellungen?tab=km'],
  ['Einstellungen Urlaub', '/cockpit/einstellungen?tab=urlaub'], ['Einstellungen Zuweisungen', '/cockpit/einstellungen?tab=assign'],
  ['Einstellungen Telegram', '/cockpit/einstellungen?tab=telegram'], ['Einstellungen Protokoll', '/cockpit/einstellungen?tab=audit'],
];
const ABR_TABS = { neu: 'Übersicht', lohn: 'Lohnübersicht', pdf: 'Zeitnachweise & Lexware', umsatz: 'Kunden-Umsätze' };

async function rundgang(rolle, geraet, theme) {
  const tag = `${rolle}/${geraet}/${theme}`;
  console.log(`Rundgang ${tag}`);
  const { ctx, page } = await seite(rolle, geraet, theme);
  const ordner = path.join(OUT, 'rundgang', `${rolle}_${geraet}_${theme}`); fs.mkdirSync(ordner, { recursive: true });
  const probleme = [];
  for (const [name, url, ls] of SEITEN) {
    if (ls) await page.evaluate((o) => Object.entries(o).forEach(([k, v]) => localStorage.setItem(k, v)), ls);
    page.fehler = [];
    await geh(page, url);
    await page.locator('.ck-page-head h1').first().waitFor({ timeout: 10000 }).catch(() => {});
    if (url.includes('/einstellungen?tab=') && !url.endsWith('brand')) await page.waitForTimeout(1200);  // eingebettete klassische Reiter
    const h1 = await page.locator('.ck-page-head h1').first().isVisible().catch(() => false);
    const pfad = new URL(page.url()).pathname;
    const umgeleitet = url !== '/cockpit' && (pfad === '/cockpit' || pfad === '/cockpit/');
    const fk = await fehlerkasten(page);
    const ue = await ueberlauf(page);
    const dunkel = await page.evaluate(() => document.querySelector('.ck')?.className || '');
    const p = [];
    if (!h1) p.push('keine Überschrift');
    if (umgeleitet) p.push('auf Heute umgeleitet');
    if (fk) p.push('Fehlerkasten');
    if (ue > 1) p.push(`waagerecht ${ue}px zu breit`);
    if (theme === 'dark' !== /dark/.test(dunkel)) p.push(`Theme nicht ${theme} (${dunkel})`);
    p.push(...page.fehler);
    if (p.length) probleme.push(`${name}: ${p.join('; ')}`);
    await page.screenshot({ path: path.join(ordner, `${name.replace(/[^A-Za-z0-9ÄÖÜäöüß]+/g, '_')}.png`) });
  }
  // Abrechnung-Reiter (Kunden-Umsaetze nur Admin)
  await geh(page, '/cockpit/abrechnung');
  const umsatzKnopf = await page.getByRole('button', { name: ABR_TABS.umsatz, exact: true }).count();
  if (rolle === 'ol' && umsatzKnopf) probleme.push('Objektleitung sieht Reiter Kunden-Umsätze');
  if (rolle === 'admin' && !umsatzKnopf) probleme.push('Admin ohne Reiter Kunden-Umsätze');
  for (const [k, lbl] of Object.entries(ABR_TABS)) {
    if (k === 'umsatz' && rolle !== 'admin') continue;
    page.fehler = [];
    await page.getByRole('button', { name: lbl, exact: true }).click().catch((e) => page.fehler.push(`Reiter ${lbl}: ${e.message.slice(0, 80)}`));
    await page.waitForLoadState('networkidle').catch(() => {}); await page.waitForTimeout(1200);
    if (await fehlerkasten(page)) page.fehler.push('Fehlerkasten');
    const ue = await ueberlauf(page); if (ue > 1) page.fehler.push(`waagerecht ${ue}px zu breit`);
    if (page.fehler.length) probleme.push(`Abrechnung/${lbl}: ${page.fehler.join('; ')}`);
    await page.screenshot({ path: path.join(ordner, `Abrechnung_${k}.png`) });
  }
  // Navigation: Desktop/iPad Seitenleiste, Handy untere Leiste + "Mehr"
  await geh(page, '/cockpit');
  if (geraet === 'handy') {
    const unten = await page.locator('.ck-bottomnav button').count();
    await page.locator('.ck-bottomnav button', { hasText: 'Mehr' }).click();
    const mehr = await page.locator('.ck-dialog .ck-nav-item').count();
    if (unten !== 5 || mehr < 4) probleme.push(`Handy-Navigation: unten ${unten}, Mehr ${mehr}`);
    await page.locator('.ck-dialog .ck-nav-item', { hasText: 'Einstellungen' }).click();
    await page.waitForTimeout(800);
    if (!page.url().includes('/cockpit/einstellungen')) probleme.push('Handy "Mehr" > Einstellungen öffnet nicht');
    await page.screenshot({ path: path.join(ordner, 'Navigation_Mehr.png') });
  } else {
    const n = await page.locator('.ck-sidebar .ck-nav-item').count();
    const sichtbar = await page.locator('.ck-sidebar').isVisible();
    if (sichtbar && n < 8) probleme.push(`Seitenleiste nur ${n} Einträge`);
    if (!sichtbar && !(await page.locator('.ck-bottomnav').isVisible())) probleme.push('keine Navigation sichtbar');
  }
  // Strg+K (Desktop: Tastenkombination, sonst Suchknopf): "Ruzica" -> Enter -> Akte
  await geh(page, '/cockpit');
  if (geraet === 'desktop') await page.keyboard.press('Control+k'); else await page.locator('.ck-search').click();
  const pal = await page.getByRole('dialog').waitFor({ timeout: 4000 }).then(() => true, () => false);
  if (pal) {
    await page.getByRole('dialog').locator('input').fill('Ruzica'); await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(ordner, 'Befehlspalette.png') });
    await page.keyboard.press('Enter'); await page.waitForTimeout(1000);
    if (!/\/cockpit\/mitarbeiter\/4$/.test(new URL(page.url()).pathname)) probleme.push(`Befehlspalette: Ruzica+Enter -> ${new URL(page.url()).pathname}`);
  } else probleme.push('Befehlspalette öffnet nicht');
  // Theme-Knopf oben
  await geh(page, '/cockpit');
  const vorher = await page.evaluate(() => localStorage.getItem('ck_theme_v2'));
  await page.locator('.ck-topbar-right .ck-btn-icon').first().click(); await page.waitForTimeout(400);
  const nachher = await page.evaluate(() => localStorage.getItem('ck_theme_v2'));
  if (vorher === nachher) probleme.push(`Theme-Knopf ändert nichts (${vorher})`);
  ok('Rundgang', tag, probleme.length === 0, probleme.join(' | ').slice(0, 900));
  await ctx.close();
}

// ================= 2) Aktionen =================
const ZUKUNFT = '2027-08-02';  // Montag, leere Woche fuer Dienstplan-Tests
async function aktionen(rolle, qa) {
  const R = rolle === 'admin' ? 'Admin' : 'Objektleitung';
  console.log(`Aktionen ${R}`);
  const { ctx, page } = await seite(rolle, 'desktop', 'light');
  const shot = (n) => page.screenshot({ path: path.join(OUT, `aktion_${rolle}_${n}.png`) });
  const dlg = () => page.getByRole('dialog');
  const sel = async (label, value) => { await dlg().locator('label', { hasText: label }).locator('select').selectOption(String(value)); };
  const feld = async (label, value) => { await dlg().locator('label', { hasText: label }).locator('input').first().fill(value); };
  const leer = () => { page.fehler = []; };
  const fehlerText = () => page.fehler.join('; ');

  // ---- Heute ----
  if (rolle === 'admin') {
    await geh(page, '/cockpit');
    const zeile = (txt) => page.locator('li.ck-row').filter({ hasText: 'QA Cockpit-Test' }).filter({ hasText: txt }).first();
    leer();
    await zeile('08:00–10:00').getByRole('button', { name: 'Genehmigen' }).click();
    ok('Heute', `${R}: Nachtrag genehmigen`, await toastDa(page, 'QA') && await pollDb(`SELECT status FROM pending_bookings WHERE id = ${qa.pb1}`, 'genehmigt') === 'genehmigt', fehlerText());
    leer();
    await zeile('08:00–10:00').getByRole('button', { name: 'Ablehnen' }).click();
    await dlg().locator('textarea, input').first().fill('QA-TEST Rückfrage').catch(() => {});
    await dlg().getByRole('button', { name: 'Ablehnen' }).click();
    ok('Heute', `${R}: Nachtrag ablehnen (Rückfrage)`, await pollDb(`SELECT status FROM pending_bookings WHERE id = ${qa.pb2}`, 'abgelehnt') === 'abgelehnt', fehlerText());
    leer();
    await zeile('QA-TEST Nachricht 2').getByRole('button', { name: 'Erledigt' }).click();
    const gel = await pollDb(`SELECT status FROM messages WHERE id = ${qa.msg2}`, 'gelesen');
    await undoKlick(page);
    ok('Heute', `${R}: Nachricht erledigt + Rückgängig`, gel === 'gelesen' && await pollDb(`SELECT status FROM messages WHERE id = ${qa.msg2}`, 'neu') === 'neu', fehlerText());
    leer();
    await zeile('QA-TEST: ').getByRole('button', { name: 'Antworten' }).click();
    await dlg().locator('textarea').fill('QA-TEST Antwort');
    await shot('heute_antworten');
    await dlg().getByRole('button', { name: /Antworten|Senden/ }).last().click();
    ok('Heute', `${R}: Nachricht beantworten`, await pollDb(`SELECT count(*) FROM messages WHERE parent_id = ${qa.msg}`, '1') === '1', fehlerText());
    leer();
    await zeile('Arbeitstage').getByRole('button', { name: 'Genehmigen' }).click();
    ok('Heute', `${R}: Urlaub genehmigen`, await pollDb(`SELECT status FROM vacation_requests WHERE id = ${qa.vac}`, 'approved') === 'approved', fehlerText());
    await shot('heute_nach_aktionen');
  }

  // ---- Dienstplan ----
  const S = (q) => sql(`SELECT coalesce(string_agg(${q}, ',' ORDER BY id), '') FROM schedules WHERE employee_id = ${qa.emp}`);
  await page.evaluate(() => localStorage.setItem('ck_dp_ansicht', 'tage'));
  await geh(page, `/cockpit/dienstplan?start=${ZUKUNFT}`);
  leer();
  await page.getByRole('button', { name: 'Schicht anlegen', exact: true }).first().click();
  await sel('Mitarbeiter', qa.emp); await sel('Objekt', qa.obj);
  await feld('Datum', '2027-08-03'); await feld('Beginn', '08:00'); await feld('Ende', '10:00');
  await shot('dienstplan_anlegen');
  await dlg().getByRole('button', { name: 'Speichern' }).click();
  const angelegt = await pollDb(`SELECT count(*) FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-03'`, '1');
  ok('Dienstplan', `${R}: Schicht anlegen`, angelegt === '1' && await toastDa(page, 'angelegt'), fehlerText());
  leer();
  await page.locator('.ck-shift, [data-shift], .ck-dp-shift').filter({ hasText: 'QA' }).first().click()
    .catch(async () => { await page.getByText('QA-TEST Objekt').first().click(); });
  await dlg().waitFor();
  await feld('Ende', '11:00'); await dlg().getByRole('button', { name: 'Speichern' }).click();
  const geaendert = await pollDb(`SELECT to_char(end_time,'HH24:MI') FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-03'`, '11:00');
  await undoKlick(page);
  const zurueck = await pollDb(`SELECT to_char(end_time,'HH24:MI') FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-03'`, '10:00');
  ok('Dienstplan', `${R}: Schicht bearbeiten + Rückgängig`, geaendert === '11:00' && zurueck === '10:00', `${geaendert}/${zurueck} ${fehlerText()}`);
  // Woche kopieren -> Folgewoche, dann ganze Kopie rueckgaengig
  leer();
  await geh(page, `/cockpit/dienstplan?start=${ZUKUNFT}`);
  await page.getByRole('button', { name: 'Woche kopieren', exact: true }).click();
  await dlg().waitFor();
  const datumsfelder = dlg().locator('input[type=date]');
  if (await datumsfelder.count()) { await datumsfelder.first().fill('2027-08-09'); if (await datumsfelder.count() > 1) await datumsfelder.nth(1).fill('2027-08-15'); }
  await dlg().getByRole('button', { name: 'Vorschau anzeigen' }).click();
  await dlg().getByRole('button', { name: /Schichten anlegen/ }).waitFor();
  await shot('dienstplan_kopie_vorschau');
  await dlg().getByRole('button', { name: /Schichten anlegen/ }).click();
  const kopiert = await pollDb(`SELECT count(*) FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-10'`, '1');
  await page.getByRole('button', { name: 'Ganze Kopie rückgängig' }).click().catch(() => {});
  const weg = await pollDb(`SELECT count(*) FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-10'`, '0');
  ok('Dienstplan', `${R}: Woche kopieren + ganze Kopie rückgängig`, kopiert === '1' && weg === '0', `kopiert ${kopiert}, danach ${weg}; ${fehlerText()}`);
  // Als fertig melden (aktuelle Woche, dort gibt es einen Plan) + Wieder oeffnen; Einstellung danach exakt wie vorher
  leer();
  const fertigVorher = sql(`SELECT value FROM app_settings WHERE key = 'dienstplan_fertig'`);
  const folge = sql(`SELECT date_trunc('week', current_date)::date::text`);  // aktuelle, geplante Woche
  await geh(page, `/cockpit/dienstplan?start=${folge}`);
  const fertigKnopf = page.getByRole('button', { name: 'Als fertig melden' }).first();
  if (await fertigKnopf.waitFor({ timeout: 6000 }).then(() => true, () => false)) {
    await fertigKnopf.click();
    const g = await toastDa(page, 'Woche als fertig gemeldet');
    const wieder = page.getByRole('button', { name: 'Wieder öffnen' }).first();
    const w = await wieder.waitFor({ timeout: 6000 }).then(() => true, () => false);
    if (w) await wieder.click();
    await page.waitForTimeout(1200);
    sql(`UPDATE app_settings SET value = '${fertigVorher.replace(/'/g, "''")}' WHERE key = 'dienstplan_fertig'`);
    ok('Dienstplan', `${R}: Woche als fertig melden + wieder öffnen`, g && w && !page.fehler.length, fehlerText());
    await shot('dienstplan_fertig');
  } else ok('Dienstplan', `${R}: Woche als fertig melden + wieder öffnen`, false, `Knopf fehlt in Woche ${folge} (Plan ungeplant?)`);
  // Loeschen + Rueckgaengig
  leer();
  await geh(page, `/cockpit/dienstplan?start=${ZUKUNFT}`);
  await page.getByText('QA-TEST Objekt').first().click().catch(() => {});
  await dlg().waitFor();
  await dlg().getByRole('button', { name: 'Löschen' }).click(); await dlg().getByRole('button', { name: 'Wirklich löschen' }).click();
  const geloescht = await pollDb(`SELECT count(*) FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-03'`, '0');
  await undoKlick(page);
  const wieder = await pollDb(`SELECT count(*) FROM schedules WHERE employee_id = ${qa.emp} AND date = '2027-08-03'`, '1');
  ok('Dienstplan', `${R}: Schicht löschen + Rückgängig`, geloescht === '0' && wieder === '1', `${geloescht}/${wieder} ${fehlerText()}`);
  await shot('dienstplan_nach_aktionen');
  sql(`DELETE FROM schedules WHERE employee_id = ${qa.emp}`);
  void S;

  // ---- Mitarbeiter-Akte: Objekt zuteilen (mit KM) + Zuteilung beenden ----
  leer();
  await geh(page, `/cockpit/mitarbeiter/${qa.emp}`);
  await page.getByRole('button', { name: 'Objekt zuteilen' }).first().click();
  await dlg().locator('select').first().selectOption(String(qa.obj));
  await dlg().getByRole('button', { name: 'Objekt zuteilen' }).click();
  const kmFeld = dlg().locator('input[inputmode=decimal], input[type=number]').first();
  if (await kmFeld.waitFor({ timeout: 4000 }).then(() => true, () => false)) { await kmFeld.fill('4,5'); await dlg().getByRole('button', { name: 'Objekt zuteilen' }).click(); }
  const zu = await pollDb(`SELECT count(*) FROM employee_object_assignments WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj} AND is_active`, '1');
  const km = sql(`SELECT coalesce(max(distance_km)::text, '') FROM km_distances WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj}`);
  ok('Mitarbeiter', `${R}: Objekt zuteilen (mit KM)`, zu === '1' && km !== '', `Zuteilung ${zu}, KM ${km}; ${fehlerText()}`);
  await shot('akte_zugeteilt');

  // ---- KM-Strecke aendern + Rueckgaengig (Einstellungen > KM-Strecken) ----
  leer();
  await geh(page, '/cockpit/einstellungen?tab=km');
  const kmZeile = page.locator('tr, li, .ck-row').filter({ hasText: 'QA Cockpit-Test' }).filter({ hasText: QA_OBJ }).first();
  const kmDa = await kmZeile.waitFor({ timeout: 6000 }).then(() => true, () => false);
  if (kmDa) {
    await kmZeile.getByRole('button').filter({ hasText: 'km' }).first().click();
    await kmZeile.locator('input').fill('6,5'); await kmZeile.getByRole('button', { name: 'Speichern' }).click();
    const neu = await pollDb(`SELECT distance_km::numeric(6,1)::text FROM km_distances WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj}`, '6.5');
    await undoKlick(page);
    const alt = await pollDb(`SELECT distance_km::numeric(6,1)::text FROM km_distances WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj}`, '4.5');
    ok('KM-Strecken', `${R}: KM ändern + Rückgängig`, neu === '6.5' && alt === '4.5', `${neu}/${alt}; ${fehlerText()}`);
  } else ok('KM-Strecken', `${R}: KM ändern + Rückgängig`, false, 'Zeile QA-Mitarbeiter/QA-Objekt in Einstellungen > KM-Strecken nicht gefunden');
  await shot('km_strecken');

  leer();
  await geh(page, `/cockpit/mitarbeiter/${qa.emp}`);
  await page.getByRole('button', { name: `Zuteilung beenden: ${QA_OBJ}` }).click();
  await page.waitForTimeout(1500);
  const ende = sql(`SELECT count(*) FROM employee_object_assignments WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj} AND is_active`);
  ok('Mitarbeiter', `${R}: Zuteilung beenden`, ende === '0', `aktiv ${ende}; ${fehlerText()}`);
  // fuer die folgenden Tests wieder zuteilen (direkt)
  sql(`UPDATE employee_object_assignments SET is_active = true WHERE employee_id = ${qa.emp} AND object_id = ${qa.obj}`);

  // ---- Objekt bearbeiten + Rueckgaengig, deaktivieren + Rueckgaengig ----
  leer();
  await geh(page, `/cockpit/objekte/${qa.obj}`);
  await page.getByRole('button', { name: 'Bearbeiten' }).click();
  await page.locator('label.ck-field', { hasText: /^Name/ }).locator('input').first().fill(`${QA_OBJ} geändert`);
  await page.getByRole('button', { name: 'Speichern' }).click();
  const n1 = await pollDb(`SELECT name FROM objects WHERE id = ${qa.obj}`, `${QA_OBJ} geändert`);
  await undoKlick(page);
  const n2 = await pollDb(`SELECT name FROM objects WHERE id = ${qa.obj}`, QA_OBJ);
  ok('Objekte', `${R}: Objekt bearbeiten + Rückgängig`, n1 === `${QA_OBJ} geändert` && n2 === QA_OBJ, `${n1} / ${n2}; ${fehlerText()}`);
  leer();
  await geh(page, `/cockpit/objekte/${qa.obj}`);
  await page.getByRole('button', { name: 'Deaktivieren' }).click();
  const a1 = await pollDb(`SELECT is_active FROM objects WHERE id = ${qa.obj}`, 'f');
  await undoKlick(page);
  const a2 = await pollDb(`SELECT is_active FROM objects WHERE id = ${qa.obj}`, 't');
  ok('Objekte', `${R}: Objekt deaktivieren + Rückgängig`, a1 === 'f' && a2 === 't', `${a1}/${a2}; ${fehlerText()}`);
  await shot('objekt_detail');
  leer();
  await geh(page, '/cockpit/objekte');
  await page.locator('input[type=search], input[placeholder]').first().fill('QA-TEST').catch(() => {});
  await page.waitForTimeout(500);
  ok('Objekte', `${R}: Objektliste + Suche`, await page.getByText(QA_OBJ).first().isVisible() && !page.fehler.length, fehlerText());

  // ---- Zeiten: nachtragen, bearbeiten + Rueckgaengig, loeschen + Rueckgaengig ----
  const gestern = sql(`SELECT (current_date - 2)::text`);
  const TE = (q) => sql(`SELECT coalesce(string_agg(${q}, ',' ORDER BY id), '') FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`);
  leer();
  await geh(page, '/cockpit/zeiten');
  await page.getByRole('button', { name: 'Buchung nachtragen' }).click();
  await sel('Mitarbeiter', qa.emp); await sel('Objekt', qa.obj);
  await feld('Datum', gestern); await feld('Kommen', '07:00'); await feld('Gehen', '09:30');
  await shot('zeiten_nachtragen');
  await dlg().getByRole('button', { name: 'Speichern' }).click();
  const z1 = await pollDb(`SELECT count(*) FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`, '1');
  ok('Zeiten', `${R}: Buchung nachtragen`, z1 === '1', `${z1}; ${fehlerText()}`);
  leer();
  await geh(page, '/cockpit/zeiten');
  await page.locator('tr, .ck-row, button').filter({ hasText: 'QA Cockpit-Test' }).filter({ hasText: '07:00' }).first().click();
  await dlg().waitFor();
  await feld('Gehen', '10:00'); await dlg().getByRole('button', { name: 'Speichern' }).click();
  const g1 = await pollDb(`SELECT to_char(check_out,'HH24:MI') FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`, '10:00');
  await undoKlick(page);
  const g2 = await pollDb(`SELECT to_char(check_out,'HH24:MI') FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`, '09:30');
  ok('Zeiten', `${R}: Buchung bearbeiten + Rückgängig`, g1 === '10:00' && g2 === '09:30', `${g1}/${g2}; ${fehlerText()}`);
  leer();
  await geh(page, '/cockpit/zeiten');
  await page.locator('tr, .ck-row, button').filter({ hasText: 'QA Cockpit-Test' }).filter({ hasText: '07:00' }).first().click();
  await dlg().waitFor();
  await dlg().getByRole('button', { name: 'Löschen' }).click(); await dlg().getByRole('button', { name: 'Wirklich löschen' }).click();
  const d1 = await pollDb(`SELECT count(*) FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`, '0');
  await undoKlick(page);
  const d2 = await pollDb(`SELECT count(*) FROM time_entries WHERE employee_id = ${qa.emp} AND check_in::date = '${gestern}'`, '1');
  ok('Zeiten', `${R}: Buchung löschen + Rückgängig`, d1 === '0' && d2 === '1', `${d1}/${d2}; ${fehlerText()}`);
  await shot('zeiten_nach_aktionen');
  leer();
  await page.getByRole('button', { name: 'Genehmigungen (klassisch)' }).click(); await page.waitForTimeout(1500);
  ok('Zeiten', `${R}: Genehmigungen (klassisch) öffnen`, !page.fehler.length && !(await fehlerkasten(page)), fehlerText());
  void TE;

  // ---- Abrechnung: Monat blaettern, PDF, Lexware ----
  leer();
  await geh(page, '/cockpit/abrechnung');
  await page.getByRole('button', { name: 'Vorheriger Monat' }).click(); await page.waitForTimeout(1200);
  await page.getByRole('button', { name: 'Nächster Monat' }).click(); await page.waitForTimeout(1200);
  ok('Abrechnung', `${R}: Monat vor/zurück`, !page.fehler.length && !(await fehlerkasten(page)), fehlerText());
  leer();
  const dl = page.waitForEvent('download', { timeout: 90000 }).then((d) => d.suggestedFilename(), () => '');
  await page.getByRole('button', { name: 'Zeitnachweise (PDF)' }).click();
  const pdf = await dl;
  ok('Abrechnung', `${R}: Zeitnachweise (PDF)`, /\.zip$/.test(pdf), `${pdf || 'kein Download'}; ${fehlerText()}`);
  leer();
  const dl2 = page.waitForEvent('download', { timeout: 60000 }).then((d) => d.suggestedFilename(), () => '');
  await page.getByRole('button', { name: 'Lexware-Export (ZIP)' }).click();
  const lex = await dl2;
  const lexToast = lex ? '' : await page.locator('.ck-toast').last().innerText().catch(() => '');
  ok('Abrechnung', `${R}: Lexware-Export`, /\.zip$/.test(lex) || /Keine|keine/.test(lexToast), `${lex || lexToast}; ${fehlerText()}`);
  await shot('abrechnung');

  // ---- Einstellungen: Branding speichern + Rueckgaengig ----
  leer();
  const brandVorher = sql(`SELECT value FROM app_settings WHERE key = 'branding'`);
  await geh(page, '/cockpit/einstellungen?tab=brand');
  await page.locator('label', { hasText: 'Produkt' }).locator('input').fill('stampo24 QA');
  await page.getByRole('button', { name: 'Speichern' }).click();
  const b1 = await pollDb(`SELECT value::json->>'produkt' FROM app_settings WHERE key = 'branding'`, 'stampo24 QA');
  await undoKlick(page);
  const b2 = await pollDb(`SELECT value FROM app_settings WHERE key = 'branding'`, brandVorher);
  if (b2 !== brandVorher) sql(`UPDATE app_settings SET value = '${brandVorher.replace(/'/g, "''")}' WHERE key = 'branding'`);
  ok('Einstellungen', `${R}: Branding speichern + Rückgängig (exakt wie vorher)`, b1 === 'stampo24 QA' && b2 === brandVorher, `${b1}; ${b2 === brandVorher ? 'gleich' : 'ABWEICHUNG, per SQL zurückgesetzt'}; ${fehlerText()}`);
  await shot('branding');
  await ctx.close();
}

// ================= 3) Rechte =================
async function rechte(qaMailToken) {
  const g = async (tk, p) => (await fetch(`${API}${p}`, { headers: tk ? { Authorization: `Bearer ${tk}` } : {} })).status;
  const ym = 'year=2026&month=10';
  const a = await g(ROLLEN.admin, `/admin/customer-revenues?${ym}`), o = await g(ROLLEN.ol, `/admin/customer-revenues?${ym}`);
  ok('Rechte', 'Kunden-Umsätze: Admin ja, Objektleitung 403', a < 400 && o === 403, `Admin ${a}, OL ${o}`);
  const ob = await g(ROLLEN.ol, `/admin/bwa?${ym}`);
  ok('Rechte', 'BWA: Objektleitung 403', ob === 403, `OL ${ob}`);
  const oa = await g(ROLLEN.ol, `/cockpit/abrechnung?${ym}`), oe = await g(ROLLEN.ol, '/cockpit/me');
  ok('Rechte', 'Objektleitung: Abrechnung + Cockpit erlaubt', oa === 200 && oe === 200, `Abrechnung ${oa}, me ${oe}`);
  const ohne = await g(null, '/cockpit/me');
  ok('Rechte', 'ohne Anmeldung: Cockpit 401', ohne === 401, `${ohne}`);
  const ma = await g(qaMailToken, '/cockpit/me'), maH = await g(qaMailToken, '/cockpit/heute');
  ok('Rechte', 'Mitarbeiter-Konto: Cockpit gesperrt (403)', ma === 403 && maH === 403, `me ${ma}, heute ${maH}`);
}

// ================= Ablauf =================
const summeVorher = pruefsumme();
let qa;
try {
  if (NUR !== 'rundgang') {
    qa = anlegen();
    for (const rolle of ['admin', 'ol']) {
      try { await aktionen(rolle, qa); } catch (e) { ok('Aktionen', `${rolle}: Abbruch`, false, e.message.split('\n')[0].slice(0, 200)); }
      aufraeumen(); qa = anlegen();
    }
    await rechte(token(QA_MAIL));
  }
  if (NUR !== 'aktionen') {
    for (const rolle of ['admin', 'ol']) for (const geraet of ['desktop', 'ipad', 'handy']) for (const theme of ['light', 'dark']) {
      try { await rundgang(rolle, geraet, theme); } catch (e) { ok('Rundgang', `${rolle}/${geraet}/${theme}: Abbruch`, false, e.message.split('\n')[0].slice(0, 200)); }
    }
  }
} catch (e) {
  ok('Ablauf', 'Abbruch', false, e.message.split('\n')[0].slice(0, 300));
} finally {
  aufraeumen();
  await browser.close();
  const summeNachher = pruefsumme();
  const diff = Object.keys(summeVorher).filter((k) => summeVorher[k] !== summeNachher[k]);
  ok('Bestandsdaten', 'unverändert (Prüfsumme vorher = nachher)', diff.length === 0, diff.join(', '));
  ok('Testdaten', 'vollständig entfernt', sql(`SELECT count(*) FROM employees WHERE personal_nr = '${QA_NR}'`) === '0'
     && sql(`SELECT count(*) FROM objects WHERE name LIKE 'QA-TEST%'`) === '0');
  fs.writeFileSync(path.join(OUT, 'ergebnis.json'), JSON.stringify(ergebnis, null, 1));
  const xx = ergebnis.filter((e) => !e.ok);
  console.log(`=== ${ergebnis.length - xx.length}/${ergebnis.length} OK ===`);
  process.exit(xx.length ? 1 : 0);
}
