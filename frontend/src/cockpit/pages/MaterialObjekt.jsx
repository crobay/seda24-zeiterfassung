import React, { useEffect, useState } from 'react';
import { Package, Plus, Trash2, ArrowUp, ArrowDown } from 'lucide-react';
import { api, apiError, t, useApi, useApp, SkeletonRows, ErrorBox } from '../core';

// Objekt-Seite: "Material stellt: Kunde | SEDA24", Kunden-Ansprechpartner und Artikelliste fuer die MA-App.
export default function MaterialObjekt({ id }) {
  const { toast } = useApp();
  const { data, error, reload } = useApi(`/material/objekte/${id}`);
  const [e, setE] = useState(null);
  const [liste, setListe] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) { setE(data.einstellung); setListe(data.artikel.map((a) => ({ id: a.id, name: a.name, einheit: a.einheit || '' }))); } }, [data]);

  if (error) return <section className="ck-card"><ErrorBox text={error} onRetry={reload} /></section>;
  if (!e || !liste) return <section className="ck-card"><SkeletonRows n={3} /></section>;

  const einstGeaendert = ['stellt', 'kontakt_anrede', 'kontakt_name', 'kontakt_mail'].some((k) => (e[k] || '') !== (data.einstellung[k] || ''));
  const listeGeaendert = JSON.stringify(liste) !== JSON.stringify(data.artikel.map((a) => ({ id: a.id, name: a.name, einheit: a.einheit || '' })));

  const einstSpeichern = async () => {
    setBusy(true);
    try { await api.put(`/material/objekte/${id}/einstellung`, e); toast(t('mat.obj_saved')); reload(); } catch (x) { toast(apiError(x), { tone: 'warn' }); }
    setBusy(false);
  };
  const listeSpeichern = async () => {
    setBusy(true);
    try { await api.put(`/material/objekte/${id}/artikel`, { artikel: liste.filter((a) => a.name.trim()) }); toast(t('mat.obj_artikel_saved')); reload(); } catch (x) { toast(apiError(x), { tone: 'warn' }); }
    setBusy(false);
  };
  const schiebe = (i, d) => setListe((l) => { const n = [...l]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n; });

  return (
    <section className="ck-card" data-mat-objekt style={{ marginBottom: 24 }}>
      <div className="ck-card-head"><h2><Package size={20} />{t('mat.obj_title')}</h2></div>
      <div className="ck-card-body">
      <div className="ck-form-grid">
        <label className="ck-field">{t('mat.obj_stellt')}
          <span className="ck-seg" role="group">
            {['seda24', 'kunde'].map((k) => <button key={k} type="button" className={e.stellt === k ? 'is-on' : ''} onClick={() => setE({ ...e, stellt: k })} data-mat-stellt={k}>{t(k === 'kunde' ? 'mat.obj_kunde' : 'mat.obj_seda')}</button>)}
          </span></label>
        <label className="ck-field">{t('mat.obj_anrede')}
          <select className="ck-input" value={e.kontakt_anrede} onChange={(x) => setE({ ...e, kontakt_anrede: x.target.value })} data-mat-anrede>
            <option value="">–</option><option>Frau</option><option>Herr</option></select></label>
        <label className="ck-field">{t('mat.obj_name')}<input className="ck-input" value={e.kontakt_name} onChange={(x) => setE({ ...e, kontakt_name: x.target.value })} data-mat-kname /></label>
        <label className="ck-field">{t('mat.obj_mail')}<input className="ck-input" type="email" value={e.kontakt_mail} onChange={(x) => setE({ ...e, kontakt_mail: x.target.value })} data-mat-kmail /></label>
      </div>
      <p className="ck-subtle">{t('mat.obj_hint_kunde')}</p>
      <div className="ab-foot"><button className="ck-btn ck-btn-primary" disabled={!einstGeaendert || busy} onClick={einstSpeichern} data-mat-einst-speichern>{t('app.save')}</button></div>

      <h3 style={{ margin: '18px 0 8px' }}>{t('mat.obj_artikel')}</h3>
      {liste.map((a, i) => (
        <div key={a.id || `neu${i}`} className="mat-artikel-zeile" data-mat-artikelzeile>
          <input className="ck-input" value={a.name} maxLength={60} onChange={(x) => setListe((l) => l.map((y, j) => j === i ? { ...y, name: x.target.value } : y))} aria-label={t('mat.artikel')} />
          <input className="ck-input" style={{ maxWidth: 140, flex: 'none' }} value={a.einheit} maxLength={20} placeholder={t('mat.obj_einheit')}
            onChange={(x) => setListe((l) => l.map((y, j) => j === i ? { ...y, einheit: x.target.value } : y))} aria-label={t('mat.obj_einheit')} />
          <button className="ck-btn ck-btn-ghost ck-btn-sm" disabled={i === 0} onClick={() => schiebe(i, -1)} aria-label="nach oben"><ArrowUp size={14} /></button>
          <button className="ck-btn ck-btn-ghost ck-btn-sm" disabled={i === liste.length - 1} onClick={() => schiebe(i, 1)} aria-label="nach unten"><ArrowDown size={14} /></button>
          <button className="ck-btn ck-btn-ghost ck-btn-sm" onClick={() => setListe((l) => l.filter((_, j) => j !== i))} aria-label="entfernen"><Trash2 size={14} /></button>
        </div>))}
      <div className="ab-foot" style={{ justifyContent: 'space-between' }}>
        <button className="ck-btn" onClick={() => setListe((l) => [...l, { name: '', einheit: '' }])} data-mat-neu><Plus size={16} />{t('mat.obj_neu')}</button>
        <button className="ck-btn ck-btn-primary" disabled={!listeGeaendert || busy} onClick={listeSpeichern} data-mat-liste-speichern>{t('app.save')}</button>
      </div>
      </div>
    </section>
  );
}
