import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { Play, Square, Pause, PlayCircle, Building, Clock, AlertCircle, X as CloseIcon, Wifi, WifiOff, Check, RefreshCw, Hourglass, CheckCircle } from 'lucide-react';
import { API_URL } from '../config.js';
import './stempeluhr-marke.css';
import { saveCObjects, loadCachedCObjects } from '../services/cObjectsCache';
import { QUEUE_KEY, vonUnseremServer, currentOwner, isOwnItem, AKTION_NAME, uhrzeit, stempelText } from '../services/stempelStatus';

// ==================== Offline-Queue Utilities ====================

const STATE_KEY = 'bie2_offline_state';
const KOMMEN_TOLERANZ_MIN = 10; // Kommen ab 10 Min vor Schichtbeginn (Backend: TOLERANZ_MIN)

function generateId() {
  return 'xxxx-xxxx-xxxx'.replace(/x/g, () => Math.floor(Math.random() * 16).toString(16));
}

function getQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
  catch { return []; }
}

function saveQueue(q) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q));
}

// Stempel gehoeren dem Benutzer, der sie gemacht hat (bleiben bei Logout erhalten,
// werden aber nur fuer diesen Benutzer uebertragen). Alte Eintraege ohne owner: wie bisher.
// currentOwner/isOwnItem: services/stempelStatus.js

function neuerStempel(action, objectId) {
  return {
    id: generateId(),
    owner: currentOwner(),
    action,            // 'check_in' | 'check_out' | 'pause_start' | 'pause_end'
    object_id: objectId,
    timestamp: new Date().toISOString(),
    status: 'pending',  // pending | syncing | synced | failed
    retries: 0
  };
}

function addToQueue(item) {
  const q = getQueue();
  q.push(item);
  saveQueue(q);
  return item;
}

function markSynced(itemId) {
  const q = getQueue().map(i => i.id === itemId ? { ...i, status: 'synced' } : i);
  // Sofort entfernen was gesynct ist
  saveQueue(q.filter(i => i.status !== 'synced'));
}

function markFailed(itemId, error) {
  const q = getQueue().map(i =>
    i.id === itemId ? { ...i, status: 'failed', error, retries: (i.retries || 0) + 1 } : i
  );
  saveQueue(q);
}

function getPendingCount() {
  return getQueue().filter(i => i.status !== 'synced' && isOwnItem(i)).length;
}

// ==================== Server-Bestaetigung ====================
// Ein Stempel gilt nur als erledigt, wenn UNSER Server ihn nachweislich bestaetigt (Kennung X-Seda24 im
// Header, JSON; Kommen/Gehen: die client_id kommt zurueck) oder eine echte JSON-Fehlermeldung unseres
// Servers liefert. HTML, Weiterleitungen (Captive Portal), 403/511, fremde Antworten, 5xx und Timeout
// zaehlen wie "kein Netz": der Stempel bleibt in der Warteschlange.
const BESTAETIGUNG_MS = 5000; // nach dem Tippen max. so lange auf die Bestaetigung warten, sonst ⏳
const SYNC_TIMEOUT_MS = 8000;
const LETZTER_KEY = 'bie2_letzter_stempel'; // zuletzt vom Server bestaetigter Stempel (fuer die ✓-Anzeige)

function bestaetigt(item, res) {
  if (!vonUnseremServer(res) || res.status < 200 || res.status >= 300) return false;
  if (item.action === 'check_in' || item.action === 'check_out') return !!res.data && res.data.client_id === item.id;
  return true;
}

function serverFehler(e) {
  const r = e && e.response;
  return !!r && vonUnseremServer(r) && r.status >= 400 && r.status < 500 && !!r.data && r.data.detail !== undefined;
}

const STEMPEL_URL = { check_in: '/time-entries/check-in', check_out: '/time-entries/check-out', pause_start: '/breaks/start', pause_end: '/breaks/end' };

// Ergebnis: 'ok' (bestaetigt) | 'fehler' (echte Ablehnung unseres Servers) | 'abgemeldet' (401 unseres Servers)
//           | 'offen' (keine Bestaetigung -> bleibt/kommt in die Warteschlange)
async function stempelSenden(item, headers, timeout) {
  const payload = { client_id: item.id, client_timestamp: item.timestamp };
  if (item.action === 'check_in') {
    payload.object_id = parseInt(item.object_id);
    payload.notes = 'Bie2 Kommen';
  }
  try {
    const res = await axios.post(`${API_URL}${STEMPEL_URL[item.action]}`, payload, { headers, timeout });
    return bestaetigt(item, res) ? { art: 'ok', res } : { art: 'offen', grund: `keine Server-Bestaetigung (HTTP ${res.status})` };
  } catch (e) {
    if (e.response && e.response.status === 401 && vonUnseremServer(e.response)) return { art: 'abgemeldet', e };
    if (serverFehler(e)) return { art: 'fehler', e };
    return { art: 'offen', e, grund: e.response ? `HTTP ${e.response.status}` : e.message };
  }
}

function merkeBestaetigt(item) {
  localStorage.setItem(LETZTER_KEY, JSON.stringify({ action: item.action, timestamp: item.timestamp }));
}

function getLetzterBestaetigt() {
  try {
    const l = JSON.parse(localStorage.getItem(LETZTER_KEY) || 'null');
    return l && new Date(l.timestamp).toDateString() === new Date().toDateString() ? l : null;
  } catch { return null; }
}

// ==================== Heute erledigt (Ein-Knopf-Ablauf) ====================
// Kommen/Gehen-Paare von heute, wie das Handy sie kennt (auch noch nicht uebertragene) - fuer
// "Schicht erledigt" ohne Netz. Je Benutzer und Tag.
const heuteKey = () => `bie2_heute_${currentOwner()}_${new Date().toDateString()}`;

function getHeute() {
  try { return JSON.parse(localStorage.getItem(heuteKey()) || '[]'); }
  catch { return []; }
}

function merkeHeute(kommenIso, gehenIso, objectId, wartet) {
  const h = getHeute().filter(e => e.gehen !== gehenIso);
  h.push({ kommen: kommenIso, gehen: gehenIso, object_id: objectId, wartet });
  localStorage.setItem(heuteKey(), JSON.stringify(h));
}

function heuteUebertragen(gehenIso) {
  localStorage.setItem(heuteKey(), JSON.stringify(getHeute().map(e => (e.gehen === gehenIso ? { ...e, wartet: false } : e))));
}

const NAECHSTE_KEY = 'bie2_naechste_schichten';

// Offline-State: Optimistischer lokaler Zustand für sofortige UI-Updates
function getOfflineState() {
  try { return JSON.parse(localStorage.getItem(STATE_KEY) || 'null'); }
  catch { return null; }
}

function saveOfflineState(state) {
  if (state) localStorage.setItem(STATE_KEY, JSON.stringify(state));
  else localStorage.removeItem(STATE_KEY);
}

// ==================== Ein-Knopf-Ablauf: Stile ====================
// Firmen-Look SEDA24 = dieselben Werte wie die Cockpit-Branding-Einstellung (Navy/Gold, Poppins/Open Sans)
const MARKE = { navy: '#1E537C', navyDunkel: '#0E2A40', gold: '#F9B233', titel: "'Poppins', 'Open Sans', system-ui, sans-serif" };

// Grosse Schrift, Daumen-Zone, farbenblind-sicher: Symbol + Wort + Rahmen (durchgezogen = fertig, gestrichelt = wartet)
const EK = {
  kopf: { textAlign: 'center', marginBottom: '14px' },
  objekt: { fontSize: '26px', fontWeight: 700, color: MARKE.navyDunkel, lineHeight: 1.2, fontFamily: MARKE.titel },
  schichtzeit: { fontSize: '22px', fontWeight: 600, color: MARKE.navy, marginTop: '4px' },
  knopf: {
    width: '100%', border: 'none', borderRadius: '24px', color: 'white', fontWeight: 700, letterSpacing: '1px', fontFamily: MARKE.titel,
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px', cursor: 'pointer',
    boxShadow: '0 6px 16px rgba(0,0,0,0.25)', marginTop: '6px',
  },
  riesig: { minHeight: 'max(260px, 42vh)', fontSize: '42px' },
  karte: { borderRadius: '18px', padding: '18px', marginBottom: '14px', display: 'flex', flexDirection: 'column', gap: '8px' },
  titel: { fontSize: '26px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px', fontFamily: MARKE.titel },
  zeile: { fontSize: '20px', fontWeight: 700 },
  klein: { fontSize: '16px', color: 'inherit' },
  ok: { border: '4px solid #166534', background: '#f0fdf4', color: '#14532d' },
  wartet: { border: '4px dashed #1d4ed8', background: '#eff6ff', color: '#1e3a8a' },
  status: { marginTop: '14px', padding: '12px 14px', borderRadius: '14px' },
  statusZeile: { fontSize: '18px', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '8px' },
};

// ==================== Komponente ====================

const Bie2Stempeluhr = ({ token, onStatusChange, onLogout, shiftsToday = [] }) => {
  const [cObjects, setCObjects] = useState([]);
  const [selectedObject, setSelectedObject] = useState(null);
  const [isWorking, setIsWorking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [checkInTime, setCheckInTime] = useState(null);
  const [pauseStartTime, setPauseStartTime] = useState(null);
  const [totalPauseDuration, setTotalPauseDuration] = useState(0);
  const [currentObjectId, setCurrentObjectId] = useState(null);
  const [entryId, setEntryId] = useState(null);
  const [isOpenCatchup, setIsOpenCatchup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timerDisplay, setTimerDisplay] = useState('00:00:00');
  const [actionLoading, setActionLoading] = useState(false);
  const [nowTick, setNowTick] = useState(Date.now());

  // Heute gebucht (NUR server-bestaetigte Eintraege)
  const [todayEntries, setTodayEntries] = useState([]);
  // Noch nicht uebertragene Stempel (lokale Daten, Queue pending)
  const [pendingEntries, setPendingEntries] = useState([]);

  // Offline-Status
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingSync, setPendingSync] = useState(getPendingCount());
  const [syncMessage, setSyncMessage] = useState(null);
  const syncingRef = useRef(false);
  // Zaehlt jeden Stempel: Status-Antworten, die VOR dem letzten Stempel angefragt wurden, sind veraltet
  const stempelSeqRef = useRef(0);
  const [letzterStempel, setLetzterStempel] = useState(getLetzterBestaetigt());
  // Echte Erreichbarkeit unseres Servers (nicht nur "WLAN verbunden"): null = unbekannt
  const [erreichbar, setErreichbar] = useState(null);
  const [toast, setToast] = useState(null);
  // Kurze Bestaetigung nach Kommen ({art: 'ok'|'wartet', text}); solange kein zweiter Knopf (kein Vertippen)
  const [quittung, setQuittung] = useState(null);
  const [heuteVersion, setHeuteVersion] = useState(0); // neu rendern, wenn sich "heute erledigt" aendert
  const [naechste, setNaechste] = useState(() => {
    try { return JSON.parse(localStorage.getItem(NAECHSTE_KEY) || '[]'); } catch { return []; }
  });

  // Netz-Erkennung: kommt der Request aus dem Objektnetz (Lidl-WLAN) oder Mobilfunk?
  const [netStatus, setNetStatus] = useState(null); // { at_object, client_ip, object_name }

  // Quick-Gehen (ohne Kommen)
  const [showQuickGehen, setShowQuickGehen] = useState(false);
  const [quickGehenKommenZeit, setQuickGehenKommenZeit] = useState('');
  const [quickGehenTime, setQuickGehenTime] = useState('');
  const [quickGehenLoading, setQuickGehenLoading] = useState(false);
  const [quickGehenMessage, setQuickGehenMessage] = useState(null);

  // Nachtrag
  const [showCatchup, setShowCatchup] = useState(false);
  const [catchupType, setCatchupType] = useState('beides_vergessen');
  const [catchupDate, setCatchupDate] = useState('');
  const [catchupTimeStart, setCatchupTimeStart] = useState('');
  const [catchupTimeEnd, setCatchupTimeEnd] = useState('');
  const [catchupNotes, setCatchupNotes] = useState('');
  const [catchupLoading, setCatchupLoading] = useState(false);
  const [catchupMessage, setCatchupMessage] = useState(null);
  const [catchupReason, setCatchupReason] = useState('');

  // Netz-Status pollen: sagt ob wir ueber das Objektnetz (Lidl-WLAN) kommen
  useEffect(() => {
    let cancelled = false;
    const objId = currentObjectId || selectedObject || 20;
    const fetchNet = async () => {
      if (!navigator.onLine) { if (!cancelled) { setNetStatus(null); setErreichbar(false); } return; }
      try {
        const res = await axios.get(`${API_URL}/time-entries/network-status`, {
          params: { object_id: objId },
          headers: { Authorization: `Bearer ${token}` },
          timeout: 8000,
        });
        // Gast-WLAN mit Anmeldeseite liefert HTML/Weiterleitung -> zaehlt als offline
        const unser = vonUnseremServer(res);
        if (!cancelled) { setNetStatus(unser ? res.data : null); setErreichbar(unser); }
      } catch (e) {
        if (!cancelled) {
          setNetStatus(null); // unbekannt -> Balken nicht anzeigen
          setErreichbar(!!(e.response && vonUnseremServer(e.response)));
        }
      }
    };
    fetchNet();
    const iv = setInterval(fetchNet, 10000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [token, isOnline, selectedObject, currentObjectId]);
  const [myCatchups, setMyCatchups] = useState([]);

  // Overdue-Warnung
  const [overdueWarning, setOverdueWarning] = useState(false);
  const [scheduledEndTime, setScheduledEndTime] = useState(null);
  const [overdueMinutes, setOverdueMinutes] = useState(0);

  // Korrektur-Modus
  const [correctionMode, setCorrectionMode] = useState(false);
  const [correctionEntries, setCorrectionEntries] = useState([]);
  const [selectedEntryId, setSelectedEntryId] = useState(null);
  const [correctionField, setCorrectionField] = useState('beides');
  const [correctionEntriesLoading, setCorrectionEntriesLoading] = useState(false);

  const timerRef = useRef(null);
  const headers = { Authorization: `Bearer ${token}` };

  // ==================== Online/Offline Detection ====================

  useEffect(() => {
    const goOnline = () => { setIsOnline(true); triggerSync(); };
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  // ==================== Auto-Sync ====================

  const triggerSync = useCallback(async () => {
    if (syncingRef.current) return;
    const queue = getQueue().filter(i => (i.status === 'pending' || i.status === 'failed') && isOwnItem(i));
    if (queue.length === 0) { setPendingSync(0); return; }

    syncingRef.current = true;
    setSyncMessage('Synchronisiere...');
    const uebertragen = [];

    for (const item of queue) {
      const r = await stempelSenden(item, headers, SYNC_TIMEOUT_MS);
      if (r.art === 'ok') {
        stempelSeqRef.current++;
        markSynced(item.id);
        merkeBestaetigt(item);
        setLetzterStempel(getLetzterBestaetigt());
        setErreichbar(true);
        if (item.action === 'check_in' || item.action === 'check_out') uebertragen.push(item);
        if (item.action === 'check_out') { heuteUebertragen(item.timestamp); setHeuteVersion(v => v + 1); }
      } else if (r.art === 'abgemeldet') {
        // Token abgelaufen → Queue NICHT löschen, User zum Re-Login auffordern
        syncingRef.current = false;
        setSyncMessage('Sitzung abgelaufen – bitte neu einloggen');
        if (onLogout) onLogout();
        return;
      } else if (r.art === 'fehler') {
        // Echte Ablehnung unseres Servers (z.B. bereits eingestempelt) = erledigt, nicht wiederholen
        markSynced(item.id);
        setError(`${AKTION_NAME[item.action]} ${uhrzeit(item.timestamp)} nicht übernommen: ${r.e.response.data.detail}`);
      } else {
        // HTML/Weiterleitung/403/511/5xx/Timeout = wie kein Netz: bleibt in der Warteschlange
        markFailed(item.id, r.grund);
        setErreichbar(false);
        break; // restliche Queue nicht weiter versuchen (Reihenfolge bleibt)
      }
    }

    syncingRef.current = false;
    const remaining = getPendingCount();
    setPendingSync(remaining);
    // Spaetere Uebertragung: kurze Info in der App (keine Telegram-Nachricht)
    if (uebertragen.length > 0) {
      setToast(`${stempelText(uebertragen)} übertragen`);
      setTimeout(() => setToast(null), 6000);
    }

    if (remaining === 0) {
      setSyncMessage('Alle Stempel synchronisiert!');
      // Pending-Eintraege leeren, Server-Status holt bestaetigte Daten
      setPendingEntries([]);
      await checkStatus('after_sync');
      if (onStatusChange) onStatusChange();
      setTimeout(() => setSyncMessage(null), 3000);
    } else {
      setSyncMessage(`${remaining} Stempel ausstehend`);
    }
  }, [token]);

  // Server wieder erreichbar (z.B. nach Anmeldung im Gast-WLAN, dort kommt kein 'online'-Ereignis): senden
  useEffect(() => {
    if (erreichbar && getPendingCount() > 0) triggerSync();
  }, [erreichbar, triggerSync]);

  // Sync bei App-Start und nach Login (token-Änderung)
  useEffect(() => {
    if (token && navigator.onLine && getPendingCount() > 0) {
      setTimeout(() => triggerSync(), 2000);
    }
  }, [token]);

  // Sync, sobald die App wieder in den Vordergrund kommt (iOS pausiert Apps im Hintergrund
  // und meldet 'online' nicht zuverlaessig)
  useEffect(() => {
    const kick = () => {
      if (document.visibilityState === 'visible' && navigator.onLine && getPendingCount() > 0) triggerSync();
    };
    document.addEventListener('visibilitychange', kick);
    window.addEventListener('pageshow', kick);
    window.addEventListener('focus', kick);
    return () => {
      document.removeEventListener('visibilitychange', kick);
      window.removeEventListener('pageshow', kick);
      window.removeEventListener('focus', kick);
    };
  }, [triggerSync]);

  // Periodischer Sync-Versuch alle 30s
  useEffect(() => {
    const interval = setInterval(() => {
      if (navigator.onLine && getPendingCount() > 0) triggerSync();
    }, 30000);
    return () => clearInterval(interval);
  }, [triggerSync]);

  // FIX 3: Sekundentakt, damit der KOMMEN-Button genau zum Schichtbeginn aktiv wird
  useEffect(() => {
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // ==================== Optimistic UI Update ====================

  const applyOptimisticState = (action, objectId) => {
    const now = new Date();
    if (action === 'check_in') {
      setIsWorking(true);
      setCheckInTime(now);
      setCurrentObjectId(objectId);
      setSelectedObject(objectId);
      setIsPaused(false);
      setTotalPauseDuration(0);
      saveOfflineState({ action: 'checked_in', objectId, checkInTime: now.toISOString() });
    } else if (action === 'check_out') {
      setIsWorking(false);
      setCheckInTime(null);
      setIsPaused(false);
      setCurrentObjectId(null);
      setEntryId(null);
      saveOfflineState(null);
    } else if (action === 'pause_start') {
      setIsPaused(true);
      setPauseStartTime(now);
    } else if (action === 'pause_end') {
      if (pauseStartTime) {
        const pauseDur = (now - pauseStartTime) / 1000;
        setTotalPauseDuration(prev => prev + pauseDur);
      }
      setIsPaused(false);
      setPauseStartTime(null);
    }
  };

  // ==================== API-Aufrufe (Online-First, Offline-Fallback) ====================

  const performAction = async (action, objectId) => {
    const item = neuerStempel(action, objectId);
    stempelSeqRef.current++;

    // Checkout-Daten VOR allem anderen sichern (State könnte danach weg sein)
    const wasCheckout = action === 'check_out';
    const savedCheckIn = checkInTime;
    const savedObjectId = currentObjectId || selectedObject;

    const buildLocalEntry = () => {
      if (!savedCheckIn) return null;
      const now = new Date();
      const ciH = savedCheckIn.getHours().toString().padStart(2, '0');
      const ciM = savedCheckIn.getMinutes().toString().padStart(2, '0');
      const coH = now.getHours().toString().padStart(2, '0');
      const coM = now.getMinutes().toString().padStart(2, '0');
      const durMin = Math.round((now - savedCheckIn) / 60000);
      const objName = cObjects.find(o => o.id === savedObjectId)?.name || '';
      return { check_in: `${ciH}:${ciM}`, check_out: `${coH}:${coM}`, duration_minutes: durMin, object_name: objName };
    };

    // Ohne Server-Bestaetigung: lokal als PENDING merken (⏳), wird automatisch nachgesendet
    const inWarteschlange = () => {
      if (wasCheckout) {
        const entry = buildLocalEntry();
        if (entry) setPendingEntries(prev => [...prev, entry]);
        if (savedCheckIn) { merkeHeute(savedCheckIn.toISOString(), item.timestamp, savedObjectId, true); setHeuteVersion(v => v + 1); }
      }
      applyOptimisticState(action, objectId);
      addToQueue(item);
      setPendingSync(getPendingCount());
      return true;
    };

    if (!navigator.onLine) return inWarteschlange();
    if (erreichbar === false) {
      // Kein echtes Netz (z.B. Gast-WLAN mit Anmeldeseite): sofort lokal speichern, Zaehler stoppt jetzt
      inWarteschlange();
      triggerSync();
      return true;
    }

    // Stehen schon Stempel aus: hinten anstellen, damit die Reihenfolge stimmt, dann senden
    if (getPendingCount() > 0) {
      inWarteschlange();
      triggerSync();
      return true;
    }

    // Online: max. BESTAETIGUNG_MS auf die Bestaetigung unseres Servers warten
    const r = await stempelSenden(item, headers, BESTAETIGUNG_MS);

    setErreichbar(r.art !== 'offen');
    if (r.art === 'ok') {
      // Bestaetigtes Kommen sofort merken (nicht erst nach /current), damit es ohne Netz sichtbar bleibt
      if (action === 'check_in') saveOfflineState({ action: 'checked_in', objectId, checkInTime: item.timestamp });
      merkeBestaetigt(item);
      setLetzterStempel(getLetzterBestaetigt());
      // Mehr als 10 Min nach Schichtende: gezaehlt bis Schichtende, Mehrzeit als Antrag gemeldet
      if (wasCheckout && r.res.data && r.res.data.mehrzeit_antrag && r.res.data.cap_message) {
        setSyncMessage(r.res.data.cap_message);
        setTimeout(() => setSyncMessage(null), 8000);
      }
      // Erfolg: State zuruecksetzen, Server-Status holen (liefert bestaetigte today_entries)
      if (wasCheckout) {
        if (savedCheckIn) { merkeHeute(savedCheckIn.toISOString(), item.timestamp, savedObjectId, false); setHeuteVersion(v => v + 1); }
        saveOfflineState(null);
        setIsWorking(false);
        setCheckInTime(null);
        setIsPaused(false);
        setCurrentObjectId(null);
        setEntryId(null);
      }
      await checkStatus('after_' + action);
      if (onStatusChange) onStatusChange();
      return true;
    }
    if (r.art === 'abgemeldet') {
      // Stempel nicht verlieren: in die Warteschlange, nach dem Login wird er gesendet
      inWarteschlange();
      setSyncMessage('Sitzung abgelaufen – bitte neu einloggen');
      if (onLogout) onLogout();
      return true;
    }
    if (r.art === 'fehler') {
      // Echte Fehlermeldung unseres Servers (z.B. Mindestdauer, zu frueh)
      await checkStatus();
      throw r.e;
    }
    // Keine Bestaetigung (kein Netz, Captive Portal, 5xx, Timeout): sicher gespeichert, ⏳
    return inWarteschlange();
  };

  // ==================== Data Loading ====================

  const ladeNaechste = async () => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/my-upcoming-shifts`, { headers, timeout: 8000 });
      if (Array.isArray(res.data)) {
        setNaechste(res.data);
        localStorage.setItem(NAECHSTE_KEY, JSON.stringify(res.data));
      }
    } catch { /* ohne Netz: zuletzt geladene bleiben */ }
  };

  const loadCObjects = async () => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/my-c-objects`, { headers });
      setCObjects(res.data || []);
      saveCObjects(res.data || []);
      if (res.data && res.data.length > 0 && !selectedObject) {
        setSelectedObject(res.data[0].id);
      }
    } catch (e) {
      console.error('Fehler beim Laden der C-Objekte:', e);
      // Ohne Verbindung: zuletzt bekannte C-Objekte (Offline-Stempeln ueber Queue)
      if (!e.response) {
        const cached = loadCachedCObjects();
        if (cached.length > 0) {
          setCObjects(prev => (prev.length > 0 ? prev : cached));
          if (!selectedObject) setSelectedObject(cached[0].id);
        }
      }
    }
  };

  const checkStatus = async (context) => {
    const seq = stempelSeqRef.current;
    try {
      const res = await axios.get(`${API_URL}/time-entries/current`, { headers });
      // Inzwischen gestempelt: diese Antwort ist veraltet (die Abfrage nach dem Stempel folgt)
      if (seq !== stempelSeqRef.current) return;
      const data = res.data;
      console.log('[checkStatus]', context || 'init', 'is_working:', data?.is_working, 'today_entries:', data?.today_entries?.length);
      // Warteschlange zuerst: steht ein Kommen/Gehen noch aus, gilt der Stand auf dem Handy, bis er
      // gesendet ist (sonst zeigt die App z.B. "eingestempelt", obwohl das Gehen schon gespeichert ist)
      const offen = getQueue().filter(i => isOwnItem(i) && i.status !== 'synced' && (i.action === 'check_in' || i.action === 'check_out'));
      if (offen.length > 0) {
        const letzter = offen[offen.length - 1];
        if (data && data.today_entries) setTodayEntries(data.today_entries);
        if (letzter.action === 'check_in') {
          setIsWorking(true);
          setCheckInTime(new Date(letzter.timestamp));
          setCurrentObjectId(letzter.object_id);
          setSelectedObject(letzter.object_id);
        } else {
          setIsWorking(false);
          setCheckInTime(null);
          setIsPaused(false);
          setCurrentObjectId(null);
          setEntryId(null);
          setOverdueWarning(false);
        }
        return;
      }
      if (data && data.is_working) {
        setIsWorking(true);
        setCheckInTime(new Date(data.check_in));
        setCurrentObjectId(data.object_id);
        setSelectedObject(data.object_id);
        setEntryId(data.entry_id);
        setIsPaused(data.is_paused || false);
        setIsOpenCatchup(data.is_open_catchup || false);
        if (data.is_paused && data.pause_start_time) {
          setPauseStartTime(new Date(data.pause_start_time));
        } else {
          setPauseStartTime(null);
        }
        setTotalPauseDuration(data.total_pause_duration || 0);
        setOverdueWarning(data.overdue_warning || false);
        setScheduledEndTime(data.scheduled_end_time || null);
        setOverdueMinutes(data.overdue_minutes || 0);
        // todayEntries NICHT löschen — bleiben sichtbar auch während nächster Schicht
        // Server-Stand merken: oeffnet die App spaeter ohne Netz (oder im Gast-WLAN), bleibt "eingestempelt" sichtbar
        saveOfflineState({ action: 'checked_in', objectId: data.object_id, checkInTime: data.check_in });
      } else {
        // Heutige abgeschlossene Eintraege uebernehmen (nur Server-Daten)
        if (data && data.today_entries) {
          setTodayEntries(data.today_entries);
          // Wenn Server Eintraege liefert, pending leeren (wurde uebertragen)
          if (data.today_entries.length > 0 && getPendingCount() === 0) {
            setPendingEntries([]);
          }
        }
        // Prüfe ob lokaler Offline-State existiert (noch nicht gesynct)
        const offState = getOfflineState();
        if (offState && getPendingCount() > 0) {
          // Offline-State beibehalten bis Sync durch
          if (offState.action === 'checked_in') {
            setIsWorking(true);
            setCheckInTime(new Date(offState.checkInTime));
            setCurrentObjectId(offState.objectId);
          }
        } else {
          setIsWorking(false);
          setCheckInTime(null);
          setIsPaused(false);
          setIsOpenCatchup(false);
          setEntryId(null);
          setCurrentObjectId(null);
          setOverdueWarning(false);
          setScheduledEndTime(null);
          setOverdueMinutes(0);
          saveOfflineState(null);
        }
      }
    } catch (e) {
      if (e.response && e.response.status === 401) {
        setSyncMessage('Sitzung abgelaufen – bitte neu einloggen');
        if (onLogout) onLogout();
        return;
      }
      console.error('Status-Fehler:', e);
      // Bei Netzwerkfehler: Offline-State verwenden falls vorhanden
      const offState = getOfflineState();
      if (offState && offState.action === 'checked_in') {
        setIsWorking(true);
        setCheckInTime(new Date(offState.checkInTime));
        setCurrentObjectId(offState.objectId);
      }
    }
  };

  const loadCorrectionEntries = async () => {
    setCorrectionEntriesLoading(true);
    try {
      const res = await axios.get(`${API_URL}/time-entries/my-entries-for-correction`, { headers });
      setCorrectionEntries(res.data || []);
    } catch (e) {
      console.error('Fehler beim Laden der Einträge:', e);
    }
    setCorrectionEntriesLoading(false);
  };

  const loadMyCatchups = async () => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/my-catchups`, { headers });
      setMyCatchups(res.data || []);
    } catch (e) {
      console.error('Fehler beim Laden der Nachträge:', e);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadCObjects();
      // Erst die Warteschlange senden, dann den Server-Stand holen (der darf ein lokal gespeichertes,
      // noch nicht gesendetes Kommen/Gehen nie ueberschreiben - siehe auch checkStatus)
      if (navigator.onLine && getPendingCount() > 0) await triggerSync();
      await checkStatus();
      ladeNaechste();
      await loadMyCatchups();
      setLoading(false);
    };
    init();
  }, []);

  // Live-Timer
  useEffect(() => {
    if (isWorking && checkInTime && !isOpenCatchup) {
      timerRef.current = setInterval(() => {
        let totalSeconds = (new Date() - checkInTime) / 1000;
        totalSeconds -= totalPauseDuration;
        if (isPaused && pauseStartTime) {
          totalSeconds -= (new Date() - pauseStartTime) / 1000;
        }
        totalSeconds = Math.max(0, totalSeconds);
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = Math.floor(totalSeconds % 60);
        setTimerDisplay(
          `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
        );
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      if (!isWorking) setTimerDisplay('00:00:00');
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isWorking, checkInTime, isPaused, pauseStartTime, totalPauseDuration, isOpenCatchup]);

  // ==================== Button Handlers ====================

  const vibriere = (muster) => { try { if (navigator.vibrate) navigator.vibrate(muster); } catch { /* iOS: keine Vibration */ } };

  const handleCheckIn = async (objektId) => {
    const obj = (typeof objektId === 'number') ? objektId : selectedObject;
    if (!obj) { setError('Bitte Objekt auswählen'); return; }
    if (actionLoading || isWorking) return;
    setActionLoading(true);
    setError(null);
    try {
      if (obj !== selectedObject) setSelectedObject(obj);
      await performAction('check_in', obj);
      const wartet = getPendingCount() > 0;
      const zeit = uhrzeit(new Date().toISOString());
      setQuittung({ art: wartet ? 'wartet' : 'ok', text: wartet ? `Kommen ${zeit} – wird übertragen` : `Kommen ${zeit}` });
      vibriere(wartet ? [40, 60, 40] : 80);
      setTimeout(() => setQuittung(null), 3000);
    } catch (e) {
      setError(e.response?.data?.detail || 'Fehler beim Einstempeln');
    }
    setActionLoading(false);
  };

  const [minDurationMsg, setMinDurationMsg] = useState(null);

  const handleCheckOut = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    setError(null);
    setMinDurationMsg(null);
    try {
      await performAction('check_out', currentObjectId);
      vibriere(getPendingCount() > 0 ? [40, 60, 40] : 80);
      // Ohne Dienstplan erscheint danach wieder KOMMEN: kurz sperren, damit ein Doppeltipp nicht sofort einstempelt
      setQuittung({ art: 'gehen' });
      setTimeout(() => setQuittung(null), 3000);
    } catch (e) {
      const detail = e.response?.data?.detail || '';
      if (e.response?.status === 422 && detail.includes('möglich zu gehen')) {
        setMinDurationMsg(detail);
      } else {
        setError(detail || 'Fehler beim Ausstempeln');
      }
    }
    setActionLoading(false);
  };

  const handlePauseStart = async () => {
    setError(null);
    try {
      await performAction('pause_start', currentObjectId);
    } catch (e) {
      setError(e.response?.data?.detail || 'Fehler beim Pause starten');
    }
  };

  const handlePauseEnd = async () => {
    setError(null);
    try {
      await performAction('pause_end', currentObjectId);
    } catch (e) {
      setError(e.response?.data?.detail || 'Fehler beim Pause beenden');
    }
  };

  // ==================== Nachtrag / Quick-Gehen (unverändert) ====================

  const resetCatchupForm = () => {
    setShowCatchup(false);
    setCatchupMessage(null);
    setCatchupDate('');
    setCatchupTimeStart('');
    setCatchupTimeEnd('');
    setCatchupNotes('');
    setCatchupType('beides_vergessen');
    setCatchupReason('');
    setCorrectionMode(false);
    setCorrectionEntries([]);
    setSelectedEntryId(null);
    setCorrectionField('beides');
  };

  const handleQuickGehen = async () => {
    if (!quickGehenKommenZeit) {
      setQuickGehenMessage({ type: 'error', text: 'Bitte Kommen-Uhrzeit eingeben' });
      return;
    }
    if (quickGehenKommenZeit === quickGehenTime) {
      setQuickGehenMessage({ type: 'error', text: 'Kommen- und Gehen-Zeit dürfen nicht identisch sein' });
      return;
    }
    if (quickGehenKommenZeit >= quickGehenTime) {
      setQuickGehenMessage({ type: 'error', text: 'Kommen-Zeit muss vor der Gehen-Zeit liegen' });
      return;
    }
    setQuickGehenLoading(true);
    setQuickGehenMessage(null);
    try {
      const now = new Date();
      const yyyy = now.getFullYear();
      const mo = (now.getMonth() + 1).toString().padStart(2, '0');
      const dd = now.getDate().toString().padStart(2, '0');
      await axios.post(`${API_URL}/time-entries/catch-up`, {
        object_id: selectedObject,
        catch_up_type: 'kommen_vergessen',
        date: `${yyyy}-${mo}-${dd}`,
        time: quickGehenKommenZeit,
        time_end: quickGehenTime,
        notes: 'Kommen vergessen, Gehen gestempelt'
      }, { headers });
      setQuickGehenMessage({ type: 'success', text: 'Gesendet! Kommen-Zeit geht zur Genehmigung an Admin.' });
      setTimeout(() => {
        setShowQuickGehen(false);
        setQuickGehenMessage(null);
        setQuickGehenKommenZeit('');
        checkStatus();
        if (onStatusChange) onStatusChange();
      }, 2000);
    } catch (e) {
      setQuickGehenMessage({ type: 'error', text: e.response?.data?.detail || 'Fehler' });
    }
    setQuickGehenLoading(false);
  };

  const handleCatchup = async () => {
    // === Korrektur-Modus ===
    if (correctionMode) {
      if (!selectedEntryId) { setCatchupMessage({ type: 'error', text: 'Bitte wähle einen Eintrag' }); return; }
      if (!catchupReason) { setCatchupMessage({ type: 'error', text: 'Bitte wähle einen Grund' }); return; }
      if ((correctionField === 'kommen' || correctionField === 'beides') && !catchupTimeStart) {
        setCatchupMessage({ type: 'error', text: 'Neue Kommen-Uhrzeit fehlt' }); return;
      }
      if ((correctionField === 'gehen' || correctionField === 'beides') && !catchupTimeEnd) {
        setCatchupMessage({ type: 'error', text: 'Neue Gehen-Uhrzeit fehlt' }); return;
      }
      setCatchupLoading(true);
      setCatchupMessage(null);
      try {
        await axios.post(`${API_URL}/time-entries/catch-up`, {
          catch_up_type: 'zeit_korrektur',
          time_entry_id: selectedEntryId,
          correction_field: correctionField,
          time: catchupTimeStart || undefined,
          time_end: catchupTimeEnd || undefined,
          reason: catchupReason,
          notes: catchupNotes,
        }, { headers });
        setCatchupMessage({ type: 'success', text: 'Korrekturanfrage eingereicht — wird geprüft.' });
        loadMyCatchups();
        setTimeout(() => { resetCatchupForm(); }, 2000);
      } catch (e) {
        setCatchupMessage({ type: 'error', text: e.response?.data?.detail || 'Fehler bei Korrektur' });
      }
      setCatchupLoading(false);
      return;
    }

    // === Nachtrag-Modus (bestehend) ===
    if (!catchupDate) { setCatchupMessage({ type: 'error', text: 'Datum ist ein Pflichtfeld' }); return; }
    if (!catchupReason) { setCatchupMessage({ type: 'error', text: 'Bitte wähle einen Grund' }); return; }
    if (catchupType === 'gehen_vergessen' && !catchupTimeEnd) {
      setCatchupMessage({ type: 'error', text: 'Gehen-Uhrzeit fehlt' }); return;
    }
    if (catchupType === 'kommen_vergessen' && !catchupTimeStart) {
      setCatchupMessage({ type: 'error', text: 'Kommen-Uhrzeit fehlt' }); return;
    }
    if (catchupType === 'beides_vergessen' && (!catchupTimeStart || !catchupTimeEnd)) {
      setCatchupMessage({ type: 'error', text: 'Kommen- und Gehen-Uhrzeit sind Pflichtfelder' }); return;
    }
    setCatchupLoading(true);
    setCatchupMessage(null);
    try {
      const payload = {
        object_id: currentObjectId || selectedObject,
        catch_up_type: catchupType,
        date: catchupDate,
        notes: catchupNotes,
        reason: catchupReason,
      };
      if (catchupType === 'gehen_vergessen') {
        payload.time = catchupTimeEnd;
      } else if (catchupType === 'kommen_vergessen') {
        payload.time = catchupTimeStart;
      } else {
        payload.time = catchupTimeStart;
        payload.time_end = catchupTimeEnd;
      }
      await axios.post(`${API_URL}/time-entries/catch-up`, payload, { headers });
      setCatchupMessage({ type: 'success', text: 'Nachtrag eingereicht — wird geprüft.' });
      loadMyCatchups();
      setTimeout(() => { resetCatchupForm(); checkStatus(); if (onStatusChange) onStatusChange(); }, 2000);
    } catch (e) {
      setCatchupMessage({ type: 'error', text: e.response?.data?.detail || 'Fehler beim Nachtrag' });
    }
    setCatchupLoading(false);
  };

  // ==================== Render ====================

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center' }}>
        <div className="animate-spin" style={{ display: 'inline-block', width: 24, height: 24, border: '3px solid #ccc', borderTop: '3px solid #f97316', borderRadius: '50%' }} />
      </div>
    );
  }

  if (cObjects.length === 0) return null;

  const currentObjectName = cObjects.find(o => o.id === (currentObjectId || selectedObject))?.name || '';

  // ==================== Ein-Knopf-Ablauf: Zustand je Schicht ====================
  // 1) vor Beginn-10: grau "Kommen ab HH:MM"  2) ab Beginn-10: nur KOMMEN  3) eingestempelt: Zaehler + nur GEHEN
  // 4) nach Gehen: "Schicht erledigt" ohne Knopf bis zur naechsten Schicht. Ohne Dienstplan: KOMMEN/GEHEN wie bisher,
  // aber nie beide gleichzeitig. Schicht vorbei ohne Kommen: "Zeit nachtragen" (ein KOMMEN wuerde 0 Std. zaehlen).
  void nowTick; void heuteVersion; // Re-Render-Trigger
  const jetzt = new Date();
  const MIN = 60000;
  const amTag = (hm) => { const [h, m] = String(hm).split(':').map(Number); const d = new Date(); d.setHours(h, m, 0, 0); return d; };
  const hm = (d) => d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  const stdText = (min) => `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, '0')} Std.`;
  const objName = (id) => cObjects.find(o => o.id === id)?.name || '';

  const schichten = (shiftsToday || [])
    .filter(s => s.start_time && s.end_time && s.has_c_assignment !== false
      && ['normal', 'vertretung'].includes(s.schedule_status || 'normal'))
    .map(s => {
      const von = amTag(s.start_time); let bis = amTag(s.end_time);
      if (bis <= von) bis = new Date(bis.getTime() + 24 * 60 * MIN); // ueber Mitternacht
      return { ...s, von, bis, ab: new Date(von.getTime() - KOMMEN_TOLERANZ_MIN * MIN) };
    })
    .sort((x, y) => x.von - y.von);

  // Heute erledigt: Server-Eintraege + was das Handy kennt (auch noch nicht uebertragen)
  const serverHeute = (todayEntries || []).map(e => ({ kommen: amTag(e.check_in), gehen: amTag(e.check_out), wartet: false,
    objectId: e.object_id, std: e.billed_hours }));
  const erledigt = [
    ...getHeute().map(e => {
      const k = new Date(e.kommen);
      const srv = serverHeute.find(x => hm(x.kommen) === hm(k));
      return { kommen: k, gehen: new Date(e.gehen), wartet: srv ? false : e.wartet, objectId: e.object_id, std: srv ? srv.std : null };
    }),
    ...serverHeute.filter(x => !getHeute().some(e => hm(new Date(e.kommen)) === hm(x.kommen))),
  ].sort((x, y) => x.gehen - y.gehen);
  const zuSchicht = (s) => [...erledigt].reverse().find(e => e.kommen < s.bis && e.gehen > new Date(s.von.getTime() - KOMMEN_TOLERANZ_MIN * MIN));

  let zustand = 'ohne_plan', schicht = null, fertig = null;
  if (schichten.length > 0) {
    const offen = schichten.filter(s => !zuSchicht(s));
    const aktiv = offen.find(s => jetzt >= s.ab && jetzt < s.bis);
    const verpasst = offen.filter(s => jetzt >= s.bis).pop();
    const kommend = offen.find(s => jetzt < s.ab);
    const zuletztErledigt = schichten.filter(s => zuSchicht(s)).pop();
    if (aktiv) { zustand = 'kommen'; schicht = aktiv; }
    else if (verpasst && (!zuletztErledigt || verpasst.bis > zuletztErledigt.bis)) { zustand = 'verpasst'; schicht = verpasst; }
    else if (zuletztErledigt) { zustand = 'erledigt'; schicht = zuletztErledigt; fertig = zuSchicht(zuletztErledigt); }
    else if (kommend) { zustand = 'warten'; schicht = kommend; }
  } else if (erledigt.length > 0) {
    fertig = erledigt[erledigt.length - 1];
  }
  // Eingestempelt: zugehoerige Schicht fuer Objekt + Schichtzeit oben
  const arbeitsSchicht = isWorking && checkInTime
    ? schichten.find(s => checkInTime < s.bis && jetzt > new Date(s.von.getTime() - 60 * MIN)) || null : null;

  // Naechste Schicht (klein): spaeter heute oder an einem der naechsten Tage
  const heuteIso = new Date().toISOString().slice(0, 10);
  const naechsteSchicht = (() => {
    const spaeterHeute = schichten.find(s => s.von > jetzt && s !== schicht && !zuSchicht(s));
    if (spaeterHeute) return { tag: 'heute', s: spaeterHeute };
    const n = (naechste || []).filter(x => x.date > heuteIso && ['normal', 'vertretung'].includes(x.schedule_status || 'normal'))
      .sort((x, y) => (x.date + x.start_time).localeCompare(y.date + y.start_time))[0];
    if (!n) return null;
    const d = new Date(n.date + 'T00:00:00');
    const morgen = new Date(); morgen.setDate(morgen.getDate() + 1);
    const tag = d.toDateString() === morgen.toDateString() ? 'morgen'
      : d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' });
    return { tag, s: { start_time: n.start_time, end_time: n.end_time, object_name: n.object_name } };
  })();

  // Objekt-Logo bzw. farbiges Kuerzel gross im Schicht-Kopf (immer mit Objektname; kommt mit der Objektliste
  // und ist damit auch ohne Netz da)
  const markeGross = (objId) => {
    const mk = cObjects.find(o => o.id === objId)?.marke;
    if (!mk) return null;
    return mk.logo
      ? <img data-ek-marke="logo" src={mk.logo} alt="" style={{ width: 64, height: 64, objectFit: 'contain', borderRadius: 12, background: '#fff', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.15)', flex: 'none' }} />
      : <span data-ek-marke="kuerzel" aria-hidden="true" style={{ width: 64, height: 64, borderRadius: 12, background: mk.farbe, color: mk.text, flex: 'none',
          display: 'grid', placeItems: 'center', fontSize: 26, fontWeight: 800, fontFamily: MARKE.titel, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.25)' }}>{mk.kuerzel}</span>;
  };
  const kopf = (objId, name, zeit) => {
    const mk = markeGross(objId);
    return (
      <div style={{ ...EK.kopf, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, textAlign: mk ? 'left' : 'center' }}>
        {mk}
        <div style={{ minWidth: 0 }}>
          <div style={EK.objekt}>{name}</div>
          {zeit && <div style={EK.schichtzeit}>{zeit}</div>}
        </div>
      </div>
    );
  };

  // Gezaehlte Zeit fuer "Schicht erledigt": innerhalb der Schicht; Stunden vom Server, sonst geschaetzt
  const gezaehlt = (e, s) => {
    const von = s && e.kommen < s.von ? s.von : e.kommen;
    const bis = s && e.gehen > s.bis ? s.bis : e.gehen;
    const min = e.std != null ? e.std * 60 : Math.ceil(Math.max(0, (bis - von) / MIN) / 5) * 5;
    return { von, bis, min };
  };

  // ==================== Stempel-Status (direkt unter dem Knopf) ====================
  // Farbenblind-sicher: Symbol (Haken/Sanduhr, als Icon - Emojis fehlen auf manchen Geraeten) + Text + Rahmenart
  // (durchgezogen = am Server, gestrichelt = wartet)
  const ausstehend = pendingSync > 0 ? getQueue().filter(i => isOwnItem(i) && i.status !== 'synced') : [];
  const keinNetz = !isOnline || erreichbar === false;
  const stempelStatus = ausstehend.length > 0 ? (
    <div data-stempel-status="wartet" role="status" style={{ ...EK.status, ...EK.wartet }}>
      <div style={EK.statusZeile}>
        <Hourglass size={24} strokeWidth={2.5} style={{ flexShrink: 0 }} aria-label="⏳" />
        <span>{stempelText(ausstehend)} gespeichert – wird übertragen</span>
      </div>
      <div style={{ fontSize: '15px', marginTop: '4px', fontWeight: 600 }}>Gespeichert – wird gesendet, sobald Netz da ist</div>
      <div style={{ fontSize: '15px', marginTop: '6px' }}>
        Kein Problem – dein Stempel ist sicher gespeichert. Öffne die App später mit Internet, dann wird er übertragen.
      </div>
    </div>
  ) : letzterStempel ? (
    <div data-stempel-status="ok" role="status" style={{ ...EK.status, ...EK.ok }}>
      <div style={EK.statusZeile}>
        <CheckCircle size={24} strokeWidth={2.5} style={{ flexShrink: 0 }} aria-label="✓" />
        <span>{AKTION_NAME[letzterStempel.action]} {uhrzeit(letzterStempel.timestamp)} übertragen</span>
      </div>
      <div style={{ fontSize: '15px', marginTop: '4px', fontWeight: 600 }}>Übertragen – am Server angekommen</div>
    </div>
  ) : null;

  return (
    <div className="ek-marke" style={{ marginTop: '16px' }}>
      {/* Netz-Anzeige: Lidl-WLAN (gruen) vs. Mobilfunk (orange) */}
      {netStatus && netStatus.at_object != null && (
        netStatus.at_object ? (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            background: '#dcfce7', color: '#166534', border: '1px solid #86efac',
            borderRadius: '10px', padding: '8px 12px', marginBottom: '8px',
            fontSize: '13px', fontWeight: 600
          }}>
            <Wifi size={16} /> Lidl-WLAN
          </div>
        ) : (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: '8px',
            background: '#ffedd5', color: '#9a3412', border: '1px solid #fdba74',
            borderRadius: '10px', padding: '8px 12px', marginBottom: '8px',
            fontSize: '13px', fontWeight: 600
          }}>
            <WifiOff size={16} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>Kein Lidl-WLAN, Verbindung über Mobilfunk. Im Putzraum ins WLAN welcome@lidl wechseln und die Lidl-Seite im Browser bestätigen.</span>
          </div>
        )
      )}
      {toast && (
        <div data-toast role="status" style={{
          position: 'fixed', top: '12px', left: '50%', transform: 'translateX(-50%)', zIndex: 1000,
          background: '#f0fdf4', border: '3px solid #166534', color: '#14532d', borderRadius: '12px',
          padding: '10px 16px', fontSize: '16px', fontWeight: 'bold', boxShadow: '0 4px 14px rgba(0,0,0,0.2)',
          display: 'flex', alignItems: 'center', gap: '8px', maxWidth: '92vw'
        }}>
          <CheckCircle size={20} strokeWidth={2.5} aria-label="✓" /> {toast}
        </div>
      )}

      {/* Header */}
      <div className="ek-titel-schrift" style={{
        background: MARKE.navy,
        borderRadius: '12px 12px 0 0', padding: '10px 16px', color: 'white',
        fontWeight: 'bold', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Clock size={16} /> Stempeluhr
        </div>
        {/* Online/Offline Indikator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', opacity: 0.9 }}>
          {keinNetz ? <WifiOff size={14} /> : <Wifi size={14} />}
          {!isOnline ? 'Offline' : (erreichbar === false ? 'Kein Internet' : '')}
          {pendingSync > 0 && (
            <span style={{
              background: 'rgba(255,255,255,0.3)', borderRadius: '10px',
              padding: '1px 8px', fontSize: '11px'
            }}>
              {pendingSync} ausstehend
            </span>
          )}
        </div>
      </div>

      <div style={{
        background: 'white', border: `2px solid ${MARKE.navy}`, borderTop: 'none',
        borderRadius: '0 0 12px 12px', padding: '16px'
      }}>
        {/* Sync-Status Banner */}
        {syncMessage && (
          <div style={{
            background: pendingSync > 0 ? '#eff6ff' : '#f0fdf4',
            border: `1px solid ${pendingSync > 0 ? '#93c5fd' : '#86efac'}`,
            borderRadius: '8px', padding: '8px 12px', marginBottom: '10px',
            fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px',
            color: pendingSync > 0 ? '#1e3a8a' : '#166534'
          }}>
            {pendingSync > 0 ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
            {syncMessage}
          </div>
        )}

        {/* Overdue-Warnung: Schichtende überschritten */}
        {overdueWarning && isWorking && !isOpenCatchup && (
          <div className="animate-pulse" style={{
            background: '#dc2626', color: 'white', borderRadius: '8px',
            padding: '12px', marginBottom: '12px', fontSize: '13px',
            border: '2px solid #991b1b'
          }}>
            <div style={{ fontWeight: 'bold', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertCircle size={16} /> Schichtende ueberschritten
            </div>
            <div>
              Deine Schicht endete um {scheduledEndTime} Uhr — bitte stempel dich aus oder melde dich beim Vorgesetzten.
            </div>
          </div>
        )}

        {error && (
          <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '8px', padding: '10px', marginBottom: '12px', fontSize: '13px', color: '#dc2626' }}>
            <AlertCircle size={14} style={{ display: 'inline', marginRight: 4 }} /> {error}
          </div>
        )}

        <style>{`
          @keyframes ek-pop { 0% { transform: scale(.3); opacity: 0 } 60% { transform: scale(1.15); opacity: 1 } 100% { transform: scale(1) } }
          .ek-pop { animation: ek-pop .45s ease-out both }
          .ek-knopf:active { transform: scale(.98) }
        `}</style>

        {/* ===== Gestern nicht ausgestempelt (offener Eintrag von gestern) ===== */}
        {isOpenCatchup && (
          <div data-ek-zustand="offen_gestern" style={{ ...EK.karte, border: '3px solid #b45309', background: '#fffbeb', color: '#78350f' }}>
            <div style={EK.titel}><AlertCircle size={28} aria-hidden="true" /> Gehen fehlt noch</div>
            <div style={EK.zeile}>
              Du bist seit {checkInTime?.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit' })},{' '}
              {checkInTime && hm(checkInTime)} Uhr eingestempelt{currentObjectName ? ` (${currentObjectName})` : ''}.
            </div>
            <div style={EK.klein}>Bitte trag ein, wann du gegangen bist.</div>
            <button className="ek-knopf" onClick={() => { setShowCatchup(true); setCatchupType('gehen_vergessen'); }}
              style={{ ...EK.knopf, background: '#b45309', minHeight: '120px', fontSize: '26px' }}>
              <Clock size={34} aria-hidden="true" /> Gehen-Zeit eintragen
            </button>
          </div>
        )}

        {/* ===== Zustand 3: eingestempelt - Zaehler + nur GEHEN ===== */}
        {isWorking && !isOpenCatchup && (
          <div data-ek-zustand="gehen">
            {kopf(arbeitsSchicht ? arbeitsSchicht.object_id : (currentObjectId || selectedObject),
              arbeitsSchicht ? arbeitsSchicht.object_name : currentObjectName,
              arbeitsSchicht && `Schicht ${arbeitsSchicht.start_time}–${arbeitsSchicht.end_time}`)}
            {quittung && quittung.art !== 'gehen' ? (
              <div data-ek-quittung={quittung.art} role="status" style={{ ...EK.karte, ...(quittung.art === 'ok' ? EK.ok : EK.wartet), textAlign: 'center', minHeight: '300px', justifyContent: 'center' }}>
                <div className="ek-pop">
                  {quittung.art === 'ok' ? <CheckCircle size={110} strokeWidth={2.5} aria-label="✓" /> : <Hourglass size={110} strokeWidth={2.5} aria-label="⏳" />}
                </div>
                <div style={{ ...EK.titel, justifyContent: 'center' }}>{quittung.art === 'ok' ? '✓ Angekommen' : '⏳ Gespeichert'}</div>
                <div style={EK.zeile}>{quittung.text}</div>
              </div>
            ) : (
              <>
                <div style={{ textAlign: 'center', margin: '6px 0 14px' }}>
                  <div style={{ fontSize: '56px', fontWeight: 'bold', fontFamily: 'monospace', color: MARKE.navyDunkel, lineHeight: 1.1 }}>{timerDisplay}</div>
                  <div style={{ fontSize: '18px', color: '#374151', marginTop: '4px' }}>
                    Arbeitszeit läuft{checkInTime ? ` – seit ${hm(checkInTime)} Uhr` : ''}
                  </div>
                </div>
                {minDurationMsg && (
                  <div style={{ ...EK.karte, border: '3px solid #b45309', background: '#fffbeb', color: '#78350f', fontSize: '17px', fontWeight: 600 }}>
                    <Clock size={24} aria-hidden="true" /> {minDurationMsg}
                  </div>
                )}
                <button className="ek-knopf" onClick={handleCheckOut} disabled={actionLoading}
                  style={{ ...EK.knopf, ...EK.riesig, background: actionLoading ? '#9ca3af' : MARKE.navy }}>
                  <Square size={44} strokeWidth={3} aria-hidden="true" /> {actionLoading ? 'Wird übertragen…' : 'GEHEN'}
                </button>
                {stempelStatus}
              </>
            )}
          </div>
        )}

        {/* ===== Nicht eingestempelt ===== */}
        {!isWorking && !isOpenCatchup && (
          <div data-ek-zustand={zustand}>
            {schicht && (
              kopf(schicht.object_id, schicht.object_name, `Schicht ${schicht.start_time}–${schicht.end_time}`)
            )}

            {/* Zustand 4: Schicht erledigt (bzw. ohne Plan: erledigt) */}
            {(zustand === 'erledigt' || (zustand === 'ohne_plan' && fertig)) && fertig && (() => {
              const g = gezaehlt(fertig, zustand === 'erledigt' ? schicht : null);
              const wartet = fertig.wartet || ausstehend.some(i => i.action === 'check_out');
              return (
                <div data-stempel-status={wartet ? 'wartet' : 'ok'} role="status" style={{ ...EK.karte, ...(wartet ? EK.wartet : EK.ok) }}>
                  <div style={EK.titel}>
                    {wartet ? <Hourglass size={34} strokeWidth={2.5} aria-label="⏳" /> : <CheckCircle size={34} strokeWidth={2.5} aria-label="✓" />}
                    {wartet ? 'Gezählt – wird übertragen' : (zustand === 'erledigt' ? 'Schicht erledigt' : 'Erledigt')}
                  </div>
                  <div style={{ ...EK.zeile, fontSize: '26px' }}>{hm(g.von)}–{hm(g.bis)} · {stdText(g.min)}</div>
                  {wartet ? (
                    <>
                      <div style={EK.klein}>Gehen {hm(fertig.gehen)} gespeichert – wird übertragen</div>
                      <div style={EK.klein}>Kein Problem – dein Stempel ist sicher gespeichert. Öffne die App später mit Internet, dann wird er übertragen.</div>
                    </>
                  ) : (
                    <>
                      <div style={EK.klein}>Gehen {hm(fertig.gehen)} übertragen – am Server angekommen</div>
                      {zustand === 'erledigt' && <div style={{ ...EK.zeile, fontSize: '22px' }}>Schönen Feierabend!</div>}
                    </>
                  )}
                </div>
              );
            })()}

            {/* Zustand 1: vor Beginn-10 - grauer Knopf, kein Gehen */}
            {zustand === 'warten' && (
              <button className="ek-knopf" disabled
                style={{ ...EK.knopf, ...EK.riesig, background: '#e5e7eb', color: '#374151', border: '4px dashed #6b7280', cursor: 'not-allowed' }}>
                <Clock size={44} aria-hidden="true" /> Kommen ab {hm(schicht.ab)}
              </button>
            )}

            {/* Zustand 2: ab Beginn-10 - nur KOMMEN (ohne Plan: KOMMEN, ggf. Objekt waehlen) */}
            {(zustand === 'kommen' || zustand === 'ohne_plan') && !(quittung && quittung.art === 'gehen') && (
              <>
                {zustand === 'ohne_plan' && cObjects.length > 1 && (
                  <select value={selectedObject || ''} onChange={(e) => setSelectedObject(parseInt(e.target.value))}
                    aria-label="Objekt" style={{ width: '100%', padding: '14px', fontSize: '18px', border: '2px solid #9ca3af', borderRadius: '12px', marginBottom: '12px' }}>
                    {cObjects.map(obj => (<option key={obj.id} value={obj.id}>{obj.name}</option>))}
                  </select>
                )}
                {zustand === 'ohne_plan' && cObjects.length === 1 && !fertig && (
                  kopf(cObjects[0].id, cObjects[0].name)
                )}
                <button className="ek-knopf" onClick={() => handleCheckIn(zustand === 'kommen' ? schicht.object_id : selectedObject)} disabled={actionLoading}
                  style={{ ...EK.knopf, ...(fertig ? { minHeight: '140px', fontSize: '32px' } : EK.riesig), background: actionLoading ? '#9ca3af' : MARKE.gold, color: MARKE.navyDunkel }}>
                  <Play size={44} strokeWidth={3} aria-hidden="true" /> {actionLoading ? 'Wird übertragen…' : 'KOMMEN'}
                </button>
                {!fertig && stempelStatus /* nach Gehen ist die Erledigt-Karte der Status */}
              </>
            )}

            {/* Schicht vorbei, aber nicht gestempelt: ein Knopf "Zeit nachtragen" */}
            {zustand === 'verpasst' && (
              <div style={{ ...EK.karte, border: '3px solid #b45309', background: '#fffbeb', color: '#78350f' }}>
                <div style={EK.titel}><AlertCircle size={30} aria-hidden="true" /> Nicht gestempelt</div>
                <div style={EK.zeile}>Für diese Schicht ist kein Kommen da. Bitte trag deine Zeit nach.</div>
                <button className="ek-knopf" onClick={() => { setCatchupType('beides_vergessen'); setShowCatchup(true); }}
                  style={{ ...EK.knopf, background: '#b45309', minHeight: '120px', fontSize: '26px' }}>
                  <Clock size={34} aria-hidden="true" /> Zeit nachtragen
                </button>
              </div>
            )}

            {zustand === 'ohne_plan' && (
              <div style={{ ...EK.klein, textAlign: 'center', marginTop: '10px' }}>Heute keine Schicht im Dienstplan.</div>
            )}

            {naechsteSchicht && (
              <div data-ek-naechste style={{ ...EK.klein, textAlign: 'center', marginTop: '14px' }}>
                Nächste Schicht: {naechsteSchicht.tag}, {naechsteSchicht.s.start_time}–{naechsteSchicht.s.end_time}
                {naechsteSchicht.s.object_name ? `, ${naechsteSchicht.s.object_name}` : ''}
              </div>
            )}
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: '16px' }}>
          <button onClick={() => setShowCatchup(true)}
            style={{ background: 'none', border: 'none', color: '#6b7280', fontSize: '14px', cursor: 'pointer', textDecoration: 'underline', padding: '8px' }}>
            Zeit nachtragen / Meine Zeit stimmt nicht
          </button>
        </div>
      </div>

      {/* ===== Meine Nachträge ===== */}
      {myCatchups.length > 0 && (
        <div style={{ marginTop: '16px', padding: '0 4px' }}>
          <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '8px' }}>Meine Nachträge</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {myCatchups.map(c => (
              <div key={c.id} style={{
                background: 'white', borderRadius: '10px', padding: '10px 12px',
                border: `1px solid ${c.status === 'genehmigt' ? '#86efac' : c.status === 'abgelehnt' ? '#fca5a5' : '#fde68a'}`,
                fontSize: '13px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontWeight: '500', color: '#1f2937' }}>
                    {c.date ? new Date(c.date + 'T00:00:00').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '-'}
                  </span>
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                    {c.catch_up_type === 'zeit_korrektur' && (
                      <span style={{ fontSize: '11px', fontWeight: '600', padding: '2px 8px', borderRadius: '9999px', background: '#dbeafe', color: '#1d4ed8' }}>
                        Korrektur
                      </span>
                    )}
                    <span style={{
                      fontSize: '11px', fontWeight: '600', padding: '2px 8px', borderRadius: '9999px',
                      background: c.status === 'genehmigt' ? '#dcfce7' : c.status === 'abgelehnt' ? '#fef2f2' : '#fefce8',
                      color: c.status === 'genehmigt' ? '#16a34a' : c.status === 'abgelehnt' ? '#dc2626' : '#ca8a04',
                    }}>
                      {c.status === 'genehmigt' ? '✅ Eingetragen' : c.status === 'abgelehnt' ? '❓ Rückfrage' : '⏳ Offen'}
                    </span>
                  </div>
                </div>
                <div style={{ color: '#6b7280', fontSize: '12px' }}>
                  {c.object_name} {c.start_time && c.end_time ? `• ${c.start_time}–${c.end_time}` : ''}
                  {c.reason && <span style={{ marginLeft: '6px', color: '#9ca3af' }}>({c.reason === 'technisch' ? 'Technisch' : c.reason === 'vergessen' ? 'Vergessen' : 'Sonstiges'})</span>}
                </div>
                {c.status === 'abgelehnt' && c.admin_notes && (
                  <div style={{ marginTop: '4px', fontSize: '12px', color: '#b45309', fontStyle: 'italic' }}>
                    Rückfrage: {c.admin_notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ===== Quick-Gehen Mini-Modal ===== */}
      {showQuickGehen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px'
        }}>
          <div style={{
            background: 'white', borderRadius: '16px', width: '100%', maxWidth: '360px',
            padding: '24px', position: 'relative'
          }}>
            <button onClick={() => { setShowQuickGehen(false); setQuickGehenMessage(null); }} style={{
              position: 'absolute', top: '12px', right: '12px', background: 'none',
              border: 'none', cursor: 'pointer', color: '#9ca3af'
            }}><CloseIcon size={20} /></button>

            <div style={{ textAlign: 'center', marginBottom: '16px' }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: '48px', height: '48px', borderRadius: '50%',
                background: '#fef2f2', marginBottom: '8px'
              }}>
                <Square size={24} color="#dc2626" />
              </div>
              <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f' }}>
                Gehen stempeln
              </h3>
              <p style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
                Kommen vergessen? Trage deine Kommen-Zeit ein.
              </p>
            </div>

            {quickGehenMessage && (
              <div style={{
                padding: '10px', borderRadius: '8px', marginBottom: '12px', fontSize: '13px',
                background: quickGehenMessage.type === 'error' ? '#fef2f2' : '#f0fdf4',
                color: quickGehenMessage.type === 'error' ? '#dc2626' : '#16a34a',
                border: `1px solid ${quickGehenMessage.type === 'error' ? '#fca5a5' : '#86efac'}`
              }}>
                {quickGehenMessage.text}
              </div>
            )}

            <div style={{
              background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '8px',
              padding: '10px', marginBottom: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span style={{ fontSize: '13px', color: '#166534' }}>Gehen-Zeit (jetzt):</span>
              <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#166534' }}>{quickGehenTime} Uhr</span>
            </div>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '14px', fontWeight: '600', display: 'block', marginBottom: '6px', color: '#374151' }}>
                Wann bist du gekommen?
              </label>
              <input
                type="time"
                value={quickGehenKommenZeit}
                onChange={e => setQuickGehenKommenZeit(e.target.value)}
                autoFocus
                style={{
                  width: '100%', padding: '12px', border: '2px solid #e5e7eb',
                  borderRadius: '8px', fontSize: '18px', textAlign: 'center'
                }}
              />
            </div>

            <div style={{
              background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px',
              padding: '8px 10px', marginBottom: '14px', fontSize: '12px', color: '#92400e'
            }}>
              Gehen-Zeit wird exakt erfasst. Die Kommen-Zeit geht zur Genehmigung an den Admin.
            </div>

            <button
              onClick={handleQuickGehen}
              disabled={quickGehenLoading}
              style={{
                width: '100%', padding: '14px', background: '#dc2626', color: 'white',
                fontSize: '16px', fontWeight: 'bold', borderRadius: '12px', border: 'none',
                cursor: quickGehenLoading ? 'wait' : 'pointer', opacity: quickGehenLoading ? 0.7 : 1
              }}
            >
              {quickGehenLoading ? 'Wird gesendet...' : 'Gehen & Nachtrag senden'}
            </button>
          </div>
        </div>
      )}

      {/* ===== Nachtrag-Modal ===== */}
      {showCatchup && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px'
        }}>
          <div style={{
            background: 'white', borderRadius: '16px', width: '100%', maxWidth: '400px',
            padding: '24px', position: 'relative', maxHeight: '90vh', overflowY: 'auto'
          }}>
            <button onClick={resetCatchupForm} style={{
              position: 'absolute', top: '12px', right: '12px', background: 'none',
              border: 'none', cursor: 'pointer', color: '#9ca3af'
            }}><CloseIcon size={20} /></button>

            <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '16px' }}>
              {correctionMode ? 'Zeit korrigieren' : 'Zeit nachtragen'}
            </h3>

            {/* Modus-Wahl */}
            <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
              <button
                onClick={() => { setCorrectionMode(false); setSelectedEntryId(null); }}
                style={{
                  flex: 1, padding: '10px 4px', borderRadius: '8px', fontSize: '13px', fontWeight: 'bold',
                  cursor: 'pointer', transition: 'all 0.15s',
                  background: !correctionMode ? '#f97316' : '#f3f4f6',
                  color: !correctionMode ? 'white' : '#6b7280',
                  border: !correctionMode ? '2px solid #ea580c' : '2px solid #e5e7eb',
                }}
              >
                Ich habe nicht gestempelt
              </button>
              <button
                onClick={() => { setCorrectionMode(true); loadCorrectionEntries(); }}
                style={{
                  flex: 1, padding: '10px 4px', borderRadius: '8px', fontSize: '13px', fontWeight: 'bold',
                  cursor: 'pointer', transition: 'all 0.15s',
                  background: correctionMode ? '#2563eb' : '#f3f4f6',
                  color: correctionMode ? 'white' : '#6b7280',
                  border: correctionMode ? '2px solid #1d4ed8' : '2px solid #e5e7eb',
                }}
              >
                Meine Zeit stimmt nicht
              </button>
            </div>

            {catchupMessage && (
              <div style={{
                padding: '10px', borderRadius: '8px', marginBottom: '12px', fontSize: '13px',
                background: catchupMessage.type === 'error' ? '#fef2f2' : '#f0fdf4',
                color: catchupMessage.type === 'error' ? '#dc2626' : '#16a34a',
                border: `1px solid ${catchupMessage.type === 'error' ? '#fca5a5' : '#86efac'}`
              }}>
                {catchupMessage.text}
              </div>
            )}

            {/* ===== KORREKTUR-FLOW ===== */}
            {correctionMode && (
              <>
                {/* Buchungsliste */}
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '600', display: 'block', marginBottom: '6px', color: '#374151' }}>Welche Buchung korrigieren?</label>
                  {correctionEntriesLoading ? (
                    <div style={{ textAlign: 'center', padding: '16px', color: '#9ca3af', fontSize: '13px' }}>Lade Buchungen...</div>
                  ) : correctionEntries.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '16px', color: '#9ca3af', fontSize: '13px' }}>Keine Buchungen zum Korrigieren vorhanden</div>
                  ) : (
                    <div style={{ maxHeight: '200px', overflowY: 'auto', border: '2px solid #e5e7eb', borderRadius: '8px' }}>
                      {correctionEntries.map(e => (
                        <div
                          key={e.id}
                          onClick={() => !e.has_pending_correction && setSelectedEntryId(e.id)}
                          style={{
                            padding: '10px 12px', borderBottom: '1px solid #f3f4f6',
                            cursor: e.has_pending_correction ? 'not-allowed' : 'pointer',
                            background: selectedEntryId === e.id ? '#eff6ff' : e.has_pending_correction ? '#f9fafb' : 'white',
                            border: selectedEntryId === e.id ? '2px solid #2563eb' : 'none',
                            borderRadius: selectedEntryId === e.id ? '6px' : '0',
                            opacity: e.has_pending_correction ? 0.5 : 1,
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: '500', fontSize: '13px' }}>
                              {new Date(e.date + 'T00:00:00').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}
                            </span>
                            <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#2563eb' }}>
                              {e.start_time}–{e.end_time}
                            </span>
                          </div>
                          <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                            {e.object_name}
                            {e.billed_hours && <span style={{ marginLeft: '8px' }}>{e.billed_hours}h</span>}
                            {e.has_pending_correction && (
                              <span style={{ marginLeft: '8px', color: '#f59e0b', fontWeight: '600' }}>Korrektur offen</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Was korrigieren? */}
                {selectedEntryId && (
                  <>
                    <div style={{ marginBottom: '12px' }}>
                      <label style={{ fontSize: '13px', fontWeight: '600', display: 'block', marginBottom: '6px', color: '#374151' }}>Was stimmt nicht?</label>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        {[
                          { value: 'kommen', label: 'Kommen' },
                          { value: 'gehen', label: 'Gehen' },
                          { value: 'beides', label: 'Beides' },
                        ].map(opt => (
                          <button
                            key={opt.value}
                            onClick={() => setCorrectionField(opt.value)}
                            style={{
                              flex: 1, padding: '10px 4px', borderRadius: '8px', fontSize: '13px', fontWeight: 'bold',
                              cursor: 'pointer', transition: 'all 0.15s',
                              background: correctionField === opt.value ? '#2563eb' : '#f3f4f6',
                              color: correctionField === opt.value ? 'white' : '#6b7280',
                              border: correctionField === opt.value ? '2px solid #1d4ed8' : '2px solid #e5e7eb',
                            }}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Kommen-Uhrzeit */}
                    {(correctionField === 'kommen' || correctionField === 'beides') && (
                      <div style={{ marginBottom: '12px' }}>
                        <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Richtige Kommen-Uhrzeit</label>
                        <input
                          type="time"
                          value={catchupTimeStart}
                          onChange={e => setCatchupTimeStart(e.target.value)}
                          style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                        />
                      </div>
                    )}

                    {/* Gehen-Uhrzeit */}
                    {(correctionField === 'gehen' || correctionField === 'beides') && (
                      <div style={{ marginBottom: '12px' }}>
                        <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Richtige Gehen-Uhrzeit</label>
                        <input
                          type="time"
                          value={catchupTimeEnd}
                          onChange={e => setCatchupTimeEnd(e.target.value)}
                          style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                        />
                      </div>
                    )}

                    {/* Grund */}
                    <div style={{ marginBottom: '12px' }}>
                      <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Grund *</label>
                      <select
                        value={catchupReason}
                        onChange={e => setCatchupReason(e.target.value)}
                        style={{ width: '100%', padding: '10px', border: `2px solid ${!catchupReason && catchupMessage?.type === 'error' ? '#fca5a5' : '#e5e7eb'}`, borderRadius: '8px', fontSize: '14px', background: 'white' }}
                      >
                        <option value="">Grund wählen...</option>
                        <option value="technisch">Stempeln ging technisch nicht</option>
                        <option value="vergessen">Vergessen</option>
                        <option value="sonstiges">Sonstiges</option>
                      </select>
                    </div>

                    {/* Hinweis */}
                    <div style={{ marginBottom: '14px' }}>
                      <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Hinweis (optional)</label>
                      <input
                        type="text"
                        value={catchupNotes}
                        onChange={e => setCatchupNotes(e.target.value)}
                        placeholder="z.B. Uhrzeit falsch abgelesen"
                        style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                      />
                    </div>
                  </>
                )}

                <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '10px', marginBottom: '14px', fontSize: '12px', color: '#1e40af' }}>
                  Korrekturanfragen gehen zur Prüfung an die Verwaltung. Die bestehende Buchung wird nach Genehmigung aktualisiert.
                </div>

                <button
                  onClick={handleCatchup}
                  disabled={catchupLoading || !selectedEntryId}
                  style={{
                    width: '100%', padding: '14px', background: !selectedEntryId ? '#93c5fd' : '#2563eb', color: 'white',
                    fontSize: '16px', fontWeight: 'bold', borderRadius: '12px', border: 'none',
                    cursor: catchupLoading || !selectedEntryId ? 'not-allowed' : 'pointer', opacity: catchupLoading ? 0.7 : 1
                  }}
                >
                  {catchupLoading ? 'Wird gesendet...' : 'Korrektur einreichen'}
                </button>
              </>
            )}

            {/* ===== NACHTRAG-FLOW (bestehend) ===== */}
            {!correctionMode && (
              <>
                {/* Typ-Auswahl */}
                <div style={{ marginBottom: '14px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '600', display: 'block', marginBottom: '6px', color: '#374151' }}>Was hast du vergessen?</label>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {[
                      { value: 'kommen_vergessen', label: 'Kommen' },
                      { value: 'gehen_vergessen', label: 'Gehen' },
                      { value: 'beides_vergessen', label: 'Beides' },
                    ].map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => setCatchupType(opt.value)}
                        style={{
                          flex: 1, padding: '10px 4px', borderRadius: '8px', fontSize: '13px', fontWeight: 'bold',
                          cursor: 'pointer', transition: 'all 0.15s',
                          background: catchupType === opt.value ? '#f97316' : '#f3f4f6',
                          color: catchupType === opt.value ? 'white' : '#6b7280',
                          border: catchupType === opt.value ? '2px solid #ea580c' : '2px solid #e5e7eb',
                        }}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Objekt (wenn nicht eingestempelt) */}
                {!currentObjectId && (
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Objekt</label>
                    <select
                      value={selectedObject || ''}
                      onChange={e => setSelectedObject(parseInt(e.target.value))}
                      style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                    >
                      {cObjects.map(obj => (
                        <option key={obj.id} value={obj.id}>{obj.name}</option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Datum */}
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Datum</label>
                  <input
                    type="date"
                    value={catchupDate}
                    onChange={e => setCatchupDate(e.target.value)}
                    max={new Date().toISOString().split('T')[0]}
                    style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                  />
                </div>

                {/* Kommen-Uhrzeit (bei kommen_vergessen und beides_vergessen) */}
                {(catchupType === 'kommen_vergessen' || catchupType === 'beides_vergessen') && (
                  <div style={{ marginBottom: '12px' }}>
                    <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>
                      Kommen-Uhrzeit
                    </label>
                    <input
                      type="time"
                      value={catchupTimeStart}
                      onChange={e => setCatchupTimeStart(e.target.value)}
                      style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                    />
                  </div>
                )}

                {/* Gehen-Uhrzeit (nur bei gehen_vergessen und beides_vergessen) */}
                {(catchupType === 'gehen_vergessen' || catchupType === 'beides_vergessen') && (
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>
                    Gehen-Uhrzeit
                  </label>
                  <input
                    type="time"
                    value={catchupTimeEnd}
                    onChange={e => setCatchupTimeEnd(e.target.value)}
                    style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                  />
                </div>
                )}

                {/* Grund (Pflicht) */}
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Grund *</label>
                  <select
                    value={catchupReason}
                    onChange={e => setCatchupReason(e.target.value)}
                    required
                    style={{ width: '100%', padding: '10px', border: `2px solid ${!catchupReason && catchupMessage?.type === 'error' ? '#fca5a5' : '#e5e7eb'}`, borderRadius: '8px', fontSize: '14px', background: 'white' }}
                  >
                    <option value="">Grund wählen...</option>
                    <option value="technisch">Stempeln ging technisch nicht</option>
                    <option value="vergessen">Vergessen</option>
                    <option value="sonstiges">Sonstiges</option>
                  </select>
                </div>

                {/* Hinweis */}
                <div style={{ marginBottom: '14px' }}>
                  <label style={{ fontSize: '13px', fontWeight: '500', display: 'block', marginBottom: '4px' }}>Hinweis (optional)</label>
                  <input
                    type="text"
                    value={catchupNotes}
                    onChange={e => setCatchupNotes(e.target.value)}
                    placeholder="z.B. App hat nicht geladen"
                    style={{ width: '100%', padding: '10px', border: '2px solid #e5e7eb', borderRadius: '8px', fontSize: '14px' }}
                  />
                </div>

                <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '10px', marginBottom: '14px', fontSize: '12px', color: '#92400e' }}>
                  Nachträge werden exakt auf die Minute berechnet (kein Aufrunden) und gehen zur Prüfung an die Verwaltung.
                </div>

                <button
                  onClick={handleCatchup}
                  disabled={catchupLoading}
                  style={{
                    width: '100%', padding: '14px', background: '#f97316', color: 'white',
                    fontSize: '16px', fontWeight: 'bold', borderRadius: '12px', border: 'none',
                    cursor: catchupLoading ? 'wait' : 'pointer', opacity: catchupLoading ? 0.7 : 1
                  }}
                >
                  {catchupLoading ? 'Wird gesendet...' : 'Nachtrag senden'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Bie2Stempeluhr;
