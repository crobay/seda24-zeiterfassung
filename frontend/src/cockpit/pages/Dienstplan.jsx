import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DndContext, DragOverlay, MouseSensor, TouchSensor, KeyboardSensor, useSensor, useSensors, useDraggable, useDroppable, pointerWithin, rectIntersection } from '@dnd-kit/core';
import { ChevronLeft, ChevronRight, Car, Pencil, Plus, Trash2, AlertTriangle, Palmtree, Thermometer, Copy, CopyPlus, MoveRight, Undo2, X, CalendarRange, Users, Rows3, Hand } from 'lucide-react';
import { api, apiError, t, fmtDate, useApi, useApp, SkeletonRows, ErrorBox, Skeleton, Dialog, Status } from '../core';

const ScheduleTab = lazy(() => import('../../components/ScheduleTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const addDays = (isoD, n) => { const d = new Date(isoD + 'T12:00:00'); d.setDate(d.getDate() + n); return iso(d); };
export const schichtBody = (x) => ({ employee_id: Number(x.employee_id), object_id: Number(x.object_id), datum: x.datum, beginn: x.beginn, ende: x.ende, fahrer: !!x.fahrer });
// Ablegen dort, wo Zeiger/Finger ist (nicht nach groesster Ueberdeckung der gezogenen Karte); Tastatur: Ueberdeckung
const zielErkennung = (args) => { const p = pointerWithin(args); return p.length ? p : rectIntersection(args); };
const istAbw = (s) => s.objekt === 'Urlaub' || s.objekt === 'Krank';

// Strg/Alt/Cmd waehrend des Ziehens = kopieren (Tastatur und Zeiger liefern den Zustand)
function useCopyModifier() {
  const ref = useRef(false);
  const [on, setOn] = useState(false);
  useEffect(() => {
    const upd = (e) => { const v = !!(e.ctrlKey || e.altKey || e.metaKey); if (v !== ref.current) { ref.current = v; setOn(v); } };
    ['keydown', 'keyup', 'pointermove', 'pointerdown'].forEach((ev) => window.addEventListener(ev, upd));
    return () => ['keydown', 'keyup', 'pointermove', 'pointerdown'].forEach((ev) => window.removeEventListener(ev, upd));
  }, []);
  return [ref, on];
}

export default function Dienstplan() {
  const { toast } = useApp();
  const [params, setParams] = useSearchParams();
  const [start, setStart] = useState(() => params.get('start') || iso(new Date()));
  const [ansicht, setAnsicht] = useState(() => localStorage.getItem('ck_dp_ansicht') || 'tage');
  const [classic, setClassic] = useState(false);
  const [edit, setEdit] = useState(null);
  const [kopie, setKopie] = useState(null);     // offener Kopier-Dialog {modus, ...}
  const [ziel, setZiel] = useState(null);       // "Verschieben/Kopieren nach ..." fuer eine Schicht
  const [letzte, setLetzte] = useState(null);   // letzter Kopiervorgang (Rueckgaengig bleibt sichtbar)
  const [drag, setDrag] = useState(null);
  const [busy, setBusy] = useState(false);
  const justDragged = useRef(false);
  const [copyRef, copyOn] = useCopyModifier();
  const { data, loading, error, reload } = useApi(`/dienstplan?start=${start}`);
  const { data: aus } = useApi('/auswahl');
  const shift = (days) => { const d = new Date((data?.start || start) + 'T12:00:00'); d.setDate(d.getDate() + days); setStart(iso(d)); };
  const today = iso(new Date());
  const wochenStart = data?.start || start;
  useEffect(() => { localStorage.setItem('ck_dp_ansicht', ansicht); }, [ansicht]);

  useEffect(() => {
    const tag = params.get('tag'); const obj = params.get('objekt');
    if (tag && obj) setEdit({ neu: { datum: tag, object_id: obj, beginn: '', ende: '', employee_id: '', fahrer: true } });
  }, []); // eslint-disable-line
  const close = () => { setEdit(null); if (params.get('tag')) setParams({ start }, { replace: true }); };

  // Langes Druecken (Touch) startet das Ziehen, kurzes Wischen scrollt weiter; Maus ab 6 px Bewegung
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 350, tolerance: 8 } }),
    useSensor(KeyboardSensor),
  );

  const kopiert = (r, text) => {
    setLetzte({ id: r.kopie_id, n: r.angelegt, text });
    toast(text, { undo: () => rueckgaengig(r.kopie_id) });
  };
  const rueckgaengig = async (id) => {
    try {
      const r = await api.delete(`/dienstplan/kopie/${id}`);
      toast(r.data.behalten_gestempelt ? t('kopie.undone_kept', { n: r.data.entfernt, k: r.data.behalten_gestempelt }) : t('kopie.undone', { n: r.data.entfernt }));
      setLetzte((l) => (l && l.id === id ? null : l)); reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };

  // Ausfuehren: verschieben oder kopieren (Drag & Drop und Menue "nach ...")
  const ausfuehren = async (s, zielDatum, zielMa, kopieren) => {
    const ma = Number(zielMa || s.employee_id);
    if (!kopieren && zielDatum === s.datum && ma === Number(s.employee_id)) return;
    setBusy(true);
    const wen = aus?.mitarbeiter.find((m) => m.id === ma)?.name || s.name;
    try {
      if (kopieren) {
        const r = await api.post('/dienstplan/kopieren', { schicht_ids: [s.id], ziel_von: zielDatum, employee_id: ma, vorschau: false });
        if (!r.data.angelegt) toast(t('kopie.skipped_one', { grund: r.data.eintraege[0]?.grund || '' }), { tone: 'warn' });
        else kopiert(r.data, t('dnd.copied', { name: wen, date: fmtDate(zielDatum, { weekday: 'short', day: '2-digit', month: '2-digit' }) }));
      } else {
        const r = await api.post(`/dienstplan/${s.id}/verschieben`, { datum: zielDatum, employee_id: ma });
        const alt = r.data.alt;
        toast(t('dnd.moved', { name: wen, date: fmtDate(zielDatum, { weekday: 'short', day: '2-digit', month: '2-digit' }) }),
          { undo: async () => { await api.put(`/dienstplan/${s.id}`, schichtBody(alt)); reload(); } });
      }
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };

  const onDragStart = (e) => { setDrag(e.active.data.current); const a = e.activatorEvent; if (a && (a.ctrlKey || a.altKey || a.metaKey)) copyRef.current = true; };
  const onDragEnd = (e) => {
    const s = e.active.data.current; setDrag(null);
    justDragged.current = true; setTimeout(() => { justDragged.current = false; }, 50);
    if (!e.over) return;
    const z = e.over.data.current;
    ausfuehren(s, z.datum, z.employee_id || s.employee_id, copyRef.current);
  };
  const oeffnen = (s) => { if (!justDragged.current && !istAbw(s)) setEdit({ id: s.id }); };

  const tage = data?.tage || Array.from({ length: 7 }).map((_, i) => ({ tag: '', datum: String(i), schichten: null }));
  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('dienstplan.title')}</h1><p>{data ? t('dienstplan.subtitle', { date: fmtDate(data.start, { day: 'numeric', month: 'long', year: 'numeric' }) }) : <Skeleton w={180} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(-7)} aria-label={t('dienstplan.prev')}><ChevronLeft size={18} /></button>
          <button className="ck-btn" onClick={() => setStart(today)}>{t('dienstplan.today')}</button>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(7)} aria-label={t('dienstplan.next')}><ChevronRight size={18} /></button>
          <button className="ck-btn" disabled={!data} onClick={() => setKopie({ modus: 'woche' })}><CopyPlus size={16} />{t('kopie.week_btn')}</button>
          <button className="ck-btn ck-btn-primary" onClick={() => setEdit({ neu: { datum: today, beginn: '', ende: '', employee_id: '', object_id: '', fahrer: true } })}><Plus size={17} />{t('dienstplan.new')}</button>
        </div>
      </div>

      <div className="ck-toolbar ck-dp-toolbar">
        <div className="ck-seg" role="group" aria-label={t('dnd.view')}>
          <button className={ansicht === 'tage' ? 'is-on' : ''} onClick={() => setAnsicht('tage')}><Rows3 size={16} />{t('dnd.view_days')}</button>
          <button className={ansicht === 'ma' ? 'is-on' : ''} onClick={() => setAnsicht('ma')}><Users size={16} />{t('dnd.view_staff')}</button>
        </div>
        <span className="ck-subtle ck-dp-hint"><Hand size={15} />{t('dnd.hint')}</span>
        <button className="ck-btn ck-btn-ghost ck-btn-sm" style={{ marginLeft: 'auto' }} onClick={() => setClassic(!classic)}><Pencil size={15} />{t('dienstplan.edit_classic')}</button>
      </div>

      {letzte && (
        <div className="ck-callout ck-callout-info" style={{ marginBottom: 16 }} role="status">
          <CopyPlus size={18} style={{ flex: 'none' }} /><span style={{ flex: 1 }}>{letzte.text}</span>
          <button className="ck-btn ck-btn-sm" onClick={() => rueckgaengig(letzte.id)}><Undo2 size={15} />{t('kopie.undo_all')}</button>
          <button className="ck-btn ck-btn-ghost ck-btn-sm ck-btn-icon" aria-label={t('app.close')} onClick={() => setLetzte(null)}><X size={15} /></button>
        </div>)}

      {classic ? (
        <section className="ck-card"><div className="ck-card-head"><h2><Pencil size={18} />{t('app.classic')}</h2>
          <button className="ck-btn ck-btn-sm" onClick={() => { setClassic(false); reload(); }}>{t('app.back')}</button></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}><ScheduleTab /></Suspense></div></section>
      ) : error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : (
        <DndContext sensors={sensors} collisionDetection={zielErkennung} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDrag(null)} autoScroll>
          <div className={busy ? 'ck-dp-busy' : ''}>
            {ansicht === 'tage' ? (
              <div className="ck-week">
                {tage.map((d) => (
                  <TagSpalte key={d.datum} d={d} heute={today} markiert={params.get('tag')} loading={loading}
                    onNeu={() => setEdit({ neu: { datum: d.datum, beginn: '', ende: '', employee_id: '', object_id: '', fahrer: true } })}
                    onTagKopieren={() => setKopie({ modus: 'tag', tag: d.datum })}>
                    {d.schichten?.map((s) => <SchichtChip key={s.id} s={{ ...s, datum: d.datum }} onOpen={oeffnen} onZiel={setZiel} />)}
                  </TagSpalte>))}
              </div>
            ) : <MatrixAnsicht tage={tage} loading={loading} mitarbeiter={aus?.mitarbeiter} heute={today} onOpen={oeffnen} onZiel={setZiel}
                  onNeu={(datum, eid) => setEdit({ neu: { datum, beginn: '', ende: '', employee_id: String(eid), object_id: '', fahrer: true } })} />}
          </div>
          <DragOverlay dropAnimation={null}>
            {drag ? <div className={`ck-shift ck-shift-drag${copyOn ? ' is-copy' : ''}`}>
              <span className="ck-drag-mode">{copyOn ? <><Copy size={13} />{t('dnd.mode_copy')}</> : <><MoveRight size={13} />{t('dnd.mode_move')}</>}</span>
              <b>{drag.name}</b><span className="ck-num">{drag.beginn}–{drag.ende}</span> · {drag.objekt}</div> : null}
          </DragOverlay>
        </DndContext>
      )}
      {edit && <SchichtDialog id={edit.id} neu={edit.neu} onClose={close} onDone={() => { close(); reload(); }}
        onDuplizieren={(s) => { close(); setKopie({ modus: 'schicht', schicht: s }); }} onZiel={(s) => { close(); setZiel(s); }} />}
      {kopie && <KopierDialog {...kopie} wochenStart={wochenStart} tage={tage} mitarbeiter={aus?.mitarbeiter || []}
        onClose={() => setKopie(null)} onDone={(r, text) => { setKopie(null); kopiert(r, text); reload(); }} />}
      {ziel && <ZielDialog s={ziel} mitarbeiter={aus?.mitarbeiter || []} onClose={() => setZiel(null)}
        onRun={(datum, ma, kop) => { setZiel(null); ausfuehren(ziel, datum, ma, kop); }} />}
    </>
  );
}

function TagSpalte({ d, heute, markiert, loading, onNeu, onTagKopieren, children }) {
  const { setNodeRef, isOver } = useDroppable({ id: `tag|${d.datum}`, data: { datum: d.datum }, disabled: !d.schichten });
  return (
    <section ref={setNodeRef} data-tag={d.datum} className={`ck-card ck-day${d.datum === heute || d.datum === markiert ? ' is-today' : ''}${isOver ? ' is-over' : ''}`} aria-label={d.tag}>
      <div className="ck-day-head"><span>{d.tag} {d.schichten && fmtDate(d.datum)}</span>
        {d.schichten && <span style={{ display: 'flex', gap: 2 }}>
          <button className="ck-btn ck-btn-ghost ck-btn-sm ck-btn-icon" style={{ width: 28, height: 28 }} title={t('kopie.day_btn')} aria-label={`${t('kopie.day_btn')} ${d.tag}`}
            disabled={!d.schichten.some((s) => !istAbw(s))} onClick={onTagKopieren}><Copy size={15} /></button>
          <button className="ck-btn ck-btn-ghost ck-btn-sm ck-btn-icon" style={{ width: 28, height: 28 }} aria-label={`${t('dienstplan.new')} ${d.tag}`} onClick={onNeu}><Plus size={16} /></button>
        </span>}</div>
      {loading || !d.schichten ? <><Skeleton h={44} style={{ marginBottom: 6 }} /><Skeleton h={44} /></> :
        d.schichten.length === 0 ? <div className="ck-subtle ck-day-empty">{t('dienstplan.empty')}</div> : children}
    </section>
  );
}

function SchichtChip({ s, onOpen, onZiel, kompakt }) {
  const abw = istAbw(s);
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: `s|${s.id}`, data: s, disabled: abw });
  if (abw) return (
    <div className="ck-shift ck-shift-abw"><b>{kompakt ? '' : s.name}</b>
      <span className="ck-mini m-info">{s.objekt === 'Urlaub' ? <Palmtree size={13} /> : <Thermometer size={13} />}{s.objekt}</span></div>);
  return (
    <div className={`ck-shift ck-shift-btn ck-drag${isDragging ? ' is-dragging' : ''}`} data-schicht={s.id} ref={setNodeRef} {...attributes} {...listeners}
      role="button" tabIndex={0} aria-roledescription={t('dnd.aria')} onClick={() => onOpen(s)}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen(s); listeners?.onKeyDown?.(e); }}>
      {!kompakt && <b>{s.name}</b>}
      <span className="ck-num">{s.beginn}–{s.ende}</span> · {s.objekt}
      {s.fahrer && <span title={t('dienstplan.driver')} style={{ marginLeft: 6, verticalAlign: '-2px' }}><Car size={14} aria-label={t('dienstplan.driver')} /></span>}
      <button className="ck-shift-more" aria-label={t('dnd.menu')} title={t('dnd.menu')}
        onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()} onTouchStart={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onZiel(s); }}><MoveRight size={15} /></button>
    </div>
  );
}

function MatrixZelle({ eid, d, children, onNeu }) {
  const { setNodeRef, isOver } = useDroppable({ id: `zelle|${eid}|${d.datum}`, data: { datum: d.datum, employee_id: eid } });
  return (
    <td ref={setNodeRef} data-zelle={`${eid}|${d.datum}`} className={isOver ? 'is-over' : ''}>
      {children}
      <button className="ck-cell-add" aria-label={t('dienstplan.new')} onClick={onNeu}><Plus size={14} /></button>
    </td>);
}

function MatrixAnsicht({ tage, loading, mitarbeiter, heute, onOpen, onZiel, onNeu }) {
  const [nurMit, setNurMit] = useState(false);
  const zeilen = useMemo(() => {
    const map = new Map();
    (mitarbeiter || []).forEach((m) => map.set(m.id, { id: m.id, name: m.name, pnr: m.personal_nr, s: {} }));
    tage.forEach((d) => (d.schichten || []).forEach((s) => {
      if (!map.has(s.employee_id)) map.set(s.employee_id, { id: s.employee_id, name: s.name, pnr: s.personal_nr, s: {} });
      (map.get(s.employee_id).s[d.datum] ||= []).push({ ...s, datum: d.datum });
    }));
    return [...map.values()].filter((z) => !nurMit || Object.keys(z.s).length).sort((a, b) => a.name.localeCompare(b.name, 'de'));
  }, [tage, mitarbeiter, nurMit]);
  if (loading && !tage[0]?.schichten) return <div className="ck-card"><SkeletonRows n={6} /></div>;
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><Users size={20} />{t('dnd.view_staff')}</h2>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14, fontWeight: 500 }}>
          <input type="checkbox" checked={nurMit} onChange={(e) => setNurMit(e.target.checked)} style={{ width: 18, height: 18 }} />{t('dnd.only_with')}</label></div>
      <div className="ck-matrix-wrap">
        <table className="ck-matrix">
          <thead><tr><th scope="col">{t('zeiten.name')}</th>
            {tage.map((d) => <th key={d.datum} scope="col" className={d.datum === heute ? 'is-today' : ''}>{d.tag} <span className="ck-subtle">{fmtDate(d.datum)}</span></th>)}</tr></thead>
          <tbody>{zeilen.map((z) => (
            <tr key={z.id}><th scope="row"><Link className="ck-link" to={`/cockpit/mitarbeiter/${z.id}`}>{z.name}</Link><span className="ck-subtle">{z.pnr}</span></th>
              {tage.map((d) => (
                <MatrixZelle key={d.datum} eid={z.id} d={d} onNeu={() => onNeu(d.datum, z.id)}>
                  {(z.s[d.datum] || []).map((s) => <SchichtChip key={s.id} s={s} onOpen={onOpen} onZiel={onZiel} kompakt />)}
                </MatrixZelle>))}
            </tr>))}</tbody>
        </table>
      </div>
    </section>
  );
}

// "Verschieben/Kopieren nach ..." - Alternative zum Ziehen (vor allem auf Touch-Geraeten)
function ZielDialog({ s, mitarbeiter, onClose, onRun }) {
  const [datum, setDatum] = useState(s.datum);
  const [ma, setMa] = useState(String(s.employee_id));
  const [art, setArt] = useState('verschieben');
  const gleich = art === 'verschieben' && datum === s.datum && ma === String(s.employee_id);
  return (
    <Dialog title={t('dnd.menu_title')} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={gleich || !datum} onClick={() => onRun(datum, ma, art === 'kopieren')}>
        {art === 'kopieren' ? <><Copy size={16} />{t('dnd.do_copy')}</> : <><MoveRight size={16} />{t('dnd.do_move')}</>}</button></>}>
      <div className="ck-shift" style={{ margin: 0 }}><b>{s.name}</b><span className="ck-num">{fmtDate(s.datum, { weekday: 'short', day: '2-digit', month: '2-digit' })} · {s.beginn}–{s.ende}</span> · {s.objekt}</div>
      <div className="ck-seg" role="radiogroup" aria-label={t('dnd.menu_title')}>
        {['verschieben', 'kopieren'].map((k) => <button key={k} role="radio" aria-checked={art === k} className={art === k ? 'is-on' : ''} onClick={() => setArt(k)}>{t(`dnd.${k}`)}</button>)}
      </div>
      <label className="ck-field">{t('zeiten.date')}<input type="date" className="ck-input" value={datum} min={iso(new Date())} onChange={(e) => setDatum(e.target.value)} /></label>
      <label className="ck-field">{t('zeiten.name')}
        <select className="ck-input" value={ma} onChange={(e) => setMa(e.target.value)}>
          {!mitarbeiter.some((m) => String(m.id) === String(s.employee_id)) && <option value={s.employee_id}>{s.name}</option>}
          {mitarbeiter.map((m) => <option key={m.id} value={m.id}>{m.name} · {m.personal_nr}</option>)}</select></label>
      <p className="ck-subtle" style={{ margin: 0 }}>{t('dnd.menu_hint')}</p>
    </Dialog>
  );
}

// Kopieren mit Vorschau: Schicht duplizieren, Tag kopieren, Woche in naechste Woche oder Zeitraum
function KopierDialog({ modus, tag, schicht, wochenStart, tage, mitarbeiter, onClose, onDone }) {
  const [f, setF] = useState(() => modus === 'woche' ? { zielArt: 'naechste', ziel_von: addDays(wochenStart, 7), ziel_bis: addDays(wochenStart, 27) }
    : modus === 'tag' ? { quelle: tag, ziel_von: addDays(tag, 7), ziel_bis: addDays(tag, 7), mehrere: false }
    : { ziel_von: addDays(schicht.datum, 1), ziel_bis: addDays(schicht.datum, 1), mehrere: false, employee_id: String(schicht.employee_id) });
  const [vor, setVor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [nurKonf, setNurKonf] = useState(false);
  const set = (k, v) => { setF((x) => ({ ...x, [k]: v })); setVor(null); setErr(''); };
  const body = () => modus === 'woche'
    ? { quelle_von: wochenStart, quelle_bis: addDays(wochenStart, 6), ziel_von: f.zielArt === 'naechste' ? addDays(wochenStart, 7) : f.ziel_von, ziel_bis: f.zielArt === 'naechste' ? undefined : f.ziel_bis }
    : modus === 'tag' ? { quelle_von: f.quelle, ziel_von: f.ziel_von, ziel_bis: f.mehrere ? f.ziel_bis : undefined }
    : { schicht_ids: [schicht.id], ziel_von: f.ziel_von, ziel_bis: f.mehrere ? f.ziel_bis : undefined, employee_id: Number(f.employee_id) };
  const vorschau = async () => {
    setBusy(true); setErr('');
    try { setVor((await api.post('/dienstplan/kopieren', { ...body(), vorschau: true })).data); } catch (e) { setErr(apiError(e)); }
    setBusy(false);
  };
  const anlegen = async () => {
    setBusy(true); setErr('');
    try {
      const r = (await api.post('/dienstplan/kopieren', { ...body(), vorschau: false })).data;
      onDone(r, t('kopie.done', { n: r.angelegt, s: r.uebersprungen, von: fmtDate(r.ziel_von), bis: fmtDate(r.ziel_bis) }));
    } catch (e) { setErr(apiError(e)); setBusy(false); }
  };
  const titel = t(`kopie.title_${modus}`);
  const zeilen = (vor?.eintraege || []).filter((e) => !nurKonf || e.status !== 'ok');
  return (
    <Dialog title={titel} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      {!vor ? <button className="ck-btn ck-btn-primary" disabled={busy} onClick={vorschau}><CalendarRange size={16} />{busy ? t('app.loading') : t('kopie.preview')}</button>
        : <button className="ck-btn ck-btn-primary" disabled={busy || !vor.anzulegen} onClick={anlegen}><CopyPlus size={16} />{t('kopie.create', { n: vor.anzulegen })}</button>}</>}>
      {modus === 'woche' && (<>
        <div className="ck-subtle">{t('kopie.source_week', { von: fmtDate(wochenStart), bis: fmtDate(addDays(wochenStart, 6)), n: tage.reduce((a, d) => a + (d.schichten || []).filter((s) => !istAbw(s)).length, 0) })}</div>
        <div className="ck-seg" role="radiogroup">
          {['naechste', 'zeitraum'].map((k) => <button key={k} role="radio" aria-checked={f.zielArt === k} className={f.zielArt === k ? 'is-on' : ''} onClick={() => set('zielArt', k)}>{t(`kopie.target_${k}`)}</button>)}
        </div>
        {f.zielArt === 'zeitraum' && <div className="ck-two-inputs">
          <label className="ck-field">{t('kopie.from')}<input type="date" className="ck-input" value={f.ziel_von} onChange={(e) => set('ziel_von', e.target.value)} /></label>
          <label className="ck-field">{t('kopie.to')}<input type="date" className="ck-input" value={f.ziel_bis} onChange={(e) => set('ziel_bis', e.target.value)} /></label></div>}
        {f.zielArt === 'zeitraum' && <p className="ck-subtle" style={{ margin: 0 }}>{t('kopie.repeat_week')}</p>}
      </>)}
      {modus === 'tag' && (
        <label className="ck-field">{t('kopie.source_day')}
          <select className="ck-input" value={f.quelle} onChange={(e) => set('quelle', e.target.value)}>
            {tage.filter((d) => d.schichten).map((d) => <option key={d.datum} value={d.datum}>{d.tag} {fmtDate(d.datum)} · {t('kopie.n_shifts', { n: d.schichten.filter((s) => !istAbw(s)).length })}</option>)}</select></label>)}
      {modus === 'schicht' && (<>
        <div className="ck-shift" style={{ margin: 0 }}><b>{schicht.name}</b><span className="ck-num">{fmtDate(schicht.datum, { weekday: 'short', day: '2-digit', month: '2-digit' })} · {schicht.beginn}–{schicht.ende}</span> · {schicht.objekt}</div>
        <label className="ck-field">{t('kopie.target_staff')}
          <select className="ck-input" value={f.employee_id} onChange={(e) => set('employee_id', e.target.value)}>
            {!mitarbeiter.some((m) => String(m.id) === String(schicht.employee_id)) && <option value={schicht.employee_id}>{schicht.name}</option>}
            {mitarbeiter.map((m) => <option key={m.id} value={m.id}>{m.name} · {m.personal_nr}</option>)}</select></label>
      </>)}
      {modus !== 'woche' && (<>
        <div className="ck-two-inputs">
          <label className="ck-field">{f.mehrere ? t('kopie.from') : t('kopie.target_day')}<input type="date" className="ck-input" value={f.ziel_von} onChange={(e) => set('ziel_von', e.target.value)} /></label>
          {f.mehrere && <label className="ck-field">{t('kopie.to')}<input type="date" className="ck-input" value={f.ziel_bis} onChange={(e) => set('ziel_bis', e.target.value)} /></label>}
        </div>
        <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontWeight: 500 }}>
          <input type="checkbox" checked={f.mehrere} onChange={(e) => set('mehrere', e.target.checked)} style={{ width: 20, height: 20 }} />{t('kopie.several_days')}</label>
      </>)}

      {vor && (
        <div className="ck-kopie-vorschau">
          <div className="ck-kopie-sum">
            <Status s="approved" label={t('kopie.will_create', { n: vor.anzulegen })} />
            {vor.uebersprungen > 0 && <Status s="fehlt" label={t('kopie.will_skip', { n: vor.uebersprungen })} />}
            <span className="ck-subtle">{fmtDate(vor.ziel_von)}–{fmtDate(vor.ziel_bis)}</span>
            {vor.uebersprungen > 0 && <label style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center', fontSize: 14 }}>
              <input type="checkbox" checked={nurKonf} onChange={(e) => setNurKonf(e.target.checked)} />{t('kopie.only_conflicts')}</label>}
          </div>
          {vor.eintraege.length === 0 ? <div className="ck-subtle">{t('kopie.nothing')}</div> : (
            <ul className="ck-list ck-kopie-list">{zeilen.map((e, i) => (
              <li key={i} className={`ck-kopie-row${e.status !== 'ok' ? ' is-skip' : ''}`}>
                <span className="ck-num">{e.tag} {fmtDate(e.datum)}</span>
                <span><b>{e.name}</b> · {e.objekt} · <span className="ck-num">{e.beginn}–{e.ende}</span></span>
                {e.status === 'ok' ? <Status s="approved" label={t('kopie.st_ok')} />
                  : e.status === 'abwesend' ? <Status s={e.grund === 'Krank' ? 'krank' : 'urlaub'} label={t('kopie.st_skip', { grund: e.grund })} />
                  : <Status s="fehlt" label={t('kopie.st_skip', { grund: e.grund })} />}
              </li>))}</ul>)}
        </div>)}
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>
  );
}

export function SchichtDialog({ id, neu, onClose, onDone, onDuplizieren, onZiel }) {
  const { toast } = useApp();
  const { data: aus } = useApi('/auswahl');
  const [f, setF] = useState(neu || null);
  const [orig, setOrig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => { if (id) api.get(`/schicht/${id}`).then((r) => { setF(r.data); setOrig(r.data); }).catch((e) => setErr(apiError(e))); }, [id]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const body = schichtBody;
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
      {id && orig && onZiel && <button className="ck-btn" onClick={() => onZiel({ ...orig, objekt: orig.objekt })}><MoveRight size={16} />{t('dnd.menu')}</button>}
      {id && orig && onDuplizieren && <button className="ck-btn" onClick={() => onDuplizieren(orig)}><Copy size={16} />{t('kopie.duplicate')}</button>}
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
