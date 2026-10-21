import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { Play, Square, Pause, PlayCircle, Building, Clock, AlertCircle, X as CloseIcon, Wifi, WifiOff, Check, RefreshCw } from 'lucide-react';
import { API_URL } from '../config.js';

// ==================== Offline-Queue Utilities ====================

const QUEUE_KEY = 'bie2_offline_queue';
const STATE_KEY = 'bie2_offline_state';

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

function addToQueue(action, objectId) {
  const q = getQueue();
  const item = {
    id: generateId(),
    action,            // 'check_in' | 'check_out' | 'pause_start' | 'pause_end'
    object_id: objectId,
    timestamp: new Date().toISOString(),
    status: 'pending',  // pending | syncing | synced | failed
    retries: 0
  };
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
  return getQueue().filter(i => i.status !== 'synced').length;
}

// Offline-State: Optimistischer lokaler Zustand für sofortige UI-Updates
function getOfflineState() {
  try { return JSON.parse(localStorage.getItem(STATE_KEY) || 'null'); }
  catch { return null; }
}

function saveOfflineState(state) {
  if (state) localStorage.setItem(STATE_KEY, JSON.stringify(state));
  else localStorage.removeItem(STATE_KEY);
}

// ==================== Komponente ====================

const Bie2Stempeluhr = ({ token, onStatusChange, onLogout }) => {
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

  // Heute gebucht (NUR server-bestaetigte Eintraege)
  const [todayEntries, setTodayEntries] = useState([]);
  // Noch nicht uebertragene Stempel (lokale Daten, Queue pending)
  const [pendingEntries, setPendingEntries] = useState([]);

  // Offline-Status
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingSync, setPendingSync] = useState(getPendingCount());
  const [syncMessage, setSyncMessage] = useState(null);
  const syncingRef = useRef(false);

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
    const queue = getQueue().filter(i => i.status === 'pending' || i.status === 'failed');
    if (queue.length === 0) { setPendingSync(0); return; }

    syncingRef.current = true;
    setSyncMessage('Synchronisiere...');

    for (const item of queue) {
      try {
        const payload = { client_id: item.id, client_timestamp: item.timestamp };

        if (item.action === 'check_in') {
          payload.object_id = item.object_id;
          payload.notes = 'Bie2 Kommen';
          await axios.post(`${API_URL}/time-entries/check-in`, payload, { headers, timeout: 10000 });
        } else if (item.action === 'check_out') {
          await axios.post(`${API_URL}/time-entries/check-out`, payload, { headers, timeout: 10000 });
        } else if (item.action === 'pause_start') {
          await axios.post(`${API_URL}/breaks/start`, payload, { headers, timeout: 10000 });
        } else if (item.action === 'pause_end') {
          await axios.post(`${API_URL}/breaks/end`, payload, { headers, timeout: 10000 });
        }

        markSynced(item.id);
      } catch (e) {
        if (e.response && e.response.status === 401) {
          // Token abgelaufen → Queue NICHT löschen, User zum Re-Login auffordern
          syncingRef.current = false;
          setSyncMessage('Sitzung abgelaufen – bitte neu einloggen');
          if (onLogout) onLogout();
          return;
        } else if (e.response && e.response.status >= 400 && e.response.status < 500) {
          // Andere Client-Fehler (400, 404) = idempotent behandeln
          markSynced(item.id);
        } else {
          markFailed(item.id, e.message);
          break; // Bei Netzwerkfehler: restliche Queue nicht weiter versuchen
        }
      }
    }

    syncingRef.current = false;
    const remaining = getPendingCount();
    setPendingSync(remaining);

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

  // Sync bei App-Start und nach Login (token-Änderung)
  useEffect(() => {
    if (token && navigator.onLine && getPendingCount() > 0) {
      setTimeout(() => triggerSync(), 2000);
    }
  }, [token]);

  // Periodischer Sync-Versuch alle 30s
  useEffect(() => {
    const interval = setInterval(() => {
      if (navigator.onLine && getPendingCount() > 0) triggerSync();
    }, 30000);
    return () => clearInterval(interval);
  }, [triggerSync]);

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
    const clientId = generateId();
    const clientTimestamp = new Date().toISOString();

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

    if (!navigator.onLine) {
      // Offline: Lokales Feedback als PENDING (nicht bestaetigt)
      if (wasCheckout) {
        const entry = buildLocalEntry();
        if (entry) setPendingEntries(prev => [...prev, entry]);
      }
      applyOptimisticState(action, objectId);
      addToQueue(action, objectId);
      setPendingSync(getPendingCount());
      setSyncMessage('Offline gespeichert - wird gesendet sobald online');
      return true;
    }

    // Online: API-Aufruf
    try {
      const payload = { client_id: clientId, client_timestamp: clientTimestamp };

      if (action === 'check_in') {
        payload.object_id = parseInt(objectId);
        payload.notes = 'Bie2 Kommen';
        await axios.post(`${API_URL}/time-entries/check-in`, payload, { headers, timeout: 10000 });
      } else if (action === 'check_out') {
        await axios.post(`${API_URL}/time-entries/check-out`, payload, { headers, timeout: 10000 });
      } else if (action === 'pause_start') {
        await axios.post(`${API_URL}/breaks/start`, payload, { headers, timeout: 10000 });
      } else if (action === 'pause_end') {
        await axios.post(`${API_URL}/breaks/end`, payload, { headers, timeout: 10000 });
      }

      // Erfolg: State zuruecksetzen, Server-Status holen (liefert bestaetigte today_entries)
      if (wasCheckout) {
        setIsWorking(false);
        setCheckInTime(null);
        setIsPaused(false);
        setCurrentObjectId(null);
        setEntryId(null);
      }

      // Server-Status nachladen (liefert server-bestaetigte Eintraege)
      await checkStatus('after_' + action);

      if (onStatusChange) onStatusChange();
      return true;
    } catch (e) {
      if (!e.response) {
        // Netzwerkfehler/Timeout: Als PENDING anzeigen (nicht bestaetigt)
        if (wasCheckout) {
          const entry = buildLocalEntry();
          if (entry) setPendingEntries(prev => [...prev, entry]);
        }
        applyOptimisticState(action, objectId);
        const item = { id: clientId, action, object_id: objectId, timestamp: clientTimestamp, status: 'pending', retries: 0 };
        const q = getQueue(); q.push(item); saveQueue(q);
        setPendingSync(getPendingCount());
        setSyncMessage('Netzwerkfehler - offline gespeichert, wird erneut versucht');
        return true;
      }
      // Server-Fehler (4xx/5xx)
      await checkStatus();
      throw e;
    }
  };

  // ==================== Data Loading ====================

  const loadCObjects = async () => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/my-c-objects`, { headers });
      setCObjects(res.data || []);
      if (res.data && res.data.length > 0 && !selectedObject) {
        setSelectedObject(res.data[0].id);
      }
    } catch (e) {
      console.error('Fehler beim Laden der C-Objekte:', e);
    }
  };

  const checkStatus = async (context) => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/current`, { headers });
      const data = res.data;
      console.log('[checkStatus]', context || 'init', 'is_working:', data?.is_working, 'today_entries:', data?.today_entries?.length);
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
        saveOfflineState(null); // Server-State ist da, kein Offline-State nötig
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
      await checkStatus();
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

  const handleCheckIn = async () => {
    if (!selectedObject) { setError('Bitte Objekt auswählen'); return; }
    if (actionLoading || isWorking) return;
    setActionLoading(true);
    setError(null);
    try {
      await performAction('check_in', selectedObject);
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

  return (
    <div style={{ marginTop: '16px' }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #ea580c 0%, #f97316 100%)',
        borderRadius: '12px 12px 0 0', padding: '10px 16px', color: 'white',
        fontWeight: 'bold', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Clock size={16} /> Stempeluhr
        </div>
        {/* Online/Offline Indikator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', opacity: 0.9 }}>
          {isOnline ? <Wifi size={14} /> : <WifiOff size={14} />}
          {!isOnline && 'Offline'}
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
        background: 'white', border: '2px solid #f97316', borderTop: 'none',
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

        {/* Offline-Hinweis bei pending Stempeln */}
        {!isOnline && pendingSync > 0 && !syncMessage && (
          <div style={{
            background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '8px',
            padding: '8px 12px', marginBottom: '10px', fontSize: '13px', color: '#92400e',
            display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            <WifiOff size={14} />
            {pendingSync} Stempel offline gespeichert - wird gesendet sobald online
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

        {/* Offene Schicht - Zombie-Nachtrag */}
        {isOpenCatchup && (
          <div style={{ background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '8px', padding: '12px', marginBottom: '12px' }}>
            <div style={{ fontWeight: 'bold', color: '#92400e', marginBottom: '4px' }}>
              <AlertCircle size={14} style={{ display: 'inline', marginRight: 4 }} />
              Offene Schicht gefunden
            </div>
            <div style={{ fontSize: '13px', color: '#78350f' }}>
              Beginn: {checkInTime?.toLocaleString('de-DE')} - {currentObjectName}
            </div>
            <div style={{ fontSize: '13px', color: '#78350f', marginTop: '4px' }}>
              Bitte trage die fehlende Gehen-Zeit nach:
            </div>
            <button
              onClick={() => { setShowCatchup(true); setCatchupType('gehen_vergessen'); }}
              style={{
                marginTop: '8px', padding: '8px 16px', background: '#f59e0b', color: 'white',
                border: 'none', borderRadius: '8px', fontWeight: 'bold', fontSize: '13px', cursor: 'pointer'
              }}
            >
              Gehen-Zeit nachtragen
            </button>
          </div>
        )}

        {/* ===== NOCH NICHT UEBERTRAGEN (pending Stempel) ===== */}
        {!isWorking && pendingEntries.length > 0 && (
          <div style={{
            background: '#eff6ff', border: '3px solid #3b82f6', borderRadius: '12px',
            padding: '14px', marginBottom: '12px'
          }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#1e3a8a', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <WifiOff size={18} /> Noch nicht uebertragen
            </div>
            {pendingEntries.map((entry, i) => {
              const h = Math.floor(entry.duration_minutes / 60);
              const m = entry.duration_minutes % 60;
              const durationStr = h > 0
                ? (m > 0 ? `${h} Std ${m} Min` : `${h} Std`)
                : `${m} Min`;
              return (
                <div key={i} style={{
                  background: 'white', borderRadius: '8px', padding: '10px 12px',
                  marginBottom: '6px', border: '1px solid #bfdbfe'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', fontFamily: 'monospace' }}>
                      {entry.check_in} – {entry.check_out}
                    </span>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: '#2563eb' }}>
                      {durationStr}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                    {entry.object_name}
                  </div>
                </div>
              );
            })}
            <div style={{ fontSize: '12px', color: '#1e3a8a', fontWeight: '600', marginTop: '8px', lineHeight: '1.4' }}>
              Bitte App geoeffnet lassen oder spaeter nochmal oeffnen, sobald Internet da ist.
            </div>
          </div>
        )}

        {/* ===== HEUTE GEBUCHT (nur server-bestaetigte Eintraege) ===== */}
        {!isWorking && !isOpenCatchup && todayEntries.length > 0 && (
          <div style={{
            background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '12px',
            padding: '14px', marginBottom: '12px'
          }}>
            <div style={{ fontSize: '13px', fontWeight: '500', color: '#166534', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={16} /> Heute gebucht
            </div>
            {todayEntries.map((entry, i) => {
              const h = Math.floor(entry.duration_minutes / 60);
              const m = entry.duration_minutes % 60;
              const durationStr = h > 0
                ? (m > 0 ? `${h} Std ${m} Min` : `${h} Std`)
                : `${m} Min`;
              return (
                <div key={i} style={{
                  background: 'white', borderRadius: '8px', padding: '10px 12px',
                  marginBottom: i < todayEntries.length - 1 ? '6px' : 0,
                  border: '1px solid #dcfce7'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '18px', fontWeight: 'bold', color: '#1f2937', fontFamily: 'monospace' }}>
                      {entry.check_in} – {entry.check_out}
                    </span>
                    <span style={{ fontSize: '14px', fontWeight: '600', color: '#16a34a' }}>
                      {durationStr}
                    </span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                    {entry.object_name}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ===== KOMMEN/GEHEN-Zustand (nicht eingestempelt) ===== */}
        {!isWorking && !isOpenCatchup && (
          <>
            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '13px', color: '#666', display: 'block', marginBottom: '4px' }}>
                <Building size={14} style={{ display: 'inline', marginRight: 4 }} /> Objekt:
              </label>
              <select
                value={selectedObject || ''}
                onChange={(e) => setSelectedObject(parseInt(e.target.value))}
                style={{ width: '100%', padding: '10px', fontSize: '15px', border: '2px solid #e5e7eb', borderRadius: '8px' }}
              >
                {cObjects.map(obj => (
                  <option key={obj.id} value={obj.id}>{obj.name}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleCheckIn}
                disabled={actionLoading}
                style={{
                  flex: 1, padding: '16px',
                  background: actionLoading ? '#86efac' : '#16a34a',
                  color: 'white', fontSize: '18px', fontWeight: 'bold',
                  borderRadius: '12px', border: 'none',
                  cursor: actionLoading ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px'
                }}
              >
                <Play size={22} /> {actionLoading ? 'Wird übertragen...' : 'KOMMEN'}
              </button>

              <button
                onClick={() => {
                  if (todayEntries.length > 0) {
                    const times = todayEntries.map(e => `${e.check_in}–${e.check_out}`).join(', ');
                    setError(`Du hast heute bereits gebucht: ${times}. Falls etwas nicht stimmt, nutze "Meine Zeit stimmt nicht" (unten).`);
                    return;
                  }
                  const now = new Date();
                  const hh = now.getHours().toString().padStart(2, '0');
                  const mm = now.getMinutes().toString().padStart(2, '0');
                  setQuickGehenTime(`${hh}:${mm}`);
                  setQuickGehenKommenZeit('');
                  setQuickGehenMessage(null);
                  setShowQuickGehen(true);
                }}
                disabled={actionLoading}
                style={{
                  flex: 1, padding: '16px',
                  background: todayEntries.length > 0 ? '#9ca3af' : '#dc2626',
                  color: 'white', fontSize: '18px', fontWeight: 'bold',
                  borderRadius: '12px', border: 'none',
                  cursor: todayEntries.length > 0 ? 'not-allowed' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px'
                }}
              >
                <Square size={22} /> GEHEN
              </button>
            </div>

            <div style={{ textAlign: 'center', marginTop: '10px' }}>
              <button
                onClick={() => setShowCatchup(true)}
                style={{ background: 'none', border: 'none', color: '#9ca3af', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                Zeit nachtragen / Meine Zeit stimmt nicht
              </button>
            </div>
          </>
        )}

        {/* ===== GEHEN-Zustand (eingestempelt) ===== */}
        {isWorking && !isOpenCatchup && (
          <>
            <div style={{
              background: 'linear-gradient(135deg, #ea580c 0%, #f97316 100%)',
              borderRadius: '12px', padding: '16px', marginBottom: '12px', color: 'white', textAlign: 'center'
            }}>
              <div style={{ fontSize: '13px', marginBottom: '4px', opacity: 0.9 }}>
                {currentObjectName}
              </div>
              <div style={{ fontSize: '40px', fontWeight: 'bold', fontFamily: 'monospace' }}>
                {timerDisplay}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.8, marginTop: '4px' }}>
                {isPaused ? 'PAUSE AKTIV' : 'Arbeitszeit läuft'}
                {!isOnline && ' (Offline)'}
              </div>
            </div>

            {/* Mindestdauer-Warnung */}
            {minDurationMsg && (
              <div style={{
                background: '#fef3c7', border: '2px solid #f59e0b', borderRadius: '10px',
                padding: '12px 14px', marginBottom: '12px', fontSize: '14px', color: '#92400e',
                display: 'flex', alignItems: 'flex-start', gap: '10px', fontWeight: 500
              }}>
                <Clock size={20} style={{ flexShrink: 0, marginTop: 1 }} color="#f59e0b" />
                <span>{minDurationMsg}</span>
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={handleCheckOut}
                disabled={actionLoading}
                style={{
                  flex: 2, padding: '14px',
                  background: actionLoading ? '#fca5a5' : '#dc2626',
                  color: 'white', fontSize: '16px', fontWeight: 'bold',
                  borderRadius: '10px', border: 'none',
                  cursor: actionLoading ? 'wait' : 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
                }}
              >
                <Square size={20} /> {actionLoading ? 'Wird übertragen...' : 'GEHEN'}
              </button>
              {!isPaused ? (
                <button
                  onClick={handlePauseStart}
                  style={{
                    flex: 1, padding: '14px', background: '#6b7280', color: 'white',
                    borderRadius: '10px', border: 'none', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    fontSize: '14px', fontWeight: 'bold'
                  }}
                >
                  <Pause size={18} /> PAUSE
                </button>
              ) : (
                <button
                  onClick={handlePauseEnd}
                  style={{
                    flex: 1, padding: '14px', background: '#2563eb', color: 'white',
                    borderRadius: '10px', border: 'none', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    fontSize: '14px', fontWeight: 'bold'
                  }}
                >
                  <PlayCircle size={18} /> WEITER
                </button>
              )}
            </div>
          </>
        )}
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
