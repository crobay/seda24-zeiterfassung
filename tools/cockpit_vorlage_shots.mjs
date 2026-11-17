// Screenshots "Plan aus Vorlage" (nur DEV): Vorlage-Seite, Woche aus Vorlage (Vorschau), Plan mit offener Luecke,
// Mitarbeiter-Leiste, Kontingent Ruzica, Leitstelle "Plan naechste Woche". Die fuer die Bilder erzeugte Woche
// (Juli 2027, Helena hat dort Urlaub) wird am Ende ueber "Rueckgaengig" wieder entfernt.
// Aufruf: CK_TOKEN=$(...dev_token.py admin@seda24.de) node cockpit_vorlage_shots.mjs <ordner>
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium, devices } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT] = process.argv.slice(2); const TOKEN = process.env.CK_TOKEN;
const BASE = 'https://dev.seda.de', API = `${BASE}/api/v1/cockpit`;
const H = { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' };
const call = async (m, p, b) => (await fetch(API + p, { method: m, headers: H, body: b ? JSON.stringify(b) : undefined })).json();
const WOCHE = '2027-07-12';
const { defaultBrowserType: _a, ...ipad } = devices['iPad (gen 7)'];
const { defaultBrowserType: _b, ...iphone } = devices['iPhone 15'];
const profile = { pc: { viewport: { width: 1440, height: 900 } }, tablet: ipad, handy: iphone };
const browser = await chromium.launch();
async function seite(prof, pfad, ansicht = 'tage') {
  const ctx = await browser.newContext({ ...prof, locale: 'de-DE', timezoneId: 'Europe/Berlin' });
  const page = await ctx.newPage(); page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  await page.goto(`${BASE}/login`);
  await page.evaluate(([tk, a]) => { localStorage.setItem('token', tk); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_theme_v2', 'light'); localStorage.setItem('ck_dp_ansicht', a); localStorage.removeItem('ck_vl_obj'); }, [TOKEN, ansicht]);
  await page.goto(BASE + pfad); await page.waitForLoadState('networkidle'); await page.waitForTimeout(900);
  return { ctx, page };
}
const f = (n) => path.join(OUT, `14_${n}.png`);
let kid = null;
try {
  // Vorschau "Woche aus Vorlage" (noch nichts gespeichert) + ungeplante Woche
  let { ctx, page } = await seite(profile.pc, `/cockpit/dienstplan?start=${WOCHE}`);
  await page.screenshot({ path: f('woche_ungeplant_pc') });
  await page.locator('.ck-plan-status').getByRole('button', { name: 'Woche aus Vorlage erstellen' }).click(); await page.waitForTimeout(1500);
  await page.screenshot({ path: f('woche_aus_vorlage_vorschau_pc') });
  await ctx.close();
  ({ ctx, page } = await seite(profile.handy, `/cockpit/dienstplan?start=${WOCHE}&vorlage=1`));
  await page.waitForTimeout(1000); await page.screenshot({ path: f('woche_aus_vorlage_vorschau_handy') });
  await ctx.close();

  // Woche anlegen (fuer die Bilder); Helena hat Urlaub -> offene Luecken
  const r = await call('POST', '/dienstplan/aus-vorlage', { woche: WOCHE, vorschau: false }); kid = r.kopie_id;
  console.log(`Woche ${WOCHE}: ${r.angelegt} angelegt, ${r.luecken} Lücken (Kopie ${kid})`);
  for (const [name, prof] of Object.entries(profile)) {
    for (const ansicht of ['tage', 'ma']) {
      if (ansicht === 'ma' && name !== 'pc') continue;
      ({ ctx, page } = await seite(prof, `/cockpit/dienstplan?start=${WOCHE}`, ansicht));
      await page.screenshot({ path: f(`plan_${ansicht === 'ma' ? 'mitarbeiter' : 'tage'}_${name}`) });
      if (ansicht === 'tage') {
        await page.locator('.ck-dp-aside').scrollIntoViewIfNeeded(); await page.waitForTimeout(300);
        if (name !== 'pc') await page.screenshot({ path: f(`leiste_kontingent_${name}`) });
        // Luecke angeklickt -> Dialog vorbelegt (nicht gespeichert)
        if (name === 'pc') {
          await page.evaluate(() => window.scrollTo(0, 0));
          // Ziehen in Arbeit: Mitarbeiter aus der Leiste auf die Luecke (mit Esc abgebrochen)
          const von = page.locator('.ck-ma-item').first(); const nach = page.locator('.ck-gap').first();
          await nach.scrollIntoViewIfNeeded(); const a = await von.boundingBox(), b = await nach.boundingBox();
          await page.mouse.move(a.x + 30, a.y + a.height / 2); await page.mouse.down();
          await page.mouse.move(a.x + 50, a.y + a.height / 2 + 5, { steps: 3 }); await page.mouse.move(b.x + b.width / 2, b.y + 30, { steps: 14 });
          await page.waitForTimeout(250); await page.screenshot({ path: f('leiste_ziehen_auf_luecke_pc') });
          await page.keyboard.press('Escape'); await page.mouse.up(); await page.waitForTimeout(300);
          await page.locator('.ck-gap').first().click(); await page.waitForTimeout(1200);
          await page.screenshot({ path: f('luecke_einplanen_dialog_pc') });
          await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
          await page.locator('.ck-konto').getByRole('button', { name: 'Rest verteilen' }).click(); await page.waitForTimeout(1500);
          await page.screenshot({ path: f('kontingent_verteilen_vorschau_pc') });
          await page.getByRole('dialog').getByRole('button', { name: 'Abbrechen' }).click();
        }
      }
      await ctx.close();
    }
    // Vorlage-Seite + Leitstelle
    ({ ctx, page } = await seite(prof, '/cockpit/vorlage'));
    await page.screenshot({ path: f(`vorlage_${name}`) });
    if (name === 'pc') { await page.locator('[data-vorlage]').first().click(); await page.waitForTimeout(800); await page.screenshot({ path: f('vorlage_eintrag_dialog_pc') }); }
    await ctx.close();
    ({ ctx, page } = await seite(prof, '/cockpit'));
    const karte = page.locator('#plan-naechste-woche'); await karte.scrollIntoViewIfNeeded(); await page.waitForTimeout(300);
    await karte.screenshot({ path: f(`leitstelle_plan_naechste_woche_${name}`) });
    await ctx.close();
  }
} finally {
  if (kid) { const u = await call('DELETE', `/dienstplan/kopie/${kid}`); console.log(`Rückgängig: ${u.entfernt} entfernt`); }
  await browser.close();
}
