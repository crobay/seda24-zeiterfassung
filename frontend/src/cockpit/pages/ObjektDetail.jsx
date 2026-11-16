import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Building2, Users, CalendarDays, Timer, Pencil, Info, Car, Plus, Euro, MapPin } from 'lucide-react';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, Skeleton, SkeletonRows, Empty, ErrorBox } from '../core';
import { SchichtDialog } from './Dienstplan';
import { KmEingabe } from './Objekte';

const FIELDS = [['address', 'obj.f_address'], ['contact_person', 'obj.f_contact'], ['phone', 'obj.f_phone'], ['email', 'obj.f_email'],
  ['emergency_phone', 'obj.f_emergency'], ['cleaning_days', 'obj.f_days'], ['cleaning_interval', 'obj.f_interval'],
  ['key_location', 'obj.f_key'], ['alarm_code', 'obj.f_alarm'], ['special_instructions', 'obj.f_special'], ['notes', 'obj.f_notes']];

export default function ObjektDetail() {
  const { id } = useParams();
  const { toast, me } = useApp();
  const { data, loading, error, reload } = useApi(`/objekte/${id}`);
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const [schicht, setSchicht] = useState(null);
  if (error) return <div className="ck-card"><ErrorBox text={error} onRetry={reload} /></div>;
  const s = data?.stamm;
  const m = data?.monat;

  const startEdit = () => { setF({ name: s.name, ...Object.fromEntries(FIELDS.map(([k]) => [k, s[k] || ''])) }); setEdit(true); };
  const save = async () => {
    setBusy(true);
    try {
      const changed = Object.fromEntries(Object.entries(f).filter(([k, v]) => (s[k] || '') !== v));
      if (Object.keys(changed).length) {
        const r = await api.put(`/objekte/${id}`, changed);
        toast(t('obj.saved', { name: f.name }), { undo: async () => { await api.put(`/objekte/${id}`, Object.fromEntries(Object.entries(r.data.alt).map(([k, v]) => [k, v ?? '']))); reload(); } });
      }
      setEdit(false); reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const toggleActive = async () => {
    try {
      await api.put(`/objekte/${id}`, { is_active: !s.is_active });
      toast(s.is_active ? t('obj.deactivated', { name: s.name }) : t('obj.activated', { name: s.name }), { undo: async () => { await api.put(`/objekte/${id}`, { is_active: s.is_active }); reload(); } });
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };

  return (
    <>
      <Link to="/cockpit/objekte" className="ck-btn ck-btn-ghost ck-btn-sm" style={{ marginBottom: 12, paddingLeft: 4 }}><ArrowLeft size={16} />{t('obj.title')}</Link>
      <div className="ck-page-head">
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div className="ck-kpi-icon" style={{ width: 56, height: 56, background: 'var(--ck-accent-soft)', color: 'var(--ck-accent)', borderRadius: 14 }}><Building2 size={26} /></div>
          <div><h1>{s ? s.name : <Skeleton w={220} h={30} />}</h1>
            <p>{s ? <>{s.kunde || '–'} · <Status s={s.is_active ? 'aktiv' : 'inaktiv'} /></> : <Skeleton w={160} h={16} />}</p></div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {s && <button className="ck-btn" onClick={toggleActive}>{s.is_active ? t('obj.deactivate') : t('obj.activate')}</button>}
          <button className="ck-btn ck-btn-primary" disabled={!data} onClick={() => setSchicht({ neu: { datum: new Date().toISOString().slice(0, 10), object_id: id, employee_id: '', beginn: s?.start_time || '', ende: s?.end_time || '', fahrer: true } })}><Plus size={17} />{t('dienstplan.new')}</button>
        </div>
      </div>

      <div className="ck-kpis">
        {[[Timer, t('obj.k_hours'), m && fmtNum(m.ist, 1), m && t('obj.k_hours_sub', { soll: fmtNum(m.soll, 1), n: m.einsaetze })],
          [Users, t('obj.k_staff'), data && data.mitarbeiter.length, data && t('obj.km_missing', { n: data.mitarbeiter.filter((x) => x.distance_km == null && x.is_driver).length })],
          [CalendarDays, t('obj.k_plan'), data && data.plan.length, data && (data.plan[0] ? `${data.plan[0].tag} ${fmtDate(data.plan[0].datum)} ${data.plan[0].beginn}` : t('ma.plan_empty'))],
          [Info, t('obj.k_times'), s && (s.start_time ? `${s.start_time}–${s.end_time || ''}` : '–'), s && (s.cleaning_days || t('obj.no_days'))],
        ].map(([Icon, l, v, sub], i) => (
          <div key={i} className="ck-card ck-kpi tone-info" style={{ cursor: 'default' }}>
            <div className="ck-kpi-label"><span className="ck-kpi-icon"><Icon size={18} /></span>{l}</div>
            <div className="ck-kpi-value ck-num" style={{ fontSize: 26 }}>{v ?? <Skeleton w={56} h={28} />}</div>
            <div className="ck-kpi-sub">{sub ?? <Skeleton w="60%" h={13} />}</div>
          </div>))}
      </div>

      <div className="ck-two">
        <div className="ck-grid" style={{ gap: 24 }}>
          <section className="ck-card"><div className="ck-card-head"><h2><Users size={20} />{t('obj.staff')}</h2></div>
            {loading ? <SkeletonRows n={3} /> : data.mitarbeiter.length === 0 ? <Empty icon={Users} title={t('obj.staff_empty')} text={t('obj.staff_empty_hint')} /> : (
              <ul className="ck-list">{data.mitarbeiter.map((x) => (
                <li key={x.id} className="ck-row">
                  <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${x.employee_id}`}>{x.name}</Link>
                    <span className="ck-tag">{t(`kat.${x.tracking_category || 'B'}`)}</span>{x.is_driver && <Car size={15} aria-label={t('dienstplan.driver')} />}</div></div>
                  <KmEingabe emp={x.employee_id} obj={Number(id)} km={x.distance_km} name={x.name} onSaved={reload} />
                </li>))}</ul>)}
          </section>
          <section className="ck-card"><div className="ck-card-head"><h2><CalendarDays size={20} />{t('ma.plan')}</h2>
            <Link className="ck-link-more" to="/cockpit/dienstplan">{t('nav.dienstplan')}</Link></div>
            {loading ? <SkeletonRows n={3} /> : data.plan.length === 0 ? <Empty icon={CalendarDays} title={t('ma.plan_empty')} text="" /> : (
              <ul className="ck-list">{data.plan.map((p) => (
                <li key={p.id} className="ck-row" style={{ cursor: 'pointer' }} onClick={() => setSchicht({ id: p.id })}>
                  <span className="ck-row-time" style={{ minWidth: 82 }}>{p.tag} {fmtDate(p.datum)}</span>
                  <div className="ck-row-main"><div className="ck-row-title" style={{ fontWeight: 550 }}>{p.name}</div></div>
                  <span className="ck-num ck-muted">{p.beginn}–{p.ende}</span><Pencil size={15} className="ck-muted" /></li>))}</ul>)}
          </section>
        </div>
        <div className="ck-grid" style={{ gap: 24 }}>
          <section className="ck-card"><div className="ck-card-head"><h2><MapPin size={20} />{t('obj.master')}</h2>
            {!edit && <button className="ck-btn ck-btn-sm" disabled={!s} onClick={startEdit}><Pencil size={15} />{t('obj.edit')}</button>}</div>
            {!s ? <div className="ck-card-body"><SkeletonRows n={4} /></div> : edit ? (<>
              <div className="ck-dialog-body">
                <label className="ck-field">{t('obj.f_name')}<input className="ck-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
                {FIELDS.map(([k, l]) => <label key={k} className="ck-field">{t(l)}
                  {k === 'special_instructions' || k === 'notes' ? <textarea className="ck-input" style={{ height: 80, padding: 10 }} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
                    : <input className="ck-input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}</label>)}
              </div>
              <div className="ck-dialog-foot"><button className="ck-btn" onClick={() => setEdit(false)}>{t('app.cancel')}</button>
                <button className="ck-btn ck-btn-primary" disabled={busy || !f.name?.trim()} onClick={save}>{t('app.save')}</button></div>
            </>) : (
              <div className="ck-card-body"><dl className="ck-dl">
                {FIELDS.map(([k, l]) => <React.Fragment key={k}><dt>{t(l)}</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{s[k] || '–'}</dd></React.Fragment>)}
                <dt>{t('obj.f_gps')}</dt><dd>{s.gps ? t('obj.gps_yes', { r: s.radius_m || '–' }) : t('obj.gps_no')}</dd>
                <dt>{t('obj.f_contract')}</dt><dd>{s.contract_start ? `${fmtDate(s.contract_start, { day: '2-digit', month: '2-digit', year: 'numeric' })} – ${s.contract_end ? fmtDate(s.contract_end, { day: '2-digit', month: '2-digit', year: 'numeric' }) : t('obj.open_end')}` : '–'}</dd>
              </dl></div>)}
          </section>
          {s?.umsatz && me?.rechte?.kunden_umsaetze && (
            <section className="ck-card"><div className="ck-card-head"><h2><Euro size={20} />{t('obj.revenue')}</h2><span className="ck-tag">{t('obj.admin_only')}</span></div>
              <div className="ck-card-body"><dl className="ck-dl">
                <dt>{t('obj.r_net')}</dt><dd>{s.umsatz.monthly_amount_netto != null ? `${fmtNum(s.umsatz.monthly_amount_netto, 2)} €` : '–'}</dd>
                <dt>{t('obj.r_gross')}</dt><dd>{s.umsatz.monthly_amount_brutto != null ? `${fmtNum(s.umsatz.monthly_amount_brutto, 2)} €` : '–'}</dd>
                <dt>{t('obj.r_invoice')}</dt><dd>{s.umsatz.invoice_type || '–'}{s.umsatz.invoice_day ? ` · ${t('obj.r_day', { d: s.umsatz.invoice_day })}` : ''}</dd>
              </dl></div></section>)}
        </div>
      </div>
      {schicht && <SchichtDialog id={schicht.id} neu={schicht.neu} onClose={() => setSchicht(null)} onDone={() => { setSchicht(null); reload(); }} />}
    </>
  );
}
