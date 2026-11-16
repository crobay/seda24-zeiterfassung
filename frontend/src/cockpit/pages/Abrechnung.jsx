import React, { Suspense, lazy, useState } from 'react';
import { Info } from 'lucide-react';
import { t, SkeletonRows, useApp } from '../core';

const LohnUebersichtTab = lazy(() => import('../../pages/LohnUebersichtTab'));
const AbrechnungenTab = lazy(() => import('../../pages/AbrechnungenTab'));
const KundenUmsaetzeTab = lazy(() => import('../../pages/KundenUmsaetzeTab'));

export default function Abrechnung() {
  const { me, toast } = useApp();
  const [tab, setTab] = useState('lohn');
  // Kunden-Umsaetze nur mit Recht (Objektleitung: nein; Backend sperrt zusaetzlich mit 403)
  const tabs = ['lohn', 'pdf', ...(me?.rechte?.kunden_umsaetze ? ['umsatz'] : [])];
  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('abr.title')}</h1><p>{t('abr.subtitle')}</p></div>
        <div className="ck-seg">{tabs.map((k) => <button key={k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{t(`abr.${k}`)}</button>)}</div>
      </div>
      <div className="ck-callout c-info" style={{ marginBottom: 16, fontWeight: 500 }}><Info size={20} style={{ flex: 'none' }} />{t('abr.hint')}</div>
      <section className="ck-card"><div className="ck-card-head"><h2>{t(`abr.${tab}`)}</h2><span className="ck-tag">{t('app.classic')}</span></div>
        <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}>{tab === 'lohn' ? <LohnUebersichtTab /> : tab === 'umsatz' && me?.rechte?.kunden_umsaetze ? <KundenUmsaetzeTab showToast={(m) => toast(m)} /> : <AbrechnungenTab />}</Suspense></div>
      </section>
    </>
  );
}
