import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL } from '../config';
import { Check, WifiOff, Search, X, Delete, LogIn, LogOut, UserRound, Lock } from 'lucide-react';

// Terminal-Modus (Drazen 24.11.2026): festes Tablet am Objekt (erst Lidl Neu Bie2). MA tippt Namen + 4-stellige PIN,
// dann EIN grosser Knopf Kommen/Gehen. Nur online, Server-Uhrzeit zaehlt, keine Warteschlange.
// Eigener Geraete-Token (localStorage 'terminal_token'), unabhaengig vom normalen Login.
const KEY = 'terminal_token';
const NAVY = '#163d5c';
const GOLD = '#F9B233';
const GRUEN = '#15803d';
const ROT = '#b91c1c';
const ZURUECK_MS = 5000;        // nach der Bestaetigung zurueck zum Start
const LEERLAUF_MS = 30000;      // PIN-/Knopf-Bildschirm ohne Eingabe -> Start
const PING_MS = 15000;          // Netz pruefen / Liste auffrischen
const PORTAL_URL = 'http://neverssl.com/';   // unverschluesselte Seite: oeffnet die WLAN-Anmeldung (Captive Portal)

class KeinNetz extends Error {}

async function rufe(pfad, { methode = 'GET', body, token, bearer } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 8000);
  let r;
  try {
    r = await fetch(`${API_URL}${pfad}`, {
      method: methode, signal: ctl.signal, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Terminal-Token': token } : {}), ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new KeinNetz('offline');
  } finally {
    clearTimeout(timer);
  }
  // Antwort ohne unsere Kennung = WLAN-Anmeldeseite o. ae., nicht unser Server
  if (r.headers.get('X-Seda24') !== '1') throw new KeinNetz('portal');
  const daten = await r.json().catch(() => null);
  if (!r.ok) {
    const e = new Error(typeof daten?.detail === 'string' ? daten.detail : 'Fehler – bitte noch einmal');
    e.status = r.status;
    throw e;
  }
  return daten;
}

function useWakeLock() {
  useEffect(() => {
    let lock = null;
    const holen = async () => {
      try { if ('wakeLock' in navigator && document.visibilityState === 'visible') lock = await navigator.wakeLock.request('screen'); } catch (e) { /* Akku-Sparmodus o. ae. */ }
    };
    const sichtbar = () => { if (document.visibilityState === 'visible') holen(); };
    holen();
    document.addEventListener('visibilitychange', sichtbar);
    return () => { document.removeEventListener('visibilitychange', sichtbar); try { lock?.release(); } catch (e) { /* egal */ } };
  }, []);
}

const S = {
  seite: { position: 'fixed', inset: 0, background: '#eef2f6', fontFamily: "'Segoe UI', Roboto, Arial, sans-serif", color: '#0f172a', display: 'flex', flexDirection: 'column', userSelect: 'none', WebkitUserSelect: 'none', overflow: 'hidden' },
  kopf: { background: NAVY, color: 'white', display: 'flex', alignItems: 'center', gap: 24, padding: '12px 28px', flex: 'none' },
  inhalt: { flex: 1, overflowY: 'auto', padding: '24px 28px' },
  kachel: { background: 'white', borderRadius: 20, border: '3px solid #cbd5e1', padding: '18px 20px', minHeight: 120, textAlign: 'left', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', boxShadow: '0 2px 6px rgba(0,0,0,0.06)' },
  knopfGross: (farbe) => ({ background: farbe, color: 'white', border: 'none', borderRadius: 28, fontSize: 56, fontWeight: 800, padding: '0 40px', minHeight: 200, minWidth: 480, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 24, cursor: 'pointer', boxShadow: '0 6px 16px rgba(0,0,0,0.18)' }),
  zweit: { background: 'white', color: NAVY, border: `3px solid ${NAVY}`, borderRadius: 18, fontSize: 26, fontWeight: 700, minHeight: 72, padding: '0 28px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 12 },
  taste: { background: 'white', border: '3px solid #cbd5e1', borderRadius: 20, fontSize: 44, fontWeight: 700, color: NAVY, height: 96, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  eingabe: { width: '100%', fontSize: 30, minHeight: 72, borderRadius: 16, border: '3px solid #94a3b8', padding: '0 20px', boxSizing: 'border-box' },
};

function Uhr({ versatz }) {
  const [jetzt, setJetzt] = useState(() => new Date(Date.now() + versatz));
  useEffect(() => { const i = setInterval(() => setJetzt(new Date(Date.now() + versatz)), 1000); return () => clearInterval(i); }, [versatz]);
  return (
    <div style={{ textAlign: 'right', lineHeight: 1.1 }} data-term-uhr>
      <div style={{ fontSize: 44, fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}>{jetzt.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}</div>
      <div style={{ fontSize: 18, opacity: 0.85 }}>{jetzt.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' })}</div>
    </div>
  );
}

function Kopf({ start, versatz, onLangDruck }) {
  const t = useRef(null);
  const drueck = () => { t.current = setTimeout(onLangDruck, 5000); };
  const los = () => clearTimeout(t.current);
  return (
    <header style={S.kopf}>
      <img src="/brand/seda24/logo-seda24-weiss.svg" alt="SEDA24" style={{ height: 46 }} draggable={false}
        onPointerDown={drueck} onPointerUp={los} onPointerLeave={los} onContextMenu={(e) => e.preventDefault()} data-term-logo />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 28, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} data-term-objekt>{start?.objekt || 'Terminal'}</div>
        <div style={{ fontSize: 17, color: GOLD, fontWeight: 600 }}>Zeiterfassung</div>
      </div>
      <Uhr versatz={versatz} />
    </header>
  );
}

function KeinWlan() {
  return (
    <div role="alert" data-term-offline style={{ position: 'fixed', inset: 0, background: ROT, color: 'white', zIndex: 50, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 28, padding: 40, textAlign: 'center' }}>
      <WifiOff size={120} />
      <div style={{ fontSize: 54, fontWeight: 800 }}>Kein WLAN – bitte mit Lidl-WLAN verbinden</div>
      <div style={{ fontSize: 26, maxWidth: 900 }}>Ohne Verbindung kann nicht gestempelt werden. Bitte die Objektleitung informieren, wenn es nicht klappt.</div>
      <button type="button" onClick={() => window.open(PORTAL_URL, '_blank')} data-term-portal
        style={{ ...S.zweit, background: 'white', color: ROT, borderColor: 'white', fontSize: 30, minHeight: 86 }}>WLAN-Anmeldung öffnen</button>
      <div style={{ fontSize: 20, opacity: 0.9 }}>Die Seite prüft die Verbindung automatisch alle 15 Sekunden.</div>
    </div>
  );
}

function Kachel({ k, onClick }) {
  const da = !!k.da_seit;
  return (
    <button type="button" style={{ ...S.kachel, borderColor: da ? GRUEN : '#cbd5e1' }} onClick={() => onClick(k)} data-term-kachel={k.name}>
      <div style={{ fontSize: 30, fontWeight: 800, color: NAVY, lineHeight: 1.15 }}>{k.name}</div>
      <div style={{ fontSize: 20, color: '#475569', marginTop: 8, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
        {k.schicht && <span>{k.schicht}</span>}
        {da && <span style={{ color: GRUEN, fontWeight: 700 }}>● da seit {k.da_seit}{k.da_objekt ? ` (${k.da_objekt})` : ''}</span>}
        {!da && k.fertig && <span style={{ fontWeight: 600 }}>✓ {k.fertig}</span>}
      </div>
    </button>
  );
}

function StartSeite({ start, onWahl, onSuche }) {
  const kacheln = start?.kacheln || [];
  return (
    <div style={S.inhalt}>
      <div style={{ fontSize: 30, fontWeight: 700, marginBottom: 18, color: NAVY }}>Bitte auf deinen Namen tippen</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 18 }}>
        {kacheln.map((k) => <Kachel key={k.employee_id} k={k} onClick={onWahl} />)}
        <button type="button" onClick={onSuche} data-term-andere
          style={{ ...S.kachel, borderStyle: 'dashed', borderColor: NAVY, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 14, background: '#f8fafc' }}>
          <Search size={34} color={NAVY} /><span style={{ fontSize: 28, fontWeight: 800, color: NAVY }}>Andere Mitarbeiter</span>
        </button>
      </div>
      {!kacheln.length && <div style={{ fontSize: 22, color: '#475569', marginTop: 22 }}>Heute ist hier niemand eingeplant – über „Andere Mitarbeiter“ den eigenen Namen suchen.</div>}
    </div>
  );
}

function SucheSeite({ token, onWahl, onZurueck, onNetz }) {
  const [q, setQ] = useState('');
  const [treffer, setTreffer] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) { setTreffer([]); return undefined; }
    const i = setTimeout(() => {
      rufe(`/terminal/suche?q=${encodeURIComponent(q.trim())}`, { token }).then((r) => setTreffer(r.treffer)).catch((e) => { if (e instanceof KeinNetz) onNetz(false); });
    }, 250);
    return () => clearTimeout(i);
  }, [q, token]); // eslint-disable-line
  return (
    <div style={S.inhalt}>
      <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 18 }}>
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Vor- oder Nachname eingeben" style={S.eingabe} data-term-suche aria-label="Name suchen" />
        <button type="button" style={S.zweit} onClick={onZurueck}><X size={28} />Zurück</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 18 }}>
        {treffer.map((k) => <Kachel key={k.employee_id} k={k} onClick={onWahl} />)}
      </div>
      {q.trim().length >= 2 && !treffer.length && <div style={{ fontSize: 22, color: '#475569' }}>Niemand gefunden.</div>}
    </div>
  );
}

function PinSeite({ ma, fehler, busy, onPin, onZurueck }) {
  const [pin, setPin] = useState('');
  const tippe = (z) => {
    if (busy || pin.length >= 4) return;
    const n = pin + z;
    setPin(n);
    if (n.length === 4) Promise.resolve(onPin(n)).finally(() => setPin(''));
  };
  return (
    <div style={{ ...S.inhalt, display: 'flex', gap: 48, alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ flex: '0 1 420px' }}>
        <div style={{ fontSize: 26, color: '#475569' }}>Hallo</div>
        <div style={{ fontSize: 46, fontWeight: 800, color: NAVY, lineHeight: 1.1 }} data-term-pin-name>{ma.name}</div>
        <div style={{ fontSize: 28, marginTop: 24, display: 'flex', alignItems: 'center', gap: 10 }}><Lock size={28} />Deine PIN</div>
        <div style={{ display: 'flex', gap: 16, marginTop: 14 }} data-term-pin-punkte={pin.length}>
          {[0, 1, 2, 3].map((i) => <span key={i} style={{ width: 52, height: 52, borderRadius: 26, border: `4px solid ${NAVY}`, background: i < pin.length ? NAVY : 'white' }} />)}
        </div>
        {fehler && <div role="alert" data-term-fehler style={{ marginTop: 22, fontSize: 24, fontWeight: 700, color: ROT }}>{fehler}</div>}
        <button type="button" style={{ ...S.zweit, marginTop: 32 }} onClick={onZurueck} data-term-zurueck><X size={28} />Zurück</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 120px)', gap: 16 }}>
        {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((z) => <button type="button" key={z} style={S.taste} onClick={() => tippe(z)} data-term-taste={z}>{z}</button>)}
        <button type="button" style={{ ...S.taste, fontSize: 26 }} onClick={() => setPin('')} aria-label="Löschen">C</button>
        <button type="button" style={S.taste} onClick={() => tippe('0')} data-term-taste="0">0</button>
        <button type="button" style={S.taste} onClick={() => setPin(pin.slice(0, -1))} aria-label="Zurück"><Delete size={36} /></button>
      </div>
    </div>
  );
}

function KnopfSeite({ info, fehler, busy, onStempeln, onZurueck }) {
  const kommen = info.aktion === 'kommen';
  return (
    <div style={{ ...S.inhalt, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 26, textAlign: 'center' }}>
      <div style={{ fontSize: 44, fontWeight: 800, color: NAVY }}>{info.name}</div>
      <div style={{ fontSize: 26, color: '#334155' }} data-term-status>
        {info.da_seit ? `Eingestempelt seit ${info.da_seit}${info.da_objekt ? ` (${info.da_objekt})` : ''}` : 'Nicht eingestempelt'}
      </div>
      {info.auto && kommen
        ? <div style={{ fontSize: 30, fontWeight: 700, color: NAVY, maxWidth: 800 }} data-term-auto>Du wirst hier automatisch gebucht – Stempeln ist nicht nötig.</div>
        : <button type="button" disabled={busy} onClick={() => onStempeln(info.aktion)} data-term-knopf={info.aktion}
            style={{ ...S.knopfGross(kommen ? GRUEN : ROT), opacity: busy ? 0.6 : 1 }}>
            {kommen ? <LogIn size={72} /> : <LogOut size={72} />}{busy ? 'Moment …' : kommen ? 'KOMMEN' : 'GEHEN'}
          </button>}
      {fehler && <div role="alert" data-term-fehler style={{ fontSize: 26, fontWeight: 700, color: ROT, maxWidth: 900 }}>{fehler}</div>}
      <button type="button" style={S.zweit} onClick={onZurueck} data-term-zurueck><X size={28} />Abbrechen</button>
    </div>
  );
}

function FertigSeite({ r, onWeiter }) {
  const [rest, setRest] = useState(ZURUECK_MS / 1000);
  useEffect(() => {
    const i = setInterval(() => setRest((x) => x - 1), 1000);
    const t = setTimeout(onWeiter, ZURUECK_MS);
    return () => { clearInterval(i); clearTimeout(t); };
  }, []); // eslint-disable-line
  const kommen = r.aktion === 'kommen';
  return (
    <div onClick={onWeiter} data-term-fertig={r.aktion}
      style={{ ...S.inhalt, background: kommen ? GRUEN : NAVY, color: 'white', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 18, textAlign: 'center' }}>
      <div style={{ width: 170, height: 170, borderRadius: 85, background: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Check size={130} color={kommen ? GRUEN : NAVY} strokeWidth={3.5} /></div>
      <div style={{ fontSize: 60, fontWeight: 800 }}>{kommen ? 'Kommen' : 'Gehen'} {r.zeit} Uhr</div>
      <div style={{ fontSize: 34 }}>{kommen ? `Hallo ${r.vorname}, gute Arbeit!` : `Danke ${r.vorname}, schönen Feierabend!`}</div>
      <div style={{ fontSize: 22, opacity: 0.85 }}>Vom Server bestätigt · zurück in {Math.max(rest, 0)} s</div>
    </div>
  );
}

// Einrichtung: Admin/Objektleitung meldet sich an, waehlt das Objekt -> Geraete-Token. Login-Token wird NICHT gespeichert.
function Einrichtung({ onFertig, hinweis }) {
  const [f, setF] = useState({ email: '', passwort: '', name: '' });
  const [login, setLogin] = useState(null);
  const [objekte, setObjekte] = useState([]);
  const [objekt, setObjekt] = useState('');
  const [fehler, setFehler] = useState(hinweis || null);
  const [busy, setBusy] = useState(false);
  const anmelden = async (e) => {
    e.preventDefault(); setBusy(true); setFehler(null);
    try {
      const r = await rufe('/auth/login', { methode: 'POST', body: { email: f.email.trim(), password: f.passwort } });
      if (!['admin', 'objektleiter'].includes(String(r.role).toLowerCase())) throw new Error('Nur Admin oder Objektleitung kann ein Terminal einrichten');
      const o = await rufe('/terminal/objekte', { bearer: r.access_token });
      setLogin(r.access_token); setObjekte(o.objekte || []);
    } catch (x) { setFehler(x instanceof KeinNetz ? 'Keine Verbindung – erst WLAN verbinden' : x.status === 401 ? 'E-Mail oder Passwort falsch' : x.message); }
    setBusy(false);
  };
  const registrieren = async () => {
    setBusy(true); setFehler(null);
    try {
      const r = await rufe('/terminal/registrieren', { methode: 'POST', bearer: login, body: { object_id: Number(objekt), name: f.name.trim() } });
      localStorage.setItem(KEY, r.token);
      onFertig();
    } catch (x) { setFehler(x.message); }
    setBusy(false);
  };
  const feld = { ...S.eingabe, fontSize: 24, minHeight: 60, marginTop: 6 };
  return (
    <div style={{ ...S.inhalt, display: 'flex', justifyContent: 'center' }}>
      <div style={{ background: 'white', borderRadius: 20, padding: 32, width: 640, maxWidth: '100%', alignSelf: 'flex-start' }} data-term-einrichtung>
        <div style={{ fontSize: 32, fontWeight: 800, color: NAVY }}>Terminal einrichten</div>
        <div style={{ fontSize: 19, color: '#475569', marginTop: 6 }}>Einmalig durch Admin oder Objektleitung. Danach stempeln die Mitarbeiter hier mit Name und PIN.</div>
        {!login ? (
          <form onSubmit={anmelden} style={{ marginTop: 20, display: 'grid', gap: 14 }}>
            <label style={{ fontSize: 20 }}>E-Mail<input style={feld} type="email" autoComplete="off" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} data-term-email /></label>
            <label style={{ fontSize: 20 }}>Passwort<input style={feld} type="password" autoComplete="off" value={f.passwort} onChange={(e) => setF({ ...f, passwort: e.target.value })} data-term-passwort /></label>
            <button type="submit" disabled={busy || !f.email || !f.passwort} style={{ ...S.zweit, background: NAVY, color: 'white', justifyContent: 'center' }} data-term-anmelden><UserRound size={26} />Anmelden</button>
          </form>
        ) : (
          <div style={{ marginTop: 20, display: 'grid', gap: 14 }}>
            <label style={{ fontSize: 20 }}>Objekt
              <select style={feld} value={objekt} onChange={(e) => setObjekt(e.target.value)} data-term-objektwahl>
                <option value="">– bitte wählen –</option>
                {objekte.map((o) => <option key={o.id} value={o.id}>{o.name}{o.test ? ' (Test)' : ''}</option>)}
              </select></label>
            <label style={{ fontSize: 20 }}>Name des Geräts (optional)<input style={feld} value={f.name} placeholder="z. B. Tablet Eingang" onChange={(e) => setF({ ...f, name: e.target.value })} data-term-geraetename /></label>
            <button type="button" disabled={busy || !objekt} onClick={registrieren} style={{ ...S.zweit, background: GRUEN, borderColor: GRUEN, color: 'white', justifyContent: 'center' }} data-term-registrieren><Check size={26} />Als Terminal registrieren</button>
          </div>
        )}
        {fehler && <div role="alert" data-term-fehler style={{ marginTop: 16, fontSize: 20, fontWeight: 700, color: ROT }}>{fehler}</div>}
      </div>
    </div>
  );
}

// Langer Druck aufs Logo (5 Sek): Terminal auf diesem Geraet abmelden - nur mit Admin/OL-Login
function Abmelden({ onAbbruch, onFertig }) {
  const [f, setF] = useState({ email: '', passwort: '' });
  const [fehler, setFehler] = useState(null);
  const los = async (e) => {
    e.preventDefault();
    try {
      const r = await rufe('/auth/login', { methode: 'POST', body: { email: f.email.trim(), password: f.passwort } });
      if (!['admin', 'objektleiter'].includes(String(r.role).toLowerCase())) throw new Error('Nur Admin oder Objektleitung');
      localStorage.removeItem(KEY); onFertig();
    } catch (x) { setFehler(x.status === 401 ? 'E-Mail oder Passwort falsch' : x.message); }
  };
  const feld = { ...S.eingabe, fontSize: 22, minHeight: 56, marginTop: 6 };
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.6)', zIndex: 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <form onSubmit={los} style={{ background: 'white', borderRadius: 20, padding: 28, width: 560, display: 'grid', gap: 12 }} data-term-abmelden>
        <div style={{ fontSize: 28, fontWeight: 800, color: NAVY }}>Terminal auf diesem Gerät abmelden?</div>
        <div style={{ fontSize: 18, color: '#475569' }}>Nur Admin oder Objektleitung. Im Cockpit bleibt das Gerät gelistet, bis es dort widerrufen wird.</div>
        <input style={feld} type="email" placeholder="E-Mail" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <input style={feld} type="password" placeholder="Passwort" value={f.passwort} onChange={(e) => setF({ ...f, passwort: e.target.value })} />
        {fehler && <div role="alert" style={{ fontSize: 18, fontWeight: 700, color: ROT }}>{fehler}</div>}
        <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
          <button type="button" style={S.zweit} onClick={onAbbruch}>Abbrechen</button>
          <button type="submit" style={{ ...S.zweit, background: ROT, borderColor: ROT, color: 'white' }}>Abmelden</button>
        </div>
      </form>
    </div>
  );
}

export default function Terminal() {
  const [token, setToken] = useState(() => localStorage.getItem(KEY));
  const [hinweis, setHinweis] = useState(null);
  const [start, setStart] = useState(null);
  const [online, setOnline] = useState(true);
  const [versatz, setVersatz] = useState(0);
  const [seite, setSeite] = useState('start');   // start | suche | pin | knopf | fertig
  const [ma, setMa] = useState(null);
  const [info, setInfo] = useState(null);
  const [ergebnis, setErgebnis] = useState(null);
  const [fehler, setFehler] = useState(null);
  const [busy, setBusy] = useState(false);
  const [abmelden, setAbmelden] = useState(false);
  const leerlauf = useRef(null);
  useWakeLock();

  useEffect(() => {  // Terminal-Manifest (Querformat, Vollbild) + Titel
    document.title = 'SEDA24 Terminal';
    try { screen.orientation?.lock?.('landscape').catch(() => {}); } catch (e) { /* nur im Vollbild/App-Modus */ }
  }, []);

  const zumStart = useCallback(() => { setSeite('start'); setMa(null); setInfo(null); setErgebnis(null); setFehler(null); setBusy(false); }, []);

  const laden = useCallback(async () => {
    if (!token) return;
    try {
      const t0 = Date.now();
      const r = await rufe('/terminal/start', { token });
      setVersatz(new Date(r.jetzt).getTime() - Math.round((t0 + Date.now()) / 2));
      setStart(r); setOnline(true);
    } catch (e) {
      if (e instanceof KeinNetz) setOnline(false);
      else if (e.status === 401) { localStorage.removeItem(KEY); setToken(null); setHinweis('Dieses Terminal wurde im Cockpit abgemeldet – bitte neu einrichten.'); }
    }
  }, [token]);

  useEffect(() => {
    laden();
    const i = setInterval(laden, PING_MS);
    const an = () => laden();
    const aus = () => setOnline(false);
    window.addEventListener('online', an);
    window.addEventListener('offline', aus);
    return () => { clearInterval(i); window.removeEventListener('online', an); window.removeEventListener('offline', aus); };
  }, [laden]);

  // Leerlauf: PIN-/Knopf-/Suche-Bildschirm nach 30 Sek ohne Eingabe zurueck
  useEffect(() => {
    clearTimeout(leerlauf.current);
    if (seite === 'start' || seite === 'fertig') return undefined;
    const neu = () => { clearTimeout(leerlauf.current); leerlauf.current = setTimeout(zumStart, LEERLAUF_MS); };
    neu();
    window.addEventListener('pointerdown', neu);
    window.addEventListener('keydown', neu);
    return () => { clearTimeout(leerlauf.current); window.removeEventListener('pointerdown', neu); window.removeEventListener('keydown', neu); };
  }, [seite, zumStart]);

  const netzFehler = (e) => {
    if (e instanceof KeinNetz) { setOnline(false); setFehler('Kein WLAN – NICHT gestempelt.'); return true; }
    return false;
  };

  const wahl = (k) => { setMa(k); setFehler(null); setSeite('pin'); };

  const pinPruefen = async (pin) => {
    setBusy(true); setFehler(null);
    try {
      const r = await rufe('/terminal/pin', { methode: 'POST', token, body: { employee_id: ma.employee_id, pin } });
      setInfo(r); setSeite('knopf');
    } catch (e) { if (!netzFehler(e)) setFehler(e.message); }
    setBusy(false);
  };

  const stempeln = async (aktion) => {
    setBusy(true); setFehler(null);
    try {
      const r = await rufe('/terminal/stempeln', { methode: 'POST', token, body: { schein: info.schein, aktion } });
      setErgebnis(r); setSeite('fertig'); laden();
    } catch (e) {
      if (!netzFehler(e)) {
        if (e.status === 401) { setFehler(e.message); setTimeout(zumStart, 3000); } else setFehler(e.message);
      }
    }
    setBusy(false);
  };

  if (!token) {
    return (
      <div style={S.seite} data-terminal>
        <Kopf start={null} versatz={0} onLangDruck={() => {}} />
        <Einrichtung hinweis={hinweis} onFertig={() => { setHinweis(null); setToken(localStorage.getItem(KEY)); zumStart(); }} />
      </div>
    );
  }

  return (
    <div style={S.seite} data-terminal>
      <Kopf start={start} versatz={versatz} onLangDruck={() => setAbmelden(true)} />
      {seite === 'start' && <StartSeite start={start} onWahl={wahl} onSuche={() => setSeite('suche')} />}
      {seite === 'suche' && <SucheSeite token={token} onWahl={wahl} onZurueck={zumStart} onNetz={setOnline} />}
      {seite === 'pin' && ma && <PinSeite ma={ma} fehler={fehler} busy={busy} onPin={pinPruefen} onZurueck={zumStart} />}
      {seite === 'knopf' && info && <KnopfSeite info={info} fehler={fehler} busy={busy} onStempeln={stempeln} onZurueck={zumStart} />}
      {seite === 'fertig' && ergebnis && <FertigSeite r={ergebnis} onWeiter={zumStart} />}
      {!online && <KeinWlan />}
      {abmelden && <Abmelden onAbbruch={() => setAbmelden(false)} onFertig={() => { setAbmelden(false); setToken(null); setStart(null); }} />}
    </div>
  );
}
