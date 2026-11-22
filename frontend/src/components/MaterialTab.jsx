import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';
import { Package, Minus, Plus, Camera, Check, X as CloseIcon, Truck, Clock } from 'lucide-react';

// Materialmeldung (Drazen 22.11.2026): nur Objekte mit Dienst heute/morgen, Objekt vorausgewaehlt,
// Artikel mit Menge, "Sonstiges" (1 Zeile) und optional 1 Foto. Status: gemeldet / bestellt / liegt bereit.
const NAVY = '#1e3a5f';
const FOTO_MAX_PX = 1280;

const STATUS_STIL = {
  gemeldet: { bg: '#f1f5f9', fg: '#334155', Icon: Clock },
  bestellt: { bg: '#e0ecf7', fg: '#1e3a5f', Icon: Truck },
  'liegt bereit': { bg: '#dcfce7', fg: '#166534', Icon: Check },
};

function fotoVerkleinern(datei) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(datei);
    const img = new Image();
    img.onload = () => {
      const f = Math.min(1, FOTO_MAX_PX / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * f);
      c.height = Math.round(img.height * f);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', 0.8));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Foto konnte nicht gelesen werden')); };
    img.src = url;
  });
}

const fmtZeit = (iso) => iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';

export default function MaterialTab() {
  const [daten, setDaten] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [objekt, setObjekt] = useState(null);
  const [mengen, setMengen] = useState({});
  const [sonstiges, setSonstiges] = useState('');
  const [foto, setFoto] = useState(null);
  const [sendet, setSendet] = useState(false);
  const [fertig, setFertig] = useState(null);

  const laden = async () => {
    try {
      const r = await api.get('/material/meine');
      setDaten(r.data);
      setObjekt((o) => o ?? r.data.vorauswahl);
      setFehler(null);
    } catch (e) {
      setFehler(e?.response?.data?.detail || 'Keine Verbindung – bitte später noch einmal');
    }
  };
  useEffect(() => { laden(); }, []);

  const obj = useMemo(() => daten?.objekte.find((o) => o.object_id === objekt), [daten, objekt]);
  const anzahl = Object.values(mengen).filter((m) => m > 0).length;
  const kannSenden = !!obj && (anzahl > 0 || sonstiges.trim().length > 0) && !sendet;

  const setze = (id, d) => setMengen((m) => ({ ...m, [id]: Math.max(0, Math.min(daten?.menge_max || 99, (m[id] || 0) + d)) }));

  const fotoWaehlen = async (e) => {
    const datei = e.target.files?.[0];
    e.target.value = '';
    if (!datei) return;
    try { setFoto(await fotoVerkleinern(datei)); } catch (x) { setFehler(x.message); }
  };

  const senden = async () => {
    if (!kannSenden) return;
    setSendet(true);
    setFehler(null);
    try {
      const positionen = Object.entries(mengen).filter(([, m]) => m > 0).map(([id, m]) => ({ artikel_id: Number(id), menge: m }));
      const r = await api.post('/material/meldung', { object_id: obj.object_id, positionen, sonstiges: sonstiges.trim(), foto });
      setFertig(r.data);
      setMengen({}); setSonstiges(''); setFoto(null);
      laden();
    } catch (e) {
      setFehler(e?.response?.data?.detail || 'Keine Verbindung – Meldung wurde NICHT gesendet. Bitte später noch einmal.');
    }
    setSendet(false);
  };

  const S = {
    karte: { background: 'white', borderRadius: 16, padding: 16, marginBottom: 14, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' },
    titel: { fontSize: 22, fontWeight: 700, color: NAVY, display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0 14px' },
    label: { fontSize: 16, fontWeight: 700, color: '#0f172a', marginBottom: 8, display: 'block' },
    zeile: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid #e2e8f0', gap: 10 },
    rund: (aktiv) => ({ width: 48, height: 48, borderRadius: 24, border: `2px solid ${aktiv ? NAVY : '#cbd5e1'}`, background: 'white', color: NAVY, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }),
    knopf: { width: '100%', minHeight: 60, borderRadius: 14, border: 'none', background: NAVY, color: 'white', fontSize: 19, fontWeight: 700, cursor: 'pointer' },
  };

  if (!daten && !fehler) return <div style={{ padding: 20, fontSize: 17 }}>Lade …</div>;

  return (
    <div style={{ padding: '8px 4px 24px' }} data-material>
      <div style={S.titel}><Package size={28} />Material melden</div>

      {fehler && <div role="alert" style={{ ...S.karte, border: '3px solid #b91c1c', color: '#7f1d1d', fontSize: 17, fontWeight: 600 }} data-material-fehler>{fehler}</div>}

      {fertig && (
        <div style={{ ...S.karte, border: '3px solid #166534', background: '#f0fdf4' }} data-material-ok>
          <div style={{ fontSize: 19, fontWeight: 700, color: '#14532d', display: 'flex', gap: 8, alignItems: 'center' }}><Check size={24} />Gemeldet – danke!</div>
          <div style={{ fontSize: 16, marginTop: 6, color: '#14532d' }}>{fertig.objekt}: die Objektleitung kümmert sich. Den Stand siehst du unten.</div>
          <button type="button" onClick={() => setFertig(null)} style={{ ...S.knopf, marginTop: 12, minHeight: 50, fontSize: 17 }}>Weitere Meldung</button>
        </div>
      )}

      {daten && !daten.objekte.length && (
        <div style={{ ...S.karte, fontSize: 17 }} data-material-keins>Du hast heute und morgen keinen Dienst. Material kannst du nur für Objekte melden, in denen du heute oder morgen eingeplant bist.</div>
      )}

      {daten && daten.objekte.length > 0 && !fertig && (<>
        <div style={S.karte}>
          <label style={S.label} htmlFor="mat-objekt">Objekt</label>
          <select id="mat-objekt" data-material-objekt value={objekt ?? ''} onChange={(e) => { setObjekt(Number(e.target.value)); setMengen({}); }}
            style={{ width: '100%', minHeight: 52, fontSize: 18, borderRadius: 12, border: '2px solid #94a3b8', padding: '0 10px', background: 'white' }}>
            {daten.objekte.map((o) => <option key={o.object_id} value={o.object_id}>{o.name} ({o.tag}{o.zeit ? ` ${o.zeit}` : ''})</option>)}
          </select>
        </div>

        {obj && (
          <div style={S.karte}>
            <span style={S.label}>Was wird gebraucht?</span>
            {obj.artikel.map((a) => {
              const m = mengen[a.id] || 0;
              return (
                <div key={a.id} style={S.zeile} data-material-artikel={a.name}>
                  <span style={{ fontSize: 17, fontWeight: m ? 700 : 400, flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>{a.name}{a.einheit ? <span style={{ color: '#64748b', fontWeight: 400 }}> ({a.einheit})</span> : null}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 'none' }}>
                    <button type="button" aria-label={`${a.name} weniger`} style={S.rund(m > 0)} onClick={() => setze(a.id, -1)} disabled={!m}><Minus size={22} /></button>
                    <span style={{ minWidth: 28, textAlign: 'center', fontSize: 20, fontWeight: 700 }} data-menge>{m}</span>
                    <button type="button" aria-label={`${a.name} mehr`} style={S.rund(true)} onClick={() => setze(a.id, 1)} data-plus><Plus size={22} /></button>
                  </span>
                </div>
              );
            })}
          </div>
        )}

        <div style={S.karte}>
          <label style={S.label} htmlFor="mat-sonst">Sonstiges (optional)</label>
          <input id="mat-sonst" data-material-sonstiges maxLength={daten.sonstiges_max} value={sonstiges} onChange={(e) => setSonstiges(e.target.value)}
            placeholder="z. B. Leiter im Putzraum defekt" style={{ width: '100%', minHeight: 50, fontSize: 17, borderRadius: 12, border: '2px solid #94a3b8', padding: '0 12px', boxSizing: 'border-box' }} />
          <div style={{ fontSize: 14, color: '#64748b', marginTop: 4, textAlign: 'right' }}>{sonstiges.length}/{daten.sonstiges_max}</div>

          <span style={{ ...S.label, marginTop: 10 }}>Foto (optional)</span>
          {foto ? (
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <img src={foto} alt="Foto zur Meldung" style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 12, display: 'block' }} />
              <button type="button" aria-label="Foto entfernen" onClick={() => setFoto(null)}
                style={{ position: 'absolute', top: 6, right: 6, width: 40, height: 40, borderRadius: 20, border: 'none', background: 'rgba(0,0,0,0.6)', color: 'white' }}><CloseIcon size={22} /></button>
            </div>
          ) : (
            <label style={{ ...S.knopf, background: 'white', color: NAVY, border: `2px solid ${NAVY}`, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, minHeight: 52, fontSize: 17 }}>
              <Camera size={22} />Foto aufnehmen
              <input type="file" accept="image/*" capture="environment" onChange={fotoWaehlen} style={{ display: 'none' }} data-material-foto />
            </label>
          )}
        </div>

        <button type="button" style={{ ...S.knopf, opacity: kannSenden ? 1 : 0.5 }} disabled={!kannSenden} onClick={senden} data-material-senden>
          {sendet ? 'Wird gesendet …' : anzahl ? `${anzahl} Artikel melden` : 'Melden'}
        </button>
        <div style={{ fontSize: 14, color: '#64748b', marginTop: 8, textAlign: 'center' }}>Die Meldung geht an die Objektleitung – nicht direkt an den Kunden.</div>
      </>)}

      {daten?.meldungen?.length > 0 && (
        <div style={{ ...S.karte, marginTop: 20 }} data-material-liste>
          <span style={S.label}>Meine Meldungen</span>
          {daten.meldungen.map((m) => {
            const st = STATUS_STIL[m.status_ma] || STATUS_STIL.gemeldet;
            return (
              <div key={m.id} style={{ ...S.zeile, alignItems: 'flex-start' }} data-material-meldung={m.id}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{m.objekt}</div>
                  <div style={{ fontSize: 14, color: '#475569' }}>{fmtZeit(m.erstellt_am)}</div>
                  <div style={{ fontSize: 15, marginTop: 4 }}>{m.positionen.filter((p) => p.menge > 0).map((p) => `${p.menge}× ${p.name}`).join(', ')}{m.sonstiges ? `${m.positionen.length ? ', ' : ''}${m.sonstiges}` : ''}</div>
                </div>
                <span style={{ background: st.bg, color: st.fg, borderRadius: 999, padding: '6px 12px', fontSize: 15, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }} data-status={m.status_ma}>
                  <st.Icon size={16} />{m.status_ma}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
