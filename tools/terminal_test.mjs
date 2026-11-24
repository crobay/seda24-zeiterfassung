// NUR DEV: Terminal-Modus (Drazen 24.11.2026) im Browser - Android-Tablet quer, Test-Objekt 25 (TEST BrowserStack), T9999.
// Ablauf: Einrichtung (Login gemockt mit echtem DEV-Admin-Token) -> Start -> Andere MA -> PIN falsch/richtig -> KOMMEN ✓
// -> nach 5 s Start, Kachel "da seit" -> GEHEN ✓ -> DB: quelle='terminal', Server-Zeit, kein client_id.
// Kein WLAN (offline + Captive Portal) -> roter Hinweis, nichts gebucht. Cockpit-Seite Terminal (PIN, Widerrufen).
// Am Ende werden Testbuchungen, Test-Terminals und die T9999-PIN in dev_cockpit geloescht.
// Aufruf: CK_TOKEN=$(./venv/bin/python ../tools/dev_token.py <admin-mail>) node terminal_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de';
const API = `${BASE}/api/v1`;
fs.mkdirSync(OUT, { recursive: true });

const sql = (q) => execFileSync('sudo', ['-n', '-u', 'postgres', 'psql', '-d', 'dev_cockpit', '-X', '-tA', '-F', '|', '-c', q], { cwd: '/tmp' }).toString().trim();
const EMP = sql("SELECT id FROM employees WHERE personal_nr = 'T9999'");
const START_ID = Number(sql('SELECT coalesce(max(id),0) FROM time_entries'));
const START_G = Number(sql('SELECT coalesce(max(id),0) FROM terminal_geraete'));
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
const api = async (m, p, body) => (await fetch(`${API}${p}`, { method: m, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` }, body: body ? JSON.stringify(body) : undefined })).json();
const PIN = String(2000 + Math.floor(Math.random() * 7000)).replace(/^(\d)\1{3}$/, '2468');

if (sql(`SELECT count(*) FROM time_entries WHERE employee_id = ${EMP} AND check_out IS NULL`) !== '0') { console.log('T9999 ist eingestempelt - Abbruch'); process.exit(1); }
await api('PUT', `/cockpit/terminal/pins/${EMP}`, { pin: PIN });

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.5, hasTouch: true, isMobile: true,
  userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-X210) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  serviceWorkers: 'block',
});
const page = await ctx.newPage();
const jsFehler = [];
page.on('pageerror', (e) => jsFehler.push(e.message));
page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource|ERR_INTERNET_DISCONNECTED|net::/.test(m.text())) jsFehler.push(m.text()); });
const shot = (n) => page.screenshot({ path: path.join(OUT, `${n}.png`) });
const tippePin = async (pin) => { for (const z of pin) await page.click(`[data-term-taste="${z}"]`); };

try {
  console.log('Einrichtung');
  await page.route('**/api/v1/auth/login', (r) => r.fulfill({ status: 200, contentType: 'application/json',
    headers: { 'X-Seda24': '1' }, body: JSON.stringify({ access_token: TOKEN, token_type: 'bearer', role: 'admin', must_change_password: false }) }));
  await page.goto(`${BASE}/terminal`);
  await page.waitForSelector('[data-term-einrichtung]');
  ok('ohne Geraete-Token: Einrichtung', true);
  ok('Terminal-Manifest', await page.evaluate(() => document.querySelector('link[rel=manifest]').getAttribute('href')) === '/terminal-manifest.json');
  await shot('01_einrichtung');
  await page.fill('[data-term-email]', 'admin@test'); await page.fill('[data-term-passwort]', 'x');
  await page.click('[data-term-anmelden]');
  await page.waitForSelector('[data-term-objektwahl]');
  await page.selectOption('[data-term-objektwahl]', '25');
  await page.fill('[data-term-geraetename]', 'Browsertest Tablet');
  await page.click('[data-term-registrieren]');
  await page.waitForSelector('[data-term-andere]');
  await page.unroute('**/api/v1/auth/login');
  const kopf = await page.waitForFunction(() => document.querySelector('[data-term-objekt]')?.textContent.includes('TEST BrowserStack'), null, { timeout: 8000 }).then(() => true, () => false);
  ok('registriert, Startbildschirm', kopf);
  ok('Login-Token NICHT gespeichert', await page.evaluate(() => !localStorage.getItem('token') && !!localStorage.getItem('terminal_token')));
  ok('Server-Uhr sichtbar', /\d\d:\d\d/.test(await page.textContent('[data-term-uhr]')));
  await shot('02_start');

  console.log('Kommen');
  await page.click('[data-term-andere]');
  await page.fill('[data-term-suche]', 'Test iPh');
  await page.waitForSelector('[data-term-kachel="Test iPhone"]');
  await shot('03_suche');
  await page.click('[data-term-kachel="Test iPhone"]');
  await page.waitForSelector('[data-term-pin-name]');
  await tippePin(PIN === '9753' ? '9751' : '9753');
  await page.waitForSelector('[data-term-fehler]');
  ok('falsche PIN abgelehnt', (await page.textContent('[data-term-fehler]')).includes('PIN falsch'));
  ok('PIN-Punkte wieder leer', (await page.getAttribute('[data-term-pin-punkte]', 'data-term-pin-punkte')) === '0');
  await shot('04_pin_falsch');
  await tippePin(PIN);
  await page.waitForSelector('[data-term-knopf="kommen"]');
  await shot('05_kommen_knopf');
  const vorher = new Date();
  await page.click('[data-term-knopf="kommen"]');
  await page.waitForSelector('[data-term-fertig="kommen"]');
  await shot('06_kommen_ok');
  let e = sql(`SELECT id, quelle, coalesce(client_id,''), extract(epoch FROM check_in)::bigint, object_id FROM time_entries WHERE employee_id = ${EMP} AND id > ${START_ID} ORDER BY id`).split('\n');
  ok('genau 1 Buchung', e.length === 1 && e[0] !== '', e.join(' ; '));
  const [eid, quelle, cid, ts, obj] = e[0].split('|');
  ok("quelle='terminal', Objekt 25, kein client_id", quelle === 'terminal' && obj === '25' && cid === '');
  ok('Server-Uhrzeit (±5 s)', Math.abs(Number(ts) - vorher.getTime() / 1000) < 5 || Math.abs(Number(ts) - (vorher.getTime() / 1000 + 3600)) < 5, ts);
  const t0 = Date.now();
  await page.waitForSelector('[data-term-andere]', { timeout: 8000 });
  ok('nach ~5 s zurueck zum Start', Date.now() - t0 > 3500, `${Date.now() - t0} ms`);

  console.log('Gehen');
  await page.click('[data-term-andere]');
  await page.fill('[data-term-suche]', 'Test iPh');
  await page.waitForSelector('[data-term-kachel="Test iPhone"]');
  ok('Kachel zeigt "da seit"', (await page.textContent('[data-term-kachel="Test iPhone"]')).includes('da seit'));
  await page.click('[data-term-kachel="Test iPhone"]');
  await tippePin(PIN);
  await page.waitForSelector('[data-term-knopf="gehen"]');
  ok('Knopf jetzt GEHEN', (await page.textContent('[data-term-status]')).includes('Eingestempelt seit'));
  await shot('07_gehen_knopf');
  await page.click('[data-term-knopf="gehen"]');
  await page.waitForSelector('[data-term-fertig="gehen"]');
  await shot('08_gehen_ok');
  ok('Buchung geschlossen', sql(`SELECT check_out IS NOT NULL FROM time_entries WHERE id = ${eid}`) === 't');
  await page.click('[data-term-fertig]');   // Tippen = sofort zurueck
  await page.waitForSelector('[data-term-andere]');

  console.log('Kein WLAN');
  await ctx.setOffline(true);
  await page.waitForSelector('[data-term-offline]', { timeout: 20000 });
  ok('roter Hinweis', (await page.textContent('[data-term-offline]')).includes('Kein WLAN – bitte mit Lidl-WLAN verbinden'));
  ok('Knopf WLAN-Anmeldung', await page.isVisible('[data-term-portal]'));
  await shot('09_kein_wlan');
  // Captive Portal: Netz da, aber Anmeldeseite statt unserem Server
  await page.route('**/api/v1/**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: '<html><body>Lidl WLAN Login</body></html>' }));
  await ctx.setOffline(false);
  await page.waitForTimeout(2500);
  ok('Captive Portal: Hinweis bleibt', await page.isVisible('[data-term-offline]'));
  await page.unroute('**/api/v1/**');
  await page.waitForSelector('[data-term-offline]', { state: 'detached', timeout: 20000 });
  ok('Netz zurueck: Hinweis weg', true);

  console.log('Netz weg beim Stempeln');
  await page.click('[data-term-andere]');
  await page.fill('[data-term-suche]', 'Test iPh');
  await page.click('[data-term-kachel="Test iPhone"]');
  await tippePin(PIN);
  await page.waitForSelector('[data-term-knopf="kommen"]');
  await page.route('**/api/v1/terminal/stempeln', (r) => r.abort('internetdisconnected'));
  await page.click('[data-term-knopf="kommen"]');
  await page.waitForSelector('[data-term-offline]');
  ok('nicht gebucht, roter Hinweis', sql(`SELECT count(*) FROM time_entries WHERE employee_id = ${EMP} AND id > ${eid}`) === '0');
  await page.unroute('**/api/v1/terminal/stempeln');
  ok('keine Warteschlange', await page.evaluate(() => !Object.keys(localStorage).some((k) => /queue|warteschlange/i.test(k) && localStorage.getItem(k) && localStorage.getItem(k) !== '[]')));
  await page.waitForSelector('[data-term-offline]', { state: 'detached', timeout: 20000 });

  console.log('Cockpit');
  const ck = await ctx.newPage();
  ck.on('pageerror', (x) => jsFehler.push(x.message));
  await ck.goto(`${BASE}/login`);
  await ck.evaluate((tk) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); }, TOKEN);
  await ck.setViewportSize({ width: 1400, height: 900 });
  await ck.goto(`${BASE}/cockpit/terminal`);
  await ck.waitForSelector('[data-term-cockpit]');
  const gid = sql(`SELECT max(id) FROM terminal_geraete WHERE name = 'Browsertest Tablet'`);
  ok('Geraet gelistet', await ck.isVisible(`[data-term-geraet="${gid}"]`));
  ok('T9999 mit PIN', (await ck.textContent('[data-term-ma="Test iPhone"]')).includes('gesetzt'));
  ok('Menue-Eintrag Terminal', await ck.isVisible('.ck-nav-item:has-text("Terminal")'));
  await ck.click('[data-term-pin-setzen="Test iPhone"]');
  await ck.fill('[data-term-pin-eingabe]', '1234');
  await ck.click('[data-term-pin-speichern]');
  await ck.waitForTimeout(800);
  ok('PIN 1234 abgelehnt', !(await ck.isVisible('[data-term-pin-neu]')));
  await ck.click('[data-term-zufall]');
  await ck.waitForSelector('[data-term-pin-neu]');
  ok('Zufalls-PIN angezeigt (4 Ziffern)', /lautet:\s*\d{4}/.test(await ck.textContent('[data-term-pin-neu]')));
  await ck.screenshot({ path: path.join(OUT, '10_cockpit_pin.png') });
  await ck.keyboard.press('Escape');
  ck.on('dialog', (d) => d.accept());
  await ck.click(`[data-term-widerrufen="${gid}"]`);
  await ck.waitForTimeout(1000);
  ok('widerrufen', sql(`SELECT widerrufen_am IS NOT NULL FROM terminal_geraete WHERE id = ${gid}`) === 't');
  await ck.screenshot({ path: path.join(OUT, '11_cockpit.png'), fullPage: true });

  console.log('Widerrufenes Tablet');
  await page.reload();
  await page.waitForSelector('[data-term-einrichtung]', { timeout: 10000 });
  ok('Tablet zurueck auf Einrichtung mit Hinweis', (await page.textContent('[data-term-einrichtung]')).includes('abgemeldet'));
  await shot('12_widerrufen');
  ok('keine JS-Fehler', jsFehler.length === 0, jsFehler.slice(0, 3).join(' | '));
} catch (x) {
  ok('Ablauf', false, x.message.split('\n')[0]);
  await shot('99_fehler').catch(() => {});
} finally {
  await browser.close();
  sql(`DELETE FROM audit_log WHERE action LIKE 'terminal_%' AND ((entity_type = 'time_entry' AND entity_id > ${START_ID})
       OR (entity_type = 'terminal_geraet' AND entity_id > ${START_G}) OR (entity_type = 'terminal_pin' AND entity_id = ${EMP}))`);
  sql(`DELETE FROM time_entries WHERE employee_id = ${EMP} AND id > ${START_ID}`);
  sql(`DELETE FROM terminal_geraete WHERE id > ${START_G}`);
  sql(`DELETE FROM terminal_pin WHERE employee_id = ${EMP}`);
  console.log(fehler ? `FEHLER: ${fehler}` : 'ALLES OK');
  process.exit(fehler ? 1 : 0);
}
