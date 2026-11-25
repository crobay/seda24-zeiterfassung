// NUR DEV: Zeitfeld-Schnelleingabe (Drazen 25.11.2026 15:44) in Buchung nachtragen/bearbeiten, Dienstplan, Vorlage.
// Speichert nichts (nur Dialoge oeffnen und abbrechen). Aufruf: CK_TOKEN=... node zeitfeld_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
import { execFileSync } from 'child_process';
const sql = (q) => execFileSync('sudo', ['-n', '-u', 'postgres', 'psql', '-d', 'dev_cockpit', '-X', '-tA', '-c', q], { cwd: '/tmp' }).toString().trim();
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de';
fs.mkdirSync(OUT, { recursive: true });
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const FAELLE = [['14', '14:00'], ['8', '08:00'], ['930', '09:30'], ['1430', '14:30'], ['14,5', '14:30'], ['14.5', '14:30'],
  ['14:3', '14:30'], ['14.30', '14:30'], ['0', '00:00'], ['2359', '23:59'], ['7,25', '07:25']];
const FALSCH = ['25', '1460', 'ab', '24:00', '9:75'];
const browser = await chromium.launch();
const jsFehler = [];
async function seite(mobil) {
  const ctx = await browser.newContext(mobil ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 1000 } });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => jsFehler.push(e.message));
  await p.goto(`${BASE}/login`);
  await p.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);
  return p;
}
const speichern = (p) => p.locator('.ck-dialog-foot .ck-btn-primary');
try {
  const page = await seite(false);
  await page.goto(`${BASE}/cockpit/zeiten`);
  await page.getByRole('button', { name: /Buchung nachtragen/ }).click();
  const k = page.locator('[data-zeit=kommen]'), g = page.locator('[data-zeit=gehen]');
  await k.waitFor();
  console.log('PC: Kommen mit Tastatur');
  for (const [ein, soll] of FAELLE) {
    await k.click(); await page.keyboard.type(ein); await page.keyboard.press('Tab');
    const fokusGehen = await g.evaluate((el) => el === document.activeElement);
    ok(`"${ein}" + Tab -> ${soll}`, await k.inputValue() === soll && fokusGehen, `${await k.inputValue()}${fokusGehen ? '' : ' (Tab nicht auf Gehen)'}`);
  }
  await k.click(); await page.keyboard.type('1430'); await page.keyboard.press('Enter');
  ok('"1430" + Enter -> 14:30', await k.inputValue() === '14:30');
  await g.click(); await page.keyboard.type('8'); await page.locator('[data-buchung-art]').click({ trial: true }); await page.locator('.ck-dialog .ck-card-head').click();
  ok('Gehen "8" + Feld verlassen (Klick) -> 08:00', await g.inputValue() === '08:00');
  ok('Dauer stimmt (14:30-08:00 = 17,50 h ueber Nacht)', /17,50/.test(await page.locator('.ck-dialog').textContent()));
  console.log('PC: Ungueltiges');
  await page.locator('[data-buchung-art]').waitFor();
  for (const x of FALSCH) {
    await k.click(); await page.keyboard.type(x); await page.keyboard.press('Tab');
    const rot = await k.evaluate((el) => el.classList.contains('ck-input-fehler') && el.getAttribute('aria-invalid') === 'true');
    ok(`"${x}" rot markiert, Speichern gesperrt`, rot && await speichern(page).isDisabled() && await page.locator('[data-zeit-fehler]').count() === 1);
  }
  await page.screenshot({ path: path.join(OUT, 'zeitfeld_fehler.png') });
  await k.click(); await page.keyboard.type('9'); await page.keyboard.press('Tab');
  ok('korrigiert: rot weg', await k.inputValue() === '09:00' && await page.locator('[data-zeit-fehler]').count() === 0);
  await page.getByRole('button', { name: /^Abbrechen$/ }).click();

  console.log('Bearbeiten (bestehende Buchung)');
  const eid = sql("SELECT id FROM time_entries WHERE check_out IS NOT NULL AND check_in >= date_trunc('month', now()) AND object_id NOT IN (998,999) ORDER BY id DESC LIMIT 1");
  await page.goto(`${BASE}/cockpit/zeiten?eintrag=${eid}`);
  await page.locator('[data-zeit=kommen]').waitFor({ timeout: 8000 }).catch(() => {});
  if (await page.locator('[data-zeit=kommen]').count()) {
    const v = await page.locator('[data-zeit=kommen]').inputValue();
    ok('zeigt gespeicherte Zeit HH:MM', /^\d{2}:\d{2}$/.test(v), v);
    await page.locator('[data-zeit=kommen]').click(); await page.keyboard.type('715'); await page.keyboard.press('Tab');
    ok('"715" -> 07:15', await page.locator('[data-zeit=kommen]').inputValue() === '07:15');
    await page.getByRole('button', { name: /^Abbrechen$/ }).click();
  } else ok('Bearbeiten-Dialog geoeffnet', false);

  console.log('Dienstplan + Vorlage');
  for (const [url, knopf] of [['dienstplan', /Schicht/], ['vorlage', /Eintrag|Schicht|Neu/]]) {
    await page.goto(`${BASE}/cockpit/${url}`);
    const b = page.locator('.ck-page-head button, .ck-btn-primary').filter({ hasText: knopf }).first();
    await b.click({ timeout: 8000 }).catch(() => {});
    const be = page.locator('[data-zeit=beginn]');
    if (!(await be.count())) { ok(`${url}: Dialog mit Zeitfeld`, false); continue; }
    await be.click(); await page.keyboard.type('6'); await page.keyboard.press('Tab');
    await page.keyboard.type('1015'); await page.keyboard.press('Tab');
    ok(`${url}: "6" Tab "1015" -> 06:00-10:15`, await be.inputValue() === '06:00' && await page.locator('[data-zeit=ende]').inputValue() === '10:15');
    await page.getByRole('button', { name: /^Abbrechen$/ }).click();
  }

  console.log('Handy');
  const h = await seite(true);
  await h.goto(`${BASE}/cockpit/zeiten`);
  await h.getByRole('button', { name: /nachtragen/ }).first().click();
  const hk = h.locator('[data-zeit=kommen]'), hg = h.locator('[data-zeit=gehen]');
  await hk.waitFor();
  ok('Handy: Zahlentastatur (inputmode decimal)', await hk.getAttribute('inputmode') === 'decimal');
  await hk.tap(); await h.keyboard.type('14,5'); await hg.tap(); await h.keyboard.type('1630'); await h.locator('.ck-dialog .ck-card-head').tap();
  ok('Handy: "14,5" / "1630" -> 14:30-16:30', await hk.inputValue() === '14:30' && await hg.inputValue() === '16:30', `${await hk.inputValue()}-${await hg.inputValue()}`);
  ok('Handy: Dauer 2,00 h', /Dauer 2,00/.test(await h.locator('.ck-dialog').textContent()));
  await hk.tap(); await h.keyboard.type('25'); await h.locator('.ck-dialog .ck-card-head').tap();
  ok('Handy: "25" rot', await hk.evaluate((el) => el.classList.contains('ck-input-fehler')));
  ok('Handy: kein Querscrollen', await h.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await h.screenshot({ path: path.join(OUT, 'zeitfeld_handy.png') });
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 2).join(' | '));
} catch (e) {
  ok('Ablauf', false, e.message.split('\n')[0]);
} finally {
  await browser.close();
}
console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
process.exit(fehler ? 1 : 0);
