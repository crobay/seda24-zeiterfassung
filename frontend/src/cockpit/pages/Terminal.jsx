import React, { useMemo, useState } from 'react';
import { Tablet, KeyRound, Trash2, Dices, ShieldOff } from 'lucide-react';
import { api, apiError, t, useApi, useApp, SkeletonRows, ErrorBox, Dialog, Status } from '../core';

// Terminal-Modus (Drazen 24.11.2026): registrierte Tablets (widerrufbar) + persoenliche 4-stellige PIN je MA.
const fmt = (iso) => iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';

function PinDialog({ ma, onClose, onSaved }) {
  const { toast } = useApp();
  const [pin, setPin] = useState('');
  const [neu, setNeu] = useState(null);
  const [busy, setBusy] = useState(false);
  const speichern = async (zufall) => {
    setBusy(true);
    try {
      const r = await api.put(`/terminal/pins/${ma.id}`, zufall ? { zufall: true } : { pin });
      setNeu(r.data.pin); onSaved(); toast(t('term.pin_ok', { name: ma.name }));
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  return (
    <Dialog title={t('term.pin_title', { name: ma.name })} onClose={onClose}
      footer={neu
        ? <button className="ck-btn ck-btn-primary" onClick={onClose}>{t('app.close')}</button>
        : <><button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
          <button className="ck-btn" disabled={busy} onClick={() => speichern(true)} data-term-zufall><Dices size={16} />{t('term.zufall')}</button>
          <button className="ck-btn ck-btn-primary" disabled={busy || !/^\d{4}$/.test(pin)} onClick={() => speichern(false)} data-term-pin-speichern>{t('app.save')}</button></>}>
      {neu ? (
        <div data-term-pin-neu>
          <p>{t('term.pin_neu')}</p>
          <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: 12, textAlign: 'center', padding: '8px 0' }}>{neu}</div>
          <p className="ck-subtle">{t('term.pin_neu_hint')}</p>
        </div>
      ) : (
        <>
          <label className="ck-field"><span>{t('term.pin_label')}</span>
            <input className="ck-input" inputMode="numeric" maxLength={4} autoComplete="off" value={pin} style={{ fontSize: 24, letterSpacing: 8, width: 160 }}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))} data-term-pin-eingabe /></label>
          <p className="ck-subtle">{ma.hat_pin ? t('term.pin_ersetzt') : ''} {t('term.pin_hint')}</p>
        </>
      )}
    </Dialog>
  );
}

export default function Terminal() {
  const { toast } = useApp();
  const { data, loading, error, reload } = useApi('/terminal');
  const [q, setQ] = useState('');
  const [pinFuer, setPinFuer] = useState(null);
  const [nurOhne, setNurOhne] = useState(false);

  const pins = useMemo(() => (data?.pins || []).filter((p) => (!nurOhne || !p.hat_pin)
    && (!q || `${p.name} ${p.personal_nr || ''}`.toLowerCase().includes(q.toLowerCase()))), [data, q, nurOhne]);
  const mitPin = (data?.pins || []).filter((p) => p.hat_pin && !p.test).length;

  const widerrufen = async (g) => {
    if (!window.confirm(t('term.widerruf_frage', { name: g.name }))) return;
    try { await api.delete(`/terminal/geraete/${g.id}`); toast(t('term.widerrufen_ok')); reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const pinWeg = async (p) => {
    if (!window.confirm(t('term.pin_weg_frage', { name: p.name }))) return;
    try { await api.delete(`/terminal/pins/${p.id}`); reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };

  if (loading && !data) return <div className="ck-card"><SkeletonRows n={6} /></div>;
  if (error) return <ErrorBox text={error} onRetry={reload} />;

  return (
    <div data-term-cockpit>
      <div className="ck-page-head"><div><h1>{t('term.title')}</h1><p>{t('term.sub')}</p></div></div>

      <section className="ck-card" style={{ marginBottom: 'var(--ck-s6)' }}>
        <div className="ck-card-head"><h2><Tablet size={20} />{t('term.geraete')}</h2></div>
        <div className="ck-card-body">
          <p className="ck-subtle" style={{ marginTop: 0 }}>{t('term.einrichten_hint')} <a href="/hilfe/terminal/" target="_blank" rel="noreferrer" data-term-anleitung>{t('term.anleitung')}</a></p>
          {!data.geraete.length ? <p>{t('term.keine_geraete')}</p> : (
            <div className="ck-table-wrap"><table className="ck-table">
              <thead><tr><th>{t('term.c_name')}</th><th>{t('term.c_objekt')}</th><th>{t('term.c_seit')}</th><th>{t('term.c_gesehen')}</th><th>{t('term.c_status')}</th><th /></tr></thead>
              <tbody>{data.geraete.map((g) => (
                <tr key={g.id} data-term-geraet={g.id}>
                  <td><b>{g.name}</b></td><td>{g.objekt}</td>
                  <td>{fmt(g.erstellt_am)}<div className="ck-subtle">{g.erstellt_von}</div></td>
                  <td>{fmt(g.zuletzt_gesehen)}</td>
                  <td>{g.widerrufen_am ? <Status s="inaktiv" label={t('term.st_widerrufen', { am: fmt(g.widerrufen_am) })} /> : <Status s="aktiv" label={t('term.st_aktiv')} />}</td>
                  <td>{!g.widerrufen_am && <button className="ck-btn ck-btn-sm" onClick={() => widerrufen(g)} data-term-widerrufen={g.id}><ShieldOff size={16} />{t('term.widerrufen')}</button>}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </div>
      </section>

      <section className="ck-card">
        <div className="ck-card-head"><h2><KeyRound size={20} />{t('term.pins', { n: mitPin })}</h2></div>
        <div className="ck-card-body">
          <div className="ck-toolbar" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
            <input className="ck-input" placeholder={t('term.suche')} value={q} onChange={(e) => setQ(e.target.value)} data-term-ma-suche />
            <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}><input type="checkbox" checked={nurOhne} onChange={(e) => setNurOhne(e.target.checked)} />{t('term.nur_ohne')}</label>
          </div>
          <div className="ck-table-wrap"><table className="ck-table">
            <thead><tr><th>{t('term.c_ma')}</th><th>{t('term.c_pin')}</th><th /></tr></thead>
            <tbody>{pins.map((p) => (
              <tr key={p.id} data-term-ma={p.name}>
                <td><b>{p.name}</b> <span className="ck-subtle">{p.personal_nr}{p.test ? ' · Test' : ''}</span></td>
                <td>{p.hat_pin ? (p.gesperrt ? <Status s="offen" label={t('term.gesperrt')} /> : <Status s="aktiv" label={t('term.gesetzt', { am: fmt(p.gesetzt_am) })} />) : <span className="ck-subtle">{t('term.keine_pin')}</span>}</td>
                <td style={{ textAlign: 'right' }}>
                  <button className="ck-btn ck-btn-sm" onClick={() => setPinFuer(p)} data-term-pin-setzen={p.name}><KeyRound size={16} />{p.hat_pin ? t('term.pin_aendern') : t('term.pin_setzen')}</button>
                  {p.hat_pin && <button className="ck-btn ck-btn-sm ck-btn-ghost" onClick={() => pinWeg(p)} aria-label={t('term.pin_weg')}><Trash2 size={16} /></button>}
                </td>
              </tr>))}</tbody>
          </table></div>
        </div>
      </section>
      {pinFuer && <PinDialog ma={pinFuer} onClose={() => setPinFuer(null)} onSaved={reload} />}
    </div>
  );
}
