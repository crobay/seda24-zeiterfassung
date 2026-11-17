import React, { Suspense, lazy, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Download, FileText, Timer, Car, Wallet, CalendarClock, ArrowUpDown, ArrowUp, ArrowDown, AlertTriangle, Users } from 'lucide-react';
import axios from 'axios';
import { API_URL } from '../../config';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, SkeletonRows, Skeleton, Empty, ErrorBox } from '../core';
import { MargeTabelle, istAdmin } from './GfKarten';

const LohnUebersichtTab = lazy(() => import('../../pages/LohnUebersichtTab'));
const AbrechnungenTab = lazy(() => import('../../pages/AbrechnungenTab'));
const KundenUmsaetzeTab = lazy(() => import('../../pages/KundenUmsaetzeTab'));
const COLS = [['name', 'abr.c_name', 'l'], ['normal_hours', 'abr.c_hours'], ['sonder_hours', 'abr.c_special'], ['sonntag_hours', 'abr.c_sun'],
  ['feiertag_hours', 'abr.c_hol'], ['urlaub_hours', 'abr.c_vac'], ['km_amount', 'abr.c_km'], ['gesamt', 'abr.c_total'], ['bestaetigung', 'abr.c_conf', 'l'], ['pruefpunkte', 'abr.c_checks', 'l']];

function vormonat() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return { y: d.getFullYear(), m: d.getMonth() + 1 }; }
const token = () => localStorage.getItem('token') || sessionStorage.getItem('token');
async function download(url, name, opts = {}) {
  const r = await axios({ url: `${API_URL}${url}`, responseType: 'blob', headers: { Authorization: `Bearer ${token()}` }, ...opts });
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([r.data])); a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

export default function Abrechnung() {
  const { me, toast } = useApp();
  const [ym, setYm] = useState(vormonat);
  const [tab, setTab] = useState(() => (new URLSearchParams(window.location.search).get('tab') === 'marge' ? 'marge' : 'neu'));
  const [sort, setSort] = useState({ k: 'name', dir: 1 });
  const [busy, setBusy] = useState('');
  const { data, loading, error, reload } = useApi(`/abrechnung?year=${ym.y}&month=${ym.m}`);
  const label = new Date(ym.y, ym.m - 1, 1).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  const step = (n) => setYm(({ y, m }) => { const d = new Date(y, m - 1 + n, 1); return { y: d.getFullYear(), m: d.getMonth() + 1 }; });
  const tabs = ['neu', 'lohn', 'pdf', ...(me?.rechte?.kunden_umsaetze ? ['umsatz'] : []), ...(istAdmin(me) ? ['marge'] : [])];   // Objekt-Marge nur Admin
  const rows = useMemo(() => [...(data?.zeilen || [])].sort((a, b) => {
    const x = a[sort.k] ?? '', y = b[sort.k] ?? ''; return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; }), [data, sort]);
  const offenePruef = rows.reduce((a, r) => a + (r.pruefpunkte || 0), 0);
  const unbestaetigt = rows.filter((r) => r.bestaetigung !== 'confirmed' && (r.normal_hours || r.gesamt)).length;
  const mm = String(ym.m).padStart(2, '0');

  const lexware = async () => {
    setBusy('lex');
    try { await download(`/admin/lexware-export?year=${ym.y}&month=${ym.m}`, `Lexware_Export_${mm}_${ym.y}.zip`); toast(t('abr.lex_done', { month: label })); }
    catch (e) { toast(e?.response?.status === 404 ? t('abr.no_entries') : apiError(e), { tone: 'warn' }); }
    setBusy('');
  };
  const pdfs = async () => {
    setBusy('pdf');
    try {
      await download('/admin/generate-pdf-bulk', `Zeitnachweise_${mm}_${ym.y}.zip`, { method: 'post',
        data: { employee_ids: rows.map((r) => r.employee_id), year: ym.y, month: ym.m, include_zeitnachweis: true, include_kilometer: true } });
      toast(t('abr.pdf_done', { n: rows.length }));
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy('');
  };
  const SortIcon = ({ k }) => sort.k !== k ? <ArrowUpDown size={14} opacity={.5} /> : sort.dir > 0 ? <ArrowUp size={14} /> : <ArrowDown size={14} />;

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('abr.title')}</h1><p>{t('abr.subtitle')}</p></div>
        <div className="ck-seg" style={{ flexWrap: 'wrap' }}>{tabs.map((k) => <button key={k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{t(`abr.${k}`)}</button>)}</div>
      </div>

      {tab === 'marge' && istAdmin(me) ? <MargeTabelle /> : tab !== 'neu' ? (
        <section className="ck-card"><div className="ck-card-head"><h2>{t(`abr.${tab}`)}</h2><span className="ck-tag">{t('app.classic')}</span></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}>
            {tab === 'lohn' ? <LohnUebersichtTab /> : tab === 'umsatz' && me?.rechte?.kunden_umsaetze ? <KundenUmsaetzeTab showToast={(m) => toast(m)} /> : <AbrechnungenTab />}
          </Suspense></div></section>
      ) : (<>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 20, flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => step(-1)} aria-label={t('abr.prev')}><ChevronLeft size={18} /></button>
          <div className="ck-card" style={{ padding: '7px 18px', fontWeight: 650, minWidth: 180, textAlign: 'center' }}>{label}</div>
          <button className="ck-btn ck-btn-icon" onClick={() => step(1)} aria-label={t('abr.next')}><ChevronRight size={18} /></button>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="ck-btn" disabled={!!busy || !rows.length} onClick={pdfs}><FileText size={16} />{busy === 'pdf' ? t('app.loading') : t('abr.pdf_btn')}</button>
            <button className="ck-btn ck-btn-primary" disabled={!!busy} onClick={lexware}><Download size={16} />{busy === 'lex' ? t('app.loading') : t('abr.lex_btn')}</button>
          </div>
        </div>

        {(offenePruef > 0 || unbestaetigt > 0) && data && (
          <div className="ck-callout" style={{ marginBottom: 16 }}><AlertTriangle size={20} style={{ flex: 'none' }} />
            <span>{t('abr.warn', { p: offenePruef, u: unbestaetigt })} <Link className="ck-link" style={{ textDecoration: 'underline' }} to={`/cockpit/zeiten?pruef=alle&monat=${ym.y}-${mm}`}>{t('abr.warn_link')}</Link></span></div>)}

        <div className="ck-kpis">
          {[[Timer, t('abr.k_hours'), data && fmtNum(data.summe.normal_hours + data.summe.sonder_hours, 1), data && t('abr.k_hours_sub', { s: fmtNum(data.summe.sonntag_hours, 1), f: fmtNum(data.summe.feiertag_hours, 1) })],
            [Car, t('abr.k_km'), data && `${fmtNum(data.summe.km_amount, 2)} €`, t('abr.k_km_sub')],
            [Wallet, t('abr.k_total'), data && `${fmtNum(data.summe.gesamt, 2)} €`, data && t('abr.k_total_sub', { n: rows.length })],
            [CalendarClock, t('abr.k_export'), data && fmtDate(data.exporttag, { weekday: 'short', day: '2-digit', month: '2-digit' }), t('abr.k_export_sub')],
          ].map(([Icon, l, v, sub], i) => (
            <div key={i} className="ck-card ck-kpi tone-info" style={{ cursor: 'default' }}>
              <div className="ck-kpi-label"><span className="ck-kpi-icon"><Icon size={18} /></span>{l}</div>
              <div className="ck-kpi-value ck-num" style={{ fontSize: 28 }}>{v ?? <Skeleton w={80} h={28} />}</div>
              <div className="ck-kpi-sub">{sub ?? <Skeleton w="60%" h={13} />}</div>
            </div>))}
        </div>

        <section className="ck-card">
          <div className="ck-card-head"><h2><Users size={20} />{t('abr.per_ma', { month: label })}</h2></div>
          {error ? <ErrorBox text={error} onRetry={reload} /> : loading ? <SkeletonRows n={6} /> : rows.length === 0 ? <Empty icon={Wallet} title={t('abr.no_entries')} text="" /> : (
            <div className="ck-table-wrap"><table className="ck-table">
              <thead><tr>{COLS.map(([k, l, al]) => <th key={k} style={{ textAlign: al ? 'left' : 'right' }} aria-sort={sort.k === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                <button onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : 1 }))}>{t(l)}<SortIcon k={k} /></button></th>)}</tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.employee_id}>
                  <td><Link className="ck-link" to={`/cockpit/mitarbeiter/${r.employee_id}`} style={{ fontWeight: 600 }}>{r.name}</Link> <span className="ck-subtle">{r.personal_nr}</span>
                    {r.festgehalt && <span className="ck-tag" style={{ marginLeft: 6 }}>{t('abr.fixed')}</span>}</td>
                  {['normal_hours', 'sonder_hours', 'sonntag_hours', 'feiertag_hours', 'urlaub_hours'].map((k) => <td key={k} className="ck-num" style={{ textAlign: 'right' }}>{r[k] ? fmtNum(r[k], 2) : '–'}</td>)}
                  <td className="ck-num" style={{ textAlign: 'right' }}>{r.km_amount ? `${fmtNum(r.km_amount, 2)} €` : '–'}</td>
                  <td className="ck-num" style={{ textAlign: 'right', fontWeight: 650 }}>{fmtNum(r.gesamt, 2)} €</td>
                  <td>{r.bestaetigung === 'confirmed' ? <Status s="approved" label={t('abr.conf_yes')} /> : r.bestaetigung === 'disputed' ? <Status s="fehlt" label={t('abr.conf_disputed')} /> : <Status s="pending" label={t('abr.conf_open')} />}</td>
                  <td>{r.pruefpunkte ? <Link to={`/cockpit/zeiten?pruef=alle&monat=${ym.y}-${mm}`}><Status s="fehlt" label={t('abr.checks_n', { n: r.pruefpunkte })} /></Link> : <Status s="da" label={t('ls.chk_ok')} />}</td>
                </tr>))}
                <tr style={{ fontWeight: 700 }}><td>{t('abr.sum')}</td>
                  {['normal_hours', 'sonder_hours', 'sonntag_hours', 'feiertag_hours', 'urlaub_hours'].map((k) => <td key={k} className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(data.summe[k], 2)}</td>)}
                  <td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(data.summe.km_amount, 2)} €</td><td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(data.summe.gesamt, 2)} €</td><td /><td /></tr>
              </tbody></table></div>)}
        </section>
      </>)}
    </>
  );
}
