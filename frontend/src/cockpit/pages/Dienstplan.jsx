import React, { Suspense, lazy, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, CalendarDays, Car, Pencil } from 'lucide-react';
import { t, fmtDate, useApi, useApp, SkeletonRows, ErrorBox, Skeleton } from '../core';

const ScheduleTab = lazy(() => import('../../components/ScheduleTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export default function Dienstplan() {
  const { me } = useApp();
  const [start, setStart] = useState(() => iso(new Date()));
  const [classic, setClassic] = useState(false);
  const { data, loading, error, reload } = useApi(`/dienstplan?start=${start}`);
  const shift = (days) => { const d = new Date((data?.start || start) + 'T12:00:00'); d.setDate(d.getDate() + days); setStart(iso(d)); };
  const today = iso(new Date());

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('dienstplan.title')}</h1><p>{data ? t('dienstplan.subtitle', { date: fmtDate(data.start, { day: 'numeric', month: 'long', year: 'numeric' }) }) : <Skeleton w={180} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(-7)} aria-label={t('dienstplan.prev')}><ChevronLeft size={18} /></button>
          <button className="ck-btn" onClick={() => setStart(today)}>{t('dienstplan.today')}</button>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(7)} aria-label={t('dienstplan.next')}><ChevronRight size={18} /></button>
          {me?.role === 'admin' && <button className="ck-btn" onClick={() => setClassic(!classic)}><Pencil size={16} />{t('dienstplan.edit_classic')}</button>}
        </div>
      </div>
      {classic ? (
        <section className="ck-card"><div className="ck-card-head"><h2><Pencil size={18} />{t('app.classic')}</h2>
          <button className="ck-btn ck-btn-sm" onClick={() => { setClassic(false); reload(); }}>{t('app.back')}</button></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}><ScheduleTab /></Suspense></div></section>
      ) : error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : (
        <div className="ck-week">
          {(data?.tage || Array.from({ length: 7 }).map((_, i) => ({ tag: '', datum: String(i), schichten: null }))).map((d) => (
            <section key={d.datum} className={`ck-card ck-day${d.datum === today ? ' is-today' : ''}`} aria-label={d.tag}>
              <div className="ck-day-head"><span>{d.tag} {d.schichten && fmtDate(d.datum)}</span>{d.schichten && <span className="ck-subtle">{d.schichten.length}</span>}</div>
              {loading || !d.schichten ? <><Skeleton h={44} style={{ marginBottom: 6 }} /><Skeleton h={44} /></> :
                d.schichten.length === 0 ? <div className="ck-subtle" style={{ padding: '4px 6px' }}>{t('dienstplan.empty')}</div> :
                d.schichten.map((s) => (
                  <div key={s.id} className="ck-shift">
                    <b><Link className="ck-link" to={`/cockpit/mitarbeiter/${s.employee_id}`}>{s.name}</Link></b>
                    <span className="ck-num">{s.beginn}–{s.ende}</span> · {s.objekt}
                    {s.fahrer && s.objekt !== 'Urlaub' && s.objekt !== 'Krank' && <span title={t('dienstplan.driver')} style={{ marginLeft: 6, verticalAlign: '-2px' }}><Car size={14} aria-label={t('dienstplan.driver')} /></span>}
                  </div>))}
            </section>
          ))}
        </div>
      )}
    </>
  );
}
