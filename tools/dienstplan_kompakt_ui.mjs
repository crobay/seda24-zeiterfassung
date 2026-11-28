// NUR DEV: Dienstplan kompakt (Drazen 28.11.2026 08:46) - Karten einzeilig, Legende, Leiste einklappbar (gemerkt),
// ganze Woche sichtbar; PC 1600, Tablet 1280x800 quer, 800x1280 hoch, Handy. Aendert keine Schichten.
// Aufruf: CK_TOKEN=... node dienstplan_kompakt_ui.mjs <ordner> [start=JJJJ-MM-TT]
import path from 'path';
const BT = '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/tools/browsertest';
process.env.PLAYWRIGHT_BROWSERS_PATH = path.join(BT, 'ms-playwright');
const { chromium } = await import(path.join(BT, 'node_modules/playwright/index.mjs'));
const [OUT, START = ''] = process.argv.slice(2);
const BASE = 'https://dev.seda.de';
let fehler = 0;
const ok = (n, c, i = '') => { console.log(`  [${c ? 'OK ' : 'XX '}] ${n}${i ? ' - ' + i : ''}`); if (!c) fehler++; };
const GROESSEN = [['pc_1600', 1600, 1000, false], ['tablet_quer_1280x800', 1280, 800, true], ['tablet_hoch_800x1280', 800, 1280, true], ['handy_390', 390, 844, true]];
const b = await chromium.launch();
const js = [];
for (const [name, w, h, touch] of GROESSEN) {
  console.log(name);
  const ctx = await b.newContext({ viewport: { width: w, height: h }, isMobile: touch && w < 900, hasTouch: touch });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => js.push(e.message));
  await p.goto(`${BASE}/login`);
  await p.evaluate((x) => { localStorage.setItem('token', x); localStorage.setItem('userRole', 'admin'); localStorage.setItem('ck_dp_ansicht', 'tage'); localStorage.removeItem('ck_dp_leiste'); }, process.env.CK_TOKEN);
  await p.goto(`${BASE}/cockpit/dienstplan${START ? `?start=${START}` : ''}`);
  await p.locator('[data-kompakt] [data-schicht]').first().waitFor({ timeout: 20000 });
  await p.waitForTimeout(600);
  const m = await p.evaluate(() => {
    const k = [...document.querySelectorAll('[data-kompakt] .ck-sk')];
    const zeile = (el) => el ? el.getBoundingClientRect().height : 0;
    const proTag = [...document.querySelectorAll('[data-kompakt] .ck-day')].map((d) => d.querySelectorAll('.ck-sk, .ck-gap').length);
    const wk = document.querySelector('[data-kompakt]').getBoundingClientRect();
    return { n: k.length, l1max: Math.max(...k.map((x) => zeile(x.querySelector('.ck-sk-l1')))), l2max: Math.max(...k.map((x) => zeile(x.querySelector('.ck-sk-l2')))),
      kartemax: Math.max(...k.map((x) => x.getBoundingClientRect().height)), proTag, wochenHoehe: Math.round(wk.height), spalten: getComputedStyle(document.querySelector('[data-kompakt]')).gridTemplateColumns.split(' ').length,
      quer: document.documentElement.scrollWidth <= window.innerWidth + 1, abgeschnitten: k.filter((x) => x.querySelector('.ck-sk-l1 b').scrollWidth > x.querySelector('.ck-sk-l1 b').clientWidth).length,
      farbig: k.filter((x) => x.style.getPropertyValue('--obj')).length };
  });
  ok('Karten da, alle mit Objektfarbe', m.n > 0 && m.farbig === m.n, `${m.n} Karten, je Tag ${m.proTag.join('/')}`);
  ok('Name einzeilig (kein Umbruch)', m.l1max <= 18, `Zeile 1 max ${m.l1max.toFixed(0)} px, ${m.abgeschnitten} Namen mit …`);
  if (w >= 700) ok(w >= 1000 ? 'Objekt + Uhrzeit in einer Zeile' : 'Tablet hoch: Objekt/Uhrzeit hoechstens 2 kurze Zeilen', w >= 1000 ? m.l2max <= 17 : m.l2max <= 32, `Zeile 2 max ${m.l2max.toFixed(0)} px, Karte max ${m.kartemax.toFixed(0)} px`);
  ok(w >= 700 ? '7 Tage nebeneinander' : 'Handy: Tage untereinander', w >= 700 ? m.spalten === 7 : m.spalten === 1, `${m.spalten} Spalte(n)`);
  ok('kein Querscrollen', m.quer);
  ok('Legende da', await p.locator('[data-legende]').isVisible());
  // Leiste einklappen, Breite, gemerkt nach Neuladen
  const breit0 = (await p.locator('[data-kompakt]').boundingBox()).width;
  if (w >= 1100) {
    await p.locator('[data-leiste-knopf]').click(); await p.waitForTimeout(300);
    const breit1 = (await p.locator('[data-kompakt]').boundingBox()).width;
    ok('Leiste eingeklappt -> Woche breiter', await p.locator('[data-leiste]').count() === 0 && breit1 > breit0 + 200, `${Math.round(breit0)} -> ${Math.round(breit1)} px`);
    await p.reload(); await p.locator('[data-kompakt] [data-schicht]').first().waitFor({ timeout: 20000 }); await p.waitForTimeout(400);
    ok('Zustand gemerkt (nach Neuladen weiter eingeklappt)', await p.locator('[data-leiste]').count() === 0);
  } else {
    await p.locator('[data-leiste-knopf]').click(); await p.waitForTimeout(300);
    ok('Leiste ein-/ausklappbar', await p.locator('[data-leiste]').count() === 0);
  }
  const wk = await p.locator('[data-kompakt]').boundingBox();
  const kopf = await p.evaluate(() => document.querySelector('[data-kompakt]').getBoundingClientRect().top + window.scrollY);
  ok('ganze Woche ohne Scrollen sichtbar', w < 700 || kopf + wk.height <= h + 2 || wk.height <= h - 60,
    `Woche ${Math.round(wk.height)} px hoch, beginnt bei ${Math.round(kopf)} px, Fenster ${h} px` + (kopf + wk.height <= h ? ' -> passt ab Seitenanfang' : ' -> passt nach Scrollen bis Wochenanfang'));
  await p.screenshot({ path: path.join(OUT, `${name}_voll.png`), fullPage: w < 700 });
  // + und Pfeil bleiben
  await p.locator('[data-kompakt] .ck-day-head button[aria-label^="Neue"], [data-kompakt] .ck-day-head button:last-child').first().click();
  ok('+ oeffnet "Neue Schicht"', await p.locator('[role="dialog"]').isVisible()); await p.keyboard.press('Escape'); await p.waitForTimeout(250);
  if (await p.locator('[role="dialog"]').count()) await p.getByRole('button', { name: 'Abbrechen' }).click();
  await p.locator('[data-kompakt] [data-schicht]').first().hover(); await p.locator('[data-kompakt] [data-schicht] .ck-shift-more').first().click();
  ok('Pfeil oeffnet "Verschieben/Kopieren nach"', await p.locator('[role="dialog"]').isVisible());
  await p.getByRole('button', { name: 'Abbrechen' }).click(); await p.waitForTimeout(250);
  ok('Kopieren-Knopf je Tag da', await p.locator('[data-kompakt] .ck-day-head button[title]').count() === 7);
  // Leiste wieder auf
  await p.locator('[data-leiste-knopf]').click(); await p.waitForTimeout(300);
  ok('Leiste wieder aufgeklappt', await p.locator('[data-leiste]').count() === 1);
  await p.screenshot({ path: path.join(OUT, `${name}_mit_leiste.png`) });
  await ctx.close();
}
ok('keine JS-Fehler', js.length === 0, js.slice(0, 2).join(' | '));
await b.close();
console.log(fehler ? `${fehler} FEHLER` : 'ALLES OK'); process.exit(fehler ? 1 : 0);
