import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, IdCard, Building2, CalendarDays, Timer, Palmtree, Plus, Car, MapPin, X, AlertTriangle, Lock } from 'lucide-react';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, Skeleton, SkeletonRows, Empty, ErrorBox, Dialog, initials } from '../core';

export default function Akte() {
  const { id } = useParams();
  const { me, toast } = useApp();
  const { data, loading, error, status, reload } = useApi(`/mitarbeiter/${id}`);
  const [assign, setAssign] = useState(false);

  if (error) return <div className="ck-card"><ErrorBox text={status === 403 ? t('ma.not_found') : error} onRetry={status === 403 ? undefined : reload} /></div>;
  const s = data?.stamm;

  const unassign = async (o) => {
    try {
      await api.delete(`/mitarbeiter/${id}/objekte/${o.id}`);
      toast(t('ma.unassigned', { obj: o.name }), {
        undo: async () => { await api.post(`/mitarbeiter/${id}/objekte`, { object_id: o.object_id, tracking_category: o.tracking_category, is_driver: o.is_driver }); reload(); } });
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };

  return (
    <>
      <Link to="/cockpit/mitarbeiter" className="ck-btn ck-btn-ghost ck-btn-sm" style={{ marginBottom: 12, paddingLeft: 4 }}><ArrowLeft size={16} />{t('ma.title')}</Link>
      <div className="ck-page-head">
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div className="ck-avatar" style={{ width: 56, height: 56, fontSize: 20 }}>{s ? initials(s.name) : ''}</div>
          <div><h1>{s ? s.name : <Skeleton w={220} h={30} />}</h1>
            <p>{s ? <>{s.personal_nr} · {t(`kat.${s.kategorie || 'C'}`)} · <Status s={s.aktiv ? 'aktiv' : 'inaktiv'} /></> : <Skeleton w={160} h={16} />}</p></div>
        </div>
        <button className="ck-btn ck-btn-primary" disabled={!data} onClick={() => setAssign(true)}><Plus size={18} />{t('ma.assign')}</button>
      </div>

      <div className="ck-kpis">
        <Mini Icon={Timer} label={t('ma.hours')} value={data && fmtNum(data.monat.stunden, 1)} sub={data && `${t('ma.month')} · ${data.monat.einsaetze} ${t('ma.missions')}`} />
        <Mini Icon={Car} label={t('ma.km')} value={data && fmtNum(data.monat.km, 0)} sub={data && (data.monat.km_betrag != null ? `${fmtNum(data.monat.km_betrag, 2)} € ${t('ma.km_money')}` : `${data.monat.fahrten} ×`)} />
        <Mini Icon={Palmtree} label={t('ma.remaining')} value={data && fmtNum(data.urlaub.days_remaining, 1)} sub={data && `${t('ma.days')} · ${t('ma.entitled')} ${fmtNum(data.urlaub.days_entitled, 0)}`} />
        <Mini Icon={CalendarDays} label={t('ma.plan')} value={data && data.plan.length} sub={data && (data.plan[0] ? `${data.plan[0].tag} ${fmtDate(data.plan[0].datum)} ${data.plan[0].beginn || ''}` : t('ma.plan_empty'))} />
      </div>

      <div className="ck-two">
        <div className="ck-grid" style={{ gap: 24 }}>
          <section className="ck-card"><div className="ck-card-head"><h2><Building2 size={20} />{t('ma.objects')}</h2></div>
            {loading ? <SkeletonRows n={2} /> : data.objekte.length === 0 ? <Empty icon={Building2} title={t('ma.objects_empty')} text=""><button className="ck-btn ck-btn-primary" onClick={() => setAssign(true)}><Plus size={16} />{t('ma.assign')}</button></Empty> : (
              <ul className="ck-list">{data.objekte.map((o) => (
                <li key={o.id} className="ck-row">
                  <MapPin size={18} />
                  <div className="ck-row-main"><div className="ck-row-title">{o.name}<span className="ck-tag">{t(`kat.${o.tracking_category || 'B'}`)}</span></div>
                    <div className="ck-row-meta">{o.km_fehlt ? <Status s="fehlt" label={t('ma.km_missing')} /> : <span>{t('ma.km_ok', { km: fmtNum(o.distance_km, 1) })}</span>}</div></div>
                  <button className="ck-btn ck-btn-sm ck-btn-ghost" onClick={() => unassign(o)} aria-label={`${t('ma.unassign')}: ${o.name}`}><X size={16} />{t('ma.unassign')}</button>
                </li>))}</ul>)}
          </section>
          <section className="ck-card"><div className="ck-card-head"><h2><CalendarDays size={20} />{t('ma.plan')}</h2></div>
            {loading ? <SkeletonRows n={3} /> : data.plan.length === 0 ? <Empty icon={CalendarDays} title={t('ma.plan_empty')} text="" /> : (
              <ul className="ck-list">{data.plan.map((p) => (
                <li key={p.id} className="ck-row"><span className="ck-row-time" style={{ minWidth: 82 }}>{p.tag} {fmtDate(p.datum)}</span>
                  <div className="ck-row-main"><div className="ck-row-title" style={{ fontWeight: 550 }}>{p.objekt}</div></div>
                  {p.objekt === 'Urlaub' || p.objekt === 'Krank' ? <Status s={p.objekt === 'Urlaub' ? 'urlaub' : 'krank'} /> : <span className="ck-num ck-muted">{p.beginn}–{p.ende}</span>}</li>))}</ul>)}
          </section>
        </div>
        <div className="ck-grid" style={{ gap: 24 }}>
          <section className="ck-card"><div className="ck-card-head"><h2><IdCard size={20} />{t('ma.profile')}</h2></div>
            <div className="ck-card-body">{!s ? <SkeletonRows n={3} /> : (
              <dl className="ck-dl">
                <dt>{t('ma.pnr')}</dt><dd>{s.personal_nr}</dd>
                <dt>{t('ma.email')}</dt><dd style={{ wordBreak: 'break-all' }}>{s.email}</dd>
                <dt>{t('ma.address')}</dt><dd>{s.adresse || '–'}</dd>
                <dt>{t('ma.category')}</dt><dd>{t(`kat.${s.kategorie || 'C'}`)}</dd>
                <dt>{t('ma.stamping')}</dt><dd>{s.stempelart || '–'}</dd>
                <dt>{t('ma.employment')}</dt><dd>{s.beschaeftigung || '–'}</dd>
                <dt>{t('ma.telegram')}</dt><dd>{s.telegram ? t('ma.yes') : t('ma.no')}</dd>
                <dt>{t('ma.since')}</dt><dd>{fmtDate(s.seit, { day: '2-digit', month: '2-digit', year: 'numeric' })}</dd>
                {me?.rechte?.verwalten && s.stundenlohn != null && <><dt>{t('ma.rate')}</dt><dd>{fmtNum(s.stundenlohn, 2)} €</dd></>}
              </dl>)}</div>
          </section>
          <section className="ck-card"><div className="ck-card-head"><h2><Palmtree size={20} />{t('ma.vacation', { year: data?.urlaub.jahr || '' })}</h2></div>
            <div className="ck-card-body">{!data ? <SkeletonRows n={2} /> : (<>
              <dl className="ck-dl" style={{ marginBottom: 12 }}>
                <dt>{t('ma.entitled')}</dt><dd>{fmtNum(data.urlaub.days_entitled, 1)} {t('ma.days')}</dd>
                <dt>{t('ma.taken')}</dt><dd>{fmtNum(data.urlaub.days_taken, 1)} {t('ma.days')}</dd>
                <dt>{t('ma.remaining')}</dt><dd>{fmtNum(data.urlaub.days_remaining, 1)} {t('ma.days')}</dd>
              </dl>
              <div className="ck-section-title" style={{ padding: '8px 0 4px' }}>{t('ma.requests')}</div>
              {data.urlaub.antraege.length === 0 ? <div className="ck-subtle">{t('ma.none_requests')}</div> :
                <ul className="ck-list">{data.urlaub.antraege.map((a) => (
                  <li key={a.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '8px 0', borderBottom: '1px solid var(--ck-border)' }}>
                    <span className="ck-num">{fmtDate(a.von)}–{fmtDate(a.bis, { day: '2-digit', month: '2-digit', year: 'numeric' })} · {a.tage ?? '–'} {t('ma.days')}</span><Status s={a.status} /></li>))}</ul>}
            </>)}</div>
          </section>
        </div>
      </div>
      {assign && <AssignDialog emp={s} existing={data.objekte} onClose={() => setAssign(false)} onDone={() => { setAssign(false); reload(); }} />}
    </>
  );
}

function Mini({ Icon, label, value, sub }) {
  return (
    <div className="ck-card ck-kpi tone-info" style={{ cursor: 'default' }}>
      <div className="ck-kpi-label"><span className="ck-kpi-icon"><Icon size={18} /></span>{label}</div>
      <div className="ck-kpi-value ck-num" style={{ fontSize: 28 }}>{value ?? <Skeleton w={56} h={28} />}</div>
      <div className="ck-kpi-sub">{sub ?? <Skeleton w="60%" h={13} />}</div>
    </div>
  );
}

function AssignDialog({ emp, existing, onClose, onDone }) {
  const { toast, me } = useApp();
  const { data: objs } = useApi('/objekte');
  const [f, setF] = useState({ object_id: '', tracking_category: 'B', is_driver: true, distance_km: '' });
  const [needKm, setNeedKm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const taken = new Set(existing.map((o) => o.object_id));
  const choices = (objs || []).filter((o) => o.is_active && !taken.has(o.id));
  const obj = choices.find((o) => String(o.id) === String(f.object_id));

  const save = async () => {
    setBusy(true); setErr('');
    try {
      const body = { object_id: Number(f.object_id), tracking_category: f.tracking_category, is_driver: f.is_driver };
      if (needKm) body.distance_km = f.distance_km;
      const r = await api.post(`/mitarbeiter/${emp.id}/objekte`, body);
      toast(r.data.km_distance_id ? t('ma.assigned_km', { obj: obj?.name, km: f.distance_km }) : t('ma.assigned', { obj: obj?.name }), {
        undo: async () => { await api.delete(`/mitarbeiter/${emp.id}/objekte/${r.data.assignment_id}`); onDone(); } });
      onDone();
    } catch (e) {
      if (e?.response?.status === 409 && e.response.data?.detail?.code === 'km_fehlt') setNeedKm(true);
      else setErr(apiError(e));
    }
    setBusy(false);
  };

  return (
    <Dialog title={t('ma.assign_title')} onClose={onClose} footer={<>
      <button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
      <button className="ck-btn ck-btn-primary" disabled={busy || !f.object_id || (needKm && f.distance_km === '')} onClick={save}>{t('ma.assign')}</button></>}>
      <label className="ck-field">{t('ma.assign_object')}
        <select className="ck-input" value={f.object_id} onChange={(e) => { setF({ ...f, object_id: e.target.value }); setNeedKm(false); }} autoFocus>
          <option value="">{t('ma.choose')}</option>
          {choices.map((o) => <option key={o.id} value={o.id}>{o.name}{o.kunde ? ` – ${o.kunde}` : ''}</option>)}
        </select></label>
      <label className="ck-field">{t('ma.assign_category')}
        <select className="ck-input" value={f.tracking_category} onChange={(e) => setF({ ...f, tracking_category: e.target.value })}>
          {['A', 'B', 'C'].map((k) => <option key={k} value={k}>{t(`kat.${k}`)}</option>)}
        </select></label>
      <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontWeight: 500 }}>
        <input type="checkbox" checked={f.is_driver} onChange={(e) => setF({ ...f, is_driver: e.target.checked })} style={{ width: 20, height: 20 }} />{t('ma.assign_driver')}</label>
      {needKm && <>
        <div className="ck-callout"><AlertTriangle size={20} style={{ flex: 'none' }} />{t('ma.assign_km_needed', { name: emp.name, obj: obj?.name })}</div>
        <label className="ck-field">{t('ma.assign_km')}
          <input className="ck-input" inputMode="decimal" value={f.distance_km} onChange={(e) => setF({ ...f, distance_km: e.target.value })} placeholder="z. B. 12,5" autoFocus /></label>
      </>}
      {err && <div className="ck-callout"><Lock size={18} />{err}</div>}
    </Dialog>
  );
}
