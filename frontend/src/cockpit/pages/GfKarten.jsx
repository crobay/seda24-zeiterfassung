// GF-Kennzahlen im Cockpit: Minijob-Grenze (Hochrechnung bis Monatsende) und Objekt-Marge (nur Admin).
// Werte (Grenze/Mindestlohn je Stichtag, Ziel-Marge) stehen in der Datenbank und sind unter Einstellungen > Lohn-Grenzen aenderbar.
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BadgeEuro, TrendingDown, Plus, Trash2, Scale } from 'lucide-react';
import { api, apiError, t, fmtNum, useApi, useApp, Status, SkeletonRows, Empty, ObjektMarke } from '../core';

const eur = (n) => `${fmtNum(n, 0)} €`;

// Leitstelle: Minijobber ab Warn-Prozent (Hochrechnung Ist + geplante Schichten bis Monatsende)
export function MinijobKarte({ rows }) {
  if (!rows || rows.length === 0) return null;
  return (
    <section className="ck-card" aria-labelledby="mj-h" data-gf="minijob">
      <div className="ck-card-head"><h2 id="mj-h"><Scale size={20} />{t('gf.mj_title')}</h2><span className="ck-tag">{rows.length}</span></div>
      <ul className="ck-list">{rows.map((r) => (
        <li key={r.employee_id} className="ck-row">
          <div className="ck-row-main">
            <div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${r.employee_id}`}>{r.name}</Link>
              {r.stufe !== 'ok' && <Status s={r.stufe === 'ueber' ? 'fehlt' : 'offen'} label={r.stufe === 'ueber' ? t('gf.mj_over') : t('gf.mj_warn')} />}</div>
            <div className="ck-row-meta">
              {r.stufe !== 'ok' && (r.hochrechnung != null
                ? t('gf.mj_line_admin', { q: r.quote, h: eur(r.hochrechnung), g: eur(r.grenze) })
                : t('gf.mj_line', { q: r.quote }))}
              {r.stufe === 'warnung' && r.rest_stunden != null && ` · ${t('gf.mj_rest', { h: fmtNum(r.rest_stunden, 1) })}`}
              {r.stufe === 'ueber' && ` · ${t('gf.mj_over_hint')}`}
              {r.unter_mindestlohn && ` · ${t('gf.mj_min', { m: fmtNum(r.mindestlohn, 2) })}`}
            </div>
            <div className="ck-progress" aria-hidden="true" style={{ marginTop: 6 }}><i style={{ width: `${Math.min(100, r.quote)}%`, background: r.stufe === 'ueber' ? 'var(--ck-danger, #b91c1c)' : 'var(--ck-warn)' }} /></div>
          </div>
        </li>))}</ul>
    </section>
  );
}

// Leitstelle (nur Admin): Objekte, die bei gleichbleibendem Verlauf unter der Ziel-Marge landen
export function MargeKarte({ rows }) {
  if (!rows || rows.length === 0) return null;
  return (
    <section className="ck-card" aria-labelledby="mg-h" data-gf="marge">
      <div className="ck-card-head"><h2 id="mg-h"><TrendingDown size={20} />{t('gf.mg_title')}</h2>
        <Link className="ck-link-more" to="/cockpit/abrechnung?tab=marge">{t('gf.mg_all')}</Link></div>
      <ul className="ck-list">{rows.slice(0, 3).map((r) => (
        <li key={r.object_id} className="ck-row">
          <div className="ck-row-main"><div className="ck-row-meta" style={{ color: 'var(--ck-text)' }}>{r.text}</div></div>
        </li>))}</ul>
      {rows.length > 3 && <div className="ck-subtle" style={{ padding: '8px 16px 0' }}>{t('gf.mg_more', { n: rows.length - 3 })}</div>}
      <div className="ck-subtle" style={{ padding: '0 16px 12px', fontSize: 13 }}>{t('gf.mg_only_admin')}</div>
    </section>
  );
}

// Abrechnung > Objekt-Marge (nur Admin): ganze Tabelle mit Hochrechnung
export function MargeTabelle() {
  const [ym, setYm] = useState(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() + 1 }; });
  const step = (n) => setYm(({ y, m }) => { const d = new Date(y, m - 1 + n, 1); return { y: d.getFullYear(), m: d.getMonth() + 1 }; });
  const label = new Date(ym.y, ym.m - 1, 1).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  const { data, loading, error } = useApi(`/objekt-marge?monat=${ym.y}-${String(ym.m).padStart(2, '0')}`);
  return (
    <section className="ck-card" data-gf="marge-seite">
      <div className="ck-card-head"><h2><BadgeEuro size={20} />{t('gf.mg_page')}</h2>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button className="ck-btn ck-btn-sm" onClick={() => step(-1)} aria-label={t('abr.prev')}>‹</button>
          <span style={{ fontWeight: 650, minWidth: 130, textAlign: 'center' }}>{label}</span>
          <button className="ck-btn ck-btn-sm" onClick={() => step(1)} aria-label={t('abr.next')}>›</button></div></div>
      <MargeInhalt data={data} loading={loading} error={error} />
    </section>);
}

function MargeInhalt({ data, loading, error }) {
  if (loading) return <SkeletonRows n={6} />;
  if (error) return <div className="ck-callout">{error}</div>;
  if (!data?.objekte?.length) return <Empty icon={BadgeEuro} title={t('gf.mg_empty')} text="" />;
  return (
    <div className="ck-table-wrap" data-gf="marge-tabelle">
      <p className="ck-subtle" style={{ margin: '12px 16px' }}>{t('gf.mg_sub', { lnk: fmtNum(data.lnk_prozent, 0), ziel: fmtNum(data.ziel_prozent, 0) })}</p>
      <table className="ck-table">
        <thead><tr><th>{t('gf.c_obj')}</th><th className="r">{t('gf.c_rev')}</th><th className="r">{t('gf.c_h')}</th><th className="r">{t('gf.c_cost_ist')}</th>
          <th className="r">{t('gf.c_cost')}</th><th className="r">{t('gf.c_margin')}</th><th>{t('gf.c_state')}</th></tr></thead>
        <tbody>{data.objekte.map((z) => (
          <tr key={z.object_id}>
            <td><ObjektMarke id={z.object_id} name={z.objekt} size="xs" /></td>
            <td className="r ck-num">{z.umsatz != null ? eur(z.umsatz) : '–'}{z.umsatz_quelle === 'Vertrag' && <span className="ck-subtle"> ({t('gf.from_contract')})</span>}</td>
            <td className="r ck-num">{fmtNum(z.stunden_ist, 1)}{z.stunden_geplant ? <span className="ck-subtle"> + {fmtNum(z.stunden_geplant, 1)}</span> : null}</td>
            <td className="r ck-num">{eur(z.kosten_ist)}</td>
            <td className="r ck-num">{eur(z.kosten_hochrechnung)}</td>
            <td className="r ck-num" style={{ fontWeight: 650 }}>{z.marge_prozent != null ? `${fmtNum(z.marge_prozent, 1)} %` : '–'}</td>
            <td>{z.status === 'ok' ? <Status s="approved" label={t('gf.st_ok')} /> : z.status === 'unter_ziel'
              ? <Status s="fehlt" label={t('gf.st_low')} /> : z.status === 'ohne_stunden' ? <Status s="offen" label={t('gf.st_nohours')} />
              : <Status s="offen" label={t('gf.st_norev')} />}</td>
          </tr>))}</tbody>
        <tfoot><tr><th>{t('gf.total')}</th><th className="r ck-num">{eur(data.gesamt.umsatz)}</th><th /><th /><th className="r ck-num">{eur(data.gesamt.kosten)}</th>
          <th className="r ck-num">{data.gesamt.marge_prozent != null ? `${fmtNum(data.gesamt.marge_prozent, 1)} %` : '–'}</th><th /></tr></tfoot>
      </table>
    </div>
  );
}

// Einstellungen > Lohn-Grenzen (nur Admin): Minijob-Grenze + Mindestlohn je "gueltig ab", Warnschwelle, Ziel-Marge
export function LohnGrenzen() {
  const { toast } = useApp();
  const g = useApi('/einstellungen/lohn-grenzen');
  const [f, setF] = useState(null);
  const [ziel, setZiel] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (g.data) setF(g.data); }, [g.data]);
  const mg = useApi('/objekt-marge');
  useEffect(() => { if (mg.data) setZiel(String(mg.data.ziel_prozent)); }, [mg.data]);
  if (!f) return <SkeletonRows n={4} />;
  const stufe = (i, k, v) => setF({ ...f, stufen: f.stufen.map((s, j) => (j === i ? { ...s, [k]: v } : s)) });
  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put('/einstellungen/lohn-grenzen', f); setF(r.data);
      if (ziel !== '' && Number(ziel) !== mg.data?.ziel_prozent) await api.put('/einstellungen/objekt-marge', { ziel_prozent: Number(String(ziel).replace(',', '.')) });
      toast(t('set.saved')); mg.reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  return (
    <section className="ck-card" data-gf="lohn-grenzen">
      <div className="ck-card-head"><h2><Scale size={20} />{t('gf.set_title')}</h2><span className="ck-tag">{t('set.only_admin')}</span></div>
      <div className="ck-dialog-body">
        <p className="ck-subtle" style={{ margin: 0 }}>{t('gf.set_hint')}</p>
        <table className="ck-table"><thead><tr><th>{t('gf.c_from')}</th><th>{t('gf.c_limit')}</th><th>{t('gf.c_minwage')}</th><th /></tr></thead>
          <tbody>{f.stufen.map((s, i) => (
            <tr key={i}>
              <td><input className="ck-input" type="date" value={s.ab} onChange={(e) => stufe(i, 'ab', e.target.value)} aria-label={t('gf.c_from')} /></td>
              <td><input className="ck-input" inputMode="decimal" value={s.minijob_grenze} onChange={(e) => stufe(i, 'minijob_grenze', e.target.value)} aria-label={t('gf.c_limit')} /></td>
              <td><input className="ck-input" inputMode="decimal" value={s.mindestlohn} onChange={(e) => stufe(i, 'mindestlohn', e.target.value)} aria-label={t('gf.c_minwage')} /></td>
              <td><button className="ck-btn ck-btn-sm ck-btn-ghost" disabled={f.stufen.length < 2} onClick={() => setF({ ...f, stufen: f.stufen.filter((_, j) => j !== i) })} aria-label={t('gf.remove')}><Trash2 size={15} /></button></td>
            </tr>))}</tbody></table>
        <button className="ck-btn ck-btn-sm" onClick={() => setF({ ...f, stufen: [...f.stufen, { ab: '', minijob_grenze: '', mindestlohn: '' }] })}><Plus size={15} />{t('gf.add')}</button>
        <label className="ck-field">{t('gf.warn_from')}<input className="ck-input" inputMode="numeric" value={f.warn_ab_prozent} onChange={(e) => setF({ ...f, warn_ab_prozent: e.target.value })} style={{ maxWidth: 120 }} /></label>
        <label className="ck-field">{t('gf.target')}<input className="ck-input" inputMode="decimal" value={ziel} onChange={(e) => setZiel(e.target.value)} style={{ maxWidth: 120 }} /></label>
        <p className="ck-subtle" style={{ margin: 0 }}>{t('gf.set_note')}</p>
      </div>
      <div className="ck-dialog-foot"><button className="ck-btn ck-btn-primary" disabled={busy} onClick={save}>{t('app.save')}</button></div>
    </section>
  );
}

export const istAdmin = (me) => (me?.role || '').toLowerCase() === 'admin';
