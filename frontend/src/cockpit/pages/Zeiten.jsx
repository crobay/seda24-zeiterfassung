import React, { Suspense, lazy, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Clock3, ArrowUpDown, ArrowUp, ArrowDown, AlertTriangle, ClipboardCheck } from 'lucide-react';
import { t, fmtNum, fmtDate, useApi, useApp, Status, SkeletonRows, Empty, ErrorBox, Skeleton } from '../core';

const GenehmigungenTab = lazy(() => import('../../pages/GenehmigungenTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const COLS = [['datum', 'zeiten.date'], ['name', 'zeiten.name'], ['objekt', 'zeiten.object'], ['kommen', 'zeiten.in'], ['gehen', 'zeiten.out'], ['stunden', 'zeiten.hours'], ['weg', 'zeiten.way'], ['hinweis', 'zeiten.hint']];

export default function Zeiten() {
  const { me, toast } = useApp();
  const [range, setRange] = useState('week');
  const [classic, setClassic] = useState(false);
  const now = new Date();
  const von = range === 'week' ? iso(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6)) : iso(new Date(now.getFullYear(), now.getMonth(), 1));
  const { data, loading, error, reload } = useApi(`/zeiten?von=${von}&bis=${iso(now)}`);
  const [q, setQ] = useState('');
  const [onlyHint, setOnlyHint] = useState(false);
  const [sort, setSort] = useState({ k: 'datum', dir: -1 });

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (data?.eintraege || [])
      .filter((r) => (!onlyHint || r.hinweis) && (!s || `${r.name} ${r.personal_nr} ${r.objekt} ${r.weg}`.toLowerCase().includes(s)))
      .sort((a, b) => { const x = a[sort.k] ?? '', y = b[sort.k] ?? ''; return (x > y ? 1 : x < y ? -1 : 0) * sort.dir || (a.kommen > b.kommen ? -1 : 1); });
  }, [data, q, onlyHint, sort]);
  const sum = rows.reduce((a, r) => a + r.stunden, 0);
  const SortIcon = ({ k }) => sort.k !== k ? <ArrowUpDown size={14} opacity={.5} /> : sort.dir > 0 ? <ArrowUp size={14} /> : <ArrowDown size={14} />;

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('zeiten.title')}</h1><p>{data ? t('zeiten.subtitle', { from: fmtDate(data.von), to: fmtDate(data.bis, { day: '2-digit', month: '2-digit', year: 'numeric' }) }) : <Skeleton w={160} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <div className="ck-seg">{['week', 'month'].map((k) => <button key={k} className={range === k ? 'is-on' : ''} onClick={() => setRange(k)}>{t(`zeiten.${k}`)}</button>)}</div>
          {me?.role === 'admin' && <button className="ck-btn" onClick={() => setClassic(!classic)}><ClipboardCheck size={16} />{t('zeiten.approvals')}</button>}
        </div>
      </div>
      {classic ? (
        <section className="ck-card"><div className="ck-card-head"><h2>{t('zeiten.approvals')}</h2><button className="ck-btn ck-btn-sm" onClick={() => setClassic(false)}>{t('app.back')}</button></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={5} />}><GenehmigungenTab showToast={(m) => toast(m)} /></Suspense></div></section>
      ) : (
        <section className="ck-card">
          <div className="ck-toolbar">
            <input className="ck-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('zeiten.filter')} aria-label={t('zeiten.filter')} />
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 500 }}><input type="checkbox" checked={onlyHint} onChange={(e) => setOnlyHint(e.target.checked)} style={{ width: 18, height: 18 }} />{t('zeiten.only_hints')}</label>
            {data && <span className="ck-subtle" style={{ marginLeft: 'auto' }}>{t('zeiten.sum', { n: rows.length, h: fmtNum(sum, 1) })}</span>}
          </div>
          {error ? <ErrorBox text={error} onRetry={reload} /> : loading ? <SkeletonRows n={6} /> : rows.length === 0 ? <Empty icon={Clock3} title={t('zeiten.empty_title')} text={t('zeiten.empty')} /> : (
            <div className="ck-table-wrap">
              <table className="ck-table">
                <thead><tr>{COLS.map(([k, l]) => (
                  <th key={k} aria-sort={sort.k === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                    <button onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : 1 }))}>{t(l)}<SortIcon k={k} /></button></th>))}</tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id}>
                    <td className="ck-num">{fmtDate(r.datum)}</td>
                    <td><Link className="ck-link" to={`/cockpit/mitarbeiter/${r.employee_id}`} style={{ fontWeight: 600 }}>{r.name}</Link></td>
                    <td>{r.objekt || '–'}</td>
                    <td className="ck-num">{r.kommen}</td>
                    <td className="ck-num">{r.gehen || <Status s="da" label={t('status.da')} />}</td>
                    <td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(r.stunden, 2)}</td>
                    <td className="ck-subtle">{r.weg}</td>
                    <td>{r.hinweis && <Status s="fehlt" label={r.hinweis} />}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
