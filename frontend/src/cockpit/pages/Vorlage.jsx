import React, { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { DndContext, DragOverlay, MouseSensor, TouchSensor, KeyboardSensor, useSensor, useSensors, useDraggable, useDroppable } from '@dnd-kit/core';
import { Plus, Trash2, AlertTriangle, Copy, MoveRight, Car, Hand, CalendarCog, CalendarPlus, Import, Repeat } from 'lucide-react';
import { api, apiError, t, fmtDate, useApi, useApp, SkeletonRows, ErrorBox, Dialog, Status, Empty } from '../core';
import { zielErkennung, useCopyModifier } from './Dienstplan';

const TAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const RHYTHMEN = ['weekly', 'biweekly_even', 'biweekly_odd', 'monthly'];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const montag = (off = 0) => { const d = new Date(); d.setHours(12); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + off * 7); return iso(d); };
const fmtH = (h) => String(Math.round(h * 100) / 100).replace('.', ',');

// Vorlage (Stamm-Dienstplan): Mitarbeiter x Wochentag. Ziehen = verschieben, Strg/Alt = kopieren; Klick = bearbeiten.
export default function Vorlage() {
  const { toast } = useApp();
  const { data, loading, error, reload } = useApi('/vorlage');
  const { data: aus } = useApi('/auswahl');
  const [obj, setObj] = useState(() => localStorage.getItem('ck_vl_obj') || '');
  const [edit, setEdit] = useState(null);
  const [ausWoche, setAusWoche] = useState(false);
  const [drag, setDrag] = useState(null);
  const [copyRef, copyOn] = useCopyModifier();
  const justDragged = useRef(false);
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 350, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );
  const waehleObj = (v) => { setObj(v); localStorage.setItem('ck_vl_obj', v); };

  const eintraege = (data?.eintraege || []).filter((e) => !obj || String(e.object_id) === obj);
  const objekte = useMemo(() => {
    const m = new Map(); (data?.eintraege || []).forEach((e) => m.set(e.object_id, e.objekt)); return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1], 'de'));
  }, [data]);
  const zeilen = useMemo(() => {
    const m = new Map();
    eintraege.forEach((e) => {
      if (!m.has(e.employee_id)) m.set(e.employee_id, { id: e.employee_id, name: e.name, pnr: e.personal_nr, tage: {} });
      (m.get(e.employee_id).tage[e.wochentag] ||= []).push(e);
    });
    return [...m.values()].sort((a, b) => a.name.localeCompare(b.name, 'de'));
  }, [eintraege]);

  const onDragEnd = async (ev) => {
    const e = ev.active.data.current; setDrag(null);
    justDragged.current = true; setTimeout(() => { justDragged.current = false; }, 50);
    const z = ev.over?.data.current;
    if (!z || (z.employee_id === e.employee_id && z.wochentag === e.wochentag && !copyRef.current)) return;
    try {
      if (copyRef.current) {
        await api.post('/vorlage', { employee_id: z.employee_id, object_id: e.object_id, wochentag: z.wochentag, beginn: e.beginn, ende: e.ende, fahrer: e.fahrer, rhythmus: e.rhythmus, monatswoche: e.monatswoche });
        toast(t('vorlage.copied', { name: e.name, tag: TAGE[z.wochentag] }));
      } else {
        const r = await api.put(`/vorlage/${e.id}`, { employee_id: z.employee_id, wochentag: z.wochentag });
        const alt = r.data.alt;
        toast(t('vorlage.moved', { name: r.data.neu.name, tag: r.data.neu.tag }),
          { undo: async () => { await api.put(`/vorlage/${e.id}`, { employee_id: alt.employee_id, wochentag: alt.wochentag }); reload(); } });
      }
      reload();
    } catch (err) { toast(apiError(err), { tone: 'warn' }); }
  };

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('vorlage.title')}</h1><p>{t('vorlage.subtitle')}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="ck-btn" onClick={() => setAusWoche(true)}><Import size={16} />{t('vorlage.from_week')}</button>
          <Link className="ck-btn" to={`/cockpit/dienstplan?start=${montag(1)}&vorlage=1`}><CalendarPlus size={16} />{t('vorlage.to_plan')}</Link>
          <button className="ck-btn ck-btn-primary" onClick={() => setEdit({ neu: { wochentag: 0, beginn: '', ende: '', employee_id: '', object_id: obj, fahrer: true, rhythmus: 'weekly' } })}><Plus size={17} />{t('vorlage.new')}</button>
        </div>
      </div>
      <div className="ck-toolbar ck-dp-toolbar">
        <select className="ck-input" style={{ maxWidth: 280 }} value={obj} onChange={(e) => waehleObj(e.target.value)} aria-label={t('zeiten.object')}>
          <option value="">{t('vorlage.all_objects')}</option>{objekte.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
        <span className="ck-subtle ck-dp-hint"><Hand size={15} />{t('vorlage.hint')}</span>
      </div>
      {error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : loading && !data ? <div className="ck-card"><SkeletonRows n={6} /></div>
        : !data.eintraege.length ? (
          <div className="ck-card"><Empty icon={CalendarCog} title={t('vorlage.empty_title')} text={t('vorlage.empty')}>
            <button className="ck-btn ck-btn-primary" onClick={() => setAusWoche(true)}><Import size={16} />{t('vorlage.from_week')}</button></Empty></div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={zielErkennung} onDragStart={(e) => { setDrag(e.active.data.current); const a = e.activatorEvent; if (a && (a.ctrlKey || a.altKey || a.metaKey)) copyRef.current = true; }}
            onDragEnd={onDragEnd} onDragCancel={() => setDrag(null)} autoScroll>
            <section className="ck-card">
              <div className="ck-matrix-wrap">
                <table className="ck-matrix ck-vl-matrix">
                  <thead><tr><th scope="col">{t('zeiten.name')}</th>{TAGE.map((d) => <th key={d} scope="col">{d}</th>)}</tr></thead>
                  <tbody>{zeilen.map((z) => (
                    <tr key={z.id}><th scope="row"><Link className="ck-link" to={`/cockpit/mitarbeiter/${z.id}`}>{z.name}</Link>
                      <span className="ck-subtle">{z.pnr} · {t('vorlage.per_week', { h: fmtH(data.wochenstunden[z.id] || 0) })}</span></th>
                      {TAGE.map((_, wt) => (
                        <VlZelle key={wt} eid={z.id} wt={wt} onNeu={() => setEdit({ neu: { wochentag: wt, employee_id: String(z.id), object_id: obj, beginn: '', ende: '', fahrer: true, rhythmus: 'weekly' } })}>
                          {(z.tage[wt] || []).map((e) => <VlChip key={e.id} e={e} zeigeObjekt={!obj} onOpen={() => !justDragged.current && setEdit({ e })} />)}
                        </VlZelle>))}
                    </tr>))}</tbody>
                </table>
              </div>
              <p className="ck-subtle" style={{ margin: 16 }}>{t('vorlage.sunday_auto')}</p>
            </section>
            <DragOverlay dropAnimation={null}>
              {drag ? <div className={`ck-shift ck-shift-drag${copyOn ? ' is-copy' : ''}`}>
                <span className="ck-drag-mode">{copyOn ? <><Copy size={13} />{t('dnd.mode_copy')}</> : <><MoveRight size={13} />{t('dnd.mode_move')}</>}</span>
                <b>{drag.name}</b><span className="ck-num">{drag.beginn}–{drag.ende}</span> · {drag.objekt}</div> : null}
            </DragOverlay>
          </DndContext>)}
      {edit && <VorlageDialog e={edit.e} neu={edit.neu} aus={aus} onClose={() => setEdit(null)} onDone={() => { setEdit(null); reload(); }} />}
      {ausWoche && <AusWocheDialog objekte={aus?.objekte || []} obj={obj} onClose={() => setAusWoche(false)} onDone={() => { setAusWoche(false); reload(); }} />}
    </>
  );
}

function VlZelle({ eid, wt, children, onNeu }) {
  const { setNodeRef, isOver } = useDroppable({ id: `vz|${eid}|${wt}`, data: { employee_id: eid, wochentag: wt } });
  return (
    <td ref={setNodeRef} data-vzelle={`${eid}|${wt}`} className={isOver ? 'is-over' : ''}>
      {children}
      <button className="ck-cell-add" aria-label={`${t('vorlage.new')} ${TAGE[wt]}`} onClick={onNeu}><Plus size={14} /></button>
    </td>);
}

function VlChip({ e, zeigeObjekt, onOpen }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: `v|${e.id}`, data: e });
  return (
    <div className={`ck-shift ck-shift-btn ck-drag${isDragging ? ' is-dragging' : ''}`} data-vorlage={e.id} ref={setNodeRef} {...attributes} {...listeners}
      role="button" tabIndex={0} aria-roledescription={t('dnd.aria')} onClick={onOpen} onKeyDown={(k) => { if (k.key === 'Enter') onOpen(); listeners?.onKeyDown?.(k); }}>
      <span className="ck-num">{e.beginn}–{e.ende}</span>{zeigeObjekt && <> · {e.objekt}</>}
      {e.fahrer && <span title={t('dienstplan.driver')} style={{ marginLeft: 6, verticalAlign: '-2px' }}><Car size={14} aria-label={t('dienstplan.driver')} /></span>}
      {e.rhythmus !== 'weekly' && <span className="ck-mini m-info" style={{ marginLeft: 6 }}><Repeat size={12} />{t(`vorlage.r_${e.rhythmus}`)}</span>}
    </div>);
}

function VorlageDialog({ e, neu, aus, onClose, onDone }) {
  const { toast } = useApp();
  const [f, setF] = useState(() => e ? { ...e, employee_id: String(e.employee_id), object_id: String(e.object_id) } : { ...neu, object_id: neu.object_id || '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [confirmDel, setConfirmDel] = useState(false);
  const set = (k) => (ev) => setF({ ...f, [k]: ev.target.type === 'checkbox' ? ev.target.checked : ev.target.value });
  const body = () => ({ employee_id: Number(f.employee_id), object_id: Number(f.object_id), wochentag: Number(f.wochentag), beginn: f.beginn, ende: f.ende,
    fahrer: !!f.fahrer, rhythmus: f.rhythmus, monatswoche: f.rhythmus === 'monthly' ? Number(f.monatswoche || 1) : null });
  const save = async () => {
    setBusy(true); setErr('');
    try {
      if (e) {
        const r = await api.put(`/vorlage/${e.id}`, body());
        toast(t('vorlage.saved'), { undo: async () => { const a = r.data.alt; await api.put(`/vorlage/${e.id}`, { ...a, employee_id: a.employee_id }); onDone(); } });
      } else {
        const r = await api.post('/vorlage', body());
        toast(t('vorlage.created'), { undo: async () => { await api.delete(`/vorlage/${r.data.id}`); onDone(); } });
      }
      onDone();
    } catch (x) { setErr(apiError(x)); setBusy(false); }
  };
  const del = async () => {
    setBusy(true);
    try {
      const r = await api.delete(`/vorlage/${e.id}`); const a = r.data.alt;
      toast(t('vorlage.deleted'), { undo: async () => { await api.post('/vorlage', a); onDone(); } });
      onDone();
    } catch (x) { setErr(apiError(x)); setBusy(false); }
  };
  return (
    <Dialog title={e ? t('vorlage.edit_title') : t('vorlage.new_title')} onClose={onClose} footer={<>
      {e && (confirmDel ? <button className="ck-btn" style={{ marginRight: 'auto', color: 'var(--ck-warn)', borderColor: 'var(--ck-warn)' }} disabled={busy} onClick={del}><Trash2 size={16} />{t('zeiten.delete_confirm')}</button>
        : <button className="ck-btn ck-btn-ghost" style={{ marginRight: 'auto' }} onClick={() => setConfirmDel(true)}><Trash2 size={16} />{t('zeiten.delete')}</button>)}
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={busy || !f.employee_id || !f.object_id || !f.beginn || !f.ende} onClick={save}>{t('app.save')}</button></>}>
      <label className="ck-field">{t('zeiten.name')}
        <select className="ck-input" value={f.employee_id} onChange={set('employee_id')} autoFocus={!e}>
          <option value="">{t('ma.choose')}</option>{(aus?.mitarbeiter || []).map((m) => <option key={m.id} value={m.id}>{m.name} · {m.personal_nr}</option>)}</select></label>
      <label className="ck-field">{t('zeiten.object')}
        <select className="ck-input" value={f.object_id} onChange={set('object_id')}>
          <option value="">{t('ma.choose')}</option>{(aus?.objekte || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr', gap: 12 }}>
        <label className="ck-field">{t('vorlage.weekday')}
          <select className="ck-input" value={f.wochentag} onChange={set('wochentag')}>{TAGE.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></label>
        <label className="ck-field">{t('dienstplan.from')}<input type="time" className="ck-input" value={f.beginn} onChange={set('beginn')} /></label>
        <label className="ck-field">{t('dienstplan.to')}<input type="time" className="ck-input" value={f.ende} onChange={set('ende')} /></label>
      </div>
      <div className="ck-two-inputs">
        <label className="ck-field">{t('vorlage.rhythm')}
          <select className="ck-input" value={f.rhythmus} onChange={set('rhythmus')}>{RHYTHMEN.map((r) => <option key={r} value={r}>{t(`vorlage.r_${r}`)}</option>)}</select></label>
        {f.rhythmus === 'monthly' && <label className="ck-field">{t('vorlage.month_week')}
          <select className="ck-input" value={f.monatswoche || 1} onChange={set('monatswoche')}>{[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}.</option>)}<option value={-1}>{t('vorlage.mw_last')}</option></select></label>}
      </div>
      <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontWeight: 500 }}>
        <input type="checkbox" checked={!!f.fahrer} onChange={set('fahrer')} style={{ width: 20, height: 20 }} />{t('ma.assign_driver')}</label>
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>
  );
}

function AusWocheDialog({ objekte, obj, onClose, onDone }) {
  const { toast } = useApp();
  const [woche, setWoche] = useState(montag(0));
  const [o, setO] = useState(obj || '');
  const [vor, setVor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const body = () => ({ woche, object_id: o ? Number(o) : undefined });
  const vorschau = async () => { setBusy(true); setErr(''); try { setVor((await api.post('/vorlage/aus-woche', { ...body(), vorschau: true })).data); } catch (x) { setErr(apiError(x)); } setBusy(false); };
  const anlegen = async () => {
    setBusy(true);
    try { const r = (await api.post('/vorlage/aus-woche', { ...body(), vorschau: false })).data; toast(t('vorlage.taken', { n: r.ids.length })); onDone(); }
    catch (x) { setErr(apiError(x)); setBusy(false); }
  };
  return (
    <Dialog title={t('vorlage.from_week_title')} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      {!vor ? <button className="ck-btn ck-btn-primary" disabled={busy} onClick={vorschau}>{busy ? t('app.loading') : t('kopie.preview')}</button>
        : <button className="ck-btn ck-btn-primary" disabled={busy || !vor.anzulegen} onClick={anlegen}><Import size={16} />{t('vorlage.take', { n: vor.anzulegen })}</button>}</>}>
      <p className="ck-subtle" style={{ margin: 0 }}>{t('vorlage.from_week_hint')}</p>
      <div className="ck-two-inputs">
        <label className="ck-field">{t('vorlage.week')}<input type="date" className="ck-input" value={woche} onChange={(e) => { setWoche(e.target.value); setVor(null); }} /></label>
        <label className="ck-field">{t('zeiten.object')}
          <select className="ck-input" value={o} onChange={(e) => { setO(e.target.value); setVor(null); }}>
            <option value="">{t('vorlage.all_objects')}</option>{objekte.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      </div>
      {vor && <div className="ck-kopie-vorschau">
        <div className="ck-kopie-sum"><Status s="approved" label={t('kopie.will_create', { n: vor.anzulegen })} />
          {vor.uebersprungen > 0 && <Status s="fehlt" label={t('kopie.will_skip', { n: vor.uebersprungen })} />}
          <span className="ck-subtle">{t('vorlage.week')} {fmtDate(vor.woche)}</span></div>
        {vor.eintraege.length === 0 ? <div className="ck-subtle">{t('kopie.nothing')}</div> : (
          <ul className="ck-list ck-kopie-list">{vor.eintraege.map((x, i) => (
            <li key={i} className={`ck-kopie-row${x.status !== 'ok' ? ' is-skip' : ''}`}>
              <span className="ck-num">{x.tag}</span><span><b>{x.name}</b> · {x.objekt} · <span className="ck-num">{x.beginn}–{x.ende}</span></span>
              {x.status === 'ok' ? <Status s="approved" label={t('kopie.st_ok')} /> : <Status s="fehlt" label={t('kopie.st_skip', { grund: x.grund })} />}
            </li>))}</ul>)}
      </div>}
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>
  );
}
