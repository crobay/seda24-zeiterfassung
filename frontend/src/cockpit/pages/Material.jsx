import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Package, Truck, CheckCircle2, Image as ImageIcon, Send, Download, Pencil, Mail, Settings2 } from 'lucide-react';
import { api, apiError, t, useApi, useApp, Status, SkeletonRows, Empty, ErrorBox, Dialog, ObjektMarke } from '../core';

// Materialmeldungen (Drazen 22.11.2026): Meldungen der MA, Status bestellt/erledigt per Klick, Mengen aenderbar,
// "An Kunden senden" nur bei Objekten mit "Material stellt: Kunde". Artikelliste/Ansprechpartner: Objekt-Seite.
const ST = { gemeldet: 'offen', bestellt: 'kommt', erledigt: 'fertig' };
export const fmtZeit = (iso) => iso ? new Date(iso).toLocaleString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
export const posText = (m) => [...m.positionen.filter((p) => p.menge > 0).map((p) => `${p.menge}× ${p.name}`), ...(m.sonstiges ? [m.sonstiges] : [])].join(', ');

async function herunterladen(pfad, name) {
  const r = await api.get(pfad, { responseType: 'blob' });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function MaterialStatus({ s }) {
  return <Status s={ST[s] || 'offen'} label={t(`mat.st_${s}`)} />;
}

function Foto({ id, onClose }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    api.get(`/material/meldungen/${id}/foto`, { responseType: 'blob' }).then((r) => { url = URL.createObjectURL(r.data); setSrc(url); }).catch(() => setSrc(''));
    return () => url && URL.revokeObjectURL(url);
  }, [id]);
  return (
    <Dialog title={t('mat.foto')} onClose={onClose} footer={<button className="ck-btn" onClick={onClose}>{t('app.close')}</button>}>
      {src === null ? <SkeletonRows n={3} /> : src ? <img src={src} alt={t('mat.foto')} style={{ maxWidth: '100%', borderRadius: 8 }} data-mat-foto-bild /> : <p>{t('app.error')}</p>}
    </Dialog>
  );
}

function Mengen({ m, onClose, onSaved }) {
  const { toast } = useApp();
  const [w, setW] = useState(() => Object.fromEntries(m.positionen.map((p) => [p.id, p.menge])));
  const [busy, setBusy] = useState(false);
  const speichern = async () => {
    setBusy(true);
    try {
      await api.put(`/material/meldungen/${m.id}/mengen`, { positionen: m.positionen.map((p) => ({ id: p.id, menge: Number(w[p.id]) || 0 })) });
      toast(t('mat.mengen_ok')); onSaved(); onClose();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  return (
    <Dialog title={t('mat.mengen_title', { objekt: m.objekt })} onClose={onClose}
      footer={<><button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button><button className="ck-btn ck-btn-primary" disabled={busy} onClick={speichern} data-mat-mengen-speichern>{t('app.save')}</button></>}>
      <table className="ck-table"><thead><tr><th>{t('mat.artikel')}</th><th>{t('mat.gemeldet')}</th><th>{t('mat.menge')}</th></tr></thead>
        <tbody>{m.positionen.map((p) => (
          <tr key={p.id}><td>{p.name}</td><td className="ck-subtle">{p.menge_gemeldet}</td>
            <td><input className="ck-input" type="number" min={0} max={99} style={{ width: 80 }} value={w[p.id]} data-mat-menge={p.name}
              onChange={(e) => setW((x) => ({ ...x, [p.id]: e.target.value }))} /></td></tr>))}</tbody></table>
      <p className="ck-subtle">{t('mat.mengen_hint')}</p>
    </Dialog>
  );
}

function Kunde({ m, mail, onClose, onSaved }) {
  const { toast } = useApp();
  const [busy, setBusy] = useState(false);
  const [ergebnis, setErgebnis] = useState(null);
  const test = mail?.testmodus || !mail?.echt_erlaubt;
  const senden = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/material/meldungen/${m.id}/an-kunden`);
      setErgebnis(r.data); onSaved();
      toast(r.data.test ? t('mat.kunde_test_ok', { an: r.data.kunde_gesendet_an }) : t('mat.kunde_ok', { an: r.data.kunde_gesendet_an }));
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(false);
  };
  const k = m.kontakt || {};
  return (
    <Dialog title={t('mat.kunde_title', { objekt: m.objekt })} onClose={onClose}
      footer={ergebnis
        ? <>{ergebnis.weg === 'datei_test' && <button className="ck-btn" onClick={() => herunterladen(`/material/meldungen/${m.id}/testmail.eml`, `Materialbedarf_${m.id}.eml`)} data-mat-eml><Download size={16} />{t('mat.eml')}</button>}
          <button className="ck-btn ck-btn-primary" onClick={onClose}>{t('app.close')}</button></>
        : <><button className="ck-btn" onClick={onClose}>{t('app.cancel')}</button>
          <button className="ck-btn ck-btn-primary" disabled={busy || !k.kontakt_mail} onClick={senden} data-mat-kunde-senden><Send size={16} />{test ? t('mat.kunde_btn_test') : t('mat.kunde_btn')}</button></>}>
      <div className="ab-mail">
        <div><span className="ck-subtle">{t('mat.an')}</span> {k.kontakt_mail ? `${k.kontakt_anrede || ''} ${k.kontakt_name || ''} <${k.kontakt_mail}>` : <b>{t('mat.keine_mail')}</b>}</div>
        {test && <div className="ck-callout" style={{ marginTop: 8 }}>{t('mat.test_hint', { an: mail?.test_an })}</div>}
        <div style={{ marginTop: 8 }}><span className="ck-subtle">{t('mat.betreff')}</span> <b>Materialbedarf für Ihr Objekt – SEDA24</b></div>
        <div style={{ marginTop: 8 }}>{posText(m)}</div>
        {m.kunde_gesendet_am && <div className="ck-subtle" style={{ marginTop: 8 }}>{t('mat.schon_gesendet', { am: fmtZeit(m.kunde_gesendet_am), an: m.kunde_gesendet_an })}</div>}
      </div>
    </Dialog>
  );
}

function MailEinstellungen({ mail, onSaved }) {
  const { toast } = useApp();
  const [f, setF] = useState(mail);
  useEffect(() => setF(mail), [mail]);
  const geaendert = ['absender', 'absender_name', 'signatur_mail', 'antwort_an', 'test_an'].some((k) => (f[k] || '') !== (mail[k] || ''));
  const speichern = async (werte) => {
    try { await api.put('/material/mail-einstellungen', werte); toast(t('mat.mail_saved')); onSaved(); } catch (e) { toast(apiError(e), { tone: 'warn' }); }
  };
  const feld = (k, label) => (
    <label className="ck-field" key={k}><span>{label}</span>
      <input className="ck-input" value={f[k] || ''} onChange={(e) => setF((x) => ({ ...x, [k]: e.target.value }))} data-mat-mail={k} /></label>);
  return (
    <section className="ck-card" data-mat-mail-karte>
      <div className="ck-card-head"><h2><Settings2 size={20} />{t('mat.mail_title')}</h2></div>
      <div className="ck-card-body">
      <p className="ck-subtle" style={{ marginTop: 0 }}>{t('mat.mail_hint')}</p>
      <div className="ck-form-grid">
        {feld('absender', t('mat.f_absender'))}{feld('absender_name', t('mat.f_name'))}
        {feld('signatur_mail', t('mat.f_sig'))}{feld('antwort_an', t('mat.f_antwort'))}{feld('test_an', t('mat.f_test'))}
      </div>
      <label className="ab-la-check" style={{ marginTop: 8 }}>
        <input type="checkbox" checked={!!mail.testmodus} disabled={!mail.echt_erlaubt && mail.testmodus} onChange={(e) => speichern({ testmodus: e.target.checked })} />
        {t('mat.testmodus')}</label>
      {!mail.echt_erlaubt && <div className="ck-subtle">{t('mat.nur_test')}</div>}
      <div className="ab-foot"><button className="ck-btn ck-btn-primary" disabled={!geaendert} onClick={() => speichern(f)} data-mat-mail-speichern>{t('app.save')}</button></div>
      </div>
    </section>
  );
}

export default function Material() {
  const { toast } = useApp();
  const [alle, setAlle] = useState(false);
  const { data, loading, error, reload } = useApi(`/material/meldungen${alle ? '?alle=true' : ''}`, [alle]);
  const [busy, setBusy] = useState(null);
  const [dlg, setDlg] = useState(null);

  const status = async (m, s) => {
    setBusy(`${m.id}${s}`);
    try {
      await api.put(`/material/meldungen/${m.id}/status`, { status: s });
      toast(t('mat.st_ok', { objekt: m.objekt, s: t(`mat.st_${s}`) }), { undo: async () => { await api.put(`/material/meldungen/${m.id}/status`, { status: m.status }); reload(); } });
      reload();
    } catch (e) { toast(apiError(e), { tone: 'warn' }); }
    setBusy(null);
  };

  return (
    <>
      <div className="ck-page-head"><div><h1>{t('mat.title')}</h1><p>{t('mat.sub')}</p></div>
        <div className="ck-seg" role="group">
          <button className={!alle ? 'is-on' : ''} onClick={() => setAlle(false)} data-mat-offen>{t('mat.offen', { n: data?.offen ?? '…' })}</button>
          <button className={alle ? 'is-on' : ''} onClick={() => setAlle(true)} data-mat-alle>{t('mat.alle')}</button>
        </div></div>

      <section className="ck-card" style={{ marginBottom: 24 }}>
        {error ? <ErrorBox text={error} onRetry={reload} /> : loading && !data ? <SkeletonRows n={4} /> : !data.meldungen.length
          ? <Empty icon={Package} title={t(alle ? 'mat.leer_alle' : 'mat.leer')} text={t('mat.leer_text')} />
          : <div className="ck-table-wrap"><table className="ck-table mat-tabelle" data-mat-tabelle>
            <thead><tr><th>{t('mat.c_zeit')}</th><th>{t('mat.c_objekt')}</th><th>{t('mat.c_ma')}</th><th>{t('mat.c_pos')}</th><th>{t('mat.c_status')}</th><th /></tr></thead>
            <tbody>{data.meldungen.map((m) => (
              <tr key={m.id} data-mat-zeile={m.id}>
                <td className="ck-subtle" style={{ whiteSpace: 'nowrap' }}>{fmtZeit(m.erstellt_am)}{m.status !== 'erledigt' && m.alter_h >= 24 && <div style={{ color: 'var(--ck-warn, #b45309)', fontWeight: 600 }}>{t('mat.ueber24')}</div>}</td>
                <td><ObjektMarke id={m.object_id} name={m.objekt} />
                  <div className="ck-subtle">{m.stellt === 'kunde' ? t('mat.stellt_kunde') : t('mat.stellt_seda')}</div></td>
                <td>{m.ma}</td>
                <td style={{ minWidth: 200 }}><div>{posText(m)}</div>
                  {m.foto && <button className="ck-btn ck-btn-ghost ck-btn-sm" onClick={() => setDlg({ art: 'foto', m })} data-mat-foto><ImageIcon size={14} />{t('mat.foto')}</button>}
                  {m.kunde_gesendet_am && <div className="ck-subtle"><Mail size={13} /> {t('mat.gesendet_am', { am: fmtZeit(m.kunde_gesendet_am) })}{m.kunde_weg !== 'graph' ? ` (${t('mat.test')})` : ''}</div>}</td>
                <td><MaterialStatus s={m.status} /></td>
                <td className="mat-aktionen">
                  {m.status === 'gemeldet' && <button className="ck-btn ck-btn-sm" disabled={!!busy} onClick={() => status(m, 'bestellt')} data-mat-bestellt><Truck size={14} />{t('mat.btn_bestellt')}</button>}
                  {m.status !== 'erledigt' && <button className="ck-btn ck-btn-sm ck-btn-primary" disabled={!!busy} onClick={() => status(m, 'erledigt')} data-mat-erledigt><CheckCircle2 size={14} />{t('mat.btn_erledigt')}</button>}
                  {m.status !== 'erledigt' && m.positionen.length > 0 && <button className="ck-btn ck-btn-ghost ck-btn-sm" onClick={() => setDlg({ art: 'mengen', m })} data-mat-mengen><Pencil size={14} />{t('mat.btn_mengen')}</button>}
                  {m.stellt === 'kunde' && m.status !== 'erledigt' && <button className="ck-btn ck-btn-ghost ck-btn-sm" onClick={() => setDlg({ art: 'kunde', m })} data-mat-kunde><Send size={14} />{t('mat.btn_kunde')}</button>}
                </td>
              </tr>))}</tbody></table></div>}
      </section>

      {data?.mail && <MailEinstellungen mail={data.mail} onSaved={reload} />}

      {dlg?.art === 'foto' && <Foto id={dlg.m.id} onClose={() => setDlg(null)} />}
      {dlg?.art === 'mengen' && <Mengen m={dlg.m} onClose={() => setDlg(null)} onSaved={reload} />}
      {dlg?.art === 'kunde' && <Kunde m={dlg.m} mail={data?.mail} onClose={() => setDlg(null)} onSaved={reload} />}
    </>
  );
}

// Kachel fuer "Heute": offene Meldungen (Admin + Objektleitung)
export function MaterialKachel({ className = '' }) {
  const { data } = useApi('/material/meldungen');
  if (!data) return null;
  const ms = data.meldungen.slice(0, 5);
  return (
    <section className={`ck-card ${className}`} aria-labelledby="mat-h" data-mat-kachel>
      <div className="ck-card-head"><h2 id="mat-h"><Package size={20} />{t('mat.title')}</h2>
        <Link className="ck-btn ck-btn-ghost ck-btn-sm" to="/cockpit/material">{t('mat.zur_liste', { n: data.offen })}</Link></div>
      {!ms.length ? <p className="ck-subtle">{t('mat.leer')}</p> : (
        <ul className="ck-list">{ms.map((m) => (
          <li key={m.id} style={{ display: 'flex', gap: 10, alignItems: 'center', justifyContent: 'space-between', padding: '6px 0' }}>
            <span><ObjektMarke id={m.object_id} name={m.objekt} /> <span className="ck-subtle">{m.ma}, {fmtZeit(m.erstellt_am)}</span>
              <div>{posText(m)}</div></span>
            <MaterialStatus s={m.status} /></li>))}</ul>)}
    </section>
  );
}
