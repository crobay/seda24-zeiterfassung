// Monatsabschluss mit einem Klick (PROTOTYP, nur Admin): 1 Prüfliste -> 2 Für Lexware erzeugen -> 3 Lohnabrechnungen
// hochladen -> 4 Vorschau je MA -> 5 Alle versenden + Monat sperren. Ersetzt das PC-Skript seda_lohn_email.py.
import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, CheckCircle2, ListChecks, FileSpreadsheet, Upload, Eye, Send, Lock, Download,
  AlertTriangle, FileText, Car, Receipt, Trash2, Mail, LockOpen, ArrowRight } from 'lucide-react';
import { api, apiError, t, fmtNum, useApi, useApp, Status, SkeletonRows, ErrorBox, Dialog } from '../core';

const SCHRITTE = [['pruef', ListChecks], ['lexware', FileSpreadsheet], ['upload', Upload], ['vorschau', Eye], ['versand', Send]];
const ANH_ICON = { lohnabrechnung: Receipt, zeitnachweis: FileText, km: Car };

function vormonat() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
const monatLabel = (k) => new Date(`${k}-15T12:00:00`).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
const schiebe = (k, n) => { const d = new Date(`${k}-15T12:00:00`); d.setMonth(d.getMonth() + n); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; };

async function laden(pfad, name) {
  const r = await api.get(pfad, { responseType: 'blob' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(r.data); a.download = name; document.body.appendChild(a); a.click(); a.remove();
}

export default function Abschluss() {
  const { toast } = useApp();
  const [monat, setMonat] = useState(() => new URLSearchParams(window.location.search).get('monat') || vormonat());
  const { data, loading, error, reload } = useApi(`/abschluss/${monat}`);
  const [schritt, setSchritt] = useState(0);
  const p = data?.pruefliste;
  const zu = data?.status === 'abgeschlossen';
  const erreichbar = (i) => i === 0 || (p?.alle_gruen && (i <= 1 || ['erzeugt', 'abgeschlossen'].includes(data?.status)));
  useEffect(() => { if (zu) setSchritt(4); }, [zu]);
  useEffect(() => { setSchritt(0); }, [monat]);

  return (
    <>
      <div className="ck-page-head">
        <div><h1>{t('ab.title')}</h1><p>{t('ab.subtitle')}</p></div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className="ck-btn ck-btn-icon" onClick={() => setMonat((k) => schiebe(k, -1))} aria-label={t('abr.prev')}><ChevronLeft size={18} /></button>
          <div className="ck-card" style={{ padding: '7px 18px', fontWeight: 650, minWidth: 170, textAlign: 'center' }} data-monat={monat}>{monatLabel(monat)}</div>
          <button className="ck-btn ck-btn-icon" onClick={() => setMonat((k) => schiebe(k, 1))} aria-label={t('abr.next')}><ChevronRight size={18} /></button>
        </div>
      </div>

      <div className="ck-callout ab-proto" role="note"><AlertTriangle size={18} style={{ flex: 'none' }} /><span>{t('ab.proto')}</span></div>

      <ol className="ab-steps" aria-label={t('ab.steps')}>
        {SCHRITTE.map(([k, Icon], i) => {
          const fertig = i < schritt || zu;
          return (
            <li key={k} className={`${i === schritt ? 'is-on' : ''}${fertig ? ' is-done' : ''}`}>
              <button disabled={!erreichbar(i)} onClick={() => setSchritt(i)} aria-current={i === schritt ? 'step' : undefined} data-schritt={k}>
                <span className="ab-num">{fertig ? <CheckCircle2 size={18} /> : i + 1}</span>
                <span className="ab-step-txt"><Icon size={15} />{t(`ab.s_${k}`)}</span>
              </button>
            </li>);
        })}
      </ol>

      {error ? <ErrorBox text={error} onRetry={reload} /> : loading && !data ? <SkeletonRows n={8} /> : (
        <>
          {schritt === 0 && <Pruefliste monat={monat} p={p} zu={zu} onDone={() => setSchritt(1)} reload={reload} toast={toast} />}
          {schritt === 1 && <Lexware monat={monat} data={data} zu={zu} onDone={() => { reload(); setSchritt(2); }} toast={toast} reload={reload} />}
          {schritt === 2 && <Hochladen monat={monat} data={data} zu={zu} onDone={() => setSchritt(3)} toast={toast} reload={reload} />}
          {schritt === 3 && <Vorschau monat={monat} onDone={() => setSchritt(4)} />}
          {schritt === 4 && <Versand monat={monat} data={data} toast={toast} reload={reload} />}
        </>)}
    </>
  );
}

// ---------- Schritt 1: Prüfliste "Hast du ... erledigt?" ----------
function Pruefliste({ monat, p, zu, onDone, reload, toast }) {
  const [busy, setBusy] = useState('');
  if (!p) return null;
  const haken = async (key, wert) => {
    setBusy(key);
    try { await api.post(`/abschluss/${monat}/haken`, { key, wert }); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy('');
  };
  const n = p.punkte.filter((x) => x.gruen).length;
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><ListChecks size={20} />{t('ab.pruef_title')}</h2>
        <span className={`ck-tag${p.alle_gruen ? ' tone-ok' : ''}`} data-fortschritt>{t('ab.n_of', { n, m: p.punkte.length })}</span></div>
      <ul className="ab-check">
        {p.punkte.map((x) => {
          const gesperrt = x.auto === false || zu;
          return (
            <li key={x.key} className={x.gruen ? 'is-ok' : x.auto === false ? 'is-bad' : ''} data-punkt={x.key}>
              <label>
                <input type="checkbox" checked={x.gruen} disabled={gesperrt || busy === x.key} onChange={(e) => haken(x.key, e.target.checked)} />
                <span className="ab-frage">{x.frage}</span>
              </label>
              <span className="ab-auto">
                {x.auto === true ? <Status s="approved" label={t('ab.auto_ok')} /> : x.auto === false ? <Status s="fehlt" label={t('ab.auto_bad')} /> : <Status s="pending" label={t('ab.auto_hand')} />}
              </span>
              {x.detail && <span className="ab-detail">{x.detail}{x.auto === false && x.link && <> · <Link className="ck-link" to={x.link}>{t('ab.fix')}</Link></>}</span>}
              {x.gruen && x.haken_von && <span className="ab-wer">✓ {x.haken_von}</span>}
            </li>);
        })}
      </ul>
      <div className="ab-foot">
        {!p.alle_gruen && <span className="ck-subtle">{t('ab.pruef_hint')}</span>}
        <button className="ck-btn ck-btn-primary" disabled={!p.alle_gruen} onClick={onDone} data-weiter>{t('ab.next')}<ArrowRight size={16} /></button>
      </div>
    </section>);
}

// ---------- Schritt 2: Für Lexware erzeugen ----------
function Lexware({ monat, data, zu, onDone, toast, reload }) {
  const v = useApi(`/abschluss/${monat}/lexware-vorschau`);
  const [la, setLa] = useState(null);
  const [busy, setBusy] = useState(false);
  const [erg, setErg] = useState(null);
  useEffect(() => { if (data?.lohnarten) setLa(data.lohnarten); }, [data]);
  const docs = (data?.dokumente || []).filter((d) => d.art !== 'lohnabrechnung');
  const speichern = async () => {
    try { const r = await api.put('/abschluss/einstellungen/lohnarten', la); setLa(r.data); toast(t('ab.la_saved')); v.reload(); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const erzeugen = async () => {
    setBusy(true);
    try { const r = await api.post(`/abschluss/${monat}/erzeugen`); setErg(r.data); toast(t('ab.made', { n: r.data.zeilen })); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const zeilen = v.data?.zeilen || [];
  return (
    <>
      <section className="ck-card" style={{ marginBottom: 16 }}>
        <div className="ck-card-head"><h2><FileSpreadsheet size={20} />{t('ab.la_title')}</h2></div>
        {la && !la.bestaetigt && <div className="ck-callout" data-la-unbestaetigt><AlertTriangle size={18} />{t('ab.la_unconfirmed')}</div>}
        {la && <div className="ab-la">
          {['normal', 'sonder', 'nacht', 'sonntag', 'feiertag', 'urlaub', 'km'].map((k) => (
            <label key={k}><span>{t(`ab.la_${k}`)}</span>
              <input className="ck-input ck-num" inputMode="numeric" value={la[k] ?? ''} disabled={zu} onChange={(e) => setLa({ ...la, [k]: e.target.value.replace(/\D/g, '') })} /></label>))}
          <label><span>{t('ab.la_persnr')}</span>
            <select className="ck-input" value={la.persnr} disabled={zu} onChange={(e) => setLa({ ...la, persnr: e.target.value })}>
              <option value="wie_app">D0040</option><option value="nur_ziffern">40</option></select></label>
          <label className="ab-la-check"><input type="checkbox" checked={!!la.kopfzeile} disabled={zu} onChange={(e) => setLa({ ...la, kopfzeile: e.target.checked })} />{t('ab.la_head')}</label>
          <label className="ab-la-check"><input type="checkbox" checked={!!la.bestaetigt} disabled={zu} onChange={(e) => setLa({ ...la, bestaetigt: e.target.checked })} />{t('ab.la_ok')}</label>
          <button className="ck-btn" disabled={zu} onClick={speichern}>{t('app.save')}</button>
        </div>}
      </section>

      <section className="ck-card">
        <div className="ck-card-head"><h2>{t('ab.lex_title', { n: zeilen.length })}</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {data?.status !== 'offen' && <button className="ck-btn" onClick={() => laden(`/abschluss/${monat}/paket`, `Monatsabschluss_${monat}_fuer_Lexware.zip`)}><Download size={16} />{t('ab.zip')}</button>}
            <button className="ck-btn ck-btn-primary" disabled={busy || zu} onClick={erzeugen} data-erzeugen><FileSpreadsheet size={16} />{busy ? t('ab.making') : t('ab.make')}</button>
          </div></div>
        <p className="ck-subtle" style={{ marginTop: 0 }}>{t('ab.lex_hint')}</p>
        {v.loading ? <SkeletonRows n={5} /> : (
          <div className="ck-table-wrap ab-lex"><table className="ck-table">
            <thead><tr><th>{t('ab.c_pnr')}</th><th>{t('abr.c_name')}</th><th style={{ textAlign: 'right' }}>{t('ab.c_la')}</th><th>{t('ab.c_bez')}</th>
              <th style={{ textAlign: 'right' }}>{t('ab.c_wert')}</th><th style={{ textAlign: 'right' }}>{t('ab.c_satz')}</th></tr></thead>
            <tbody>{zeilen.map((z, i) => (
              <tr key={i}><td className="ck-num">{z.personal_nr}</td><td>{z.name}</td><td className="ck-num" style={{ textAlign: 'right' }}>{z.lohnart}</td>
                <td>{z.bezeichnung}</td><td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(z.wert, 2)}</td>
                <td className="ck-num" style={{ textAlign: 'right' }}>{z.stundensatz ? fmtNum(z.stundensatz, 2) : ''}</td></tr>))}</tbody>
          </table></div>)}
        {(erg || docs.length > 0) && (
          <div className="ab-made" data-erzeugt>
            <CheckCircle2 size={18} /><span>{t('ab.made_info', { z: docs.filter((d) => d.art === 'zeitnachweis').length, k: docs.filter((d) => d.art === 'km').length, am: (data?.erzeugt_am || '').replace('T', ' ') })}</span>
            {erg?.fehler?.length > 0 && <span className="ck-subtle">{erg.fehler.join(' · ')}</span>}
            <button className="ck-btn ck-btn-primary" onClick={onDone} style={{ marginLeft: 'auto' }}>{t('ab.next')}<ArrowRight size={16} /></button>
          </div>)}
      </section>
    </>);
}

// ---------- Schritt 3: Lohnabrechnungen hochladen ----------
function Hochladen({ monat, data, zu, onDone, toast, reload }) {
  const v = useApi(`/abschluss/${monat}/vorschau`);
  const [busy, setBusy] = useState(false);
  const [ueber, setUeber] = useState(false);
  const inp = useRef(null);
  const docs = (data?.dokumente || []).filter((d) => d.art === 'lohnabrechnung');
  const ma = v.data?.mitarbeiter || [];
  const senden = async (files) => {
    if (!files?.length) return;
    const fd = new FormData(); [...files].forEach((f) => fd.append('dateien', f));
    setBusy(true);
    try { const r = await api.post(`/abschluss/${monat}/lohnabrechnungen`, fd); toast(t('ab.up_done', { n: r.data.neu, d: r.data.doppelt })); reload(); v.reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const zuordnen = async (id, eid) => { try { await api.put(`/abschluss/${monat}/dokument/${id}`, { employee_id: Number(eid) }); reload(); v.reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); } };
  const weg = async (id) => { try { await api.delete(`/abschluss/${monat}/dokument/${id}`); reload(); v.reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); } };
  const ohne = ma.filter((m) => !docs.some((d) => d.employee_id === m.employee_id));
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><Upload size={20} />{t('ab.up_title')}</h2>
        <span className={`ck-tag${ohne.length ? '' : ' tone-ok'}`} data-up-stand>{t('ab.up_stand', { n: ma.length - ohne.length, m: ma.length })}</span></div>
      <p className="ck-subtle" style={{ marginTop: 0 }}>{t('ab.up_hint')}</p>
      {!zu && <div className={`ab-drop${ueber ? ' is-over' : ''}`} onClick={() => inp.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setUeber(true); }} onDragLeave={() => setUeber(false)}
        onDrop={(e) => { e.preventDefault(); setUeber(false); senden(e.dataTransfer.files); }} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') inp.current?.click(); }}>
        <Upload size={26} /><b>{busy ? t('app.loading') : t('ab.drop')}</b><span className="ck-subtle">{t('ab.drop_sub')}</span>
        <input ref={inp} type="file" multiple accept=".pdf,.zip,application/pdf,application/zip" hidden onChange={(e) => { senden(e.target.files); e.target.value = ''; }} data-upload />
      </div>}
      {docs.length > 0 && <div className="ck-table-wrap"><table className="ck-table">
        <thead><tr><th>{t('ab.c_datei')}</th><th>{t('ab.c_ma')}</th><th>{t('ab.c_wie')}</th><th /></tr></thead>
        <tbody>{docs.map((d) => (
          <tr key={d.id} data-dok={d.dateiname}>
            <td><Receipt size={14} /> {d.dateiname}</td>
            <td>{d.employee_id ? <span><b>{d.name}</b> <span className="ck-subtle">{d.personal_nr}</span></span>
              : <select className="ck-input" defaultValue="" onChange={(e) => zuordnen(d.id, e.target.value)} disabled={zu} data-zuordnen>
                  <option value="" disabled>{t('ab.pick')}</option>{ma.map((m) => <option key={m.employee_id} value={m.employee_id}>{m.personal_nr} · {m.name}</option>)}</select>}</td>
            <td>{d.employee_id ? <Status s={d.zuordnung === 'von Hand' ? 'pending' : 'approved'} label={t(`ab.wie_${d.zuordnung === 'von Hand' ? 'hand' : d.zuordnung}`)} /> : <Status s="fehlt" label={t('ab.wie_offen')} />}</td>
            <td style={{ textAlign: 'right' }}>{!zu && <button className="ck-btn ck-btn-icon ck-btn-ghost" onClick={() => weg(d.id)} aria-label={t('ab.del')}><Trash2 size={16} /></button>}</td>
          </tr>))}</tbody></table></div>}
      {ohne.length > 0 && docs.length > 0 && <p className="ck-subtle">{t('ab.up_missing')}: {ohne.map((m) => m.name).join(', ')}</p>}
      <div className="ab-foot"><button className="ck-btn ck-btn-primary" disabled={!docs.length} onClick={onDone}>{t('ab.next')}<ArrowRight size={16} /></button></div>
    </section>);
}

// ---------- Schritt 4: Vorschau je MA ----------
function Vorschau({ monat, onDone }) {
  const { data, loading } = useApi(`/abschluss/${monat}/vorschau`);
  const [offen, setOffen] = useState(null);
  if (loading || !data) return <SkeletonRows n={8} />;
  const alle = data.bereit === data.gesamt && !data.nicht_zugeordnet.length;
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><Eye size={20} />{t('ab.vor_title')}</h2>
        <span className={`ck-tag${alle ? ' tone-ok' : ''}`} data-bereit>{t('ab.vor_stand', { n: data.bereit, m: data.gesamt })}</span></div>
      {data.nicht_zugeordnet.length > 0 && <div className="ck-callout"><AlertTriangle size={18} />{t('ab.vor_lose', { n: data.nicht_zugeordnet.length })}</div>}
      <div className="ck-table-wrap"><table className="ck-table">
        <thead><tr><th>{t('abr.c_name')}</th><th>{t('ab.c_mail')}</th><th>{t('ab.c_anh')}</th><th>{t('ab.c_status')}</th></tr></thead>
        <tbody>{data.mitarbeiter.map((m) => (
          <tr key={m.employee_id} className="ab-row" onClick={() => setOffen(m)} data-ma={m.personal_nr}>
            <td><b>{m.name}</b> <span className="ck-subtle">{m.personal_nr}</span><div className="ck-subtle">{m.anrede},</div></td>
            <td>{m.email ? <span><Mail size={13} /> {m.email}</span> : <Status s="fehlt" label={t('ab.no_mail')} />}</td>
            <td><div className="ab-anh">{m.anhaenge.map((a, i) => { const I = ANH_ICON[a.art] || FileText; return <span key={i} className="ck-tag" title={a.datei}><I size={13} />{t(`ab.art_${a.art}`)}</span>; })}
              {m.ohne_km && <span className="ck-subtle">{t('ab.no_km')}</span>}</div></td>
            <td>{m.bereit ? <Status s="approved" label={t('ab.ready')} /> : <Status s="fehlt" label={t('ab.missing', { was: m.fehlt.join(', ') })} />}</td>
          </tr>))}</tbody></table></div>
      <div className="ab-foot"><button className="ck-btn ck-btn-primary" onClick={onDone}>{t('ab.next')}<ArrowRight size={16} /></button></div>
      {offen && <Dialog title={t('ab.mail_title', { name: offen.name })} onClose={() => setOffen(null)}>
        <div className="ab-mail" data-mail>
          <div><span className="ck-subtle">{t('ab.mail_to')}</span> {offen.email || '–'}</div>
          <div><span className="ck-subtle">{t('ab.mail_subj')}</span> <b>{offen.betreff}</b></div>
          <pre>{offen.text}</pre>
          <div className="ab-anh">{offen.anhaenge.map((a, i) => <span key={i} className="ck-tag"><FileText size={13} />{a.datei}</span>)}</div>
        </div></Dialog>}
    </section>);
}

// ---------- Schritt 5: Alle versenden + Monat sperren ----------
function Versand({ monat, data, toast, reload }) {
  const v = useApi(`/abschluss/${monat}/vorschau`);
  const [frage, setFrage] = useState(false);
  const [oeffnen, setOeffnen] = useState(false);
  const [grund, setGrund] = useState('');
  const [busy, setBusy] = useState(false);
  const prot = data?.protokoll;
  const zu = data?.status === 'abgeschlossen';
  const bereit = v.data && v.data.bereit === v.data.gesamt && !v.data.nicht_zugeordnet.length;
  const los = async () => {
    setBusy(true);
    try { await api.post(`/abschluss/${monat}/versenden`); toast(t('ab.sent')); setFrage(false); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const auf = async () => {
    try { await api.post(`/abschluss/${monat}/wieder-oeffnen`, { grund }); setOeffnen(false); setGrund(''); reload(); toast(t('ab.reopened')); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2>{zu ? <Lock size={20} /> : <Send size={20} />}{zu ? t('ab.closed_title', { m: monatLabel(monat) }) : t('ab.send_title')}</h2>
        {zu && <span className="ck-tag tone-ok" data-gesperrt>{t('ab.closed_at', { am: (prot?.gesperrt_am || '').replace('T', ' ') })}</span>}</div>
      {!zu && <>
        <p>{t('ab.send_text', { n: v.data?.gesamt ?? '…' })}</p>
        {!bereit && v.data && <div className="ck-callout"><AlertTriangle size={18} />{t('ab.send_notready', { n: v.data.gesamt - v.data.bereit })}</div>}
        <button className="ck-btn ck-btn-primary ab-big" disabled={!bereit || busy} onClick={() => setFrage(true)} data-versenden><Send size={18} />{t('ab.send_btn', { n: v.data?.gesamt ?? '' })}</button>
      </>}
      {prot?.versand?.length > 0 && <div className="ck-table-wrap" style={{ marginTop: 16 }}><table className="ck-table" data-protokoll>
        <thead><tr><th>{t('abr.c_name')}</th><th>{t('ab.c_mail')}</th><th>{t('ab.c_anh')}</th><th>{t('ab.c_status')}</th><th>{t('ab.c_am')}</th></tr></thead>
        <tbody>{prot.versand.map((r) => (
          <tr key={r.id}><td><b>{r.name}</b> <span className="ck-subtle">{r.personal_nr}</span></td><td>{r.an}</td><td className="ck-subtle">{r.anhaenge.length} {t('ab.files')}</td>
            <td>{r.status === 'gesendet' ? <Status s="approved" label={t('ab.st_sent')} /> : r.status === 'simuliert' ? <Status s="pending" label={t('ab.st_sim')} /> : <Status s="fehlt" label={r.fehler || r.status} />}</td>
            <td className="ck-num">{r.am.replace('T', ' ')}</td></tr>))}</tbody></table></div>}
      {zu && <div className="ab-foot"><span className="ck-subtle">{t('ab.closed_hint')}</span>
        <button className="ck-btn" onClick={() => setOeffnen(true)}><LockOpen size={16} />{t('ab.reopen')}</button></div>}
      {frage && <Dialog title={t('ab.confirm_title')} onClose={() => setFrage(false)}
        footer={<><button className="ck-btn" onClick={() => setFrage(false)}>{t('app.cancel')}</button>
          <button className="ck-btn ck-btn-primary" disabled={busy} onClick={los} data-ja>{t('ab.confirm_yes')}</button></>}>
        <p>{t('ab.confirm_text', { n: v.data?.gesamt, m: monatLabel(monat) })}</p></Dialog>}
      {oeffnen && <Dialog title={t('ab.reopen')} onClose={() => setOeffnen(false)}
        footer={<><button className="ck-btn" onClick={() => setOeffnen(false)}>{t('app.cancel')}</button>
          <button className="ck-btn ck-btn-primary" disabled={!grund.trim()} onClick={auf}>{t('ab.reopen')}</button></>}>
        <label className="ck-field"><span>{t('ab.reopen_why')}</span><input className="ck-input" value={grund} onChange={(e) => setGrund(e.target.value)} autoFocus /></label></Dialog>}
    </section>);
}
