import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Clock3, ArrowUpDown, ArrowUp, ArrowDown, ClipboardCheck, Plus, Pencil, Trash2, AlertTriangle, X, Moon, ChevronLeft, ChevronRight, Lock } from 'lucide-react';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, SkeletonRows, Empty, ErrorBox, Skeleton, Dialog, ObjektMarke } from '../core';

const GenehmigungenTab = lazy(() => import('../../pages/GenehmigungenTab'));
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
// Verspaetet uebertragen (offline nachgereicht, Drazen 24.11.2026): unter der Zeit immer sichtbar klein, grau
// "📶 +3:40 h verspätet"; am PC Tooltip mit Handy-/Server-Zeit
const VerspKurz = ({ r, art }) => {
  const v = (r.verspaetet || []).find((x) => x.art === art);
  return v ? <div className="ck-subtle" title={v.text} onClick={(e) => e.stopPropagation()} style={{ fontSize: '75%', fontWeight: 400, whiteSpace: 'nowrap', lineHeight: 1.3, cursor: 'help' }} data-versp-kurz={art}>{v.kurz}</div> : null;
};
const COLS = [['datum', 'zeiten.date'], ['name', 'zeiten.name'], ['objekt', 'zeiten.object'], ['kommen', 'zeiten.in'], ['gehen', 'zeiten.out'], ['stunden', 'zeiten.hours'], ['weg', 'zeiten.way'], ['hinweis', 'zeiten.hint']];

export default function Zeiten() {
  const { me, toast } = useApp();
  const [params, setParams] = useSearchParams();
  const pruef = params.get('pruef');
  const monat = params.get('monat');
  const range = params.get('range') || 'week';
  const [classic, setClassic] = useState(false);
  const now = new Date();
  // Monat blaettern (‹ Oktober 2026 ›): ?monat=JJJJ-MM, sonst laufender Monat. "Monat" = ganzer Monat (laufender bis heute),
  // "7 Tage" = die letzten 7 Tage des Monats (laufender: bis heute). ?von=&bis= (Deep-Link aus dem Monatsabschluss) geht vor.
  const aktM = iso(now).slice(0, 7);
  const m = monat || aktM;
  const [my, mm] = m.split('-').map(Number);
  const ende = m >= aktM ? now : new Date(my, mm, 0);
  const von = range === 'week' ? iso(new Date(ende.getFullYear(), ende.getMonth(), ende.getDate() - 6)) : `${m}-01`;
  const path = pruef ? `/zeiten?pruef=${pruef}&monat=${m}`
    : params.get('von') && params.get('bis') && !monat ? `/zeiten?von=${params.get('von')}&bis=${params.get('bis')}` : `/zeiten?von=${von}&bis=${iso(ende)}`;
  const blaettern = (n) => {
    const d = new Date(my, mm - 1 + n, 1);
    const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    const x = new URLSearchParams(params); x.set('monat', k); x.delete('von'); x.delete('bis'); x.delete('eintrag'); x.delete('neu');
    setParams(x, { replace: true });
  };
  const monatName = new Date(my, mm - 1, 15).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  const { data, loading, error, reload } = useApi(path);
  const [q, setQ] = useState(() => params.get('q') || '');
  const [onlyHint, setOnlyHint] = useState(false);
  const [sort, setSort] = useState({ k: 'datum', dir: -1 });
  const [edit, setEdit] = useState(null); // {eintrag} | {neu: {...}}
  const setParam = (k, v) => { const n = new URLSearchParams(params); if (v == null) n.delete(k); else n.set(k, v); setParams(n, { replace: true }); };

  // Deep-Links aus der Leitstelle: ?eintrag=ID (bearbeiten), ?neu=SCHICHT (für Schicht nachtragen)
  useEffect(() => {
    const e = params.get('eintrag'); const n = params.get('neu');
    if (e) api.get(`/zeiten/${e}`).then((r) => setEdit({ eintrag: r.data })).catch((x) => toast(apiError(x), { tone: 'warn' }));
    if (n) api.get(`/schicht/${n}`).then((r) => setEdit({ neu: { employee_id: r.data.employee_id, object_id: r.data.object_id, datum: r.data.datum, kommen: r.data.beginn, gehen: r.data.ende, schedule_id: r.data.id } }))
      .catch((x) => toast(apiError(x), { tone: 'warn' }));
  }, []); // eslint-disable-line

  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (data?.eintraege || [])
      .filter((r) => (!onlyHint || r.hinweis || r.verspaetet?.length) && (!s || `${r.name} ${r.personal_nr} ${r.objekt} ${r.weg}`.toLowerCase().includes(s)))
      .sort((a, b) => { const x = a[sort.k] ?? '', y = b[sort.k] ?? ''; return (x > y ? 1 : x < y ? -1 : 0) * sort.dir || (a.check_in > b.check_in ? -1 : 1); });
  }, [data, q, onlyHint, sort]);
  const sum = rows.reduce((a, r) => a + r.stunden, 0);
  const SortIcon = ({ k }) => sort.k !== k ? <ArrowUpDown size={14} opacity={.5} /> : sort.dir > 0 ? <ArrowUp size={14} /> : <ArrowDown size={14} />;
  // Pruefpunkt "geplant, nicht gestempelt": Zeile oeffnet "Buchung nachtragen" mit den Plan-Zeiten der Schicht
  const oeffnen = (r) => setEdit(r.fehlt ? { neu: { employee_id: r.employee_id, object_id: r.object_id, datum: r.datum, kommen: r.kommen, gehen: r.gehen, schedule_id: r.schicht_id } } : { eintrag: r });
  const closeEdit = () => { setEdit(null); setParam('eintrag', null); setParam('neu', null); };

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('zeiten.title')}</h1><p>{data ? t('zeiten.subtitle', { from: fmtDate(data.von), to: fmtDate(data.bis, { day: '2-digit', month: '2-digit', year: 'numeric' }) }) : <Skeleton w={160} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }} data-monat-nav>
            <button className="ck-btn ck-btn-icon" onClick={() => blaettern(-1)} aria-label={t('abr.prev')} data-monat-zurueck><ChevronLeft size={18} /></button>
            <span className="ck-card" style={{ padding: '6px 14px', fontWeight: 650, minWidth: 150, textAlign: 'center' }} data-zeiten-monat={m}>{monatName}</span>
            <button className="ck-btn ck-btn-icon" onClick={() => blaettern(1)} disabled={m >= aktM} aria-label={t('abr.next')} data-monat-vor><ChevronRight size={18} /></button>
          </div>
          {!pruef && <div className="ck-seg">{['week', 'month'].map((k) => <button key={k} className={range === k ? 'is-on' : ''} onClick={() => setParam('range', k)}>{t(`zeiten.${k}`)}</button>)}</div>}
          <button className="ck-btn" onClick={() => setClassic(!classic)}><ClipboardCheck size={16} />{t('zeiten.approvals')}</button>
          <button className="ck-btn ck-btn-primary" onClick={() => setEdit({ neu: { datum: iso(now), kommen: '', gehen: '' } })}><Plus size={17} />{t('zeiten.new')}</button>
        </div>
      </div>
      {pruef && (
        <div className="ck-callout" style={{ marginBottom: 16, alignItems: 'center' }}><AlertTriangle size={20} style={{ flex: 'none' }} />
          <span>{t(`ls.chk_${pruef}`)} · {data ? new Date(`${data.monat}-01T12:00`).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' }) : ''} · {t('zeiten.pruef_hint')}</span>
          <button className="ck-btn ck-btn-sm" style={{ marginLeft: 'auto' }} onClick={() => setParam('pruef', null)}><X size={15} />{t('zeiten.pruef_off')}</button></div>
      )}
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
          {error ? <ErrorBox text={error} onRetry={reload} /> : loading ? <SkeletonRows n={6} /> : rows.length === 0 ? (
            pruef ? <Empty icon={ClipboardCheck} title={t('zeiten.pruef_empty_title')} text={t('zeiten.pruef_empty')} /> : <Empty icon={Clock3} title={t('zeiten.empty_title')} text={t('zeiten.empty')} />
          ) : (
            <div className="ck-table-wrap">
              <table className="ck-table ck-table-click">
                <thead><tr>{COLS.map(([k, l]) => (
                  <th key={k} aria-sort={sort.k === k ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'}>
                    <button onClick={() => setSort((s) => ({ k, dir: s.k === k ? -s.dir : 1 }))}>{t(l)}<SortIcon k={k} /></button></th>))}<th aria-label={t('zeiten.edit')} /></tr></thead>
                <tbody>{rows.map((r) => (
                  <tr key={r.id} onClick={() => oeffnen(r)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && oeffnen(r)}>
                    <td className="ck-num">{fmtDate(r.datum)}</td>
                    <td><Link className="ck-link" to={`/cockpit/mitarbeiter/${r.employee_id}`} onClick={(e) => e.stopPropagation()} style={{ fontWeight: 600 }}>{r.name}</Link></td>
                    <td>{r.objekt ? <ObjektMarke id={r.object_id} name={r.objekt} size="xs" /> : '–'}</td>
                    <td className="ck-num">{r.kommen}<VerspKurz r={r} art="kommen" /></td>
                    <td className="ck-num">{r.gehen ? <>{r.gehen}{r.gehen_datum && r.gehen_datum !== r.datum && <span className="ck-subtle"> ({fmtDate(r.gehen_datum)})</span>}<VerspKurz r={r} art="gehen" /></> : <Status s="da" label={t('status.da')} />}</td>
                    <td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(r.stunden, 2)}</td>
                    <td className="ck-subtle">{r.weg}</td>
                    <td>{r.hinweis && <Status s="fehlt" label={r.hinweis} />}</td>
                    <td>{r.fehlt ? <Plus size={15} className="ck-muted" aria-hidden="true" /> : r.gesperrt ? <Lock size={15} className="ck-muted" aria-label={t('zeiten.locked_short')} /> : <Pencil size={15} className="ck-muted" aria-hidden="true" />}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {edit && <BuchungDialog eintrag={edit.eintrag} neu={edit.neu} onClose={closeEdit} onDone={() => { closeEdit(); reload(); }} />}
    </>
  );
}

export function BuchungDialog({ eintrag, neu, onClose, onDone }) {
  const { toast } = useApp();
  const { data: aus } = useApi('/auswahl');
  const init = eintrag ? { employee_id: eintrag.employee_id, object_id: eintrag.object_id || '', datum: eintrag.gehen_datum && eintrag.hinweis.includes('Gehen vor Kommen') ? eintrag.gehen_datum : eintrag.datum,
    kommen: eintrag.kommen, gehen: eintrag.gehen || '', notes: eintrag.notes || '' } : { employee_id: '', object_id: '', notes: '', ...neu };
  const [f, setF] = useState(init);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [confirmDel, setConfirmDel] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const nacht = f.kommen && f.gehen && f.gehen <= f.kommen;
  const dauer = (() => {
    if (!f.kommen || !f.gehen) return null;
    const [a, b] = [f.kommen, f.gehen].map((x) => { const [h, m] = x.split(':').map(Number); return h * 60 + m; });
    return ((b - a + 1440) % 1440 || 1440) / 60;
  })();
  const fixed = eintrag?.hinweis?.includes('Gehen vor Kommen');
  const gesperrt = !!eintrag?.gesperrt;   // abgeschlossener Monat: Server lehnt ab (423), hier gleich sichtbar

  const save = async () => {
    setBusy(true); setErr('');
    try {
      if (eintrag) {
        const before = { datum: eintrag.datum, kommen: eintrag.kommen, gehen: eintrag.gehen, object_id: eintrag.object_id, notes: eintrag.notes };
        await api.put(`/zeiten/${eintrag.id}`, { datum: f.datum, kommen: f.kommen, gehen: f.gehen, object_id: f.object_id ? Number(f.object_id) : undefined, notes: f.notes });
        toast(t('zeiten.saved', { name: eintrag.name }), before.gehen && !fixed ? { undo: async () => { await api.put(`/zeiten/${eintrag.id}`, before); onDone(); } } : {});
      } else {
        const r = await api.post('/zeiten', { ...f, employee_id: Number(f.employee_id), object_id: Number(f.object_id) });
        toast(t('zeiten.created', { name: r.data.name }), { undo: async () => { await api.delete(`/zeiten/${r.data.id}`); onDone(); } });
      }
      onDone();
    } catch (e) { setErr(apiError(e)); }
    setBusy(false);
  };
  const del = async () => {
    setBusy(true);
    try {
      const r = await api.delete(`/zeiten/${eintrag.id}`);
      const a = r.data.alt;
      toast(t('zeiten.deleted', { name: eintrag.name }), a.gehen ? { undo: async () => { await api.post('/zeiten', { employee_id: a.employee_id, object_id: a.object_id, datum: a.datum, kommen: a.kommen, gehen: a.gehen, notes: a.notes, schedule_id: a.schedule_id }); onDone(); } } : {});
      onDone();
    } catch (e) { setErr(apiError(e)); setBusy(false); }
  };

  return (
    <Dialog title={eintrag ? t('zeiten.edit_title', { name: eintrag.name }) : t('zeiten.new_title')} onClose={onClose} footer={<>
      {eintrag && !gesperrt && (confirmDel ? <button className="ck-btn" style={{ marginRight: 'auto', color: 'var(--ck-warn)', borderColor: 'var(--ck-warn)' }} disabled={busy} onClick={del}><Trash2 size={16} />{t('zeiten.delete_confirm')}</button>
        : <button className="ck-btn ck-btn-ghost" style={{ marginRight: 'auto' }} onClick={() => setConfirmDel(true)}><Trash2 size={16} />{t('zeiten.delete')}</button>)}
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={gesperrt || busy || !f.datum || !f.kommen || !f.gehen || (!eintrag && (!f.employee_id || !f.object_id))} onClick={save}>{t('app.save')}</button></>}>
      {gesperrt && <div className="ck-callout" data-gesperrt><Lock size={20} style={{ flex: 'none' }} />{t('zeiten.locked')}</div>}
      {fixed && <div className="ck-callout"><AlertTriangle size={20} style={{ flex: 'none' }} />{t('zeiten.fix_hint', { kommen: fmtDate(eintrag.datum), gehen: fmtDate(eintrag.gehen_datum) })}</div>}
      {!eintrag && (
        <label className="ck-field">{t('zeiten.name')}
          <select className="ck-input" value={f.employee_id} onChange={set('employee_id')} autoFocus>
            <option value="">{t('ma.choose')}</option>{(aus?.mitarbeiter || []).map((m) => <option key={m.id} value={m.id}>{m.name} · {m.personal_nr}</option>)}</select></label>)}
      <label className="ck-field">{t('zeiten.object')}
        <select className="ck-input" value={f.object_id} onChange={set('object_id')}>
          <option value="">{t('ma.choose')}</option>{(aus?.objekte || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 1fr', gap: 12 }}>
        <label className="ck-field">{t('zeiten.date')}<input type="date" className="ck-input" value={f.datum} onChange={set('datum')} /></label>
        <label className="ck-field">{t('zeiten.in')}<input type="time" className="ck-input" value={f.kommen} onChange={set('kommen')} /></label>
        <label className="ck-field">{t('zeiten.out')}<input type="time" className="ck-input" value={f.gehen} onChange={set('gehen')} /></label>
      </div>
      {dauer != null && <div className="ck-subtle" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: -6 }}>
        {nacht && <><Moon size={15} />{t('zeiten.next_day')} · </>}{t('zeiten.duration', { h: fmtNum(dauer, 2) })}</div>}
      <label className="ck-field">{t('zeiten.note')}<input className="ck-input" value={f.notes} onChange={set('notes')} /></label>
      {err && <div className="ck-callout"><AlertTriangle size={18} />{err}</div>}
    </Dialog>
  );
}
