import React, { Suspense, lazy, useState } from 'react';
import { Info } from 'lucide-react';
import { t, SkeletonRows } from '../core';

const LohnUebersichtTab = lazy(() => import('../../pages/LohnUebersichtTab'));
const AbrechnungenTab = lazy(() => import('../../pages/AbrechnungenTab'));

export default function Abrechnung() {
  const [tab, setTab] = useState('lohn');
  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('abr.title')}</h1><p>{t('abr.subtitle')}</p></div>
        <div className="ck-seg">{['lohn', 'pdf'].map((k) => <button key={k} className={tab === k ? 'is-on' : ''} onClick={() => setTab(k)}>{t(`abr.${k}`)}</button>)}</div>
      </div>
      <div className="ck-callout c-info" style={{ marginBottom: 16, fontWeight: 500 }}><Info size={20} style={{ flex: 'none' }} />{t('abr.hint')}</div>
      <section className="ck-card"><div className="ck-card-head"><h2>{t(`abr.${tab}`)}</h2><span className="ck-tag">{t('app.classic')}</span></div>
        <div className="ck-embed"><Suspense fallback={<SkeletonRows n={6} />}>{tab === 'lohn' ? <LohnUebersichtTab /> : <AbrechnungenTab />}</Suspense></div>
      </section>
    </>
  );
}
