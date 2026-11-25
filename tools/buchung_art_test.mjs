// NUR DEV: Dialog "Buchung nachtragen/bearbeiten" mit Art (4 Werte), Satz (ueberschreibbar), Fahrt mit KM + Sondersatz im Stammblatt (Drazen 25.11.2026 12:20).
// Helena (33) an Lidl Neu Bie2 (20) am 22.11.2026 (dort auf DEV ohne Buchung/KM), raeumt selbst auf.
// Aufruf: CK_TOKEN=$(./venv/bin/python ../tools/dev_token.py <admin-mail>) node buchung_art_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de';
const EMP = 33, OBJ = 20, TAG = '2026-11-22';
fs.mkdirSync(OUT, { recursive: true });
const sql = (q) => execFileSync('sudo', ['-n', '-u', 'postgres', 'psql', '-d', 'dev_cockpit', '-X', '-tA', '-F', '|', '-c', q], { cwd: '/tmp' }).toString().trim();
if (sql(`SELECT count(*) FROM time_entries WHERE employee_id=${EMP} AND check_in::date='${TAG}'`) !== '0'
  || sql(`SELECT count(*) FROM km_daily_entries WHERE employee_id=${EMP} AND date='${TAG}'`) !== '0') { console.log('Testtag nicht frei - Abbruch'); process.exit(1); }
const BASIC = sql(`SELECT hourly_rate_basic FROM employees WHERE id=${EMP}`);
const START = Number(sql('SELECT coalesce(max(id),0) FROM time_entries')), START_A = Number(sql('SELECT coalesce(max(id),0) FROM audit_log'));
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
const jsFehler = [];
page.on('pageerror', (e) => jsFehler.push(e.message));
const feld = (label) => page.locator('[role=dialog] label.ck-field, .ck-dialog label.ck-field').filter({ hasText: label }).locator('input, select').first();
const satzText = async () => (await page.locator('[data-buchung-satz]').textContent().catch(() => '')) || '';
const warteSatz = (re) => page.waitForFunction((s) => new RegExp(s).test(document.querySelector('[data-buchung-satz]')?.textContent || ''), re.source, { timeout: 8000 }).then(() => true, () => false);
try {
  await page.goto(`${BASE}/login`);
  await page.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);
  await page.goto(`${BASE}/cockpit/zeiten`);
  console.log('Nachtragen');
  await page.getByRole('button', { name: /Buchung nachtragen/ }).click();
  await feld('Mitarbeiter').selectOption(String(EMP));
  await feld('Objekt').selectOption(String(OBJ));
  await feld('Datum').fill('2026-11-23');
  ok('Kommen/Gehen aus Dienstplan vorbelegt (12:55-16:25)', await page.waitForFunction(() => /Dienstplan/.test(document.querySelector('[data-buchung-zeitquelle]')?.textContent || ''), null, { timeout: 8000 }).then(() => true, () => false)
    && await feld('Kommen').inputValue() === '12:55' && await feld('Gehen').inputValue() === '16:25', `${await feld('Kommen').inputValue()}-${await feld('Gehen').inputValue()}`);
  await page.screenshot({ path: path.join(OUT, 'nachtragen_vorbelegt.png') });
  await feld('Datum').fill(TAG); await feld('Kommen').fill('09:00'); await feld('Gehen').fill('11:00');
  ok('eigene Zeit bleibt, Hinweis weg', await feld('Kommen').inputValue() === '09:00' && await page.locator('[data-buchung-zeitquelle]').count() === 0);
  ok('Art Standard Unterhaltsreinigung', await page.locator('[data-buchung-art]').inputValue() === 'Unterhaltsreinigung');
  const arten = await page.locator('[data-buchung-art] option').allTextContents();
  ok('Arten wie alte Ansicht', arten.join('|') === 'Unterhaltsreinigung|Grundreinigung|Sonderreinigung|Fensterreinigung', arten.join('|'));
  ok('Satz vorbelegt: 17,00 €/h · Lohnart 0001', await warteSatz(/17,00 €\/h.*Lohnart 0001/), await satzText());
  ok('kein Feld Taetigkeit', await page.locator('[data-buchung-taetigkeit]').count() === 0);
  await page.waitForFunction(() => document.querySelector('[data-buchung-fahrt]')?.checked, null, { timeout: 5000 }).catch(() => {});
  ok('Fahrt mit KM AN (Helena ist Fahrerin)', await page.locator('[data-buchung-fahrt]').isChecked());
  await page.locator('[data-buchung-art]').selectOption('Sonderreinigung');
  ok('Satz wechselt: 20,00 €/h · Lohnart 0030', await warteSatz(/20,00 €\/h.*Lohnart 0030/), await satzText());
  await page.locator('[data-buchung-satz-aendern]').click();
  ok('Link "ändern" oeffnet Eingabe mit 20,00', await page.locator('[data-buchung-satz-eingabe]').inputValue() === '20,00');
  await page.locator('[data-buchung-satz-eingabe]').fill('15,50');
  await page.screenshot({ path: path.join(OUT, 'nachtragen_sonder.png') });
  await page.getByRole('button', { name: /^Speichern$/ }).click();
  await page.waitForTimeout(1500);
  const id = sql(`SELECT max(id) FROM time_entries WHERE employee_id=${EMP} AND id>${START}`);
  const row = sql(`SELECT service_type, hourly_rate, is_manual_entry FROM time_entries WHERE id=${id || 0}`);
  ok('gespeichert: Sonderreinigung, eigener Satz 15,50', row === 'Sonderreinigung|15.50|t', row);
  ok('KM gebucht', sql(`SELECT count(*) FROM km_daily_entries WHERE time_entry_id=${id || 0}`) === '1');

  console.log('Ruzica (D0002) ohne KM');
  await page.getByRole('button', { name: /Buchung nachtragen/ }).click();
  await feld('Mitarbeiter').selectOption('4');
  await feld('Objekt').selectOption(String(OBJ));
  await page.waitForTimeout(1500);
  ok('Fahrt mit KM bei Ruzica aus', !(await page.locator('[data-buchung-fahrt]').isChecked()));
  await page.getByRole('button', { name: /^Abbrechen$/ }).click();

  console.log('Bearbeiten');
  await page.goto(`${BASE}/cockpit/zeiten?eintrag=${id}`);
  await page.waitForSelector('[data-buchung-art]');
  ok('zeigt bestehende Art', await page.locator('[data-buchung-art]').inputValue() === 'Sonderreinigung');
  ok('zeigt eigenen Satz 15,50', await warteSatz(/15,50 €\/h · eigener Satz.*Lohnart 0030/), await satzText());
  ok('zeigt Fahrt mit KM an', await page.locator('[data-buchung-fahrt]').isChecked());
  await page.screenshot({ path: path.join(OUT, 'bearbeiten_vorher.png') });
  await page.locator('[data-buchung-art]').selectOption('Grundreinigung');
  ok('Grundreinigung: 20,00 neu nach Art · 0030', await warteSatz(/20,00 €\/h · neu nach Art.*Lohnart 0030/), await satzText());
  await page.locator('[data-buchung-art]').selectOption('Unterhaltsreinigung');
  ok('Unterhalt: 17,00 neu nach Art · 0001', await warteSatz(/17,00 €\/h · neu nach Art.*Lohnart 0001/), await satzText());
  await page.locator('[data-buchung-fahrt]').uncheck();
  await page.getByRole('button', { name: /^Speichern$/ }).click();
  await page.waitForTimeout(1500);
  const row2 = sql(`SELECT service_type, hourly_rate FROM time_entries WHERE id=${id}`);
  ok('gespeichert: Unterhalt, 17,00', row2 === 'Unterhaltsreinigung|17.00', row2);
  ok('KM entfernt', sql(`SELECT count(*) FROM km_daily_entries WHERE time_entry_id=${id}`) === '0');
  ok('Protokoll: Buchung geaendert + KM aus', sql(`SELECT count(*) FROM audit_log WHERE id>${START_A} AND entity_id=${id} AND action IN ('booking_updated','km_entry_changed')`) === '2');

  console.log('Sondersatz beim Mitarbeiter');
  await page.goto(`${BASE}/cockpit/mitarbeiter/${EMP}`);
  await page.waitForSelector('[data-sondersatz]');
  ok('Stammblatt zeigt Sondersatz 20,00 €', /20,00 €/.test(await page.locator('[data-sondersatz]').textContent()), await page.locator('[data-sondersatz]').textContent());
  await page.locator('[data-sondersatz-aendern]').click();
  await page.locator('[data-sondersatz-eingabe]').fill('19,50');
  await page.locator('[data-sondersatz-speichern]').click();
  await page.waitForFunction(() => /19,50/.test(document.querySelector('[data-sondersatz]')?.textContent || ''), null, { timeout: 8000 }).catch(() => {});
  ok('Sondersatz 19,50 gespeichert und angezeigt', Number(sql(`SELECT hourly_rate_basic FROM employees WHERE id=${EMP}`) )  === 19.5 && /19,50/.test(await page.locator('[data-sondersatz]').textContent()));
  await page.screenshot({ path: path.join(OUT, 'stammblatt_sondersatz.png') });
  sql(`UPDATE employees SET hourly_rate_basic=${BASIC} WHERE id=${EMP}`);

  console.log('Handy');
  const h = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await h.goto(`${BASE}/login`);
  await h.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);
  await h.goto(`${BASE}/cockpit/zeiten?eintrag=${id}`);
  await h.waitForSelector('[data-buchung-art]');
  await h.locator('[data-buchung-art]').selectOption('Fensterreinigung');
  await h.locator('[data-buchung-satz-aendern]').click();
  await h.waitForSelector('[data-buchung-satz-eingabe]');
  const w = await h.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  ok('Dialog passt aufs Handy (kein Querscrollen)', w);
  await h.screenshot({ path: path.join(OUT, 'handy_dialog.png') });
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} catch (e) {
  ok('Ablauf', false, e.message.split('\n')[0]);
  await page.screenshot({ path: path.join(OUT, 'fehler.png') }).catch(() => {});
} finally {
  await browser.close();
  sql(`UPDATE employees SET hourly_rate_basic=${BASIC} WHERE id=${EMP}`);
  const ids = sql(`SELECT string_agg(id::text, ',') FROM time_entries WHERE employee_id=${EMP} AND id>${START}`);
  if (ids) {
    sql(`DELETE FROM km_daily_entries WHERE time_entry_id IN (${ids}) OR (employee_id=${EMP} AND date='${TAG}')`);
    sql(`DELETE FROM time_entries WHERE id IN (${ids})`);
  }
  sql(`DELETE FROM audit_log WHERE id>${START_A} AND employee_id=${EMP}`);
  console.log(`  aufgeraeumt: ${ids || '-'}`);
}
console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
