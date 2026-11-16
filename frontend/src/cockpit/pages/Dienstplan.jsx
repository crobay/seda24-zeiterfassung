import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Car, Pencil, Plus, Trash2, AlertTriangle, Palmtree, Thermometer } from 'lucide-react';
import { api, apiError, t, fmtDate, useApi, useApp, SkeletonRows, ErrorBox, Skeleton, Dialog } from '../core';

const ScheduleTab = lazy(() => import('../../components/ScheduleTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export default function Dienstplan() {
  const [params, setParams] = useSearchParams();
  const [start, setStart] = useState(() => params.get('start') || iso(new Date()));
  const [classic, setClassic] = useState(false);
  const [edit, setEdit] = useState(null);
  const { data, loading, error, reload } = useApi(`/dienstplan?start=${start}`);
  const shift = (days) => { const d = new Date((data?.start || start) + 'T12:00:00'); d.setDate(d.getDate() + days); setStart(iso(d)); };
  const today = iso(new Date());

  // Deep-Link aus der Leitstelle: ?tag=YYYY-MM-DD&objekt=ID -> Schicht anlegen, vorausgefüllt
  useEffect(() => {
    const tag = params.get('tag'); const obj = params.get('objekt');
    if (tag && obj) setEdit({ neu: { datum: tag, object_id: obj, beginn: '', ende: '', employee_id: '', fahrer: true } });
  }, []); // eslint-disable-line
  const close = () => { setEdit(null); if (params.get('tag')) setParams({ start }, { replace: true }); };

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('dienstplan.title')}</h1><p>{data ? t('dienstplan.subtitle', { date: fmtDate(data.start, { day: 'numeric', month: 'long', year: 'numeric' }) }) : <Skeleton w={180} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(-7)} aria-label={t('dienstplan.prev')}><ChevronLeft size={18} /></button>
          <button className="ck-btn" onClick={() => setStart(today)}>{t('dienstplan.today')}</button>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(7)} aria-label={t('dienstplan.next')}><ChevronRight size={18} /></button>
          <button className="ck-btn" onClick={() => setClassic(!classic)}><Pencil size={16} />{t('dienstplan.edit_classic')}</button>
          <button className="ck-btn ck-btn-primary" onClick={() => setEdit({ neu: { datum: today, beginn: '', ende: '', employee_id: '', object_id: '', fahrer: true } })}><Plus size={17} />{t('dienstplan.new')}</button>
        </div>
      </div>
      {classic ? (
        <section className="ck-card"><div className="ck-card-head"><h2><Pencil size={18} />{t('app.classic')}</h2>
          <button className="ck-btn ck-btn-sm" onClick={() => { setClassic(false); reload(); }}>{t('app.back')}</button></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}><ScheduleTab /></Suspense></div></section>
      ) : error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : (
        <div className="ck-week">
          {(data?.tage || Array.from({ length: 7 }).map((_, i) => ({ tag: '', datum: String(i), schichten: null }))).map((d) => (
            <section key={d.datum} className={`ck-card ck-day${d.datum === today ? ' is-today' : ''}${d.datum === params.get('tag') ? ' is-today' : ''}`} aria-label={d.tag}>
              <div className="ck-day-head"><span>{d.tag} {d.schichten && fmtDate(d.datum)}</span>
                {d.schichten && <button className="ck-btn ck-btn-ghost ck-btn-sm ck-btn-icon" style={{ width: 28, height: 28 }} aria-label={`${t('dienstplan.new')} ${d.tag}`}
                  onClick={() => setEdit({ neu: { datum: d.datum, beginn: '', ende: '', employee_id: '', object_id: '', fahrer: true } })}><Plus size={16} /></button>}</div>
              {loading || !d.schichten ? <><Skeleton h={44} style={{ marginBottom: 6 }} /><Skeleton h={44} /></> :
                d.schichten.length === 0 ? <div className="ck-subtle" style={{ padding: '4px 6px' }}>{t('dienstplan.empty')}</div> :
                d.schichten.map((s) => {
                  const abw = s.objekt === 'Urlaub' || s.objekt === 'Krank';
                  return (
                    <button key={s.id} className="ck-shift ck-shift-btn" onClick={() => !abw && setEdit({ id: s.id })} disabled={abw}>
                      <b>{s.name}</b>
                      {abw ? <span className="ck-mini m-info">{s.objekt === 'Urlaub' ? <Palmtree size={13} /> : <Thermometer size={13} />}{s.objekt}</span>
                        : <><span className="ck-num">{s.beginn}–{s.ende}</span> · {s.objekt}
                          {s.fahrer && <span title={t('dienstplan.driver')} style={{ marginLeft: 6, verticalAlign: '-2px' }}><Car size={14} aria-label={t('dienstplan.driver')} /></span>}</>}
                    </button>);
                })}
            </section>
          ))}
        </div>
      )}
      {edit && <SchichtDialog id={edit.id} neu={edit.neu} onClose={close} onDone={() => { close(); reload(); }} />}
    </>
  );
}

export function SchichtDialog({ id, neu, onClose, onDone }) {
  const { toast } = useApp();
  const { data: aus } = useApi('/auswahl');
  const [f, setF] = useState(neu || null);
  const [orig, setOrig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => { if (id) api.get(`/schicht/${id}`).then((r) => { setF(r.data); setOrig(r.data); }).catch((e) => setErr(apiError(e))); }, [id]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const body = (x) => ({ employee_id: Number(x.employee_id), object_id: Number(x.object_id), datum: x.datum, beginn: x.beginn, ende: x.ende, fahrer: !!x.fahrer });
  const name = (eid) => aus?.mitarbeiter.find((m) => String(m.id) === String(eid))?.name || '';

  const save = async () => {
    setBusy(true); setErr('');
    try {
      if (id) {
        await api.put(`/dienstplan/${id}`, body(f));
        toast(t('dienstplan.saved', { name: name(f.employee_id), date: fmtDate(f.datum) }), { undo: async () => { await api.put(`/dienstplan/${id}`, body(orig)); onDone(); } });
      } else {
        const r = await api.post('/dienstplan', body(f));
        toast(t('dienstplan.created', { name: r.data.name, date: fmtDate(r.data.datum) }), { undo: async () => { await api.delete(`/dienstplan/${r.data.id}`); onDone(); } });
      }
      onDone();
    } catch (e) { setErr(apiError(e)); }
    setBusy(false);
  };
  const del = async () => {
    setBusy(true);
    try {
      const r = await api.delete(`/dienstplan/${id}`);
      toast(t('dienstplan.deleted', { name: r.data.alt.name, date: fmtDate(r.data.alt.datum) }), { undo: async () => { await api.post('/dienstplan', body(r.data.alt)); onDone(); } });
      onDone();
    } catch (e) { setErr(apiError(e)); setBusy(false); }
  };

  return (
    <Dialog title={id ? t('dienstplan.edit_title') : t('dienstplan.new_title')} onClose={onClose} footer={<>
      {id && (confirmDel ? <button className="ck-btn" style={{ marginRight: 'auto', color: 'var(--ck-warn)', borderColor: 'var(--ck-warn)' }} disabled={busy} onClick={del}><Trash2 size={16} />{t('zeiten.delete_confirm')}</button>
        : <button className="ck-btn ck-btn-ghost" style={{ marginRight: 'auto' }} onClick={() => setConfirmDel(true)}><Trash2 size={16} />{t('zeiten.delete')}</button>)}
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={busy || !f || !f.employee_id || !f.object_id || !f.datum || !f.beginn || !f.ende} onClick={save}>{t('app.save')}</button></>}>
      {!f ? <SkeletonRows n={3} /> : (<>
        <label className="ck-field">{t('zeiten.name')}
          <select className="ck-input" value={f.employee_id} onChange={set('employee_id')} autoFocus={!id}>
            <option value="">{t('ma.choose')}</option>{(aus?.mitarbeiter || []).map((m) => <option key={m.id} value={m.id}>{m.name} · {m.personal_nr}</option>)}</select></label>
        <label className="ck-field">{t('zeiten.object')}
          <select className="ck-input" value={f.object_id} onChange={set('object_id')}>
            <option value="">{t('ma.choose')}</option>{(aus?.objekte || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
        <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr', gap: 12 }}>
          <label className="ck-field">{t('zeiten.date')}<input type="date" className="ck-input" value={f.datum} onChange={set('datum')} /></label>
          <label className="ck-field">{t('dienstplan.from')}<input type="time" className="ck-input" value={f.beginn} onChange={set('beginn')} /></label>
          <label className="ck-field">{t('dienstplan.to')}<input type="time" className="ck-input" value={f.ende} onChange={set('ende')} /></label>
        </div>
        <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontWeight: 500 }}>
          <input type="checkbox" checked={!!f.fahrer} onChange={set('fahrer')} style={{ width: 20, height: 20 }} />{t('ma.assign_driver')}</label>
        {id && f.employee_id && <Link className="ck-link ck-subtle" to={`/cockpit/mitarbeiter/${f.employee_id}`}>{t('dienstplan.to_profile')}</Link>}
      </>)}
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>
  );
}
