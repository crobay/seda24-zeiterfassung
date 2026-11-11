// Echte App-Screenshots fuer die Hilfeseiten "iPhone/Android - so geht's" (Chromium, Handy-Groesse wie als
// installierte App ohne Browserleisten). Eingeloggt als T9999, Objekt TEST BrowserStack.
// Testbuchungen werden am Ende wieder geloescht.
// Aufruf: node screenshots.mjs [--device iphone|android] [--base https://app.seda.de] [--out <ordner>]
//   iphone  = iPhone 15 (393x852), android = Pixel 7 (412x915), jeweils volle Hoehe ohne Browserleisten
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const PY = path.join(ROOT, 'backend/venv/bin/python');
const HELPER = path.join(ROOT, 'backend/scripts/browsertest_db.py');
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(HERE, 'ms-playwright');
const { chromium, devices } = await import('playwright');

const arg = (name, def) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : def; };
const BASE = arg('--base', 'https://app.seda.de');
const DEVICE = arg('--device', 'iphone');
const PROFILES = {
  iphone: { descriptor: 'iPhone 15', viewport: { width: 393, height: 852 } },
  android: { descriptor: 'Pixel 7', viewport: { width: 412, height: 915 } },
};
if (!PROFILES[DEVICE]) throw new Error('--device iphone oder android');
const OUT = arg('--out', path.join(ROOT, `frontend/public/hilfe/${DEVICE}/img`));
const env = Object.fromEntries(fs.readFileSync(path.join(HERE, 't9999.env'), 'utf8')
  .split('\n').filter((l) => l.includes('=')).map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));
const db = (...a) => JSON.parse(execFileSync(PY, [HELPER, ...a], { env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }).toString());

fs.mkdirSync(OUT, { recursive: true });
const start = db('precheck');
if (start.open_entries.length) throw new Error('T9999 ist eingestempelt - erst ausstempeln');

const { defaultBrowserType, ...device } = devices[PROFILES[DEVICE].descriptor];
const browser = await chromium.launch();
const context = await browser.newContext({
  ...device, viewport: PROFILES[DEVICE].viewport, deviceScaleFactor: 2,
  locale: 'de-DE', timezoneId: 'Europe/Berlin', serviceWorkers: 'allow',
});
const page = await context.newPage();
page.setDefaultTimeout(20000);
const shots = [];

// Markierung (Kreis/Rahmen + Beschriftung) um ein Element legen
async function mark(locator, { color = '#dc2626', label = '', pad = 8, labelPos = 'below' } = {}) {
  const box = await locator.boundingBox();
  await page.evaluate(({ box, color, label, pad, labelPos }) => {
    const sx = window.scrollX, sy = window.scrollY;
    const ring = document.createElement('div');
    ring.className = 'hilfe-mark';
    Object.assign(ring.style, {
      position: 'absolute', zIndex: 99999, pointerEvents: 'none',
      left: `${box.x + sx - pad}px`, top: `${box.y + sy - pad}px`,
      width: `${box.width + 2 * pad}px`, height: `${box.height + 2 * pad}px`,
      border: `4px solid ${color}`, borderRadius: box.height > 70 ? '18px' : '999px', boxShadow: '0 0 0 3px rgba(255,255,255,0.85)',
    });
    document.body.appendChild(ring);
    if (label) {
      const l = document.createElement('div');
      l.className = 'hilfe-mark';
      l.textContent = label;
      Object.assign(l.style, {
        position: 'absolute', zIndex: 99999, pointerEvents: 'none', background: color, color: 'white',
        font: 'bold 16px -apple-system, sans-serif', padding: '6px 12px', borderRadius: '10px', whiteSpace: 'nowrap',
        top: labelPos === 'below' ? `${box.y + sy + box.height + pad + 10}px` : `${box.y + sy - pad - 44}px`,
      });
      document.body.appendChild(l);
      const left = Math.min(Math.max(8, box.x + sx + box.width / 2 - l.offsetWidth / 2), document.documentElement.clientWidth - l.offsetWidth - 8);
      l.style.left = `${left}px`;
    }
  }, { box, color, label, pad, labelPos });
}
const unmark = () => page.evaluate(() => document.querySelectorAll('.hilfe-mark').forEach((e) => e.remove()));
async function shot(name, what) {
  await page.waitForTimeout(400);
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, type: 'jpeg', quality: 82 });
  shots.push(`${name} - ${what}`);
  await unmark();
}
const stempeluhr = () => page.getByText('Stempeluhr', { exact: true });
const center = (loc) => loc.evaluate((e) => e.scrollIntoView({ block: 'center' }));

try {
  // Login-Maske
  await page.goto(BASE + '/login');
  await page.evaluate(() => navigator.serviceWorker.ready);
  await mark(page.getByText('Eingeloggt bleiben (30 Tage)').locator('xpath=..'), { color: '#16a34a', pad: 6 });
  await shot('01-login.jpg', 'Login-Maske, "Eingeloggt bleiben" gruen markiert');

  await page.fill('input[name=email]', env.T9999_EMAIL);
  await page.fill('input[name=password]', env.T9999_PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('**/dashboard');
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).waitFor();
  const sel = page.locator('select').filter({ hasText: 'TEST BrowserStack' }).first();
  if (await sel.count()) await sel.selectOption({ label: 'TEST BrowserStack' });
  await page.waitForTimeout(1500);

  // Stempeluhr online mit WLAN-Zeichen
  await center(page.getByRole('button', { name: 'KOMMEN', exact: true }));
  const wifi = stempeluhr().locator('xpath=../div[2]');
  await mark(wifi, { color: '#16a34a', label: 'WLAN-Zeichen = übertragen', pad: 6 });
  await shot('02-stempeluhr-online.jpg', 'Stempeluhr online, WLAN-Zeichen markiert');

  // Nach KOMMEN (online)
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).click();
  await page.getByRole('button', { name: 'GEHEN', exact: true }).waitFor();
  await page.waitForTimeout(1200);
  await center(page.getByRole('button', { name: 'GEHEN', exact: true }));
  await shot('03-nach-kommen.jpg', 'nach KOMMEN: Arbeitszeit laeuft, GEHEN-Knopf');
  await page.getByRole('button', { name: 'GEHEN', exact: true }).click();
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).waitFor();
  await page.waitForTimeout(1000);

  // Offline: KOMMEN -> "1 ausstehend"
  await context.setOffline(true);
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).click();
  await page.getByText('1 ausstehend').waitFor();
  await center(stempeluhr());
  await page.evaluate(() => window.scrollBy(0, 150));
  await mark(page.getByText('1 ausstehend'), { color: '#2563eb', label: 'auf dem Handy gespeichert', pad: 6 });
  await shot('04-offline-ausstehend.jpg', 'offline gestempelt: "Offline" und "1 ausstehend"');

  // Offline: GEHEN -> "Noch nicht uebertragen"
  await page.getByRole('button', { name: 'GEHEN', exact: true }).click();
  const pendingBox = page.getByText(/Noch nicht (ue|ü)bertragen/);
  await pendingBox.waitFor();
  await center(pendingBox);
  await mark(pendingBox.locator('xpath=..'), { color: '#2563eb', pad: 4 });
  await shot('05-noch-nicht-uebertragen.jpg', 'offline gestempelt: "Noch nicht uebertragen"');

  // Wieder online -> "Alle Stempel synchronisiert"
  await context.setOffline(false);
  const synced = page.getByText('Alle Stempel synchronisiert');
  await synced.waitFor({ timeout: 30000 });
  await center(synced);
  await mark(synced, { color: '#16a34a', pad: 6 });
  await shot('06-synchronisiert.jpg', 'nach Wiederverbinden: "Alle Stempel synchronisiert!"');

  // Logout-Knopf als Warnung
  await page.evaluate(() => window.scrollTo(0, 0));
  const logout = page.locator('button:visible', { hasText: 'Logout' }).first();
  await mark(logout, { color: '#dc2626', label: 'NIE drücken!', pad: 8 });
  await shot('07-logout-warnung.jpg', 'Logout-Knopf rot eingekreist: NIE druecken');
} finally {
  await browser.close();
  const c = db('cleanup', String(start.max_te_id), `Screenshots Hilfeseite ${DEVICE}`);
  console.log('Testbuchungen geloescht:', JSON.stringify(c));
}
console.log(shots.join('\n'));
