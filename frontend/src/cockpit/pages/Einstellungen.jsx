import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Palette, Building2 } from 'lucide-react';
import { api, apiError, t, useApp, SkeletonRows } from '../core';

const KmVerwaltungTab = lazy(() => import('../../components/KmVerwaltungTab'));
const MitarbeiterObjekteTab = lazy(() => import('../../pages/MitarbeiterObjekteTab'));
const PushVerwaltungTab = lazy(() => import('../../pages/PushVerwaltungTab'));
const AuditLogTab = lazy(() => import('../../pages/AuditLogTab'));
const TABS = ['brand', 'km', 'assign', 'telegram', 'audit'];

export default function Einstellungen() {
  const { brand, setBrand, toast } = useApp();
  const [tab, setTab] = useState('brand');
  const [f, setF] = useState(brand || {});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (brand) setF(brand); }, [brand]);

  const save = async () => {
    setBusy(true);
    const before = brand;
    try {
      const r = await api.put('/branding', { firma: f.firma, produkt: f.produkt, logo_url: f.logo_url, akzent: f.akzent });
      setBrand(r.data);
      toast(t('set.saved'), { undo: async () => { const u = await api.put('/branding', before); setBrand(u.data); } });
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };

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
              <label className="ck-field">{t('set.logo')}<input className="ck-input" value={f.logo_url || ''} onChange={(e) => setF({ ...f, logo_url: e.target.value })} placeholder="https://…/logo.png" /></label>
              <label className="ck-field">{t('set.accent')}
                <div style={{ display: 'flex', gap: 8 }}>
                  <input type="color" value={f.akzent || '#2563eb'} onChange={(e) => setF({ ...f, akzent: e.target.value })} style={{ width: 52, height: 42, border: '1px solid var(--ck-border)', borderRadius: 10, background: 'none' }} aria-label={t('set.accent')} />
                  <input className="ck-input" value={f.akzent || ''} onChange={(e) => setF({ ...f, akzent: e.target.value })} />
                </div></label>
            </div>
            <div className="ck-dialog-foot"><button className="ck-btn ck-btn-primary" disabled={busy} onClick={save}>{t('app.save')}</button></div>
          </section>
          <section className="ck-card"><div className="ck-card-head"><h2><Palette size={20} />{t('set.preview')}</h2></div>
            <div className="ck-card-body" style={{ '--ck-accent': f.akzent, display: 'grid', gap: 16 }}>
              <div className="ck-brand" style={{ padding: 0 }}><div className="ck-logo" style={{ background: f.akzent }}>{f.logo_url ? <img src={f.logo_url} alt="" /> : (f.firma || ' ').slice(0, 1)}</div>
                <div><b>{f.firma}</b><span>{f.produkt} {t('app.subtitle')}</span></div></div>
              <div style={{ display: 'flex', gap: 8 }}><button className="ck-btn ck-btn-primary" style={{ background: f.akzent, borderColor: f.akzent }}>{t('act.genehmigen')}</button><button className="ck-btn">{t('act.ablehnen')}</button></div>
            </div>
          </section>
        </div>
      ) : (
        <section className="ck-card"><div className="ck-card-head"><h2>{t(`set.${tab}`)}</h2><span className="ck-tag">{t('app.classic')}</span></div>
          <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}>
            {tab === 'km' && <KmVerwaltungTab showToast={(m) => toast(m)} />}
            {tab === 'assign' && <MitarbeiterObjekteTab />}
            {tab === 'telegram' && <PushVerwaltungTab />}
            {tab === 'audit' && <AuditLogTab />}
          </Suspense></div></section>
      )}
    </>
  );
}
