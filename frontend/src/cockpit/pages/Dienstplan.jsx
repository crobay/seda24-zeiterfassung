import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DndContext, DragOverlay, MouseSensor, TouchSensor, KeyboardSensor, useSensor, useSensors, useDraggable, useDroppable, pointerWithin, rectIntersection } from '@dnd-kit/core';
import { ChevronLeft, ChevronRight, Car, Pencil, Plus, Trash2, AlertTriangle, Palmtree, Thermometer, Copy, CopyPlus, MoveRight, Undo2, X, CalendarRange, Users, Rows3, Hand, CalendarPlus, CircleDashed, UserPlus, Search, CheckCircle2, RotateCcw, Scale } from 'lucide-react';
import { api, apiError, t, fmtDate, useApi, useApp, SkeletonRows, ErrorBox, Skeleton, Dialog, Status, ObjektMarke } from '../core';

const ScheduleTab = lazy(() => import('../../components/ScheduleTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const addDays = (isoD, n) => { const d = new Date(isoD + 'T12:00:00'); d.setDate(d.getDate() + n); return iso(d); };
export const schichtBody = (x) => ({ employee_id: Number(x.employee_id), object_id: Number(x.object_id), datum: x.datum, beginn: x.beginn, ende: x.ende, fahrer: !!x.fahrer });
// Ablegen dort, wo Zeiger/Finger ist (nicht nach groesster Ueberdeckung der gezogenen Karte); Tastatur: Ueberdeckung
export const zielErkennung = (args) => { const p = pointerWithin(args); return p.length ? p : rectIntersection(args); };
const istAbw = (s) => s.objekt === 'Urlaub' || s.objekt === 'Krank';
const wtag = (isoD) => (new Date(isoD + 'T12:00:00').getDay() + 6) % 7;
const dauer = (b, e) => { if (!b || !e) return 0; const [bh, bm] = b.split(':').map(Number); const [eh, em] = e.split(':').map(Number); return (((eh * 60 + em) - (bh * 60 + bm) + 1440) % 1440 || 1440) / 60; };
const fmtH = (h) => String(Math.round(h * 100) / 100).replace('.', ',');

// Strg/Alt/Cmd waehrend des Ziehens = kopieren (Tastatur und Zeiger liefern den Zustand)
export function useCopyModifier() {
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
  const { data: vorlage } = useApi('/vorlage');
  const [vlDialog, setVlDialog] = useState(() => params.get('vorlage') === '1');
  const monat = (data?.start || start).slice(0, 7);
  const konto = useApi(`/kontingent?monat=${monat}`);
  const shift = (days) => { const d = new Date((data?.start || start) + 'T12:00:00'); d.setDate(d.getDate() + days); setStart(iso(d)); };
  const today = iso(new Date());
  const wochenStart = data?.start || start;
  useEffect(() => { localStorage.setItem('ck_dp_ansicht', ansicht); }, [ansicht]);
  // Aus der Freitags-Meldung "Plan öffnen" (?luecken=1): direkt zur ersten Lücke springen und alle Lücken hervorheben
  const zuLuecken = params.get('luecken') === '1';
  useEffect(() => {
    if (!zuLuecken || !data) return;
    const alle = document.querySelectorAll('[data-luecke]');
    alle.forEach((el) => el.classList.add('is-hervor'));
    if (alle[0]) alle[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [zuLuecken, data]);

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
    konto.reload();
  };
  const neuLaden = () => { reload(); konto.reload(); };

  // Einplanen aus der Mitarbeiter-Leiste: Objekt/Zeit aus der Luecke, sonst aus der Vorlage dieses MA fuer den Wochentag
  const vorbelegen = (eid, datum, luecke) => {
    if (luecke) return { datum, employee_id: String(eid), object_id: String(luecke.object_id), beginn: luecke.beginn, ende: luecke.ende, fahrer: luecke.fahrer };
    const v = (vorlage?.eintraege || []).find((e) => e.employee_id === Number(eid) && e.wochentag === wtag(datum));
    return { datum, employee_id: String(eid), object_id: v ? String(v.object_id) : '', beginn: v?.beginn || '', ende: v?.ende || '', fahrer: v ? v.fahrer : true };
  };
  const einplanen = (eid) => {
    const lu = (data?.tage || []).flatMap((d) => d.luecken || [])[0];
    const tag = lu ? lu.datum : ((data?.tage || []).find((d) => d.datum >= today)?.datum || wochenStart);
    setEdit({ neu: vorbelegen(eid, tag, lu) });
  };
  const fertigMelden = async (fertig) => {
    try { await api.post('/dienstplan/fertig', { woche: wochenStart, fertig }); toast(t(fertig ? 'plan.marked_done' : 'plan.reopened')); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
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
    if (s.typ === 'ma') { setEdit({ neu: vorbelegen(s.employee_id, z.datum, z.luecke) }); return; }   // danach nur noch Speichern
    ausfuehren(s, z.datum, z.employee_id || s.employee_id, copyRef.current);
  };
  const oeffnen = (s) => { if (!justDragged.current && !istAbw(s)) setEdit({ id: s.id }); };

  const ungeplant = !!data?.plan?.ungeplant;   // noch nichts aus der Vorlage eingeplant: Hinweis statt einzelner Luecken
  const tage = (data?.tage || Array.from({ length: 7 }).map((_, i) => ({ tag: '', datum: String(i), schichten: null }))).map((d) => (ungeplant ? { ...d, luecken: [] } : d));
  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('dienstplan.title')}</h1><p>{data ? t('dienstplan.subtitle', { date: fmtDate(data.start, { day: 'numeric', month: 'long', year: 'numeric' }) }) : <Skeleton w={180} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(-7)} aria-label={t('dienstplan.prev')}><ChevronLeft size={18} /></button>
          <button className="ck-btn" onClick={() => setStart(today)}>{t('dienstplan.today')}</button>
          <button className="ck-btn ck-btn-icon" onClick={() => shift(7)} aria-label={t('dienstplan.next')}><ChevronRight size={18} /></button>
          <button className="ck-btn" disabled={!data} onClick={() => setVlDialog(true)}><CalendarPlus size={16} />{t('plan.from_template')}</button>
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

      {data?.plan && !classic && data.start >= addDays(today, -6) && <PlanStatus p={data.plan} onFertig={fertigMelden} onVorlage={() => setVlDialog(true)} onFixumWeg={rueckgaengig} />}

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
        <DndContext sensors={sensors} collisionDetection={zielErkennung} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDrag(null)} autoScroll={drag?.typ !== 'ma' || window.innerWidth < 1100}>
          <div className="ck-dp-layout">
          {/* Leiste bleibt am PC stehen (sticky); dort beim Ziehen aus der Leiste kein automatisches Mitscrollen, sonst verrutscht das Ziel */}
          <aside className="ck-dp-aside">
            {(konto.data?.personen || []).map((p) => <KontingentKarte key={p.employee_id} p={p} onDone={(r, text) => { kopiert(r, text); reload(); }} />)}
            <MaLeiste mitarbeiter={aus?.mitarbeiter} tage={data?.tage} vorlage={vorlage} onAdd={einplanen} />
          </aside>
          <div className={`ck-dp-main${busy ? ' ck-dp-busy' : ''}`}>
            {ansicht === 'tage' ? (
              <div className="ck-week">
                {tage.map((d) => (
                  <TagSpalte key={d.datum} d={d} heute={today} markiert={params.get('tag')} loading={loading}
                    onNeu={() => setEdit({ neu: { datum: d.datum, beginn: '', ende: '', employee_id: '', object_id: '', fahrer: true } })}
                    onTagKopieren={() => setKopie({ modus: 'tag', tag: d.datum })}>
                    {d.schichten?.map((s) => <SchichtChip key={s.id} s={{ ...s, datum: d.datum }} onOpen={oeffnen} onZiel={setZiel} />)}
                    {(d.luecken || []).map((l) => <LueckeChip key={`${l.vorlage_id}`} l={l} onOpen={() => setEdit({ neu: { ...vorbelegen('', l.datum, l), employee_id: '' } })} />)}
                  </TagSpalte>))}
              </div>
            ) : <MatrixAnsicht tage={tage} loading={loading} mitarbeiter={aus?.mitarbeiter} heute={today} onOpen={oeffnen} onZiel={setZiel}
                  onLuecke={(l) => setEdit({ neu: { ...vorbelegen('', l.datum, l), employee_id: '' } })}
                  onNeu={(datum, eid) => setEdit({ neu: vorbelegen(eid, datum) })} />}
          </div>
          </div>
          <DragOverlay dropAnimation={null}>
            {drag ? <div className={`ck-shift ck-shift-drag${copyOn ? ' is-copy' : ''}`}>
              <span className="ck-drag-mode">{copyOn ? <><Copy size={13} />{t('dnd.mode_copy')}</> : <><MoveRight size={13} />{t('dnd.mode_move')}</>}</span>
              {drag.typ === 'ma' ? <><UserPlus size={15} /> <b>{drag.name}</b></> : <><b>{drag.name}</b><span className="ck-num">{drag.beginn}–{drag.ende}</span> · <ObjektMarke id={drag.object_id} name={drag.objekt} size="xs" /></>}</div> : null}
          </DragOverlay>
        </DndContext>
      )}
      {vlDialog && <VorlageWocheDialog woche={wochenStart} onClose={() => setVlDialog(false)}
        onDone={(r, text) => { setVlDialog(false); if (r.start) setStart(r.start); kopiert(r, text); reload(); }} />}
      {edit && <SchichtDialog id={edit.id} neu={edit.neu} onClose={close} onDone={() => { close(); neuLaden(); }}
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
        d.schichten.length === 0 && !(d.luecken || []).length ? <div className="ck-subtle ck-day-empty">{t('dienstplan.empty')}</div> : children}
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
      <span className="ck-num">{s.beginn}–{s.ende}</span> · <ObjektMarke id={s.object_id} name={s.objekt} size="xs" />
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

function MatrixAnsicht({ tage, loading, mitarbeiter, heute, onOpen, onZiel, onNeu, onLuecke }) {
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
          <tbody>{tage.some((d) => (d.luecken || []).length) && (
            <tr className="ck-gap-row"><th scope="row"><CircleDashed size={15} /> {t('plan.gaps_row')}</th>
              {tage.map((d) => <td key={d.datum}>{(d.luecken || []).map((l) => <LueckeChip key={l.vorlage_id} l={l} onOpen={() => onLuecke(l)} kompakt />)}</td>)}</tr>)}
            {zeilen.map((z) => (
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
      <div className="ck-shift" style={{ margin: 0 }}><b>{s.name}</b><span className="ck-num">{fmtDate(s.datum, { weekday: 'short', day: '2-digit', month: '2-digit' })} · {s.beginn}–{s.ende}</span> · <ObjektMarke id={s.object_id} name={s.objekt} size="xs" /></div>
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
        <div className="ck-shift" style={{ margin: 0 }}><b>{schicht.name}</b><span className="ck-num">{fmtDate(schicht.datum, { weekday: 'short', day: '2-digit', month: '2-digit' })} · {schicht.beginn}–{schicht.ende}</span> · <ObjektMarke id={schicht.object_id} name={schicht.objekt} size="xs" /></div>
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
                <span><b>{e.name}</b> · <ObjektMarke id={e.object_id} name={e.objekt} size="xs" /> · <span className="ck-num">{e.beginn}–{e.ende}</span></span>
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

// Status der angezeigten Planwoche: offen/fertig, offene Luecken, Abgabe Freitag 12:00
function PlanStatus({ p, onFertig, onVorlage, onFixumWeg }) {
  if (p.ungeplant && !p.fertig) return (
    <div className="ck-callout ck-plan-status" role="status">
      <Status s="fehlt" label={t('plan.status_open')} />
      <span className="ck-plan-facts"><span><CircleDashed size={15} />{t('plan.unplanned', { n: p.soll })}</span>
        <span className="ck-subtle">{t('plan.due', { date: fmtDate(p.abgabe.slice(0, 10), { weekday: 'short', day: '2-digit', month: '2-digit' }) })}</span></span>
      <button className="ck-btn ck-btn-sm ck-btn-primary" onClick={onVorlage}><CalendarPlus size={15} />{t('plan.title')}</button>
    </div>);
  const lu = p.luecken === 1 ? t('plan.n_gaps_1') : p.luecken ? t('plan.n_gaps', { n: p.luecken }) : t('plan.no_gaps');
  return (
    <div className={`ck-callout ck-plan-status${p.fertig ? ' is-done' : ''}`} role="status">
      {p.fertig ? <Status s="approved" label={t('plan.status_done')} /> : <Status s="fehlt" label={t('plan.status_open')} />}
      <span className="ck-plan-facts">
        <span>{p.luecken ? <CircleDashed size={15} /> : <CheckCircle2 size={15} />}{lu}</span>
        <span>{t('plan.n_shifts', { n: p.schichten })}</span>
        {p.fertig ? <span className="ck-subtle">{t('plan.done_by', { wer: p.gemeldet_von, am: fmtDate(p.gemeldet_am.slice(0, 10)) + ' ' + p.gemeldet_am.slice(11, 16) })}</span>
          : <span className="ck-subtle">{t('plan.due', { date: fmtDate(p.abgabe.slice(0, 10), { weekday: 'short', day: '2-digit', month: '2-digit' }) })}</span>}
      </span>
      {p.fertig ? <button className="ck-btn ck-btn-sm" onClick={() => onFertig(false)}><RotateCcw size={15} />{t('plan.reopen')}</button>
        : <button className="ck-btn ck-btn-sm ck-btn-primary" onClick={() => onFertig(true)}><CheckCircle2 size={15} />{t('plan.mark_done')}</button>}
      {p.fixum && <div className="ck-plan-fixum" data-fixum>
        <CalendarPlus size={15} /><span>{p.fixum.zurueckgenommen ? t('plan.fixum_undone', { am: fmtDate(p.fixum.zurueckgenommen.slice(0, 10), { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' + p.fixum.zurueckgenommen.slice(11, 16) })
          : t(p.fertig ? 'plan.fixum_info' : 'plan.fixum_draft', { n: p.fixum.angelegt, am: fmtDate(p.fixum.am.slice(0, 10), { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' + p.fixum.am.slice(11, 16) })}</span>
        {!p.fertig && !p.fixum.zurueckgenommen && p.fixum.kopie_id && p.fixum.angelegt > 0 && <button className="ck-btn ck-btn-sm ck-btn-ghost" onClick={() => onFixumWeg(p.fixum.kopie_id)}><Undo2 size={15} />{t('plan.fixum_undo')}</button>}
      </div>}
    </div>);
}

// Offene Luecke (Vorlage-Schicht ohne Besetzung): anklicken = einplanen, Mitarbeiter darauf ziehen = einplanen
function LueckeChip({ l, onOpen, kompakt }) {
  const { setNodeRef, isOver } = useDroppable({ id: `l|${l.vorlage_id}|${l.datum}`, data: { datum: l.datum, luecke: l } });
  return (
    <button ref={setNodeRef} className={`ck-shift ck-gap${isOver ? ' is-over' : ''}`} data-luecke={`${l.vorlage_id}|${l.datum}`} onClick={onOpen}
      title={t('plan.gap_title', { objekt: l.objekt, zeit: `${l.beginn}–${l.ende}` })}>
      <span className="ck-gap-tag"><CircleDashed size={13} />{t('plan.gap')}</span>
      <span className="ck-num">{l.beginn}–{l.ende}</span>{!kompakt ? <> · <ObjektMarke id={l.object_id} name={l.objekt} size="xs" /></> : <ObjektMarke id={l.object_id} name={l.objekt} ohneName />}
      <span className="ck-gap-why">{t('plan.gap_reason', { name: l.name.split(' ')[0], grund: l.grund })}</span>
    </button>);
}

// Mitarbeiter-Seitenleiste: ziehen auf Tag/Zelle/Luecke oder "+ einplanen" (danach nur noch Speichern)
function MaLeiste({ mitarbeiter, tage, vorlage, onAdd }) {
  const [q, setQ] = useState('');
  const std = useMemo(() => {
    const m = {};
    (tage || []).forEach((d) => (d.schichten || []).forEach((s) => { if (!istAbw(s)) m[s.employee_id] = (m[s.employee_id] || 0) + dauer(s.beginn, s.ende); }));
    return m;
  }, [tage]);
  const liste = (mitarbeiter || []).filter((m) => !q || `${m.name} ${m.personal_nr}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <section className="ck-card ck-ma-leiste" aria-labelledby="ml-h">
      <div className="ck-card-head"><h2 id="ml-h"><UserPlus size={18} />{t('leiste.title')}</h2>
        <label className="ck-search-field"><Search size={16} /><input className="ck-input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('leiste.search')} aria-label={t('leiste.search')} /></label></div>
      <div className="ck-ma-leiste-body">
        <p className="ck-subtle ck-ma-hint">{t('leiste.hint')}</p>
        {liste.length === 0 ? <div className="ck-subtle">{t('leiste.none')}</div> : (
          <ul className="ck-ma-list">{liste.map((m) => <MaItem key={m.id} m={m} h={std[m.id] || 0} vh={vorlage?.wochenstunden?.[m.id]} onAdd={onAdd} />)}</ul>)}
      </div>
    </section>);
}

function MaItem({ m, h, vh, onAdd }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: `ma|${m.id}`, data: { typ: 'ma', employee_id: m.id, name: m.name } });
  return (
    <li className={`ck-ma-item ck-drag${isDragging ? ' is-dragging' : ''}`} ref={setNodeRef} {...attributes} {...listeners} data-ma={m.id} aria-roledescription={t('dnd.aria')}>
      <span className="ck-ma-name"><b>{m.name}</b>
        <span className="ck-subtle">{t('leiste.week_h', { h: fmtH(h) })}{vh ? ` · ${t('leiste.tpl_h', { h: fmtH(vh) })}` : ''}</span></span>
      <button className="ck-btn ck-btn-sm" onPointerDown={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()} onTouchStart={(e) => e.stopPropagation()}
        onClick={(e) => { e.stopPropagation(); onAdd(m.id); }} aria-label={`${m.name} ${t('leiste.add')}`}><Plus size={15} />{t('leiste.add')}</button>
    </li>);
}

// Monatskontingent (Festgehalt): Soll / verplant / Rest; Sonntage kommen aus der Sonntagsautomatik
function KontingentKarte({ p, onDone }) {
  const [verteilen, setVerteilen] = useState(false);
  const mon = new Date(p.monat + '-15T12:00:00').toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  const pct = (h) => `${Math.max(0, Math.min(100, (h / (p.soll || 1)) * 100))}%`;
  return (
    <section className="ck-card ck-konto" aria-label={t('konto.title', { monat: mon })}>
      <div className="ck-card-head"><h2><Scale size={18} />{t('konto.title', { monat: mon })}</h2></div>
      <div className="ck-card-body" style={{ display: 'grid', gap: 10 }}>
        <div><b>{p.name}</b> <span className="ck-subtle">· {t('konto.fixed_salary')} {fmtH(p.soll)} h</span></div>
        <div className="ck-konto-bar" role="img" aria-label={`${t('konto.sundays')} ${fmtH(p.sonntag_stunden)} h, ${t('konto.weekdays')} ${fmtH(p.werktag_stunden)} h, ${t('konto.rest')} ${fmtH(p.rest)} h`}>
          <i className="k-so" style={{ width: pct(p.sonntag_stunden) }} /><i className="k-wt" style={{ width: pct(p.werktag_stunden) }} /></div>
        <dl className="ck-konto-zahlen">
          <div><dt>{t('konto.soll')}</dt><dd className="ck-num">{fmtH(p.soll)} h</dd></div>
          <div><dt><i className="k-dot k-so" />{t('konto.sundays')}</dt><dd className="ck-num">{fmtH(p.sonntag_stunden)} h</dd></div>
          <div><dt><i className="k-dot k-wt" />{t('konto.weekdays')}</dt><dd className="ck-num">{fmtH(p.werktag_stunden)} h</dd></div>
          <div className={p.rest < 0 ? 'is-warn' : ''}><dt><i className="k-dot k-rest" />{p.rest < 0 ? t('konto.over') : t('konto.rest')}</dt><dd className="ck-num">{fmtH(Math.abs(p.rest))} h</dd></div>
        </dl>
        {p.sonntage.length > 0 && <div className="ck-subtle" style={{ fontSize: 13 }}>
          {t('konto.sundays')}: {p.sonntage.map((x) => fmtDate(x.datum)).join(', ')} · {t('konto.sunday_auto')}{p.sonntage.some((x) => !x.angelegt) ? ` (${t('konto.sunday_pending')})` : ''}</div>}
        {p.rest > 0 && <button className="ck-btn ck-btn-sm" onClick={() => setVerteilen(true)}><Scale size={15} />{t('konto.distribute')}</button>}
      </div>
      {verteilen && <VerteilenDialog p={p} onClose={() => setVerteilen(false)} onDone={(r, text) => { setVerteilen(false); onDone(r, text); }} />}
    </section>);
}

function VerteilenDialog({ p, onClose, onDone }) {
  const [vor, setVor] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api.post('/kontingent/verteilen', { employee_id: p.employee_id, monat: p.monat, vorschau: true }).then((r) => setVor(r.data)).catch((e) => setError(apiError(e)));
  }, [p.employee_id, p.monat]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const anlegen = async () => {
    setBusy(true);
    try {
      const r = (await api.post('/kontingent/verteilen', { employee_id: p.employee_id, monat: p.monat, vorschau: false })).data;
      onDone(r, t('konto.distributed', { n: r.angelegt, name: p.name }));
    } catch (x) { setErr(apiError(x)); setBusy(false); }
  };
  return (
    <Dialog title={t('konto.distribute_title')} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={busy || !vor?.anzulegen} onClick={anlegen}><CalendarPlus size={16} />{t('kopie.create', { n: vor?.anzulegen || 0 })}</button></>}>
      {!vor && !error ? <SkeletonRows n={4} /> : error ? <div className="ck-callout"><AlertTriangle size={18} />{error}</div> : (<>
        <p className="ck-subtle" style={{ margin: 0 }}>{vor.hinweis || t('konto.distribute_hint', { h: fmtH(vor.rest), n: vor.tage })}</p>
        <VorschauListe vor={vor} />
      </>)}
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>);
}

function VorschauListe({ vor, lueckeText }) {
  if (!vor.eintraege?.length) return null;
  return (
    <div className="ck-kopie-vorschau">
      <div className="ck-kopie-sum"><Status s="approved" label={t('kopie.will_create', { n: vor.anzulegen })} />
        {vor.luecken > 0 && <Status s="urlaub" label={t('plan.will_gap', { n: vor.luecken })} />}
        {vor.uebersprungen - (vor.luecken || 0) > 0 && <Status s="fehlt" label={t('kopie.will_skip', { n: vor.uebersprungen - (vor.luecken || 0) })} />}</div>
      <ul className="ck-list ck-kopie-list">{vor.eintraege.map((e, i) => (
        <li key={i} className={`ck-kopie-row${e.status !== 'ok' ? ' is-skip' : ''}`}>
          <span className="ck-num">{e.tag} {fmtDate(e.datum)}</span>
          <span><b>{e.name}</b> · <ObjektMarke id={e.object_id} name={e.objekt} size="xs" /> · <span className="ck-num">{e.beginn}–{e.ende}</span>{e.status === 'ok' && !lueckeText ? <span className="ck-subtle"> · {fmtH(dauer(e.beginn, e.ende))} h</span> : null}</span>
          {e.status === 'ok' ? <Status s="approved" label={t('kopie.st_ok')} />
            : e.status === 'abwesend' ? <Status s={e.grund === 'Krank' ? 'krank' : 'urlaub'} label={lueckeText ? t('plan.st_gap', { grund: e.grund }) : t('kopie.st_skip', { grund: e.grund })} />
            : <Status s="fehlt" label={t('kopie.st_skip', { grund: e.grund })} />}
        </li>))}</ul>
    </div>);
}

// Woche nur aus der Vorlage erzeugen: Vorschau -> anlegen -> Rueckgaengig fuer den ganzen Vorgang
function VorlageWocheDialog({ woche, onClose, onDone }) {
  const heute = new Date(); const mo = new Date(heute); mo.setHours(12); mo.setDate(heute.getDate() - ((heute.getDay() + 6) % 7));
  const diese = iso(mo); const naechste = addDays(diese, 7);
  const [w, setW] = useState(woche > diese ? woche : naechste);
  const [vor, setVor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const laden = async (x) => {
    setBusy(true); setErr(''); setVor(null);
    try { setVor((await api.post('/dienstplan/aus-vorlage', { woche: x, vorschau: true })).data); } catch (e) { setErr(apiError(e)); }
    setBusy(false);
  };
  useEffect(() => { laden(w); }, [w]); // eslint-disable-line
  const anlegen = async () => {
    setBusy(true);
    try {
      const r = (await api.post('/dienstplan/aus-vorlage', { woche: w, vorschau: false })).data;
      onDone({ ...r, start: w }, t('plan.done', { n: r.angelegt, l: r.luecken }));
    } catch (e) { setErr(apiError(e)); setBusy(false); }
  };
  return (
    <Dialog title={t('plan.title')} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={busy || !vor?.anzulegen} onClick={anlegen}><CalendarPlus size={16} />{t('kopie.create', { n: vor?.anzulegen || 0 })}</button></>}>
      <p className="ck-subtle" style={{ margin: 0 }}>{t('plan.hint')}</p>
      <div className="ck-seg" role="radiogroup" aria-label={t('plan.week')}>
        {[[diese, 'this_week'], [naechste, 'next_week']].map(([x, k]) => <button key={k} role="radio" aria-checked={w === x} className={w === x ? 'is-on' : ''} onClick={() => setW(x)}>{t(`plan.${k}`)}</button>)}
        {w !== diese && w !== naechste && <button role="radio" aria-checked className="is-on">{fmtDate(w)}</button>}
      </div>
      <div className="ck-subtle">{fmtDate(w, { weekday: 'short', day: '2-digit', month: '2-digit' })} – {fmtDate(addDays(w, 6), { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })}</div>
      {busy && !vor && <SkeletonRows n={4} />}
      {vor && (vor.eintraege.length ? <VorschauListe vor={vor} lueckeText /> : <div className="ck-subtle">{t('kopie.nothing')}</div>)}
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}
        {/leer/.test(err) && <Link className="ck-link" style={{ marginLeft: 8 }} to="/cockpit/vorlage">{t('plan.to_template')}</Link>}</div>}
    </Dialog>);
}
