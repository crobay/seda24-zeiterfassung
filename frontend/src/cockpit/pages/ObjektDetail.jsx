import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Building2, Users, CalendarDays, Timer, Pencil, Info, Car, Plus, Euro, MapPin, ImagePlus, Trash2, Check, Wand2 } from 'lucide-react';
import { api, apiError, t, fmtNum, fmtDate, useApi, useApp, Status, Skeleton, SkeletonRows, Empty, ErrorBox, ObjektMarke } from '../core';
import MaterialObjekt from './MaterialObjekt';
import { SchichtDialog } from './Dienstplan';
import { KmEingabe } from './Objekte';

const FIELDS = [['address', 'obj.f_address'], ['contact_person', 'obj.f_contact'], ['phone', 'obj.f_phone'], ['email', 'obj.f_email'],
  ['emergency_phone', 'obj.f_emergency'], ['cleaning_days', 'obj.f_days'], ['cleaning_interval', 'obj.f_interval'],
  ['key_location', 'obj.f_key'], ['alarm_code', 'obj.f_alarm'], ['special_instructions', 'obj.f_special'], ['notes', 'obj.f_notes']];

// ---------- Logo und Kuerzel (nur interne Anzeige) ----------
const FARBNAMEN = { '#0072B2': 'Blau', '#E69F00': 'Orange', '#009E73': 'Grün', '#CC79A7': 'Rosa',
  '#D55E00': 'Rot', '#56B4E9': 'Hellblau', '#000000': 'Schwarz', '#F0E442': 'Gelb' };
const LOGO_PX = 160;

// Bild im Browser auf max. 160 px verkleinern und als PNG liefern (PNG/JPG/SVG; nichts wird aus dem Internet geladen)
function logoVerkleinern(datei) {
  return new Promise((resolve, reject) => {
    if (!/^image\/(png|jpeg|svg\+xml)$/.test(datei.type)) { reject(new Error('Bitte PNG, JPG oder SVG wählen')); return; }
    if (datei.size > 3 * 1024 * 1024) { reject(new Error('Datei zu groß (max. 3 MB)')); return; }
    const url = URL.createObjectURL(datei);
    const img = new Image();
    img.onload = () => {
      const w0 = img.naturalWidth || LOGO_PX, h0 = img.naturalHeight || LOGO_PX;
      const f = Math.min(1, LOGO_PX / Math.max(w0, h0));
      const c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(w0 * f)); c.height = Math.max(1, Math.round(h0 * f));
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/png'));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Bild konnte nicht gelesen werden')); };
    img.src = url;
  });
}

function MarkeKarte({ id, name }) {
  const { marken, loadMarken, toast } = useApp();
  const m = marken?.marken?.[String(id)];
  const [kz, setKz] = useState(null);
  const [busy, setBusy] = useState(false);
  const kuerzel = kz ?? (m?.auto ? '' : m?.kuerzel || '');
  const speichern = async (body, text, rueck) => {
    setBusy(true);
    try {
      await api.put(`/objekte/${id}/marke`, body);
      await loadMarken(); setKz(null);
      toast(text, { undo: async () => { await api.put(`/objekte/${id}/marke`, rueck); loadMarken(); } });
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const vorher = { kuerzel: m?.auto ? '' : m?.kuerzel, farbe: m?.auto ? '' : m?.farbe };
  const hochladen = async (e) => {
    const datei = e.target.files?.[0]; e.target.value = '';
    if (!datei) return;
    setBusy(true);
    try {
      const alt = m?.logo;
      await api.put(`/objekte/${id}/logo`, { logo: await logoVerkleinern(datei) });
      await loadMarken();
      toast(`Logo für ${name} gespeichert`, { undo: async () => { await (alt ? api.put(`/objekte/${id}/logo`, { logo: alt }) : api.delete(`/objekte/${id}/logo`)); loadMarken(); } });
    } catch (err) { toast(err.response ? apiError(err) : err.message, { tone: 'warn' }); }
    setBusy(false);
  };
  const entfernen = async () => {
    const alt = m?.logo;
    try {
      await api.delete(`/objekte/${id}/logo`); await loadMarken();
      toast(`Logo für ${name} entfernt`, { undo: async () => { await api.put(`/objekte/${id}/logo`, { logo: alt }); loadMarken(); } });
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  return (
    <section className="ck-card" data-marke-karte style={{ marginBottom: 24 }}>
      <div className="ck-card-head"><h2><ImagePlus size={20} />Logo und Kürzel</h2></div>
      <div className="ck-card-body" style={{ display: 'grid', gap: 16 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <ObjektMarke id={id} name={name} size="lg" />
          <span className="ck-subtle">{m?.logo ? 'Logo' : 'Kürzel'} – so erscheint das Objekt in Leitstelle, Dienstplan, Zeiten und in der Stempeluhr.</span>
        </div>
        <div>
          <div style={{ fontWeight: 650, marginBottom: 6 }}>Logo (nur intern)</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <label className="ck-btn" style={{ cursor: busy ? 'wait' : 'pointer', position: 'relative' }}>
              <ImagePlus size={17} />{m?.logo ? 'Logo ersetzen' : 'Logo hochladen'}
              <input type="file" accept="image/png,image/jpeg,image/svg+xml" onChange={hochladen} disabled={busy}
                aria-label="Logo hochladen (PNG, JPG oder SVG)" style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }} />
            </label>
            {m?.logo && <button className="ck-btn ck-btn-ghost" onClick={entfernen} disabled={busy}><Trash2 size={17} />Logo entfernen</button>}
          </div>
          <p className="ck-subtle" style={{ margin: '8px 0 0' }} data-logo-hinweis>
            Nur für interne Anzeige. Fremde Logos nicht für Werbung verwenden.
            {' '}PNG, JPG oder SVG – wird automatisch verkleinert und nur auf unserem Server gespeichert.
          </p>
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ fontWeight: 650 }}>Kürzel und Farbe (ohne Logo)</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input className="ck-input" style={{ width: 90, textTransform: 'uppercase' }} maxLength={3} value={kuerzel}
              placeholder={m?.kuerzel || ''} aria-label="Kürzel (1–3 Zeichen)" onChange={(e) => setKz(e.target.value.toUpperCase())} />
            <button className="ck-btn" disabled={busy || kz === null} onClick={() => speichern({ kuerzel: kuerzel }, `Kürzel für ${name} gespeichert`, { kuerzel: vorher.kuerzel || '' })}>
              <Check size={17} />Kürzel speichern</button>
            {!m?.auto && <button className="ck-btn ck-btn-ghost" disabled={busy}
              onClick={() => speichern({ kuerzel: '', farbe: '' }, `${name}: Kürzel und Farbe automatisch`, { kuerzel: vorher.kuerzel || '', farbe: vorher.farbe || '' })}>
              <Wand2 size={17} />Automatisch</button>}
          </div>
          <div role="radiogroup" aria-label="Farbe" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {(marken?.palette || []).map((f) => {
              const aktiv = m?.farbe === f;
              return (
                <button key={f} role="radio" aria-checked={aktiv} aria-label={`Farbe ${FARBNAMEN[f] || f}`} title={FARBNAMEN[f] || f}
                  disabled={busy} onClick={() => speichern({ farbe: f }, `Farbe für ${name}: ${FARBNAMEN[f] || f}`, { farbe: vorher.farbe || '' })}
                  style={{ width: 44, height: 44, borderRadius: 10, background: f, cursor: 'pointer', display: 'grid', placeItems: 'center',
                    border: aktiv ? '3px solid var(--ck-text, #111)' : '1px solid rgba(0,0,0,.25)', color: f === '#F0E442' || f === '#E69F00' || f === '#56B4E9' ? '#000' : '#fff', fontWeight: 800 }}>
                  {aktiv ? <Check size={20} strokeWidth={3} /> : (m?.kuerzel || '')}
                </button>);
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

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
          {s ? <ObjektMarke id={Number(id)} name={s.name} size="lg" ohneName /> : <div className="ck-kpi-icon" style={{ width: 56, height: 56, background: 'var(--ck-accent-soft)', color: 'var(--ck-accent-ink)', borderRadius: 14 }}><Building2 size={26} /></div>}
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

      {s && me?.rechte?.objekt_logo && <MarkeKarte id={Number(id)} name={s.name} />}
      {s && me?.rechte?.material && <MaterialObjekt id={Number(id)} />}

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
