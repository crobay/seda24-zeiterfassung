// Monatsabschluss mit einem Klick (nur Admin): 1 Prüfliste -> 2 Für Lexware erzeugen -> 3 Lohnabrechnungen
// hochladen -> 4 Vorschau je MA -> 5 Alle versenden + Monat sperren. Ersetzt das PC-Skript seda_lohn_email.py.
import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, CheckCircle2, ListChecks, FileSpreadsheet, Upload, Eye, Send, Lock, Download,
  AlertTriangle, FileText, Car, Receipt, Trash2, Mail, LockOpen, ArrowRight, KeyRound, History, ShieldCheck } from 'lucide-react';
import { api, apiError, t, fmtNum, useApi, useApp, Status, SkeletonRows, ErrorBox, Dialog } from '../core';

const SCHRITTE = [['pruef', ListChecks], ['lexware', FileSpreadsheet], ['upload', Upload], ['vorschau', Eye], ['versand', Send]];
const ANH_ICON = { lohnabrechnung: Receipt, zeitnachweis: FileText, km: Car };

function vormonat() { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
const monatsende = (k) => { const [y, m] = k.split('-').map(Number); return `${k}-${String(new Date(y, m, 0).getDate()).padStart(2, '0')}`; };
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
  const offen = data?.protokoll?.nachtraege?.oeffnungen?.find((o) => o.offen);
  // geoeffneter Monat: Schritt 5 (wieder sperren) immer erreichbar - auch wenn die Korrektur die Pruefliste rot macht
  const erreichbar = (i) => i === 0 || (offen && i === 4) || (p?.alle_gruen && (i <= 1 || ['erzeugt', 'abgeschlossen'].includes(data?.status)));
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

      <div className="ck-callout ab-proto" role="note"><AlertTriangle size={18} style={{ flex: 'none' }} /><span>{t('ab.proto', { von: data?.protokoll?.versandweg?.absender || 'lohn@seda.de' })}</span></div>
      {offen && <div className="ck-callout" role="alert" data-geoeffnet><LockOpen size={18} style={{ flex: 'none' }} />
        <span style={{ flex: 1 }}>{t('ab.offen_hinweis', { am: offen.geoeffnet_am.replace('T', ' ').slice(0, 16), wer: offen.geoeffnet_von, grund: offen.grund })}</span>
        <button className="ck-btn ck-btn-sm" onClick={async () => { try { await api.post(`/abschluss/${monat}/sperren`); reload(); toast(t('ab.locked')); } catch (e) { toast(apiError(e), { tone: 'warn' }); } }}
          data-sperren-oben><Lock size={14} />{t('ab.lock')}</button></div>}

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
          <Nachtraege n={data?.protokoll?.nachtraege} />
        </>)}
    </>
  );
}

// ---------- Schritt 1: Prüfliste "Hast du ... erledigt?" ----------
function Pruefliste({ monat, p, zu, onDone, reload, toast }) {
  const [busy, setBusy] = useState('');
  const [sofort, setSofort] = useState({});      // Haken sofort zeigen, Server bestaetigt danach
  useEffect(() => { setSofort({}); }, [p]);
  if (!p) return null;
  const haken = async (key, wert) => {
    setBusy(key); setSofort((s) => ({ ...s, [key]: wert }));
    try { await api.post(`/abschluss/${monat}/haken`, { key, wert }); reload(); }
    catch (e) { setSofort((s) => { const n = { ...s }; delete n[key]; return n; }); toast(apiError(e), { tone: 'warn' }); }
    setBusy('');
  };
  const n = p.punkte.filter((x) => x.gruen).length;
  return (
    <>
    <MaListe monat={monat} p={p} zu={zu} haken={haken} sofort={sofort} busy={busy} reload={reload} toast={toast} />
    <section className="ck-card">
      <div className="ck-card-head"><h2><ListChecks size={20} />{t('ab.pruef_title')}</h2>
        <span className={`ck-tag${p.alle_gruen ? ' tone-ok' : ''}`} data-fortschritt>{t('ab.n_of', { n, m: p.punkte.length })}</span></div>
      <ul className="ab-check">
        {p.punkte.map((x) => {
          const gesperrt = x.auto === false || zu;
          return (
            <li key={x.key} className={x.gruen ? 'is-ok' : x.auto === false ? 'is-bad' : ''} data-punkt={x.key}>
              <label>
                <input type="checkbox" checked={x.key in sofort ? sofort[x.key] : x.gruen} disabled={gesperrt || busy === x.key} onChange={(e) => haken(x.key, e.target.checked)} />
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
    </section>
    </>);
}

// Liste je MA (Wunsch Drazen 20.11.): Stunden + KM mit je einem Haken, daneben die automatische Stichprobe.
// Der Haken merkt sich die Zahl - aendert sie sich (Korrektur), ist er weg und muss neu gesetzt werden.
function MaListe({ monat, p, zu, haken, sofort, busy, reload, toast }) {
  const mas = p.mitarbeiter || [];
  const [alleBusy, setAlleBusy] = useState(false);
  const [zeigProt, setZeigProt] = useState(false);
  const alle = async () => {
    setAlleBusy(true);
    try {
      const r = await api.post(`/abschluss/${monat}/haken-alle-unauffaellig`);
      toast(t('ab.ma_alle_ok', { n: r.data.gesetzt / 2, o: r.data.offen_mit_hinweis.length }));
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setAlleBusy(false);
  };
  const prot = p.haken_protokoll || [];
  const an = (x, art) => { const k = `ma:${x.employee_id}:${art}`; return k in sofort ? sofort[k] : x[`haken_${art}`]; };
  const box = (x, art) => {
    const k = `ma:${x.employee_id}:${art}`;
    return (
      <label className="ab-ma-haken" title={x[`haken_${art}_von`] ? `✓ ${x[`haken_${art}_von`]}` : undefined}>
        <input type="checkbox" checked={an(x, art)} disabled={zu || busy === k} onChange={(e) => haken(k, e.target.checked)} data-ma-haken={`${x.personal_nr}:${art}`} />
        {t(`ab.ma_h_${art === 'stunden' ? 'std' : 'km'}`)}
      </label>);
  };
  return (
    <section className="ck-card" style={{ marginBottom: 16 }} data-ma-liste>
      <div className="ck-card-head"><h2><ListChecks size={20} />{t('ab.ma_title')}</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="ck-btn ck-btn-sm" disabled={zu || alleBusy || !p.ma_unauffaellig_offen} onClick={alle} data-ma-alle>
            <CheckCircle2 size={15} />{t('ab.ma_alle', { n: p.ma_unauffaellig_offen || 0 })}</button>
          <span className={`ck-tag${p.ma_ok === p.ma_gesamt ? ' tone-ok' : ''}`} data-ma-fortschritt>{t('ab.ma_n', { n: p.ma_ok, m: p.ma_gesamt })}</span>
        </div></div>
      <p className="ck-subtle" style={{ margin: '0 16px 10px' }}>{t('ab.ma_hint')}</p>
      <div className="ck-table-wrap"><table className="ck-table ab-ma">
        <thead><tr><th>{t('ab.c_pnr')}</th><th>{t('abr.c_name')}</th><th style={{ textAlign: 'right' }}>{t('ab.ma_c_std')}</th><th></th>
          <th style={{ textAlign: 'right' }}>{t('ab.ma_c_km')}</th><th></th><th style={{ textAlign: 'right' }}>{t('ab.ma_c_plan')}</th><th>{t('ab.ma_c_pruef')}</th></tr></thead>
        <tbody>{mas.map((x) => {
          const rot = x.hinweise.some((h) => h.rot);
          const fertig = an(x, 'stunden') && an(x, 'km');
          return (
            <tr key={x.employee_id} className={fertig ? 'is-ok' : ''} data-ma={x.personal_nr}>
              <td className="ck-num">{x.personal_nr}</td>
              <td><Link className="ck-link" to={`/cockpit/zeiten?von=${monat}-01&bis=${monatsende(monat)}&q=${encodeURIComponent(x.personal_nr)}`} title={t('ab.ma_zeiten')}>{x.name}</Link></td>
              <td className="ck-num" style={{ textAlign: 'right' }} title={t('ab.ma_detail', { n: fmtNum(x.normal, 2), s: fmtNum(x.sonder, 2), f: fmtNum(x.feiertag, 2), u: fmtNum(x.urlaub, 2) })}>{fmtNum(x.stunden, 2)}</td>
              <td>{box(x, 'stunden')}{x.haken_stunden_veraltet && <div className="ab-ma-alt">{t('ab.ma_veraltet')}</div>}</td>
              <td className="ck-num" style={{ textAlign: 'right' }}>{x.ohne_km ? <span className="ck-subtle">{t('ab.ma_kein_km')}</span> : `${fmtNum(x.km, 2)} €`}</td>
              <td>{box(x, 'km')}{x.haken_km_veraltet && <div className="ab-ma-alt">{t('ab.ma_veraltet')}</div>}</td>
              <td className="ck-num" style={{ textAlign: 'right' }}>{fmtNum(x.plan_h, 2)} / {fmtNum(x.ist_h, 2)}</td>
              <td className="ab-ma-pruef">{x.hinweise.length === 0 ? <Status s="approved" label={t('ab.ma_ok')} />
                : x.hinweise.map((h, i) => <div key={i} className={h.rot ? 'is-rot' : 'is-info'} data-ma-hinweis={h.rot ? 'rot' : 'info'}>{h.rot ? '● ' : '○ '}{h.text}</div>)}
                {rot && <span className="ck-subtle"> </span>}</td>
            </tr>);
        })}</tbody>
      </table></div>
      <div style={{ padding: '10px 16px' }}>
        <button className="ck-btn ck-btn-sm" onClick={() => setZeigProt(!zeigProt)} data-haken-prot-knopf><History size={14} />{t('ab.ma_prot', { n: prot.length })}</button>
        {zeigProt && <ul className="ab-haken-prot" data-haken-prot>
          {prot.length === 0 ? <li className="ck-subtle">{t('ab.ma_prot_leer')}</li> : prot.map((r) => (
            <li key={r.key}><span className="ck-num">{(r.am || '').replace('T', ' ')}</span> · <b>{r.von}</b> · {r.was}{r.sammel ? ` · ${t('ab.ma_sammel')}` : ''}</li>))}
        </ul>}
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
        {v.data?.fehlende_lohnarten?.length > 0 && <div className="ck-callout" data-la-fehlt><AlertTriangle size={18} />{t('ab.la_fehlt', { was: v.data.fehlende_lohnarten.join(', ') })}</div>}
        {la && <div className="ab-la">
          {['normal', 'sonder', 'nacht', 'sonntag', 'feiertag', 'urlaub', 'km'].map((k) => (
            <label key={k}><span>{t(`ab.la_${k}`)}</span>
              <input className="ck-input ck-num" inputMode="numeric" value={la[k] ?? ''} placeholder={t('ab.la_leer')} disabled={zu} onChange={(e) => setLa({ ...la, [k]: e.target.value.replace(/\D/g, '') })} /></label>))}
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
            {data?.status !== 'offen' && <button className="ck-btn" data-lex-test onClick={() => laden(`/abschluss/${monat}/lexware-datei?als=${schiebe(monat, 1)}`, `Lexware_Lohndaten_${monat}_als_${schiebe(monat, 1)}_TEST.txt`).catch(() => toast(t('ab.la_fehlt', { was: '…' }), { tone: 'warn' }))}>
              <Download size={16} />{t('ab.lex_als', { m: monatLabel(schiebe(monat, 1)) })}</button>}
            <button className="ck-btn ck-btn-primary" disabled={busy || zu} onClick={erzeugen} data-erzeugen><FileSpreadsheet size={16} />{busy ? t('ab.making') : t('ab.make')}</button>
          </div></div>
        <p className="ck-subtle" style={{ marginTop: 0 }}>{t('ab.lex_hint')}</p>
        {v.loading ? <SkeletonRows n={5} /> : (
          <div className="ck-table-wrap ab-lex"><table className="ck-table">
            <thead><tr><th>{t('ab.c_pnr')}</th><th>{t('abr.c_name')}</th><th style={{ textAlign: 'right' }}>{t('ab.c_la')}</th><th>{t('ab.c_bez')}</th>
              <th style={{ textAlign: 'right' }}>{t('ab.c_wert')}</th><th style={{ textAlign: 'right' }}>{t('ab.c_satz')}</th></tr></thead>
            <tbody>{zeilen.map((z, i) => (
              <tr key={i}><td className="ck-num">{z.personal_nr}</td><td>{z.name}</td><td className="ck-num" style={{ textAlign: 'right' }}>{z.lohnart ?? <Status s="fehlt" label={t('ab.la_leer')} />}</td>
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
  // Kein manuelles Hochladen (Drazen 19.11.): das PC-Skript seda24_lohn_upload.ps1 auf SEDA2026 laedt neue
  // Lohnabrechnung_*.pdf aus dem Lexware-Ausgabeordner hoch. Hier: Stand "x von y da", Zuordnung, Aufbewahrung.
  const v = useApi(`/abschluss/${monat}/vorschau`);
  const docs = (data?.dokumente || []).filter((d) => d.art === 'lohnabrechnung');
  const st = data?.lohnabrechnungen;
  const ma = v.data?.mitarbeiter || [];
  const abl = data?.lohnablage;
  const [monate, setMonate] = useState('');
  useEffect(() => { if (abl) setMonate(String(abl.aufbewahrung_monate)); }, [abl?.aufbewahrung_monate]);
  useEffect(() => {        // neue Dateien vom PC sofort sehen
    if (zu || st?.komplett) return undefined;
    const i = setInterval(() => { reload(); v.reload(); }, 20000);
    return () => clearInterval(i);
  }, [zu, st?.komplett]);
  const zuordnen = async (id, eid) => { try { await api.put(`/abschluss/${monat}/dokument/${id}`, { employee_id: Number(eid) }); reload(); v.reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); } };
  const weg = async (id) => { try { await api.delete(`/abschluss/${monat}/dokument/${id}`); reload(); v.reload(); } catch (e) { toast(apiError(e), { tone: 'warn' }); } };
  const ablageSpeichern = async () => {
    try { await api.put('/abschluss/einstellungen/lohnablage', { aufbewahrung_monate: Number(monate) }); toast(t('ab.set_saved')); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const wie = (z) => (z === 'von Hand' ? 'hand' : z === 'PDF-Text' ? 'text' : z);
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2><Receipt size={20} />{t('ab.up_title')}</h2>
        {st && <span className={`ck-tag${st.komplett ? ' tone-ok' : ''}`} data-up-stand>
          {st.komplett && <CheckCircle2 size={14} />} {t('ab.up_stand', { n: st.da, m: st.erwartet })}</span>}</div>
      <p className="ck-subtle" style={{ marginTop: 0 }}>{t('ab.up_hint')}{' '}
        <a href="/downloads/seda24_lohn_upload.ps1" download>{t('ab.up_skript')}</a></p>
      {st && st.fehlen.length > 0 && <div className="ck-callout" data-up-fehlen><AlertTriangle size={18} style={{ flex: 'none' }} />
        <span>{t('ab.up_missing')}: {st.fehlen.map((m) => m.name).join(', ')}</span></div>}
      {docs.length > 0 && <div className="ck-table-wrap"><table className="ck-table">
        <thead><tr><th>{t('ab.c_datei')}</th><th>{t('ab.c_ma')}</th><th>{t('ab.c_wie')}</th><th /></tr></thead>
        <tbody>{docs.map((d) => (
          <tr key={d.id} data-dok={d.dateiname}>
            <td><Receipt size={14} /> {d.dateiname}</td>
            <td>{d.employee_id ? <span><b>{d.name}</b> <span className="ck-subtle">{d.personal_nr}</span></span>
              : <select className="ck-input" defaultValue="" onChange={(e) => zuordnen(d.id, e.target.value)} disabled={zu} data-zuordnen>
                  <option value="" disabled>{t('ab.pick')}</option>{ma.map((m) => <option key={m.employee_id} value={m.employee_id}>{m.personal_nr} · {m.name}</option>)}</select>}</td>
            <td>{d.employee_id ? <Status s={d.zuordnung === 'von Hand' ? 'pending' : 'approved'} label={t(`ab.wie_${wie(d.zuordnung)}`)} />
              : <Status s="fehlt" label={t(d.zuordnung === 'Widerspruch' ? 'ab.wie_widerspruch' : 'ab.wie_offen')} />}</td>
            <td style={{ textAlign: 'right' }}>{!zu && <button className="ck-btn ck-btn-icon ck-btn-ghost" onClick={() => weg(d.id)} aria-label={t('ab.del')}><Trash2 size={16} /></button>}</td>
          </tr>))}</tbody></table></div>}
      {!docs.length && <p className="ck-subtle" data-up-leer>{t('ab.up_leer')}</p>}
      {abl && <div className="ab-la" style={{ marginTop: 16 }} data-aufbewahrung>
        <label><span>{t('ab.abl_monate')}</span>
          <input className="ck-input ck-num" inputMode="numeric" value={monate} onChange={(e) => setMonate(e.target.value.replace(/\D/g, ''))} /></label>
        <button className="ck-btn" disabled={!monate || monate === String(abl.aufbewahrung_monate)} onClick={ablageSpeichern}>{t('app.save')}</button>
        <span className="ck-subtle">{t('ab.abl_hint', { am: new Date(`${abl.loeschen_ab}T12:00:00`).toLocaleDateString('de-DE') })}</span>
      </div>}
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
// Versand über Microsoft Graph aus lohn@seda.de, einstellbar (Kopie in „Gesendete Elemente“, kein BCC). Testmodus = alles an Drazen.
function Versand({ monat, data, toast, reload }) {
  const v = useApi(`/abschluss/${monat}/vorschau`);
  const [frage, setFrage] = useState(false);
  const [oeffnen, setOeffnen] = useState(false);
  const [grund, setGrund] = useState('');
  const [pin, setPin] = useState('');
  const [pinDlg, setPinDlg] = useState(false);
  const sp = data?.superpin || {};
  const [busy, setBusy] = useState(null);
  const [verlauf, setVerlauf] = useState(false);
  const prot = data?.protokoll;
  const ein = prot?.einstellungen || {};
  const weg = prot?.versandweg || {};
  const [testAn, setTestAn] = useState('');
  useEffect(() => { setTestAn(ein.test_an || ''); }, [ein.test_an]);
  const zu = data?.status === 'abgeschlossen';
  const test = ein.testmodus !== false;
  const kannSenden = weg.konfiguriert || (test && weg.weg_test && weg.weg_test !== 'keiner');
  const bereit = v.data && v.data.bereit === v.data.gesamt && !v.data.nicht_zugeordnet.length;
  const los = async () => {
    setBusy('alle');
    try {
      const r = await api.post(`/abschluss/${monat}/versenden`);
      const e = r.data.ergebnis;
      toast(t(e.testmodus ? 'ab.sent_test' : 'ab.sent', { n: e.gesendet, f: e.fehler }), e.fehler ? { tone: 'warn' } : undefined);
      setFrage(false); reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(null);
  };
  const einzeln = async (eid) => {
    setBusy(eid);
    try { const r = await api.post(`/abschluss/${monat}/versenden/${eid}`); toast(r.data.ergebnis.fehler ? t('ab.resend_bad') : t('ab.resend_ok'), r.data.ergebnis.fehler ? { tone: 'warn' } : undefined); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(null);
  };
  const einstellen = async (werte) => {
    try { await api.put('/abschluss/einstellungen/lohnversand', { ...ein, ...werte }); toast(t('ab.set_saved')); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const sperren = async () => {
    try { await api.post(`/abschluss/${monat}/sperren`); reload(); toast(t('ab.locked')); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const auf = async () => {
    try { await api.post(`/abschluss/${monat}/wieder-oeffnen`, { grund, pin }); setOeffnen(false); setGrund(''); setPin(''); reload(); toast(t('ab.reopened')); }
    catch (e) { setPin(''); toast(apiError(e), { tone: 'warn' }); reload(); }
  };
  const stat = (r) => r.status === 'gesendet' ? <Status s="approved" label={t('ab.st_sent')} />
    : r.status === 'test' ? <Status s="pending" label={t('ab.st_test')} />
    : r.status === 'simuliert' ? <Status s="pending" label={t('ab.st_sim')} /> : <Status s="fehlt" label={r.fehler || r.status} />;
  const vorschauMa = v.data?.mitarbeiter || [];
  const jeMa = Object.fromEntries((prot?.je_ma || []).map((r) => [r.employee_id, r]));
  return (
    <section className="ck-card">
      <div className="ck-card-head"><h2>{zu ? <Lock size={20} /> : <Send size={20} />}{zu ? t('ab.closed_title', { m: monatLabel(monat) }) : t('ab.send_title')}</h2>
        {zu && <span className="ck-tag tone-ok" data-gesperrt>{t('ab.closed_at', { am: (prot?.gesperrt_am || '').replace('T', ' ') })}</span>}</div>

      <div className={`ck-callout${test ? '' : ' c-info'}`} data-versandweg>
        <Mail size={18} style={{ flex: 'none' }} />
        <div style={{ flex: 1 }}>
          <div data-absender>{t('ab.weg', { von: weg.absender || 'lohn@seda.de', name: weg.absender_name || '', antwort: weg.antwort_an || weg.absender || '' })}{!weg.konfiguriert && <b> {t('ab.weg_fehlt')}</b>}</div>
          <Absender ein={ein} einstellen={einstellen} />
          {!weg.konfiguriert && test && <div data-testweg>{t('ab.testweg', { weg: weg.weg || '' })}
</div>}
          <label className="ab-la-check" style={{ marginTop: 6 }}>
            <input type="checkbox" checked={test} data-testmodus onChange={(e) => einstellen({ testmodus: e.target.checked })} disabled={!weg.echt_erlaubt && test} />
            {t('ab.testmodus')}</label>
          {test && <label className="ck-field" style={{ maxWidth: 360 }}><span>{t('ab.test_an')}</span>
            <span style={{ display: 'flex', gap: 6 }}><input className="ck-input" value={testAn} onChange={(e) => setTestAn(e.target.value)} />
              <button className="ck-btn" disabled={testAn === ein.test_an} onClick={() => einstellen({ test_an: testAn })}>{t('app.save')}</button></span></label>}
          {!weg.echt_erlaubt && <div className="ck-subtle">{t('ab.nur_test')}</div>}
          <MicrosoftZugang weg={weg} toast={toast} reload={reload} />
        </div>
      </div>

      {(!zu || test) && <>
        <p>{t(test ? 'ab.send_text_test' : 'ab.send_text', { n: v.data?.gesamt ?? '…', an: ein.test_an })}</p>
        {!bereit && v.data && <div className="ck-callout"><AlertTriangle size={18} />{t('ab.send_notready', { n: v.data.gesamt - v.data.bereit })}</div>}
        <button className="ck-btn ck-btn-primary ab-big" disabled={!bereit || !!busy || !kannSenden} onClick={() => setFrage(true)} data-versenden>
          <Send size={18} />{busy === 'alle' ? t('ab.sending') : t(test ? 'ab.send_btn_test' : 'ab.send_btn', { n: v.data?.gesamt ?? '' })}</button>
        {test && weg.weg_test === 'datei_test' && prot?.versand?.some((r) => r.status === 'test') &&
          <button className="ck-btn ab-big" style={{ marginLeft: 10 }} onClick={() => laden(`/abschluss/${monat}/testversand.zip`, `Testversand_${monat}.zip`)} data-eml>
            <Download size={18} />{t('ab.eml_laden')}</button>}
      </>}

      {vorschauMa.length > 0 && <div className="ck-table-wrap" style={{ marginTop: 16 }}><table className="ck-table" data-je-ma>
        <thead><tr><th>{t('abr.c_name')}</th><th>{t('ab.c_mail')}</th><th>{t('ab.c_status')}</th><th>{t('ab.c_am')}</th><th /></tr></thead>
        <tbody>{vorschauMa.map((m) => { const r = jeMa[m.employee_id]; return (
          <tr key={m.employee_id} data-ma={m.personal_nr}><td><b>{m.name}</b> <span className="ck-subtle">{m.personal_nr}</span></td>
            <td>{r?.an || m.email || '–'}</td><td>{r ? stat(r) : <span className="ck-subtle">{t('ab.st_offen')}</span>}</td>
            <td className="ck-num">{r ? r.am.replace('T', ' ') : ''}</td>
            <td style={{ textAlign: 'right' }}>{r && <button className="ck-btn ck-btn-sm" disabled={!!busy || !m.bereit || !kannSenden} onClick={() => einzeln(m.employee_id)} data-erneut>
              <Send size={14} />{busy === m.employee_id ? t('ab.sending') : t('ab.resend')}</button>}</td></tr>); })}</tbody></table></div>}

      {prot?.versand?.length > 0 && <div style={{ marginTop: 12 }}>
        <button className="ck-btn ck-btn-ghost" onClick={() => setVerlauf((x) => !x)}>{t('ab.verlauf', { n: prot.versand.length })}</button>
        {verlauf && <div className="ck-table-wrap" style={{ marginTop: 8 }}><table className="ck-table" data-protokoll>
          <thead><tr><th>{t('ab.c_am')}</th><th>{t('abr.c_name')}</th><th>{t('ab.c_mail')}</th><th>{t('ab.c_anh')}</th><th>{t('ab.c_status')}</th></tr></thead>
          <tbody>{prot.versand.slice().reverse().map((r) => (
            <tr key={r.id}><td className="ck-num">{r.am.replace('T', ' ')}</td><td>{r.name}</td><td>{r.an}</td>
              <td className="ck-subtle" title={r.anhaenge.join('\n')}>{r.anhaenge.length} {t('ab.files')}</td><td>{stat(r)}</td></tr>))}</tbody></table></div>}
      </div>}

      <div className="ab-foot">
        {zu ? <><span className="ck-subtle">{t('ab.closed_hint')}</span>
          {sp.inhaber && <button className="ck-btn" onClick={() => setOeffnen(true)} data-oeffnen><LockOpen size={16} />{t('ab.reopen')}</button>}</>
          : data?.status === 'erzeugt' &&
            <button className="ck-btn" onClick={sperren} data-sperren><Lock size={16} />{t('ab.lock')}</button>}
        {sp.inhaber && <button className="ck-btn ck-btn-ghost ck-btn-sm" onClick={() => setPinDlg(true)} data-pin-einrichten>
          <KeyRound size={14} />{t(sp.eingerichtet ? 'ab.pin_aendern' : 'ab.pin_einrichten')}</button>}
      </div>
      {pinDlg && <SuperPin sp={sp} onClose={() => setPinDlg(false)} toast={toast} reload={reload} />}
      {frage && <Dialog title={t(test ? 'ab.confirm_title_test' : 'ab.confirm_title')} onClose={() => setFrage(false)}
        footer={<><button className="ck-btn" onClick={() => setFrage(false)}>{t('app.cancel')}</button>
          <button className="ck-btn ck-btn-primary" disabled={!!busy} onClick={los} data-ja>{busy ? t('ab.sending') : t('ab.confirm_yes')}</button></>}>
        <p>{t(test ? 'ab.confirm_text_test' : 'ab.confirm_text', { n: v.data?.gesamt, m: monatLabel(monat), an: ein.test_an })}</p></Dialog>}
      {oeffnen && <Dialog title={t('ab.reopen_title', { m: monatLabel(monat) })} onClose={() => { setOeffnen(false); setPin(''); }}
        footer={<><button className="ck-btn" onClick={() => { setOeffnen(false); setPin(''); }}>{t('app.cancel')}</button>
          <button className="ck-btn ck-btn-primary" disabled={grund.trim().length < 10 || pin.length < 6 || !sp.eingerichtet} onClick={auf} data-oeffnen-ok>
            <LockOpen size={16} />{t('ab.reopen')}</button></>}>
        <p>{t('ab.reopen_text')}</p>
        {!sp.eingerichtet ? <div className="ck-callout"><KeyRound size={18} />{t('ab.pin_fehlt')}</div>
          : (sp.gesperrt_bis || sp.dauerhaft_gesperrt) && <div className="ck-callout"><AlertTriangle size={18} />
            {sp.dauerhaft_gesperrt ? t('ab.pin_dauerhaft') : t('ab.pin_gesperrt', { bis: sp.gesperrt_bis.slice(11, 16) })}</div>}
        <label className="ck-field"><span>{t('ab.reopen_why')}</span>
          <textarea className="ck-input" rows={3} value={grund} onChange={(e) => setGrund(e.target.value)} autoFocus data-grund placeholder={t('ab.reopen_why_ph')} /></label>
        <label className="ck-field" style={{ maxWidth: 220 }}><span>{t('ab.pin')}</span>
          <input className="ck-input" type="password" inputMode="numeric" autoComplete="off" maxLength={10} value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} data-pin /></label></Dialog>}
    </section>);
}

// Microsoft-Zugang (Entra-App) im Cockpit eintragen: nur schreiben, nie anzeigen. Test = nur Anmeldung, keine Mail.
function MicrosoftZugang({ weg, toast, reload }) {
  const [auf, setAuf] = useState(false);
  const [z, setZ] = useState({ tenant: '', client_id: '', secret: '' });
  const [test, setTest] = useState(null);
  const speichern = async () => {
    try { await api.put('/abschluss/einstellungen/microsoft', z); setZ({ tenant: '', client_id: '', secret: '' }); setAuf(false); toast(t('ab.ms_saved')); reload(); }
    catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const pruefen = async () => { setTest({ text: t('app.loading') }); try { setTest((await api.post('/abschluss/einstellungen/microsoft/test')).data); } catch (e) { setTest({ ok: false, text: apiError(e) }); } };
  return (
    <div style={{ marginTop: 8 }} data-ms-zugang>
      {weg.konfiguriert && <span className="ck-subtle">{t('ab.ms_da', { am: weg.zugang_am || '.env', id: weg.client_ende || '' })} </span>}
      {weg.konfiguriert && <button className="ck-btn ck-btn-sm" onClick={pruefen} data-ms-test>{t('ab.ms_test')}</button>}
      <button className="ck-btn ck-btn-sm ck-btn-ghost" onClick={() => setAuf((x) => !x)}>{t(weg.konfiguriert ? 'ab.ms_neu' : 'ab.ms_eintragen')}</button>
      {test && <div className={test.ok ? '' : 'ck-subtle'} style={{ marginTop: 6 }} data-ms-ergebnis>{test.ok ? '✓ ' : ''}{test.text}</div>}
      {auf && <div className="ab-la" style={{ marginTop: 8 }}>
        {[['tenant', 'ab.ms_tenant'], ['client_id', 'ab.ms_client'], ['secret', 'ab.ms_secret']].map(([k, l]) => (
          <label key={k}><span>{t(l)}</span><input className="ck-input" type="password" autoComplete="off" value={z[k]} onChange={(e) => setZ({ ...z, [k]: e.target.value })} /></label>))}
        <button className="ck-btn" disabled={!z.tenant || !z.client_id || !z.secret} onClick={speichern}>{t('app.save')}</button>
        <span className="ck-subtle">{t('ab.ms_hint')}</span>
      </div>}
    </div>);
}

// Super-PIN (nur Inhaber = Drazen): erstes Einrichten mit Login-Passwort, Ändern mit alter PIN. Nichts wird angezeigt.
function SuperPin({ sp, onClose, toast, reload }) {
  const [f, setF] = useState({ passwort: '', pin_alt: '', pin: '', pin2: '' });
  const set = (k) => (e) => setF({ ...f, [k]: k === 'passwort' ? e.target.value : e.target.value.replace(/\D/g, '') });
  const ok = f.pin.length >= 6 && f.pin === f.pin2 && (sp.eingerichtet ? f.pin_alt.length >= 6 : f.passwort);
  const speichern = async () => {
    try {
      await api.put('/abschluss/einstellungen/superpin', sp.eingerichtet ? { pin_alt: f.pin_alt, pin: f.pin } : { passwort: f.passwort, pin: f.pin });
      toast(t('ab.pin_ok')); onClose(); reload();
    } catch (e) { setF({ ...f, pin_alt: '', passwort: '' }); toast(apiError(e), { tone: 'warn' }); reload(); }
  };
  const feld = (k, label, art = 'pin') => (
    <label className="ck-field" style={{ maxWidth: 260 }}><span>{t(label)}</span>
      <input className="ck-input" type="password" autoComplete={art === 'pin' ? 'off' : 'current-password'} inputMode={art === 'pin' ? 'numeric' : undefined}
        maxLength={art === 'pin' ? 10 : undefined} value={f[k]} onChange={set(k)} data-feld={k} /></label>);
  return (
    <Dialog title={t(sp.eingerichtet ? 'ab.pin_aendern' : 'ab.pin_einrichten')} onClose={onClose}
      footer={<><button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
        <button className="ck-btn ck-btn-primary" disabled={!ok} onClick={speichern} data-pin-speichern>{t('app.save')}</button></>}>
      <p>{t('ab.pin_regeln')}</p>
      {sp.eingerichtet ? feld('pin_alt', 'ab.pin_alt') : feld('passwort', 'ab.pin_passwort', 'pw')}
      {feld('pin', 'ab.pin_neu')}
      {feld('pin2', 'ab.pin_neu2')}
      {f.pin2 && f.pin !== f.pin2 && <div className="ck-subtle">{t('ab.pin_ungleich')}</div>}
    </Dialog>);
}

// „Nachträgliche Änderungen“: jede Öffnung (Grund, wer, wann), jede Änderung alt → neu, erneutes Sperren. Nur lesen.
const wert = (v) => v === null || v === undefined || v === '' ? '(leer)' : typeof v === 'object' ? JSON.stringify(v) : String(v).replace(/^(\d{4}-\d\d-\d\d)T(\d\d:\d\d)(:\d\d(\.\d+)?)?$/, '$1 $2');
function Nachtraege({ n }) {
  if (!n?.oeffnungen?.length) return null;
  return (
    <section className="ck-card" style={{ marginTop: 16 }} data-nachtraege>
      <div className="ck-card-head"><h2><History size={20} />{t('ab.nach_title')}</h2>
        <span className={`ck-tag ${n.kette_ok ? 'tone-ok' : 'tone-bad'}`} data-kette title={t('ab.kette_hint')}>
          {n.kette_ok ? <><ShieldCheck size={14} /> {t('ab.kette_ok', { n: n.zeilen })}</> : t('ab.kette_bad')}</span></div>
      <p className="ck-subtle">{t('ab.nach_text')}</p>
      {n.oeffnungen.slice().reverse().map((o) => (
        <div key={o.id} className="ab-nach" data-oeffnung={o.id} style={{ borderTop: '1px solid var(--ck-border)', paddingTop: 10, marginTop: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><LockOpen size={15} /> <b>{t('ab.nach_geoeffnet', { am: wert(o.geoeffnet_am), wer: o.geoeffnet_von })}</b></div>
          <div style={{ margin: '4px 0 8px 22px' }}>{t('ab.nach_grund')}: <i>{o.grund}</i></div>
          {o.aenderungen.length ? <div className="ck-table-wrap"><table className="ck-table">
            <thead><tr><th>{t('ab.c_am')}</th><th>{t('ab.nach_wer')}</th><th>{t('ab.nach_was')}</th><th>{t('abr.c_name')}</th><th>{t('ab.nach_felder')}</th></tr></thead>
            <tbody>{o.aenderungen.map((a) => (
              <tr key={a.id} data-aenderung={a.id}><td className="ck-num">{wert(a.am)}</td><td>{a.wer}</td>
                <td>{a.tabelle} #{a.datensatz_id ?? '–'} <b>{a.aktion}</b></td><td>{a.mitarbeiter || '–'}</td>
                <td>{a.felder.map((f) => <div key={f.feld}><span className="ck-subtle">{f.feld}:</span> {a.aktion !== 'neu' && <><s>{wert(f.alt)}</s> → </>}{a.aktion === 'gelöscht' ? '' : wert(f.neu)}</div>)}</td></tr>))}</tbody>
          </table></div> : <div className="ck-subtle" style={{ marginLeft: 22 }}>{t('ab.nach_keine')}</div>}
          <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>{o.offen ? <span className="ck-tag tone-warn">{t('ab.nach_offen')}</span>
            : <><Lock size={15} /> {t('ab.nach_gesperrt', { am: wert(o.gesperrt_am), wer: o.gesperrt_von })}</>}</div>
        </div>))}
    </section>);
}

// Absender der Lohn-Mails (Drazen 19.11.: lohn@seda.de „SEDA24 Lohnbuchhaltung“; buchhaltung@ bleibt für Kundenrechnungen)
function Absender({ ein, einstellen }) {
  const [auf, setAuf] = useState(false);
  const [f, setF] = useState({ absender: '', absender_name: '', antwort_an: '' });
  useEffect(() => { setF({ absender: ein.absender || '', absender_name: ein.absender_name || '', antwort_an: ein.antwort_an || '' }); }, [ein.absender, ein.absender_name, ein.antwort_an, auf]);
  if (!auf) return <button className="ck-btn ck-btn-sm ck-btn-ghost" style={{ marginTop: 4 }} onClick={() => setAuf(true)} data-abs-aendern>{t('ab.abs_aendern')}</button>;
  return (
    <div className="ab-la" style={{ marginTop: 8 }} data-abs-form>
      {[['absender', 'ab.abs_adresse'], ['absender_name', 'ab.abs_name'], ['antwort_an', 'ab.abs_antwort']].map(([k, l]) => (
        <label key={k}><span>{t(l)}</span><input className="ck-input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-abs={k} /></label>))}
      <button className="ck-btn" disabled={!f.absender.endsWith('@seda.de') || f.absender_name.trim().length < 2}
        onClick={async () => { await einstellen(f); setAuf(false); }} data-abs-speichern>{t('app.save')}</button>
      <button className="ck-btn ck-btn-ghost" onClick={() => setAuf(false)}>{t('app.cancel')}</button>
      <span className="ck-subtle">{t('ab.abs_hint')}</span>
    </div>);
}
