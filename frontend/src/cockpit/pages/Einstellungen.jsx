import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Palette, Building2, Car, Search } from 'lucide-react';
import { api, apiError, t, useApi, useApp, SkeletonRows, Empty, Status, brandStyle, contrast } from '../core';
import { KmEingabe } from './Objekte';

const UrlaubVerwaltungTab = lazy(() => import('../../pages/UrlaubVerwaltungTab'));
const MitarbeiterObjekteTab = lazy(() => import('../../pages/MitarbeiterObjekteTab'));
const PushVerwaltungTab = lazy(() => import('../../pages/PushVerwaltungTab'));
const AuditLogTab = lazy(() => import('../../pages/AuditLogTab'));
const BRAND_KEYS = ['firma', 'produkt', 'logo_url', 'akzent', 'cta', 'cta_text', 'leiste', 'leiste_text', 'schrift_css', 'schrift_titel', 'schrift_text'];
const TABS = ['brand', 'km', 'urlaub', 'assign', 'telegram', 'audit'];

export default function Einstellungen() {
  const { brand, setBrand, toast } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get('tab')) ? params.get('tab') : 'brand';
  const setTab = (k) => setParams({ tab: k }, { replace: true });
  const [f, setF] = useState(brand || {});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (brand) setF(brand); }, [brand]);

  const save = async () => {
    setBusy(true);
    const before = brand;
    try {
      const r = await api.put('/branding', Object.fromEntries(BRAND_KEYS.map((k) => [k, f[k] || ''])));
      setBrand(r.data);
      toast(t('set.saved'), { undo: async () => { const u = await api.put('/branding', before); setBrand(u.data); } });
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const farbe = (k, label, fallback) => (  // Funktion statt Komponente: Eingabefeld behaelt beim Tippen den Fokus
    <label key={k} className="ck-field">{label}
      <div style={{ display: 'flex', gap: 8 }}>
        <input type="color" value={f[k] || fallback} onChange={(e) => setF({ ...f, [k]: e.target.value })} style={{ width: 52, height: 42, border: '1px solid var(--ck-border)', borderRadius: 10, background: 'none' }} aria-label={label} />
        <input className="ck-input" value={f[k] || ''} placeholder={t('set.empty_default')} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
      </div></label>);
  const kontrast = (a, b) => { const r = contrast(a, b); return r ? t('set.contrast', { r: r.toFixed(1).replace('.', ','), ok: r >= 4.5 ? t('set.contrast_ok') : t('set.contrast_bad') }) : ''; };

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('set.title')}</h1><p>{t('set.subtitle')}</p></div>
        <div className="ck-seg" style={{ flexWrap: 'wrap' }}>{TABS.map((k) => <button key={k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{t(`set.${k}`)}</button>)}</div>
      </div>
      {tab === 'brand' ? (
        <div className="ck-two">
          <section className="ck-card"><div className="ck-card-head"><h2><Building2 size={20} />{t('set.brand')}</h2></div>
            <div className="ck-dialog-body">
              <label className="ck-field">{t('set.company')}<input className="ck-input" value={f.firma || ''} onChange={(e) => setF({ ...f, firma: e.target.value })} /></label>
              <label className="ck-field">{t('set.product')}<input className="ck-input" value={f.produkt || ''} onChange={(e) => setF({ ...f, produkt: e.target.value })} /></label>
              <label className="ck-field">{t('set.logo')}<input className="ck-input" value={f.logo_url || ''} onChange={(e) => setF({ ...f, logo_url: e.target.value })} placeholder="/brand/firma/logo.svg" /></label>
              <h3 style={{ fontSize: 16, marginTop: 8 }}>{t('set.colors')}</h3>
              {farbe('akzent', t('set.accent'), '#2563eb')}
              {farbe('cta', t('set.cta'), '#2563eb')}
              {farbe('cta_text', t('set.cta_text'), '#ffffff')}
              {farbe('leiste', t('set.side'), '#ffffff')}
              {farbe('leiste_text', t('set.side_text'), '#0f172a')}
              <h3 style={{ fontSize: 16, marginTop: 8 }}>{t('set.fonts')}</h3>
              <label className="ck-field">{t('set.font_css')}<input className="ck-input" value={f.schrift_css || ''} placeholder="/brand/firma/fonts/fonts.css" onChange={(e) => setF({ ...f, schrift_css: e.target.value })} /></label>
              <label className="ck-field">{t('set.font_head')}<input className="ck-input" value={f.schrift_titel || ''} placeholder="Inter" onChange={(e) => setF({ ...f, schrift_titel: e.target.value })} /></label>
              <label className="ck-field">{t('set.font_body')}<input className="ck-input" value={f.schrift_text || ''} placeholder="Inter" onChange={(e) => setF({ ...f, schrift_text: e.target.value })} /></label>
            </div>
            <div className="ck-dialog-foot"><button className="ck-btn ck-btn-primary" disabled={busy} onClick={save}>{t('app.save')}</button></div>
          </section>
          <section className="ck-card"><div className="ck-card-head"><h2><Palette size={20} />{t('set.preview')}</h2></div>
            <div className="ck-card-body ck-brand-scope" style={{ ...brandStyle(f), display: 'grid', gap: 16 }}>
              <div style={{ background: 'var(--ck-side-bg)', color: 'var(--ck-side-fg)', borderRadius: 12, padding: 12 }}>
                {f.logo_url ? <div className="ck-brand-mark" style={{ padding: 0 }}><img src={f.logo_url} alt="" /><span>{f.produkt} {t('app.subtitle')}</span></div>
                  : <div className="ck-brand" style={{ padding: 0 }}><div className="ck-logo">{(f.firma || ' ').slice(0, 1)}</div><div><b>{f.firma}</b><span>{f.produkt} {t('app.subtitle')}</span></div></div>}
                <div className="ck-nav-item is-active" style={{ marginTop: 8 }}>{t('nav.heute')}</div>
                <div className="ck-nav-item">{t('nav.dienstplan')}</div>
              </div>
              <h3 style={{ fontSize: 20, color: 'var(--ck-accent-ink)' }}>{f.firma} {t('app.subtitle')}</h3>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><button className="ck-btn ck-btn-primary">{t('act.genehmigen')}</button><button className="ck-btn">{t('act.ablehnen')}</button>
                <Status s="da" /><Status s="fehlt" /></div>
              <ul className="ck-subtle" style={{ margin: 0, paddingLeft: 18 }}>
                <li>{t('set.cta_text')}: {kontrast(f.cta_text || '#ffffff', f.cta || f.akzent || '#2563eb')}</li>
                <li>{t('set.side_text')}: {kontrast(f.leiste_text || '#0f172a', f.leiste || '#ffffff')}</li>
                <li>{t('set.accent')}: {kontrast(f.akzent || '#2563eb', '#ffffff')}</li>
              </ul>
            </div>
          </section>
        </div>
      ) : tab === 'km' ? <KmStrecken /> : (
        <section className="ck-card"><div className="ck-card-head"><h2>{t(`set.${tab}`)}</h2><span className="ck-tag">{t('app.classic')}</span></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}>
            {tab === 'urlaub' && <UrlaubVerwaltungTab />}
            {tab === 'assign' && <MitarbeiterObjekteTab />}
            {tab === 'telegram' && <PushVerwaltungTab />}
            {tab === 'audit' && <AuditLogTab />}
          </Suspense></div></section>
      )}
    </>
  );
}

function KmStrecken() {
  const { data, loading, reload } = useApi('/km-strecken');
  const [q, setQ] = useState('');
  const [nur, setNur] = useState(false);
  const rows = useMemo(() => (data || []).filter((r) => (!nur || (r.distance_km == null && r.fahrer))
    && `${r.name} ${r.personal_nr} ${r.objekt}`.toLowerCase().includes(q.trim().toLowerCase())), [data, q, nur]);
  const fehlt = (data || []).filter((r) => r.distance_km == null && r.fahrer).length;
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><Car size={20} />{t('set.km')}</h2><span className="ck-subtle">{t('set.km_sub', { n: (data || []).length, f: fehlt })}</span></div>
      <div className="ck-toolbar">
        <label className="ck-search" style={{ cursor: 'text', minWidth: 240, maxWidth: 360 }}><Search size={18} />
          <input style={{ border: 0, outline: 0, background: 'transparent', flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('set.km_search')} aria-label={t('set.km_search')} /></label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 500 }}><input type="checkbox" checked={nur} onChange={(e) => setNur(e.target.checked)} style={{ width: 18, height: 18 }} />{t('set.km_only_missing')}</label>
      </div>
      {loading ? <SkeletonRows n={6} /> : rows.length === 0 ? <Empty icon={Car} title={t('set.km_empty')} text="" /> : (
        <ul className="ck-list">{rows.map((r) => (
          <li key={`${r.employee_id}-${r.object_id}`} className="ck-row">
            <div className="ck-row-main"><div className="ck-row-title"><Link to={`/cockpit/mitarbeiter/${r.employee_id}`}>{r.name}</Link><span className="ck-subtle">→</span>
              <Link to={`/cockpit/objekte/${r.object_id}`}>{r.objekt}</Link></div>
              <div className="ck-row-meta">{r.fahrer ? t('set.km_driver') : t('set.km_nodriver')}</div></div>
            <KmEingabe emp={r.employee_id} obj={r.object_id} km={r.distance_km} name={r.name} onSaved={reload} />
          </li>))}</ul>)}
    </section>
  );
}
