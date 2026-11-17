// NUR DEV: Objekt-Logo + farbiges Kuerzel. Cockpit (Admin, Desktop): Hinweistext, Logo-Upload PNG/SVG (im Browser
// verkleinert), Kuerzel/Farbe, Anzeige in Objekt-Detail/-Liste, Leitstelle, Dienstplan, Vorlage, Zeiten, Strg+K.
// Stempeluhr (T9999, iPhone 15): Kuerzel bzw. Logo gross im Kopf, auch im Gast-WLAN ohne Netz (Objekt-Cache).
// Am Ende: Marke von TEST BrowserStack (Objekt 25) wieder geloescht (vorher gab es keine).
// Aufruf: CK_TOKEN=<admin> MA_TOKEN=<t9999> MA_EMAIL=<t9999> node objekt_marke_test.mjs <ordner>
import path from 'path';
import fs from 'fs';
import zlib from 'zlib';
import { execFileSync } from 'child_process';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2);
const { CK_TOKEN, MA_TOKEN, MA_EMAIL } = process.env;
const BASE = 'https://dev.seda.de';
const OBJ = 25;
const sql = (q) => execFileSync('psql', ['-h', 'localhost', '-U', 'seda24_user', 'dev_cockpit', '-X', '-tA', '-F', '|', '-c', q],
  { env: { ...process.env, PGPASSWORD: 'SedaDev2025' } }).toString().trim();
let fehler = 0;
const ok = (name, cond, info = '') => { console.log(`  [${cond ? 'OK ' : 'XX '}] ${name}${info ? ' - ' + info : ''}`); if (!cond) fehler++; return cond; };
if (sql(`SELECT count(*) FROM objekt_marken WHERE object_id = ${OBJ}`) !== '0') { console.log('Objekt 25 hat schon eine Marke - Abbruch'); process.exit(1); }

// Neutrales Test-Logo (kein Fremdlogo): 400x240 PNG, Navy mit goldenem Balken; dazu ein SVG
function png(w, h) {
  const crc = (b) => { let c, t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    let x = 0xffffffff; for (const v of b) x = t[(x ^ v) & 0xff] ^ (x >>> 8); return (x ^ 0xffffffff) >>> 0; };
  const chunk = (typ, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(typ), d]);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const zeilen = [];
  for (let y = 0; y < h; y++) { const z = [0]; for (let x = 0; x < w; x++) { const gold = y > h * 0.62 && y < h * 0.78 && x > w * 0.15 && x < w * 0.85; z.push(...(gold ? [0xf9, 0xb2, 0x33] : [0x1e, 0x53, 0x7c])); } zeilen.push(Buffer.from(z)); }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(zeilen))), chunk('IEND', Buffer.alloc(0))]);
}
const PNG_DATEI = path.join(OUT, 'testlogo.png'); fs.writeFileSync(PNG_DATEI, png(400, 240));
const SVG_DATEI = path.join(OUT, 'testlogo.svg');
fs.writeFileSync(SVG_DATEI, '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"><circle cx="150" cy="150" r="140" fill="#009E73"/><text x="150" y="185" font-size="110" text-anchor="middle" fill="#fff" font-family="sans-serif">TB</text></svg>');
const logoGroesse = () => { const b64 = sql(`SELECT substr(logo, 23) FROM objekt_marken WHERE object_id = ${OBJ}`);
  if (!b64) return null; const b = Buffer.from(b64, 'base64'); return b.slice(1, 4).toString() === 'PNG' ? [b.readUInt32BE(16), b.readUInt32BE(20)] : 'kein PNG'; };

const browser = await chromium.launch();
async function seite(prof, token, rolle, pfad) {
  const ctx = await browser.newContext({ ...prof, locale: 'de-DE', timezoneId: 'Europe/Berlin', serviceWorkers: 'block' });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => ok('kein JS-Fehler', false, e.message));
  await page.goto(BASE + '/login');
  await page.evaluate(([tk, r, em]) => { localStorage.clear(); localStorage.setItem('token', tk); localStorage.setItem('userRole', r);
    if (em) localStorage.setItem('userEmail', em); localStorage.setItem('ck_theme_v2', 'light'); }, [token, rolle, MA_EMAIL]);
  await page.goto(BASE + pfad); await page.waitForLoadState('networkidle'); await page.waitForTimeout(700);
  return { ctx, page };
}
const shot = (page, n, opt = {}) => page.screenshot({ path: path.join(OUT, `17_${n}.png`), ...opt });
const desk = { viewport: { width: 1440, height: 900 } };
const { defaultBrowserType: _d, ...iphone } = devices['iPhone 15'];

try {
  // ---------- Stempeluhr zuerst ohne Logo: automatisches Kuerzel ----------
  console.log('Stempeluhr (T9999, iPhone): Kuerzel');
  let { ctx, page } = await seite(iphone, MA_TOKEN, 'mitarbeiter', '/dashboard');
  await page.locator('[data-ek-zustand]').first().waitFor();
  const kz = page.locator('[data-ek-marke="kuerzel"]');
  ok('Stempeluhr: Kuerzel gross neben Objektname', await kz.isVisible() && (await kz.innerText()) === 'TE', await kz.innerText().catch(() => ''));
  await page.locator('[data-ek-zustand]').first().evaluate((el) => el.scrollIntoView({ block: 'start' })); await page.evaluate(() => window.scrollBy(0, -160));
  await shot(page, 'stempeluhr_kuerzel');
  await ctx.close();

  // ---------- Cockpit: Objekt-Detail ----------
  console.log('Cockpit: Objekt-Detail TEST BrowserStack');
  ({ ctx, page } = await seite(desk, CK_TOKEN, 'admin', `/cockpit/objekte/${OBJ}`));
  const karte = page.locator('[data-marke-karte]');
  ok('Karte "Logo und Kürzel" da', await karte.isVisible());
  ok('Hinweistext im Upload-Feld', (await page.locator('[data-logo-hinweis]').innerText()).includes('Nur für interne Anzeige. Fremde Logos nicht für Werbung verwenden.'));
  await karte.getByLabel('Kürzel (1–3 Zeichen)').fill('tb');
  await karte.getByRole('button', { name: 'Kürzel speichern' }).click();
  await page.waitForTimeout(800);
  await karte.getByRole('radio', { name: 'Farbe Grün' }).click();
  await page.waitForTimeout(800);
  ok('Kürzel TB + Farbe Grün gespeichert', sql(`SELECT kuerzel || farbe FROM objekt_marken WHERE object_id = ${OBJ}`) === 'TB#009E73'
     && await karte.getByRole('radio', { name: 'Farbe Grün' }).getAttribute('aria-checked') === 'true');
  await shot(page, 'cockpit_objekt_kuerzel', { fullPage: false });
  await karte.locator('input[type=file]').setInputFiles(SVG_DATEI);
  await page.waitForTimeout(1500);
  const g1 = logoGroesse();
  ok('SVG-Logo: im Browser zu PNG ≤ 160 px', Array.isArray(g1) && g1[0] <= 160 && g1[1] <= 160, JSON.stringify(g1));
  await karte.locator('input[type=file]').setInputFiles(PNG_DATEI);
  await page.waitForTimeout(1500);
  const g2 = logoGroesse();
  ok('PNG 400×240: verkleinert auf 160×96', JSON.stringify(g2) === '[160,96]', JSON.stringify(g2));
  ok('Logo im Seitenkopf', await page.locator('.ck-page-head img.ck-om-logo').isVisible());
  await shot(page, 'cockpit_objekt_logo', { fullPage: false });
  // Ueberall sichtbar
  for (const [pfad, n, sel] of [['/cockpit/objekte', 'objekte', '.ck-om'], ['/cockpit', 'leitstelle', '.ck-om'], ['/cockpit/dienstplan', 'dienstplan', '.ck-om'],
    ['/cockpit/vorlage', 'vorlage', '.ck-om'], ['/cockpit/zeiten', 'zeiten', '.ck-om']]) {
    await page.goto(BASE + pfad); await page.waitForLoadState('networkidle'); await page.waitForTimeout(900);
    const anz = await page.locator(sel).count();
    const zeichen = await page.locator('.ck-om .ck-om-kz, .ck-om .ck-om-logo').count();
    ok(`${n}: Kürzel/Logo mit Objektname`, anz > 0 && zeichen > 0, `${anz} Objekte, ${zeichen} mit Zeichen`);
    await shot(page, `cockpit_${n}`);
  }
  await page.keyboard.press('Control+k');
  await page.keyboard.type('Lidl');  // Test-Objekte blendet die Suche aus
  await page.waitForTimeout(600);
  ok('Strg+K: Objekt mit Kürzel', await page.locator('.ck-cmd .ck-om-kz').count() > 0);
  await shot(page, 'cockpit_strg_k');
  await ctx.close();

  // ---------- Stempeluhr mit Logo, auch im Gast-WLAN ----------
  console.log('Stempeluhr (T9999, iPhone): Logo, offline');
  ({ ctx, page } = await seite(iphone, MA_TOKEN, 'mitarbeiter', '/dashboard'));
  await page.locator('[data-ek-zustand]').first().waitFor();
  ok('Stempeluhr: Logo gross im Kopf', await page.locator('[data-ek-marke="logo"]').isVisible());
  await page.route('**/api/v1/**', (r) => r.fulfill({ status: 200, contentType: 'text/html', body: '<html>WLAN-Anmeldung</html>' }));
  await page.reload(); await page.locator('[data-ek-zustand]').first().waitFor(); await page.waitForTimeout(1200);
  ok('Gast-WLAN ohne Netz: Logo weiter da (App-Cache)', await page.locator('[data-ek-marke="logo"]').isVisible());
  await page.locator('[data-ek-zustand]').first().evaluate((el) => el.scrollIntoView({ block: 'start' })); await page.evaluate(() => window.scrollBy(0, -160));
  await shot(page, 'stempeluhr_logo_offline');
  await ctx.close();
} finally {
  sql(`DELETE FROM objekt_marken WHERE object_id = ${OBJ}`);
  await browser.close();
}
console.log(fehler ? `=== ${fehler} Fehler ===` : '=== alles OK ===');
process.exit(fehler ? 1 : 0);
