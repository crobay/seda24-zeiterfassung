// Echter Browser-Test Offline-Stempeln (Chromium, iPhone-15-Groesse) - wird von deploy.sh aufgerufen.
// Ablauf mit Test-Mitarbeiter T9999 gegen die echte Seite:
//   online laden + einloggen -> offline -> neu laden: App startet aus dem Service Worker und bleibt eingeloggt
//   -> KOMMEN offline -> Warteschlange = 1 -> online -> in 30 s in der DB -> GEHEN genauso -> Testeintraege loeschen
// Aufruf: node offline_test.mjs [--base https://app.seda.de] [--expect-cache seda24-cache-v123]
// Exit-Code 0 = bestanden, sonst Fehler.
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
const EXPECT_CACHE = arg('--expect-cache', '');
const SYNC_LIMIT_MS = 30000;

// Zugangsdaten T9999 aus t9999.env (nicht im Git)
const env = Object.fromEntries(fs.readFileSync(path.join(HERE, 't9999.env'), 'utf8')
  .split('\n').filter((l) => l.includes('=')).map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim()]));

const db = (...a) => JSON.parse(execFileSync(PY, [HELPER, ...a], { env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }).toString());
let pass = 0, fail = 0;
const ok = (name, cond, info = '') => { cond ? pass++ : fail++; console.log(`  [${cond ? 'OK ' : 'FEHLER'}] ${name}${info ? ' - ' + info : ''}`); return cond; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t = () => new Date().toLocaleTimeString('de-DE');

const pendingQueue = (page) => page.evaluate(() => {
  try { return JSON.parse(localStorage.getItem('bie2_offline_queue') || '[]').filter((i) => i.status === 'pending' || i.status === 'failed'); }
  catch (e) { return []; }
});

// Warten, bis der Eintrag mit dieser client_id in der DB steht (cond prueft Kommen oder Gehen)
async function waitForDb(clientId, cond) {
  const t0 = Date.now();
  while (Date.now() - t0 < SYNC_LIMIT_MS) {
    const e = db('entry', clientId);
    if (e && cond(e)) return { entry: e, ms: Date.now() - t0 };
    await sleep(500);
  }
  return { entry: null, ms: Date.now() - t0 };
}

async function stampOffline(context, page, label, action) {
  await context.setOffline(true);
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.waitForFunction((a) => {
    try { return JSON.parse(localStorage.getItem('bie2_offline_queue') || '[]').some((i) => i.action === a && i.status === 'pending'); }
    catch (e) { return false; }
  }, action, { timeout: 10000 });
  const q = await pendingQueue(page);
  ok(`${label} offline: Warteschlange = 1`, q.length === 1, `${q.length} ausstehend (${q.map((i) => i.action).join(', ')})`);
  const badge = await page.getByText('1 ausstehend').isVisible().catch(() => false);
  ok(`${label} offline: Anzeige "1 ausstehend"`, badge);
  return q.find((i) => i.action === action);
}

const start = db('precheck');
console.log(`Offline-Browser-Test ${t()} gegen ${BASE} (T9999 = Mitarbeiter ${start.employee_id})`);
if (!ok('T9999 ist nicht eingestempelt', start.open_entries.length === 0, `offen: ${start.open_entries.join(', ') || 'keine'}`)) process.exit(1);

const { defaultBrowserType, ...iphone } = devices['iPhone 15'];
const browser = await chromium.launch();
const times = {};
try {
  const context = await browser.newContext({ ...iphone, locale: 'de-DE', timezoneId: 'Europe/Berlin', serviceWorkers: 'allow' });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);

  // 1) Online laden, Service Worker installiert sich und uebernimmt die Seite
  await page.goto(BASE + '/login');
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => navigator.serviceWorker.ready.then((r) => r.active && r.active.state === 'activated'));
  if (!(await page.evaluate(() => !!navigator.serviceWorker.controller))) await page.reload();
  ok('Service Worker aktiv und steuert die Seite', await page.evaluate(() => !!navigator.serviceWorker.controller));
  const keys = await page.evaluate(() => caches.keys());
  if (EXPECT_CACHE) ok('Cache dieses Deploys vorhanden', keys.includes(EXPECT_CACHE), keys.join(', '));

  // 2) Einloggen (Eingeloggt bleiben ist angehakt)
  await page.fill('input[name=email]', env.T9999_EMAIL);
  await page.fill('input[name=password]', env.T9999_PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('**/dashboard');
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).waitFor();
  const opt = page.locator('select').filter({ hasText: 'TEST BrowserStack' }).first();
  if (await opt.count()) await opt.selectOption({ label: 'TEST BrowserStack' });
  ok('online eingeloggt, Stempeluhr da', true);

  // 3) Offline + neu laden: App kommt aus dem Service Worker und bleibt eingeloggt
  await context.setOffline(true);
  const sw = context.serviceWorkers()[0];
  const swNet = sw ? await sw.evaluate(() => fetch('/manifest.json?probe=' + Date.now(), { cache: 'no-store' }).then(() => 'erreichbar', () => 'gesperrt')) : 'kein SW';
  ok('Netz im Service Worker wirklich weg', swNet === 'gesperrt', swNet);
  const r0 = Date.now();
  const resp = await page.reload({ waitUntil: 'domcontentloaded' });
  times.page = Date.now() - r0;
  ok('Seite offline aus dem Service Worker geladen', resp && resp.fromServiceWorker(), `${times.page} ms`);
  await page.getByRole('button', { name: 'KOMMEN', exact: true }).waitFor();
  times.offlineStart = Date.now() - r0;
  ok('App startet offline und bleibt eingeloggt', page.url().includes('/dashboard'), `Stempeluhr nach ${(times.offlineStart / 1000).toFixed(1)} s, ${new URL(page.url()).pathname}`);

  // 4) KOMMEN offline -> online -> in 30 s in der DB
  const kommen = await stampOffline(context, page, 'KOMMEN', 'check_in');
  await context.setOffline(false);
  const k = await waitForDb(kommen.id, (e) => e.check_in);
  times.kommen = k.ms;
  ok('KOMMEN nach Wiederverbinden in der DB', k.entry, k.entry ? `${(k.ms / 1000).toFixed(1)} s, Eintrag ${k.entry.id}, Kommen ${k.entry.check_in}` : 'nicht in 30 s');
  await page.waitForFunction(() => {
    try { return !JSON.parse(localStorage.getItem('bie2_offline_queue') || '[]').some((i) => i.status === 'pending' || i.status === 'failed'); }
    catch (e) { return false; }
  }, null, { timeout: 10000 }).catch(() => {});
  ok('Warteschlange danach leer', (await pendingQueue(page)).length === 0);

  // 5) GEHEN genauso
  if (k.entry) {
    await page.getByRole('button', { name: 'GEHEN', exact: true }).waitFor();
    const gehen = await stampOffline(context, page, 'GEHEN', 'check_out');
    await context.setOffline(false);
    const g = await waitForDb(kommen.id, (e) => e.check_out);
    times.gehen = g.ms;
    ok('GEHEN nach Wiederverbinden in der DB', g.entry && gehen, g.entry ? `${(g.ms / 1000).toFixed(1)} s, Gehen ${g.entry.check_out}` : 'nicht in 30 s');
    const synced = await page.getByText('Alle Stempel synchronisiert').waitFor({ timeout: 10000 }).then(() => true, () => false);
    ok('Anzeige "Alle Stempel synchronisiert"', synced);
  }
  await context.close();
} catch (e) {
  ok('Testablauf', false, String(e.message || e).split('\n')[0]);
} finally {
  await browser.close();
  // 6) Testeintraege wieder loeschen
  try {
    const c = db('cleanup', String(start.max_te_id), 'Deploy-Offline-Test');
    ok('Testeintraege geloescht', true, c.deleted.length ? `Zeiteintraege ${c.deleted.join(', ')}, KM ${c.counts.km_daily_entries || 0}` : 'keine angelegt');
    ok('T9999 danach nicht eingestempelt', db('precheck').open_entries.length === 0);
  } catch (e) {
    ok('Testeintraege geloescht', false, String(e.message || e).split('\n')[0]);
  }
}

console.log(`=== Offline-Browser-Test: ${pass}/${pass + fail} OK (Offline-Start ${((times.offlineStart || 0) / 1000).toFixed(1)} s, `
  + `KOMMEN ${times.kommen != null ? (times.kommen / 1000).toFixed(1) + ' s' : '-'}, GEHEN ${times.gehen != null ? (times.gehen / 1000).toFixed(1) + ' s' : '-'}) ===`);
process.exit(fail ? 1 : 0);
