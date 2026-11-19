import React, { useState } from 'react';
import { Clock, Check, Hourglass, X as CloseIcon } from 'lucide-react';

// Mehrzeit nach Schichtende (Regel Drazen 19.11.2026): direkt nach dem Gehen bzw. aus der Historie.
// "Nein, nur später gestempelt" -> nichts. "Ja, länger gearbeitet" -> Pflicht-Grund -> Antrag an die Genehmiger.
// onAbsenden(grund) liefert { art: 'ok' } (Server hat bestaetigt), { art: 'wartet' } (in der Warteschlange,
// wird automatisch uebertragen) oder { art: 'fehler', text }.
const GRUND_MIN = 10;
const GRUND_MAX = 300;
const NAVY = '#1E537C';

const S = {
  hinter: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '14px' },
  box: { background: 'white', borderRadius: '22px', padding: '22px', maxWidth: '440px', width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.35)', position: 'relative', maxHeight: '94vh', overflowY: 'auto' },
  zu: { position: 'absolute', top: '10px', right: '10px', background: 'none', border: 'none', padding: '8px', cursor: 'pointer', color: '#475569' },
  titel: { fontSize: '24px', fontWeight: 700, color: '#0E2A40', lineHeight: 1.25, margin: '6px 34px 6px 0', fontFamily: "'Poppins', 'Open Sans', system-ui, sans-serif" },
  info: { fontSize: '17px', color: '#334155', marginBottom: '16px' },
  knopf: { width: '100%', minHeight: '64px', borderRadius: '16px', fontSize: '20px', fontWeight: 700, cursor: 'pointer', marginTop: '10px', padding: '10px 14px' },
  ja: { background: NAVY, color: 'white', border: 'none' },
  nein: { background: 'white', color: '#0E2A40', border: '3px solid #94a3b8' },
  text: { width: '100%', minHeight: '110px', fontSize: '18px', padding: '12px', borderRadius: '12px', border: '2px solid #94a3b8', boxSizing: 'border-box', fontFamily: 'inherit' },
  ok: { border: '4px solid #166534', background: '#f0fdf4', color: '#14532d', borderRadius: '14px', padding: '14px', fontSize: '19px', fontWeight: 700, display: 'flex', gap: '10px', alignItems: 'center' },
  wartet: { border: '4px dashed #1d4ed8', background: '#eff6ff', color: '#1e3a8a', borderRadius: '14px', padding: '14px', fontSize: '19px', fontWeight: 700, display: 'flex', gap: '10px', alignItems: 'center' },
  fehler: { color: '#b91c1c', fontSize: '16px', fontWeight: 600, marginTop: '10px' },
};

export default function MehrzeitFrage({ minuten, schichtEnde, gehen, datum, nurGrund = false, onNein, onSchliessen, onAbsenden }) {
  const [schritt, setSchritt] = useState(nurGrund ? 'grund' : 'frage'); // frage | grund | ok | wartet
  const [grund, setGrund] = useState('');
  const [sendet, setSendet] = useState(false);
  const [fehler, setFehler] = useState(null);
  const laenge = grund.trim().length;

  const absenden = async () => {
    if (laenge < GRUND_MIN || sendet) return;
    setSendet(true);
    setFehler(null);
    const r = await onAbsenden(grund.trim());
    setSendet(false);
    if (r.art === 'fehler') { setFehler(r.text); return; }
    setSchritt(r.art);
  };

  return (
    <div style={S.hinter} data-mehrzeit-frage role="dialog" aria-modal="true" aria-labelledby="mz-titel">
      <div style={S.box}>
        <button type="button" style={S.zu} onClick={onSchliessen} aria-label="Schließen"><CloseIcon size={28} /></button>
        <div style={{ color: NAVY }}><Clock size={34} /></div>
        {schritt === 'frage' && (<>
          <div id="mz-titel" style={S.titel}>Du bist {minuten} Minuten nach Schichtende. Hast du länger gearbeitet?</div>
          <div style={S.info}>Schichtende {schichtEnde}{gehen ? `, Gehen ${gehen}` : ''}{datum ? ` (${datum})` : ''}. Gezählt wird bis Schichtende.</div>
          <button type="button" data-mz-nein style={{ ...S.knopf, ...S.nein }} onClick={onNein}>Nein, nur später gestempelt</button>
          <button type="button" data-mz-ja style={{ ...S.knopf, ...S.ja }} onClick={() => setSchritt('grund')}>Ja, länger gearbeitet</button>
        </>)}
        {schritt === 'grund' && (<>
          <div id="mz-titel" style={S.titel}>Mehrzeit {minuten} Min beantragen</div>
          <div style={S.info}>Von Schichtende {schichtEnde} bis Gehen {gehen}{datum ? ` am ${datum}` : ''}. Die Objektleitung entscheidet.</div>
          <label htmlFor="mz-grund" style={{ fontSize: '17px', fontWeight: 700, display: 'block', marginBottom: '6px' }}>Was hast du länger gemacht? (Pflicht)</label>
          <textarea id="mz-grund" data-mz-grund style={S.text} maxLength={GRUND_MAX} value={grund}
            onChange={(e) => setGrund(e.target.value)} placeholder="z. B. Konferenzraum nach Kundenessen gesaugt" />
          <div style={{ fontSize: '14px', color: laenge < GRUND_MIN ? '#b45309' : '#475569', marginTop: '4px' }}>
            {laenge < GRUND_MIN ? `Noch ${GRUND_MIN - laenge} Zeichen` : `${laenge}/${GRUND_MAX}`}
          </div>
          {fehler && <div style={S.fehler}>{fehler}</div>}
          <button type="button" data-mz-senden disabled={laenge < GRUND_MIN || sendet}
            style={{ ...S.knopf, ...S.ja, opacity: laenge < GRUND_MIN || sendet ? 0.5 : 1 }} onClick={absenden}>
            {sendet ? 'Wird gesendet …' : 'Mehrzeit beantragen'}
          </button>
          {!nurGrund && <button type="button" style={{ ...S.knopf, ...S.nein }} onClick={onNein}>Nein, nur später gestempelt</button>}
        </>)}
        {schritt === 'ok' && (<>
          <div id="mz-titel" style={S.titel}>Antrag gesendet</div>
          <div style={S.ok} data-mz-status="ok"><Check size={26} strokeWidth={3} aria-label="✓" style={{ flex: 'none' }} /> Mehrzeit {minuten} Min beantragt – die Objektleitung entscheidet.</div>
          <button type="button" style={{ ...S.knopf, ...S.ja }} onClick={onSchliessen}>Fertig</button>
        </>)}
        {schritt === 'wartet' && (<>
          <div id="mz-titel" style={S.titel}>Antrag gespeichert</div>
          <div style={S.wartet} data-mz-status="wartet"><Hourglass size={26} strokeWidth={2.5} aria-label="⏳" style={{ flex: 'none' }} /> Ohne Netz gespeichert – wird mit dem Gehen automatisch übertragen.</div>
          <button type="button" style={{ ...S.knopf, ...S.ja }} onClick={onSchliessen}>Fertig</button>
        </>)}
      </div>
    </div>
  );
}
