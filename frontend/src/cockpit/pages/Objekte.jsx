import React, { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Building2, Users, CalendarCheck2, MapPin, Search, Car, Check, AlertTriangle, X } from 'lucide-react';
import { api, apiError, t, fmtNum, useApi, useApp, Status, Skeleton, SkeletonRows, Empty, ErrorBox, ObjektMarke } from '../core';

/* Inline-Eingabe einer KM-Strecke (MA -> Objekt), mit Rückgängig */
export function KmEingabe({ emp, obj, km, name, onSaved }) {
  const { toast } = useApp();
  const [v, setV] = useState(km != null ? String(km).replace('.', ',') : '');
  const [open, setOpen] = useState(km == null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const r = await api.put('/km-strecken', { employee_id: emp, object_id: obj, distance_km: v });
      toast(t('obj.km_saved', { name, km: fmtNum(r.data.distance_km, 1) }), r.data.alt ? { undo: async () => { await api.put('/km-strecken', { employee_id: emp, object_id: obj, distance_km: r.data.alt.distance_km }); onSaved(); } } : {});
      setOpen(false); onSaved();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  if (!open) return (
    <button className="ck-btn ck-btn-sm ck-btn-ghost" onClick={() => setOpen(true)} title={t('obj.km_edit')}><Car size={15} /><span className="ck-num">{fmtNum(km, 1)} km</span></button>);
  return (
    <form className="ck-km-inline" onSubmit={(e) => { e.preventDefault(); save(); }}>
      {km == null && <Status s="fehlt" label={t('ma.km_missing')} />}
      <input className="ck-input" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} placeholder="km" aria-label={t('ma.assign_km')} style={{ width: 84, height: 34 }} />
      <button className="ck-btn ck-btn-sm ck-btn-primary" disabled={busy || !v} aria-label={t('app.save')}><Check size={16} /></button>
      {km != null && <button type="button" className="ck-btn ck-btn-sm ck-btn-ghost ck-btn-icon" style={{ width: 32 }} onClick={() => setOpen(false)} aria-label={t('app.cancel')}><X size={15} /></button>}
    </form>);
}

export default function Objekte() {
  const { data, loading, error, reload } = useApi('/objekte');
  const [params, setParams] = useSearchParams();
  const pruef = params.get('pruef') === 'km_fehlt';
  const fehlt = useApi(pruef ? '/km-strecken?fehlend=true' : null);
  const [q, setQ] = useState('');
  const [aktiv, setAktiv] = useState('aktiv');
  const list = useMemo(() => (data || []).filter((o) => (aktiv === 'alle' || (aktiv === 'aktiv') === !!o.is_active)
    && `${o.name} ${o.kunde || ''} ${o.address || ''}`.toLowerCase().includes(q.trim().toLowerCase())), [data, q, aktiv]);

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('obj.title')}</h1><p>{data ? t('obj.subtitle', { n: list.length }) : <Skeleton w={100} h={16} />}</p></div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <label className="ck-search" style={{ cursor: 'text', minWidth: 240 }}><Search size={18} />
            <input style={{ border: 0, outline: 0, background: 'transparent', flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('obj.search')} aria-label={t('obj.search')} /></label>
          <div className="ck-seg">{['aktiv', 'inaktiv', 'alle'].map((k) => <button key={k} className={aktiv === k ? 'is-on' : ''} onClick={() => setAktiv(k)}>{k === 'alle' ? t('heute.filter_all') : t(`status.${k}`)}</button>)}</div>
          {!pruef && <button className="ck-btn" onClick={() => setParams({ pruef: 'km_fehlt' })}><Car size={16} />{t('ls.chk_km_fehlt')}</button>}
        </div>
      </div>

      {pruef && (
        <section className="ck-card" style={{ marginBottom: 20 }}>
          <div className="ck-card-head"><h2><AlertTriangle size={20} color="var(--ck-warn)" />{t('ls.chk_km_fehlt')}</h2>
            <button className="ck-btn ck-btn-sm" onClick={() => setParams({})}><X size={15} />{t('zeiten.pruef_off')}</button></div>
          {!fehlt.data ? <SkeletonRows n={2} /> : fehlt.data.length === 0 ? <Empty icon={Check} title={t('obj.km_all_ok')} text={t('obj.km_all_ok_hint')} /> : (
            <ul className="ck-list">{fehlt.data.map((r) => (
              <li key={`${r.employee_id}-${r.object_id}`} className="ck-row">
                <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${r.employee_id}`}>{r.name}</Link> → <Link to={`/cockpit/objekte/${r.object_id}`}><ObjektMarke id={r.object_id} name={r.objekt} size="xs" /></Link></div>
                  <div className="ck-row-meta">{t('obj.km_why')}</div></div>
                <KmEingabe emp={r.employee_id} obj={r.object_id} km={null} name={r.name} onSaved={() => { fehlt.reload(); reload(); }} />
              </li>))}</ul>)}
        </section>
      )}

      {error ? <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div> : loading ? (
        <div className="ck-tiles">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="ck-card ck-tile"><Skeleton w="60%" h={18} /><Skeleton w="80%" h={14} /><Skeleton w={120} h={24} r={999} /></div>)}</div>
      ) : list.length === 0 ? <div className="ck-card"><Empty icon={Building2} title={t('obj.empty_title')} text={t('obj.empty')} /></div> : (
        <div className="ck-tiles">
          {list.map((o) => (
            <Link key={o.id} to={`/cockpit/objekte/${o.id}`} className="ck-card ck-tile">
              <div style={{ fontWeight: 650, fontSize: 17, display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}><ObjektMarke id={o.id} name={o.name} size="md" /></div>
              <div className="ck-muted" style={{ fontSize: 15 }}>{o.kunde || '–'}</div>
              {o.address && <div className="ck-subtle" style={{ display: 'flex', gap: 6 }}><MapPin size={15} style={{ flex: 'none', marginTop: 3 }} />{o.address}</div>}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                <span className="ck-tag"><Users size={14} />{t('obj.ma', { n: o.ma })}</span>
                <span className="ck-tag"><CalendarCheck2 size={14} />{o.schichten_heute ? t('obj.today', { n: o.schichten_heute }) : t('obj.none_today')}</span>
              </div>
              <div>{!o.is_active ? <Status s="inaktiv" /> : o.ohne_km > 0 ? <Status s="fehlt" label={t('obj.km_missing', { n: o.ohne_km })} /> : <Status s="da" label={t('obj.km_ok')} />}</div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
