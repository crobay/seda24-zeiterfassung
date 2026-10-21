import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LogOut, Play, Square, Pause, Building, User, Clock, Calendar, Star, CheckCircle, AlertCircle, Gauge, Users, PlayCircle, ChevronsRight, Shield, UserCheck, Info, Home, History, Car, Menu, X as CloseIcon, Mail, Send, Lock, HelpCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_URL } from '../config.js';
import HistoryTab from "../components/HistoryTab";
import VacationTab from "../components/VacationTab";
import KilometerTab from "../components/KilometerTab";
import ShiftChangeForm from "../components/ShiftChangeForm";
import NachrichtenTab from "../components/NachrichtenTab";
import SelbstbuchungTab from "../components/SelbstbuchungTab";
import Bie2Stempeluhr from "../components/Bie2Stempeluhr";
import DienstplanTab from "../components/DienstplanTab";
import { getPendingNotifications } from '../services/pushService';

const Dashboard = () => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [activeTab, setActiveTab] = useState('stempeluhr');
  const [isWorking, setIsWorking] = useState(false);
  const [workStartTime, setWorkStartTime] = useState(null);
  const [todayHours, setTodayHours] = useState(0);
  const [colleagues, setColleagues] = useState([]);
  const [weekHours, setWeekHours] = useState(0);
  const [monthHours, setMonthHours] = useState(0);
  const [totalHours, setTotalHours] = useState(0);
  const [selectedObject, setSelectedObject] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [locationError, setLocationError] = useState(null);
  const [isLoadingLocation, setIsLoadingLocation] = useState(false);
  const [workingWithColleague, setWorkingWithColleague] = useState(false);
  const [selectedColleague, setSelectedColleague] = useState('');
  const [serviceType, setServiceType] = useState('Unterhaltsreinigung');
  const [buttonText, setButtonText] = useState('ICH WAR HEUTE ANWESEND');
  
  // NEU: Geplante Objekte aus Dienstplan
  const [scheduledObjects, setScheduledObjects] = useState([]);
  const [hasWorkToday, setHasWorkToday] = useState(false);
  const [infoMessage, setInfoMessage] = useState('');
  
  // Bottom Navigation - Mehr Overlay
  const [showMoreMenu, setShowMoreMenu] = useState(false);

  // Passwort ändern
  const [showPasswordChange, setShowPasswordChange] = useState(false);
  const [pwOld, setPwOld] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwError, setPwError] = useState('');
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwLoading, setPwLoading] = useState(false);

  // Offene Bestaetigungen
  const [pendingPushes, setPendingPushes] = useState([]);

  // Kat B V3.0: Schichten
  const [todayShifts, setTodayShifts] = useState([]);
  const [upcomingShifts, setUpcomingShifts] = useState([]);
  const [confirmingShiftId, setConfirmingShiftId] = useState(null);

  // Schicht-Modal (Tauschen/Absagen)
  const [selectedShift, setSelectedShift] = useState(null);
  const [showShiftModal, setShowShiftModal] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [showCancelReasons, setShowCancelReasons] = useState(false);
  const [sendingRequest, setSendingRequest] = useState(false);
  const [shiftRequestSent, setShiftRequestSent] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState('');
  // Schicht tauschen
  const [showSwapFlow, setShowSwapFlow] = useState(false);
  const [swapColleagues, setSwapColleagues] = useState([]);
  const [loadingColleagues, setLoadingColleagues] = useState(false);
  // Krank erweitert
  const [showSickDuration, setShowSickDuration] = useState(false);
  const [sickUntilDate, setSickUntilDate] = useState('');
  // Sonstiges
  const [showCustomReason, setShowCustomReason] = useState(false);
  const [customReasonText, setCustomReasonText] = useState('');

  // Cap-Decision Dialog (Obergrenze Dienstplan)
  const [showCapDialog, setShowCapDialog] = useState(false);
  const [capDialogData, setCapDialogData] = useState(null);
  const [capOvertimeReason, setCapOvertimeReason] = useState('');
  const [capSubmitting, setCapSubmitting] = useState(false);


  const getCurrentLocation = () => {
    return new Promise((resolve, reject) => {
      setIsLoadingLocation(true);
      setLocationError(null);
      
      if (!navigator.geolocation) {
        setLocationError('GPS nicht unterstützt');
        setIsLoadingLocation(false);
        reject('Geolocation not supported');
        return;
      }

      navigator.geolocation.getCurrentPosition(
        (position) => {
          const location = {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            accuracy: position.coords.accuracy
          };
          setUserLocation(location);
          setIsLoadingLocation(false);
          resolve(location);
        },
        (error) => {
          setLocationError('GPS-Position nicht verfügbar');
          setIsLoadingLocation(false);
          reject(error);
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 0
        }
      );
    });
  };
  // Kategorie des Mitarbeiters
  const [employeeCategory, setEmployeeCategory] = useState(null);
  const [employeeData, setEmployeeData] = useState(null);

  const validateLocation = async (objectId, isCheckOut = false) => {
    console.log("GPS-VALIDIERUNG STARTET FÜR OBJEKT:", objectId);
    
    const currentUserEmail = localStorage.getItem('userEmail') || '';

    const objectCoords = {
      1: { name: 'SEDA24 Zentrale', lat: 48.794968, lng: 8.310615 },
      3: { name: 'Lidl Muggensturmer Str', lat: 48.8888214774413, lng: 8.26481250682591 },
      4: { name: 'Lidl Wochenende', lat: 48.8888214774413, lng: 8.26481250682591 },
      5: { name: 'Enfido', lat: 48.9090646883034, lng: 8.26101850482367 },
      6: { name: 'Metalicone', lat: 48.8797133935092, lng: 8.28035636486564 }
    };

    try {
      const location = await getCurrentLocation();
      const target = objectCoords[objectId];
      
      if (!target) return true;

      const R = 6371000;
      const dLat = (location.lat - target.lat) * Math.PI / 180;
      const dLng = (location.lng - target.lng) * Math.PI / 180;
      const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                Math.cos(target.lat * Math.PI / 180) * Math.cos(location.lat * Math.PI / 180) *
                Math.sin(dLng/2) * Math.sin(dLng/2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
      const distance = R * c;
      
      if (distance <= 100) {
        const action = isCheckOut ? "Ausgestempelt" : "Eingestempelt";
        alert(`? GPS OK! ${Math.round(distance)}m Entfernung. ${action}!`);
        return true;
      } else {
        const action = isCheckOut ? "AUSSTEMPELN" : "EINSTEMPELN";
        const distText = distance > 1000 ? `${(distance/1000).toFixed(1)} km` : `${Math.round(distance)}m`;
        alert(`? ${action} NICHT MÖGLICH! Du bist ${distText} vom ${target.name} entfernt!`);
        return false;
      }
    } catch (error) {
      console.error("GPS-Fehler:", error);
      return false;
    }
  };
  const [loadingCategory, setLoadingCategory] = useState(true);
  const [hasCAssignments, setHasCAssignments] = useState(false);
  const [employeeTachoData, setEmployeeTachoData] = useState(null);
    
  const [isPaused, setIsPaused] = useState(false);
  const [pauseId, setPauseId] = useState(null);
  const [pauseStartTime, setPauseStartTime] = useState(null);
  const [totalPauseTime, setTotalPauseTime] = useState(0);

  const navigate = useNavigate();
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  const userRole = localStorage.getItem('userRole');
  const canAccessAdmin = userRole === 'admin' || userRole === 'objektleiter';

  const fallbackObjects = {};
  const objectMap = {};
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    fetchEmployeeCategory();
    //fetchColleagues();
    loadScheduledObjects();
    checkStatus();
    fetchTodayHours();
    fetchWeekHours();
    fetchMonthHours();
    fetchTachoData();
    loadPendingPushes();
    loadTodayShifts();
    loadUpcomingShifts();
    checkPendingCap();
  }, []);

  // Sync: Wenn App wieder sichtbar wird, Daten neu laden
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        loadTodayShifts();
        loadPendingPushes();
        loadUpcomingShifts();
        fetchTodayHours();
        fetchWeekHours();
        fetchMonthHours();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);

  // Push-Notifications laden
  const loadPendingPushes = async () => {
    try {
      const pushes = await getPendingNotifications();
      setPendingPushes(pushes || []);
    } catch (e) {
      console.log('Push-Laden fehlgeschlagen:', e);
    }
  };

  // Kat B: Heutige Schichten laden
  const loadTodayShifts = async () => {
    try {
      const response = await axios.get(`${API_URL}/time-entries/my-shifts-today`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTodayShifts(response.data || []);
    } catch (e) {
      console.log('Schichten-Laden fehlgeschlagen:', e);
    }
  };

  // Kat B: Zukuenftige Schichten laden
  const loadUpcomingShifts = async () => {
    try {
      const response = await axios.get(`${API_URL}/time-entries/my-upcoming-shifts`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setUpcomingShifts(response.data || []);
    } catch (e) {
      console.log('Upcoming-Schichten-Laden fehlgeschlagen:', e);
    }
  };

  // Kollegen am selben Objekt laden (fuer Schicht-Tausch)
  const loadShiftColleagues = async (objectId) => {
    setLoadingColleagues(true);
    try {
      const response = await axios.get(
        `${API_URL}/time-entries/shift-colleagues?object_id=${objectId}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setSwapColleagues(response.data || []);
    } catch (e) {
      console.log('Kollegen laden fehlgeschlagen:', e);
      setSwapColleagues([]);
    }
    setLoadingColleagues(false);
  };

  // Modal oeffnen mit Reset aller States
  const openShiftModal = (shift) => {
    setSelectedShift(shift);
    setShowShiftModal(true);
    setShowCancelReasons(false);
    setShowSwapFlow(false);
    setShowSickDuration(false);
    setShowCustomReason(false);
    setCancelReason('');
    setCustomReasonText('');
    setSickUntilDate('');
    setShiftRequestSent(false);
    setConfirmationMessage('');
    setSendingRequest(false);
  };

  // Kat B: Direkte Bestaetigung OHNE Modal (ein Klick!)
  const confirmShiftDirect = async (shift) => {
    setConfirmingShiftId(shift.schedule_id);
    try {
      if (shift.push_id) {
        // Push vorhanden -> ueber Push-API bestaetigen (erstellt TimeEntry + KM)
        await axios.post(
          `${API_URL}/push/respond/${shift.push_id}`,
          { response: 'confirmed' },
          { headers: { Authorization: `Bearer ${token}` }}
        );
      } else {
        // Kein Push -> direkt ueber war-anwesend buchen
        await axios.post(
          `${API_URL}/time-entries/war-anwesend`,
          { object_id: shift.object_id, schedule_id: shift.schedule_id },
          { headers: { Authorization: `Bearer ${token}` }}
        );
      }
      // Alles neu laden nach Bestaetigung
      await Promise.all([
        loadTodayShifts(),
        loadPendingPushes(),
        fetchTodayHours(),
        fetchWeekHours(),
        fetchMonthHours(),
      ]);
    } catch (error) {
      const msg = error.response?.data?.detail || error.response?.data?.message || error.message;
      if (msg && msg.includes('bereits')) {
        // Schon gebucht - einfach neu laden
        await loadTodayShifts();
        await loadPendingPushes();
      } else {
        alert('Fehler: ' + msg);
      }
    }
    setConfirmingShiftId(null);
  };

  const fetchEmployeeCategory = async () => {

  const fetchColleagues = async () => {
    try {
      const response = await api.get("/employees/my-colleagues-today", {
        headers: { Authorization: `Bearer ${token}` }
      });
      console.log("Kollegen geladen:", response.data);
      setColleagues(response.data || []);
    } catch (error) {
      console.error("Fehler beim Laden der Kollegen:", error);
      setColleagues([]);
    }
  };
    try {
      setLoadingCategory(true);
      const response = await axios.get(`${API_URL}/employees/my-category`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      setEmployeeCategory(response.data.tracking_mode || 'C');
      setEmployeeData(response.data);
      setHasCAssignments(response.data.has_c_assignments || false);
      console.log('Mitarbeiter-Kategorie:', response.data.tracking_mode);
      console.log("Kategorie von Backend:", response.data);
    } catch (error) {
      console.error('Fehler beim Abrufen der Kategorie:', error);
      setEmployeeCategory('C');
    } finally {
      setLoadingCategory(false);
    }
  };

  const loadScheduledObjects = async () => {
    try {
      const response = await axios.get(`${API_URL}/time-entries/my-objects-today`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.data && response.data.length > 0) {
        setScheduledObjects(response.data);
        if (!selectedObject && response.data.length > 0) {
          setSelectedObject(response.data[0].id);
        }
        setInfoMessage('');
      } else {
        const workCheck = await axios.get(`${API_URL}/time-entries/has-work-today`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        if (!workCheck.data.has_work) {
          setInfoMessage('Heute ist kein Arbeitstag laut Dienstplan');
        } else {
          setInfoMessage('Keine Objekte für heute geplant');
        }
        
        const fallbackList = Object.entries(fallbackObjects).map(([id, obj]) => ({
          id: parseInt(id),
          name: obj.name,
          address: '',
          planned_hours: 8
        }));
        setScheduledObjects(fallbackList);
        if (!selectedObject) {
          setSelectedObject(1);
        }
      }
    } catch (error) {
      console.error('Fehler beim Laden der geplanten Objekte:', error);
      const fallbackList = Object.entries(fallbackObjects).map(([id, obj]) => ({
        id: parseInt(id),
        name: obj.name,
        address: '',
        planned_hours: null
      }));
      setScheduledObjects(fallbackList);
      if (!selectedObject) {
        setSelectedObject(1);
      }
    }
  };

  const checkStatus = async () => {
    try {
      const response = await axios.get(`${API_URL}/time-entries/current`, { 
        headers: { Authorization: `Bearer ${token}` } 
      });
      
      if (response.data && response.data.is_working) {
        setIsWorking(true);
        const backendTime = new Date(response.data.check_in);
        const correctedTime = new Date(backendTime.getTime() + 2 * 60 * 60 * 1000);
        setWorkStartTime(correctedTime);
        setSelectedObject(response.data.object_id);
        setIsPaused(response.data.is_paused);
        if(response.data.is_paused && response.data.pause_start_time) {
          setPauseStartTime(new Date(response.data.pause_start_time));
        }
        setTotalPauseTime(response.data.total_pause_duration || 0);
      } else {
        setIsWorking(false);
      }
    } catch (error) {
      console.error('Status-Fehler:', error);
      setIsWorking(false);
    }
  };

  const fetchTodayHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/today`, { 
        headers: { Authorization: `Bearer ${token}` } 
      });
      setTodayHours(response.data.total_hours);
    } catch (error) { 
      console.error('Fehler:', error); 
    }
  };

  const fetchWeekHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/week`, { 
        headers: { Authorization: `Bearer ${token}` } 
      });
      setWeekHours(response.data.total_hours);
    } catch (error) { 
      console.error('Fehler:', error); 
    }
  };

  const fetchMonthHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/month`, { 
        headers: { Authorization: `Bearer ${token}` } 
      });
      setMonthHours(response.data.total_hours);
    } catch (error) { 
      console.error('Fehler:', error); 
    }
  };

  const fetchTachoData = async () => {
	  try {
		const response = await axios.get(`${API_URL}/reports/my/tacho`, { 
		  headers: { Authorization: `Bearer ${token}` } 
		});
		if (response.data) {
		  setEmployeeTachoData(response.data);
		}
	  } catch (error) { 
		console.error('Tacho nicht verfügbar'); 
	  }
	};

  const handleWarAnwesend = async () => {
  try {
    console.log('Sende Leistungsart:', serviceType);
    
    const response = await axios.post(
      `${API_URL}/time-entries/war-anwesend`,
      { 
        object_id: parseInt(selectedObject), 
        service_type: serviceType 
      },
      { headers: { Authorization: `Bearer ${token}` }}
    );
    
    console.log('Antwort vom Server:', response.data);
    
    setButtonText(`? ${response.data.scheduled_hours}h gebucht!`);
    setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 8000);
    
    fetchTodayHours();
    fetchWeekHours();
    fetchMonthHours();
  } catch (error) {
    if (error.response?.status === 400 && error.response?.data?.detail?.includes('bereits Stunden')) {
      setButtonText('? Bereits gebucht!');
      setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 8000);
    } else {
      console.error('Fehler:', error);
      setButtonText('? Fehler!');
      setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 8000);
    }
  }
};

  // Crash-Recovery: Prueft ob eine offene Cap-Entscheidung existiert
  const checkPendingCap = async () => {
    try {
      const res = await axios.get(`${API_URL}/time-entries/pending-cap`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data && res.data.pending) {
        setCapDialogData({
          entry_id: res.data.entry_id,
          excess_minutes: res.data.excess_minutes,
          planned_hours: res.data.planned_hours,
          schedule_str: res.data.schedule_str,
        });
        setCapOvertimeReason('');
        setShowCapDialog(true);
      }
    } catch (e) {
      console.log('Pending-Cap-Check fehlgeschlagen:', e);
    }
  };

  // Cap-Entscheidung absenden
  const handleCapDecision = async (choice) => {
    if (!capDialogData) return;
    if (choice === 'request_overtime' && capOvertimeReason.trim().length < 10) {
      alert('Bitte gib einen Grund an (mind. 10 Zeichen).');
      return;
    }
    setCapSubmitting(true);
    try {
      await axios.post(
        `${API_URL}/time-entries/${capDialogData.entry_id}/cap-decision`,
        { choice, reason: capOvertimeReason.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setShowCapDialog(false);
      setCapDialogData(null);
      setCapOvertimeReason('');
      fetchTodayHours();
      fetchWeekHours();
      fetchMonthHours();
    } catch (error) {
      alert('Fehler: ' + (error.response?.data?.detail || error.message));
    }
    setCapSubmitting(false);
  };

  const handleCheckIn = async () => {
    try {
      const isValid = await validateLocation(parseInt(selectedObject));
      if (!isValid) return;
      const notes = "Arbeitsbeginn";
      await axios.post(`${API_URL}/time-entries/check-in`, { 
        object_id: parseInt(selectedObject), 
        notes: notes 
      }, { 
        headers: { Authorization: `Bearer ${token}` }
      });
      checkStatus();
    } catch (error) { 
      alert('Fehler beim Einstempeln: ' + (error.response?.data?.message || error.message)); 
    }
  };

  const handleCheckOut = async () => {
    try {
      const res = await axios.post(`${API_URL}/time-entries/check-out`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      checkStatus();
      fetchTodayHours();
      fetchWeekHours();
      fetchMonthHours();
      if (res.data && res.data.cap_decision_needed) {
        // >10min: Interaktiver Dialog
        setCapDialogData({
          entry_id: res.data.id,
          excess_minutes: res.data.cap_excess_minutes,
          planned_hours: (res.data.cap_planned_h || 0) + (res.data.cap_planned_m || 0) / 60,
          schedule_str: res.data.cap_schedule_str,
          planned_h: res.data.cap_planned_h,
          planned_m: res.data.cap_planned_m,
        });
        setCapOvertimeReason('');
        setShowCapDialog(true);
      } else if (res.data && res.data.cap_message) {
        // <=10min: Automatisch gekappt, nur Hinweis
        alert(res.data.cap_message);
      }
    } catch (error) {
      alert('Fehler beim Ausstempeln: ' + (error.response?.data?.message || error.message));
    }
  };

  const handlePauseStart = async () => {
    try {
      await axios.post(`${API_URL}/breaks/start`, {}, { 
        headers: { Authorization: `Bearer ${token}` }
      });
      checkStatus();
    } catch (error) { 
      alert("Fehler beim Pause starten: " + (error.response?.data?.message || error.message)); 
    }
  };

  const handlePauseEnd = async () => {
    try {
      await axios.post(`${API_URL}/breaks/end`, {}, { 
        headers: { Authorization: `Bearer ${token}` }
      });
      checkStatus();
    } catch (error) { 
      alert("Fehler beim Pause beenden: " + (error.response?.data?.message || error.message)); 
    }
  };

  const calculateWorkTime = () => {
    if (!workStartTime) return '00:00:00';
    let totalSeconds = (new Date() - workStartTime) / 1000;
    totalSeconds -= totalPauseTime;
    if (isPaused && pauseStartTime) {
      const currentPauseDuration = (new Date() - pauseStartTime) / 1000;
      totalSeconds -= currentPauseDuration;
    }
    totalSeconds = Math.max(0, totalSeconds);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  const formatHours = (hours) => {
    if (!hours) return "0 Min";
    const h = Math.floor(hours);
    const m = Math.round((hours % 1) * 60);
    if (h === 0) return `${m} Min`;
    if (m === 0) return `${h} Std`;
    return `${h} Std ${m} Min`;
  };

  const formatTotalHours = (hours) => {
    if (!hours) return "0 Std";
    return Math.floor(hours).toLocaleString('de-DE') + ' Std';
  };
  
  const handleLogout = () => {
    localStorage.clear();
    sessionStorage.clear();
    navigate('/login');
  };

  const currentObject = scheduledObjects.find(obj => obj.id === selectedObject);

  // BOTTOM NAVIGATION KOMPONENTE
  const BottomNav = ({ categoryLabel }) => {
    return (
      <>
        {/* Bottom Navigation Bar */}
        <div style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          backgroundColor: 'white',
          borderTop: '2px solid #e0e0e0',
          display: 'flex',
          justifyContent: 'space-around',
          padding: '8px 0',
          zIndex: 1000,
          boxShadow: '0 -2px 10px rgba(0,0,0,0.1)'
        }}>
          {/* Tab 1: Stempel/Übersicht */}
          <button
            onClick={() => {
              setActiveTab('stempeluhr');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'stempeluhr' ? '#1e3a5f' : '#666',
              fontWeight: activeTab === 'stempeluhr' ? 'bold' : 'normal'
            }}
          >
            <Home size={24} />
            <span style={{ fontSize: '11px' }}>{categoryLabel}</span>
          </button>

          {/* Tab 2: Historie */}
          <button
            onClick={() => {
              setActiveTab('historie');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'historie' ? '#1e3a5f' : '#666',
              fontWeight: activeTab === 'historie' ? 'bold' : 'normal'
            }}
          >
            <History size={24} />
            <span style={{ fontSize: '11px' }}>Historie</span>
          </button>

          {/* Tab 3: Kilometer */}
          <button
            onClick={() => {
              setActiveTab('kilometer');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'kilometer' ? '#1e3a5f' : '#666',
              fontWeight: activeTab === 'kilometer' ? 'bold' : 'normal'
            }}
          >
            <Car size={24} />
            <span style={{ fontSize: '11px' }}>KM</span>
          </button>

          {/* Tab 4: Dienstplan */}
          <button
            onClick={() => {
              setActiveTab('dienstplan');
              setShowMoreMenu(false);
            }}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: activeTab === 'dienstplan' ? '#1e3a5f' : '#666',
              fontWeight: activeTab === 'dienstplan' ? 'bold' : 'normal'
            }}
          >
            <Calendar size={24} />
            <span style={{ fontSize: '11px' }}>Plan</span>
          </button>

          {/* Tab 5: Mehr */}
          <button
            onClick={() => setShowMoreMenu(!showMoreMenu)}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              background: 'none',
              border: 'none',
              padding: '8px',
              cursor: 'pointer',
              color: showMoreMenu || ['urlaub', 'schichtaenderung', 'selbstbuchung'].includes(activeTab) ? '#1e3a5f' : '#666',
              fontWeight: showMoreMenu || ['urlaub', 'schichtaenderung', 'selbstbuchung'].includes(activeTab) ? 'bold' : 'normal'
            }}
          >
            <Menu size={24} />
            <span style={{ fontSize: '11px' }}>Mehr</span>
          </button>
        </div>

        {/* Mehr-Overlay */}
        {showMoreMenu && (
          <div
            onClick={() => setShowMoreMenu(false)}
            style={{
              position: 'fixed',
              bottom: 0,
              left: 0,
              right: 0,
              top: 0,
              backgroundColor: 'rgba(0,0,0,0.5)',
              zIndex: 999,
              display: 'flex',
              alignItems: 'flex-end'
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: 'white',
                width: '100%',
                borderTopLeftRadius: '16px',
                borderTopRightRadius: '16px',
                padding: '20px',
                paddingBottom: '80px',
                boxShadow: '0 -4px 20px rgba(0,0,0,0.2)'
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px'
              }}>
                <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f' }}>Weitere Optionen</h3>
                <button
                  onClick={() => setShowMoreMenu(false)}
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: '8px'
                  }}
                >
                  <CloseIcon size={24} color="#666" />
                </button>
              </div>
              
              {employeeCategory !== 'A' && !hasCAssignments && (
              <button
                onClick={() => {
                  setActiveTab('selbstbuchung');
                  setShowMoreMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '16px',
                  backgroundColor: activeTab === 'selbstbuchung' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'selbstbuchung' ? 'white' : '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  marginBottom: '12px'
                }}
              >
                <Send size={24} />
                Schicht buchen
              </button>
              )}

              <button
                onClick={() => {
                  setActiveTab('urlaub');
                  setShowMoreMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '16px',
                  backgroundColor: activeTab === 'urlaub' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'urlaub' ? 'white' : '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <Calendar size={24} />
                Urlaub
              </button>

              <button
                onClick={() => {
                  setActiveTab('schichtaenderung');
                  setShowMoreMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '16px',
                  marginTop: '12px',
                  backgroundColor: activeTab === 'schichtaenderung' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'schichtaenderung' ? 'white' : '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <Clock size={24} />
                Schichtaenderung
              </button>

              <button
                onClick={() => {
                  setActiveTab('nachrichten');
                  setShowMoreMenu(false);
                }}
                style={{
                  width: '100%',
                  padding: '16px',
                  marginTop: '12px',
                  backgroundColor: activeTab === 'nachrichten' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'nachrichten' ? 'white' : '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <Mail size={24} />
                Nachricht senden
              </button>

              <button
                onClick={() => {
                  setShowPasswordChange(true);
                  setShowMoreMenu(false);
                  setPwOld('');
                  setPwNew('');
                  setPwConfirm('');
                  setPwError('');
                  setPwSuccess('');
                }}
                style={{
                  width: '100%',
                  padding: '16px',
                  marginTop: '12px',
                  backgroundColor: '#f8f9fa',
                  color: '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}
              >
                <Lock size={24} />
                Passwort ändern
              </button>

              <a
                href="/hilfe/"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  width: '100%',
                  padding: '16px',
                  marginTop: '12px',
                  backgroundColor: '#f8f9fa',
                  color: '#333',
                  border: 'none',
                  borderRadius: '12px',
                  fontSize: '16px',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  textDecoration: 'none'
                }}
              >
                <HelpCircle size={24} />
                Hilfe & FAQ
              </a>
            </div>
          </div>
        )}

        {/* Passwort ändern Modal */}
        {showPasswordChange && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '16px',
          }} onClick={() => setShowPasswordChange(false)}>
            <div style={{
              background: 'white', borderRadius: '16px', width: '100%', maxWidth: '400px',
              padding: '24px', position: 'relative',
            }} onClick={e => e.stopPropagation()}>
              <button onClick={() => setShowPasswordChange(false)} style={{
                position: 'absolute', top: '12px', right: '12px', background: 'none',
                border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '4px',
              }}><CloseIcon size={20} /></button>

              <h3 style={{ fontSize: '20px', fontWeight: 'bold', marginBottom: '16px' }}>Passwort ändern</h3>

              {pwError && <div style={{ background: '#fef2f2', color: '#dc2626', padding: '10px', borderRadius: '8px', marginBottom: '12px', fontSize: '14px' }}>{pwError}</div>}
              {pwSuccess && <div style={{ background: '#f0fdf4', color: '#16a34a', padding: '10px', borderRadius: '8px', marginBottom: '12px', fontSize: '14px' }}>{pwSuccess}</div>}

              {!pwSuccess ? (
                <form onSubmit={async (e) => {
                  e.preventDefault();
                  setPwError('');
                  if (pwNew !== pwConfirm) { setPwError('Neue Passwörter stimmen nicht überein!'); return; }
                  if (pwNew.length < 6) { setPwError('Mindestens 6 Zeichen!'); return; }
                  setPwLoading(true);
                  try {
                    const token = localStorage.getItem('token') || sessionStorage.getItem('token');
                    await axios.post(`${API_URL}/auth/change-password`,
                      { new_password: pwNew, old_password: pwOld },
                      { headers: { 'Authorization': `Bearer ${token}` }}
                    );
                    setPwSuccess('Passwort erfolgreich geändert!');
                  } catch (err) {
                    setPwError(err.response?.data?.detail || 'Fehler beim Ändern');
                  } finally {
                    setPwLoading(false);
                  }
                }}>
                  <input
                    type="password"
                    placeholder="Altes Passwort"
                    value={pwOld}
                    onChange={e => setPwOld(e.target.value)}
                    required
                    style={{ width: '100%', padding: '12px', marginBottom: '12px', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '16px' }}
                  />
                  <input
                    type="password"
                    placeholder="Neues Passwort"
                    value={pwNew}
                    onChange={e => setPwNew(e.target.value)}
                    autoComplete="new-password"
                    required
                    style={{ width: '100%', padding: '12px', marginBottom: '12px', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '16px' }}
                  />
                  <input
                    type="password"
                    placeholder="Neues Passwort bestätigen"
                    value={pwConfirm}
                    onChange={e => setPwConfirm(e.target.value)}
                    autoComplete="new-password"
                    required
                    style={{ width: '100%', padding: '12px', marginBottom: '12px', border: '1px solid #d1d5db', borderRadius: '8px', fontSize: '16px' }}
                  />
                  <button
                    type="submit"
                    disabled={pwLoading}
                    style={{
                      width: '100%', padding: '14px', background: '#1e3a5f', color: 'white',
                      border: 'none', borderRadius: '10px', fontSize: '16px', fontWeight: 'bold',
                      cursor: pwLoading ? 'not-allowed' : 'pointer', opacity: pwLoading ? 0.6 : 1,
                    }}
                  >
                    {pwLoading ? 'Speichere...' : 'Passwort ändern'}
                  </button>
                </form>
              ) : (
                <button
                  onClick={() => setShowPasswordChange(false)}
                  style={{
                    width: '100%', padding: '14px', background: '#1e3a5f', color: 'white',
                    border: 'none', borderRadius: '10px', fontSize: '16px', fontWeight: 'bold', cursor: 'pointer',
                  }}
                >
                  Schliessen
                </button>
              )}
            </div>
          </div>
        )}

        {/* Spacer für Bottom Nav */}
        <div style={{ height: '70px' }}></div>
      </>
    );
  };

  if (loadingCategory) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#1e3a5f' }}>
        <div className="text-white text-xl">Lade Mitarbeiterdaten...</div>
      </div>
    );
  }

  // Loading: Kategorie noch nicht geladen
  if (employeeCategory === null) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#1e3a5f' }}>
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
          <p>Wird geladen...</p>
        </div>
      </div>
    );
  }

  if (employeeCategory === 'A') {
    return (
      <div className="min-h-screen" style={{ backgroundColor: '#1e3a5f' }}>
        <div className="max-w-4xl mx-auto p-4">
          {/* HEADER */}
          <div style={{ backgroundColor: '#2c5f7c', borderRadius: '16px', padding: '16px', marginBottom: '24px' }}>
            <div className="flex justify-between items-center w-full">
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-start' }}>
                <img src="/seda24-logo-white.png" alt="SEDA24" style={{ width: '75px', height: '75px', objectFit: 'contain' }} />
              </div>
              <div style={{ flex: '1', textAlign: 'center' }}>
                <div style={{ fontWeight: 'bold', color: 'white', fontSize: '16px' }}>
                  {employeeData?.name || 'Mitarbeiter'}
                </div>
                <div style={{ color: '#e2e8f0', fontSize: '12px' }}>
                  Pers.Nr: {employeeData?.personal_nr || '-'}
                </div>
              </div>
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                {canAccessAdmin && (
                  <button onClick={() => navigate('/admin')} className="px-4 py-1 text-sm rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#3b82f6' }}>
                    <Shield size={20} className="inline mr-1" />
                    Verwaltung
                  </button>
                )}
                <button onClick={handleLogout} className="px-4 py-1 text-sm rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#dc2626' }}>
                  <LogOut size={20} className="inline mr-2" />
                  Logout
                </button>
              </div>
            </div>
          </div>

          {/* TAB-INHALT */}
          <div className="bg-white rounded-2xl shadow-xl p-8" style={{ marginBottom: '20px' }}>
            {activeTab === 'stempeluhr' ? (
              <>
                <div className="text-center mb-6">
                  <div style={{ fontSize: '60px', fontWeight: 'bold', color: '#1e3a5f' }}>
                    {currentTime.toLocaleTimeString('de-DE')}
                  </div>
                  <div style={{ fontSize: '16px', color: '#666' }}>
                    {currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </div>
                </div>

                <div style={{ 
                  background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)', 
                  borderRadius: '16px', 
                  padding: '24px', 
                  marginBottom: '24px', 
                  color: 'white', 
                  textAlign: 'center' 
                }}>
                  <Shield size={48} className="mx-auto mb-3" />
                  <div style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '12px' }}>
                    Vollautomatische Zeiterfassung
                  </div>
                  <div style={{ fontSize: '16px', opacity: 0.9 }}>
                    Deine Arbeitszeiten werden automatisch vom System erfasst.
                    Du musst nichts tun - das System stempelt dich basierend auf deinem Dienstplan ein und aus.
                  </div>
                  <div style={{ marginTop: '16px', padding: '12px', background: 'rgba(255, 255, 255, 0.2)', borderRadius: '8px' }}>
                    <div style={{ fontSize: '14px' }}>
                      <Clock size={16} className="inline mr-2" />
                      Automatisches Einstempeln: 6:00 Uhr
                    </div>
                    <div style={{ fontSize: '14px', marginTop: '4px' }}>
                      <Clock size={16} className="inline mr-2" />
                      Automatisches Ausstempeln: Nach Sollstunden
                    </div>
                  </div>
                </div>

                <div style={{marginTop: '32px', paddingTop: '24px', borderTop: '2px solid #e0e0e0'}}>
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px'}}>
                    <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}>
                        <Clock size={18} color="#0ea5e9" />
                        <span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Heute</span>
                      </div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(todayHours)}</div>
                    </div>
                    <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}>
                        <Calendar size={18} color="#22c55e" />
                        <span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Diese Woche</span>
                      </div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(weekHours)}</div>
                    </div>
                    <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}>
                        <Building size={18} color="#f97316" />
                        <span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Dieser Monat</span>
                      </div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(monthHours)}</div>
                    </div>
                    <div style={{ background: 'linear-gradient(135deg, #f5a623 0%, #f7b733 100%)', padding: '16px', borderRadius: '12px', color: 'white', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}>
                        <Gauge size={18} color="white" />
                        <span style={{ fontSize: '14px', fontWeight: '500' }}>Seit Beginn</span>
                      </div>
                      <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
					  {(() => {
					  if (employeeTachoData && employeeTachoData.total_hours_since_start) {
						const total = employeeTachoData.total_hours_since_start;
						const h = Math.floor(total);
						const m = Math.round((total % 1) * 60);
						return `${h} Std ${m} Min`;
					  }
					  return '0 Std 0 Min';
					})()}
					</div>
                    </div>
                  </div>
                </div>
              </>
            ) : activeTab === 'historie' ? (
              <HistoryTab />
            ) : activeTab === 'kilometer' ? (
              <KilometerTab />
            ) : activeTab === 'dienstplan' ? (
              <DienstplanTab token={token} />
            ) : activeTab === 'urlaub' ? (
              <VacationTab token={token} />
            ) : activeTab === 'schichtaenderung' ? (
              <ShiftChangeForm />
            ) : activeTab === 'nachrichten' ? (
              <NachrichtenTab />
            ) : null}
          </div>

          {/* BOTTOM NAVIGATION */}
          <BottomNav categoryLabel="Übersicht" />
        </div>
      </div>
    );
  }


  // KATEGORIE B: Schicht-Uebersicht + Push-Bestaetigung
  if (employeeCategory === 'B') {
    const openShifts = todayShifts.filter(s => s.status !== 'confirmed');
    return (
      <div className="min-h-screen" style={{ backgroundColor: '#1e3a5f' }}>
        <div className="max-w-4xl mx-auto p-4">
          {/* HEADER */}
          <div style={{ backgroundColor: '#2c5f7c', borderRadius: '16px', padding: '16px', marginBottom: '24px' }}>
            <div className="flex justify-between items-center w-full">
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-start' }}>
                <img src="/seda24-logo-white.png" alt="SEDA24" style={{ width: '75px', height: '75px', objectFit: 'contain' }} />
              </div>
              <div style={{ flex: '1', textAlign: 'center' }}>
                <div style={{ fontWeight: 'bold', color: 'white', fontSize: '16px' }}>
                  {employeeData?.name || 'Mitarbeiter'}
                </div>
                <div style={{ color: '#e2e8f0', fontSize: '12px' }}>
                  Pers.Nr: {employeeData?.personal_nr || '-'}
                </div>
              </div>
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                {canAccessAdmin && (
                  <button onClick={() => navigate('/admin')} className="px-4 py-1 text-sm rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#3b82f6' }}>
                    <Shield size={20} className="inline mr-1" />
                    Verwaltung
                  </button>
                )}
                <button onClick={handleLogout} className="px-4 py-1 text-sm rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#dc2626' }}>
                  <LogOut size={20} className="inline mr-2" />
                  Logout
                </button>
              </div>
            </div>
          </div>

          {/* TAB-INHALT */}
          <div className="bg-white rounded-2xl shadow-xl p-6" style={{ marginBottom: '20px' }}>
            {activeTab === 'stempeluhr' ? (
              <>
                {/* Datum + Uhrzeit */}
                <div className="text-center mb-4">
                  <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#1e3a5f' }}>
                    {currentTime.toLocaleTimeString('de-DE')}
                  </div>
                  <div style={{ fontSize: '15px', color: '#666' }}>
                    {currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </div>
                </div>

                {/* Heutige Schichten */}
                <div style={{ marginBottom: '24px' }}>
                  <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Calendar size={18} />
                    Deine Schichten heute
                  </div>

                  {(() => {
                    const activeShifts = todayShifts.filter(s => s.status !== 'confirmed' && !['sick', 'cancelled'].includes(s.schedule_status));
                    const inactiveShifts = todayShifts.filter(s => ['sick', 'cancelled'].includes(s.schedule_status));
                    if (todayShifts.length === 0 && !hasCAssignments) return (
                    <div style={{
                      background: '#f0fdf4',
                      border: '1px solid #bbf7d0',
                      borderRadius: '12px',
                      padding: '24px',
                      textAlign: 'center',
                      color: '#166534'
                    }}>
                      <CheckCircle size={32} className="mx-auto" style={{ marginBottom: '8px' }} />
                      <div style={{ fontWeight: 'bold', fontSize: '16px' }}>Heute keine Schichten</div>
                      <div style={{ fontSize: '13px', marginTop: '4px', opacity: 0.8 }}>
                        Laut Dienstplan hast du heute frei
                      </div>
                    </div>
                    );
                    if (todayShifts.length === 0 && hasCAssignments) return null;
                    if (activeShifts.length === 0 && inactiveShifts.length === 0) return (
                    <div style={{
                      background: '#f0fdf4',
                      border: '1px solid #bbf7d0',
                      borderRadius: '12px',
                      padding: '24px',
                      textAlign: 'center',
                      color: '#166534'
                    }}>
                      <CheckCircle size={32} className="mx-auto" style={{ marginBottom: '8px' }} />
                      <div style={{ fontWeight: 'bold', fontSize: '16px' }}>Alles erledigt!</div>
                      <div style={{ fontSize: '13px', marginTop: '4px', opacity: 0.8 }}>
                        Alle Schichten fuer heute sind gebucht
                      </div>
                    </div>
                    );
                    if (activeShifts.length === 0 && inactiveShifts.length > 0) return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{
                        background: '#f0fdf4',
                        border: '1px solid #bbf7d0',
                        borderRadius: '12px',
                        padding: '24px',
                        textAlign: 'center',
                        color: '#166534'
                      }}>
                        <CheckCircle size={32} className="mx-auto" style={{ marginBottom: '8px' }} />
                        <div style={{ fontWeight: 'bold', fontSize: '16px' }}>Alles erledigt!</div>
                      </div>
                      {inactiveShifts.map(shift => (
                        <div key={shift.schedule_id} style={{
                          border: '1px solid #e5e7eb', borderRadius: '12px', padding: '14px',
                          background: '#f3f4f6', opacity: 0.6,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <div style={{ fontWeight: '600', color: '#9ca3af', textDecoration: 'line-through' }}>{shift.object_name}</div>
                              <div style={{ fontSize: '13px', color: '#9ca3af' }}>{shift.start_time} - {shift.end_time}</div>
                            </div>
                            <span style={{ fontSize: '12px', padding: '4px 8px', borderRadius: '20px', background: '#f3f4f6', color: '#6b7280', fontWeight: 'bold' }}>
                              {shift.schedule_status === 'sick' ? '\u{1F912} Krank' : '\u274C Abgesagt'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    );
                    return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {activeShifts.map((shift) => {
                          // Pruefen ob Schicht gerade laeuft (gestartet aber nicht beendet)
                          const isRunning = !shift.shift_ended && shift.status !== 'confirmed' && (() => {
                            const now = new Date();
                            const [h, m] = shift.start_time.split(':').map(Number);
                            const start = new Date();
                            start.setHours(h, m, 0, 0);
                            return now >= start;
                          })();

                          return (
                          <div
                            key={shift.schedule_id}
                            style={{
                              border: shift.status === 'confirmed' ? '2px solid #22c55e'
                                : shift.shift_ended ? '2px solid #f59e0b'
                                : isRunning ? '2px solid #3b82f6'
                                : '2px solid #e5e7eb',
                              borderRadius: '12px',
                              padding: '16px',
                              background: shift.status === 'confirmed' ? '#f0fdf4'
                                : shift.shift_ended ? '#fffbeb'
                                : isRunning ? '#eff6ff'
                                : '#fff',
                            }}
                          >
                            {/* Objekt + Status */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                              <div>
                                <div style={{ fontWeight: 'bold', fontSize: '16px', color: '#1e3a5f' }}>
                                  {shift.object_name}
                                </div>
                                <div style={{ fontSize: '14px', color: '#666', display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px' }}>
                                  <Clock size={14} />
                                  {shift.start_time} - {shift.end_time}
                                  <span style={{ marginLeft: '4px', color: '#999' }}>({shift.planned_hours}h)</span>
                                </div>
                              </div>
                              <div style={{
                                padding: '4px 10px',
                                borderRadius: '20px',
                                fontSize: '12px',
                                fontWeight: 'bold',
                                ...(shift.status === 'confirmed'
                                  ? { background: '#dcfce7', color: '#166534' }
                                  : shift.shift_ended
                                  ? { background: '#fef3c7', color: '#92400e' }
                                  : isRunning
                                  ? { background: '#dbeafe', color: '#1e40af' }
                                  : { background: '#f3f4f6', color: '#6b7280' })
                              }}>
                                {shift.status === 'confirmed' ? 'Gebucht' :
                                 shift.shift_ended ? 'Offen' :
                                 isRunning ? 'Läuft gerade' : 'Geplant'}
                              </div>
                            </div>

                            {/* DIREKTE Bestaetigung - ein Klick! (NICHT bei C-Zuweisungen, dort wird gestempelt) */}
                            {shift.status !== 'confirmed' && shift.shift_ended && !shift.has_c_assignment && (
                              <button
                                onClick={() => confirmShiftDirect(shift)}
                                disabled={confirmingShiftId === shift.schedule_id}
                                style={{
                                  marginTop: '8px',
                                  width: '100%',
                                  background: confirmingShiftId === shift.schedule_id
                                    ? '#9ca3af'
                                    : 'linear-gradient(135deg, #22c55e, #16a34a)',
                                  borderRadius: '10px',
                                  padding: '14px',
                                  color: 'white',
                                  fontSize: '16px',
                                  fontWeight: 'bold',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '8px',
                                  border: 'none',
                                  cursor: confirmingShiftId === shift.schedule_id ? 'wait' : 'pointer',
                                }}
                              >
                                {confirmingShiftId === shift.schedule_id ? (
                                  <>
                                    <div style={{ width: '20px', height: '20px', border: '3px solid white', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                                    Wird gebucht...
                                  </>
                                ) : (
                                  <>
                                    <CheckCircle size={22} />
                                    Ja, war anwesend - Jetzt buchen
                                  </>
                                )}
                              </button>
                            )}

                            {/* Hinweis bei C-Zuweisung: Stempeluhr nutzen */}
                            {shift.status !== 'confirmed' && shift.shift_ended && shift.has_c_assignment && (
                              <div style={{
                                marginTop: '8px',
                                background: '#eff6ff',
                                border: '1px solid #bfdbfe',
                                borderRadius: '10px',
                                padding: '12px',
                                fontSize: '13px',
                                color: '#1e40af',
                                fontWeight: '600',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px'
                              }}>
                                <Clock size={16} />
                                Hier bitte unten die Stempeluhr nutzen
                              </div>
                            )}

                            {/* Laufende Schicht */}
                            {shift.status !== 'confirmed' && !shift.shift_ended && isRunning && (
                              <div style={{
                                marginTop: '8px',
                                background: '#dbeafe',
                                borderRadius: '8px',
                                padding: '10px',
                                fontSize: '13px',
                                color: '#1e40af',
                                fontWeight: '600',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px'
                              }}>
                                <Clock size={16} />
                                {shift.has_c_assignment
                                  ? 'Schicht läuft - bitte unten die Stempeluhr nutzen'
                                  : 'Schicht läuft gerade - Bestätigung nach Schichtende'}
                              </div>
                            )}

                            {/* Geplante Schicht (noch nicht gestartet) */}
                            {shift.status !== 'confirmed' && !shift.shift_ended && !isRunning && (
                              <div style={{
                                marginTop: '8px',
                                background: '#f0f9ff',
                                borderRadius: '8px',
                                padding: '10px',
                                fontSize: '13px',
                                color: '#1e40af',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px'
                              }}>
                                <Info size={16} />
                                {shift.has_c_assignment
                                  ? 'Bitte unten die Stempeluhr nutzen'
                                  : 'Bestätigung nach Schichtende möglich'}
                              </div>
                            )}

                            {/* Bestaetigte Schicht */}
                            {shift.status === 'confirmed' && (
                              <div style={{ marginTop: '8px', fontSize: '13px', color: '#16a34a', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <CheckCircle size={16} />
                                {shift.planned_hours}h gebucht
                              </div>
                            )}
                          </div>
                          );
                      })}
                      {inactiveShifts.map(shift => (
                        <div key={shift.schedule_id} style={{
                          border: '1px solid #e5e7eb', borderRadius: '12px', padding: '14px',
                          background: '#f3f4f6', opacity: 0.6,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div>
                              <div style={{ fontWeight: '600', color: '#9ca3af', textDecoration: 'line-through' }}>{shift.object_name}</div>
                              <div style={{ fontSize: '13px', color: '#9ca3af' }}>{shift.start_time} - {shift.end_time}</div>
                            </div>
                            <span style={{ fontSize: '12px', padding: '4px 8px', borderRadius: '20px', background: '#f3f4f6', color: '#6b7280', fontWeight: 'bold' }}>
                              {shift.schedule_status === 'sick' ? '\u{1F912} Krank' : '\u274C Abgesagt'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                    );
                  })()}
                </div>

                {/* Zukuenftige Schichten */}
                {upcomingShifts.length > 0 && (
                  <div style={{ marginBottom: '24px' }}>
                    <div style={{ fontSize: '16px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <ChevronsRight size={18} />
                      Naechste Schichten
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {upcomingShifts.slice(0, 7).map((shift) => {
                        const inactive = ['swapped', 'sick', 'cancelled'].includes(shift.schedule_status);
                        return (
                        <div key={shift.schedule_id} onClick={() => !inactive && openShiftModal(shift)} style={{
                          border: inactive ? '1px solid #e5e7eb' : '1px solid #e5e7eb',
                          borderRadius: '10px',
                          padding: '12px 16px',
                          background: inactive ? '#f3f4f6' : '#f9fafb',
                          opacity: inactive ? 0.7 : 1,
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          cursor: inactive ? 'default' : 'pointer',
                          transition: 'all 0.15s',
                        }}>
                          <div>
                            <div style={{ fontSize: '14px', fontWeight: '600', color: inactive ? '#9ca3af' : '#374151', textDecoration: inactive ? 'line-through' : 'none' }}>
                              {new Date(shift.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}
                            </div>
                            <div style={{ fontSize: '13px', color: '#9ca3af' }}>
                              {shift.object_name}
                            </div>
                            {shift.schedule_status === 'swapped' && (
                              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                                {'\u{1F504}'} Getauscht{shift.swap_with ? ` mit ${shift.swap_with}` : ''}
                              </div>
                            )}
                            {shift.schedule_status === 'sick' && (
                              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                                {'\u{1F3E5}'} Krank gemeldet
                              </div>
                            )}
                            {shift.schedule_status === 'cancelled' && (
                              <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                                {'\u274C'} Abgesagt
                              </div>
                            )}
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{ textAlign: 'right' }}>
                              <div style={{ fontSize: '14px', fontWeight: '500', color: inactive ? '#9ca3af' : '#1e3a5f' }}>
                                {shift.start_time} - {shift.end_time}
                              </div>
                              <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                                {shift.planned_hours}h
                              </div>
                            </div>
                            {!inactive && <div style={{ color: '#9ca3af', fontSize: '18px' }}>&rsaquo;</div>}
                          </div>
                        </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Stunden-Statistik */}
                <div style={{ paddingTop: '16px', borderTop: '2px solid #e0e0e0' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
                    <div style={{ background: '#f8f9fa', padding: '14px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '6px' }}>
                        <Clock size={16} color="#0ea5e9" />
                        <span style={{ fontSize: '13px', color: '#666' }}>Heute</span>
                      </div>
                      <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(todayHours)}</div>
                    </div>
                    <div style={{ background: '#f8f9fa', padding: '14px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '6px' }}>
                        <Calendar size={16} color="#22c55e" />
                        <span style={{ fontSize: '13px', color: '#666' }}>Woche</span>
                      </div>
                      <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(weekHours)}</div>
                    </div>
                    <div style={{ background: '#f8f9fa', padding: '14px', borderRadius: '12px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '6px' }}>
                        <Building size={16} color="#f97316" />
                        <span style={{ fontSize: '13px', color: '#666' }}>Monat</span>
                      </div>
                      <div style={{ fontSize: '22px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(monthHours)}</div>
                    </div>
                    <div style={{ background: 'linear-gradient(135deg, #f5a623, #f7b733)', padding: '14px', borderRadius: '12px', color: 'white', textAlign: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '6px' }}>
                        <Gauge size={16} color="white" />
                        <span style={{ fontSize: '13px' }}>Gesamt</span>
                      </div>
                      <div style={{ fontSize: '22px', fontWeight: 'bold' }}>
                        {(() => {
                          if (employeeTachoData?.total_hours_since_start) {
                            const total = employeeTachoData.total_hours_since_start;
                            return `${Math.floor(total)} Std ${Math.round((total % 1) * 60)} Min`;
                          }
                          return '0 Std';
                        })()}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : activeTab === 'historie' ? (
              <HistoryTab />
            ) : activeTab === 'kilometer' ? (
              <KilometerTab />
            ) : activeTab === 'dienstplan' ? (
              <DienstplanTab token={token} />
            ) : activeTab === 'urlaub' ? (
              <VacationTab token={token} />
            ) : activeTab === 'schichtaenderung' ? (
              <ShiftChangeForm />
            ) : activeTab === 'nachrichten' ? (
              <NachrichtenTab />
            ) : activeTab === 'selbstbuchung' ? (
              <SelbstbuchungTab />
            ) : null}

            {/* Bie2 Stempeluhr fuer C-Zuweisungen */}
            {hasCAssignments && activeTab === 'stempeluhr' && (
              <Bie2Stempeluhr token={token} onStatusChange={() => { fetchTodayHours(); fetchWeekHours(); fetchMonthHours(); }} onLogout={handleLogout} />
            )}
          </div>

          {/* BOTTOM NAVIGATION */}
          <BottomNav categoryLabel="Schichten" />
        </div>

        {/* SCHICHT-MODAL (Kat B) */}
        {showShiftModal && selectedShift && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', zIndex: 9999,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '16px',
          }} onClick={() => setShowShiftModal(false)}>
            <div style={{
              background: 'white', borderRadius: '16px', width: '100%', maxWidth: '400px',
              padding: '24px', position: 'relative', maxHeight: '90vh', overflowY: 'auto',
            }} onClick={e => e.stopPropagation()}>
              <button onClick={() => setShowShiftModal(false)} style={{
                position: 'absolute', top: '12px', right: '12px', background: 'none',
                border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '4px',
              }}><CloseIcon size={20} /></button>

              {/* Schicht-Info */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '4px' }}>
                  {selectedShift.object_name}
                </div>
                <div style={{ fontSize: '15px', color: '#374151' }}>
                  {new Date(selectedShift.date).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                </div>
                <div style={{ fontSize: '15px', color: '#6b7280', marginTop: '2px' }}>
                  {selectedShift.start_time} - {selectedShift.end_time} Uhr ({selectedShift.planned_hours}h)
                </div>
              </div>

              {/* Bestaetigungsnachricht */}
              {shiftRequestSent && (
                <div style={{
                  background: cancelReason === 'Krank' ? '#fef2f2' : '#dcfce7',
                  color: cancelReason === 'Krank' ? '#991b1b' : '#166534',
                  padding: '12px 16px', borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                  display: 'flex', alignItems: 'flex-start', gap: '8px',
                }}>
                  <span style={{ fontSize: '18px', flexShrink: 0 }}>
                    {cancelReason === 'Krank' ? '\u{1F3E5}' : '\u2705'}
                  </span>
                  <span>{confirmationMessage}</span>
                </div>
              )}

              {/* HAUPTMENUE: 2 Buttons */}
              {!shiftRequestSent && !showCancelReasons && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <button
                    onClick={() => setShowCancelReasons(true)}
                    style={{
                      background: '#ef4444', color: 'white', border: 'none', borderRadius: '10px',
                      padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                    }}
                  >
                    {'\u274C'} Kann nicht kommen
                  </button>
                  <button
                    onClick={() => setShowShiftModal(false)}
                    style={{
                      background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: '10px',
                      padding: '14px', fontSize: '15px', fontWeight: '500', cursor: 'pointer',
                    }}
                  >
                    OK
                  </button>
                </div>
              )}

              {/* ABSAGE-FLOW: Grund-Auswahl */}
              {!shiftRequestSent && showCancelReasons && !showSickDuration && !showCustomReason && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>
                    Grund angeben:
                  </div>
                  <button onClick={() => { setCancelReason('Krank'); setShowSickDuration(true); }} style={{
                    background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca',
                    borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center',
                  }}>{'\u{1F912}'} Krank</button>
                  <button disabled={sendingRequest} onClick={async () => {
                    setSendingRequest(true); setCancelReason('Privat');
                    try {
                      const resp = await axios.post(`${API_URL}/time-entries/shift-request`, {
                        schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Privat',
                      }, { headers: { Authorization: `Bearer ${token}` } });
                      setConfirmationMessage(resp.data.message); setShiftRequestSent(true);
                    } catch (err) { console.error(err); }
                    setSendingRequest(false);
                  }} style={{
                    background: '#fffbeb', color: '#d97706', border: '1px solid #fde68a',
                    borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center',
                  }}>{'\u{1F3E0}'} Privat</button>
                  <button onClick={() => { setCancelReason('Sonstiges'); setShowCustomReason(true); }} style={{
                    background: '#f0f9ff', color: '#2563eb', border: '1px solid #bfdbfe',
                    borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center',
                  }}>{'\u{1F4DD}'} Sonstiges</button>
                  <button onClick={() => setShowCancelReasons(false)} style={{
                    background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px',
                    padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px',
                  }}>Zurueck</button>
                </div>
              )}

              {/* KRANK: Dauer-Picker */}
              {!shiftRequestSent && showSickDuration && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>
                    {'\u{1F912}'} Wie lange krank?
                  </div>
                  <button disabled={sendingRequest} onClick={async () => {
                    setSendingRequest(true);
                    try {
                      const resp = await axios.post(`${API_URL}/time-entries/shift-request`, {
                        schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank',
                        sick_from: selectedShift.date, sick_until: selectedShift.date,
                      }, { headers: { Authorization: `Bearer ${token}` } });
                      setConfirmationMessage(resp.data.message); setShiftRequestSent(true);
                    } catch (err) { console.error(err); }
                    setSendingRequest(false);
                  }} style={{
                    background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca',
                    borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                  }}>Nur diesen Tag</button>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '13px', color: '#374151', fontWeight: '500' }}>Ab heute bis:</label>
                    <input type="date" value={sickUntilDate} onChange={(e) => setSickUntilDate(e.target.value)}
                      min={selectedShift.date} style={{
                        width: '100%', padding: '12px', borderRadius: '10px',
                        border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box',
                      }} />
                    {sickUntilDate && (
                      <button disabled={sendingRequest} onClick={async () => {
                        setSendingRequest(true);
                        try {
                          const resp = await axios.post(`${API_URL}/time-entries/shift-request`, {
                            schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank',
                            sick_from: selectedShift.date, sick_until: sickUntilDate,
                          }, { headers: { Authorization: `Bearer ${token}` } });
                          setConfirmationMessage(resp.data.message); setShiftRequestSent(true);
                        } catch (err) { console.error(err); }
                        setSendingRequest(false);
                      }} style={{
                        background: '#dc2626', color: 'white', border: 'none', borderRadius: '10px',
                        padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                      }}>Krankmeldung senden</button>
                    )}
                  </div>
                  <button disabled={sendingRequest} onClick={async () => {
                    setSendingRequest(true);
                    try {
                      const resp = await axios.post(`${API_URL}/time-entries/shift-request`, {
                        schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank',
                        sick_from: selectedShift.date, sick_until: null,
                      }, { headers: { Authorization: `Bearer ${token}` } });
                      setConfirmationMessage(resp.data.message); setShiftRequestSent(true);
                    } catch (err) { console.error(err); }
                    setSendingRequest(false);
                  }} style={{
                    background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a',
                    borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                  }}>Weiss noch nicht</button>
                  <button onClick={() => setShowSickDuration(false)} style={{
                    background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px',
                    padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px',
                  }}>Zurueck</button>
                </div>
              )}

              {/* SONSTIGES: Freitext */}
              {!shiftRequestSent && showCustomReason && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>
                    {'\u{1F4DD}'} Grund angeben:
                  </div>
                  <textarea value={customReasonText} onChange={(e) => setCustomReasonText(e.target.value)}
                    placeholder="Beschreibe kurz den Grund..."
                    style={{
                      width: '100%', padding: '12px', borderRadius: '10px',
                      border: '1px solid #d1d5db', fontSize: '15px',
                      minHeight: '80px', resize: 'vertical', fontFamily: 'inherit', boxSizing: 'border-box',
                    }} />
                  <button disabled={sendingRequest || !customReasonText.trim()} onClick={async () => {
                    setSendingRequest(true);
                    try {
                      const resp = await axios.post(`${API_URL}/time-entries/shift-request`, {
                        schedule_id: selectedShift.schedule_id, request_type: 'cancel',
                        reason: 'Sonstiges', custom_reason: customReasonText,
                      }, { headers: { Authorization: `Bearer ${token}` } });
                      setConfirmationMessage(resp.data.message); setShiftRequestSent(true);
                    } catch (err) { console.error(err); }
                    setSendingRequest(false);
                  }} style={{
                    background: !customReasonText.trim() ? '#9ca3af' : '#2563eb',
                    color: 'white', border: 'none', borderRadius: '10px',
                    padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                  }}>Nachricht senden</button>
                  <button onClick={() => { setShowCustomReason(false); setCustomReasonText(''); }} style={{
                    background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px',
                    padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px',
                  }}>Zurueck</button>
                </div>
              )}

              {/* Schliessen-Button nach Absenden */}
              {shiftRequestSent && (
                <button onClick={() => setShowShiftModal(false)} style={{
                  background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: '10px',
                  padding: '14px', fontSize: '15px', fontWeight: '500', cursor: 'pointer', width: '100%',
                }}>Schliessen</button>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

 // KATEGORIE C: Normale Stempeluhr - MIT DIENSTPLAN-FILTER
  return (
    <div className="min-h-screen" style={{ backgroundColor: '#1e3a5f' }}>
      <div className="max-w-4xl mx-auto p-4">
        {/* HEADER */}
        <div style={{ backgroundColor: '#2c5f7c', borderRadius: '16px', padding: '16px', marginBottom: '24px' }}>
          <div className="flex justify-between items-center w-full">
            <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-start' }}>
              <img src="/seda24-logo-white.png" alt="SEDA24" style={{ width: '75px', height: '75px', objectFit: 'contain' }} />
            </div>
            <div style={{ flex: '1', textAlign: 'center' }}>
              <div style={{ fontWeight: 'bold', color: 'white', fontSize: '16px' }}>
                {employeeData?.name || 'Mitarbeiter'}
              </div>
              <div style={{ color: '#e2e8f0', fontSize: '12px' }}>
                Pers.Nr: {employeeData?.personal_nr || '-'}
              </div>
            </div>
            <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              {canAccessAdmin && (
                <button onClick={() => navigate('/admin')} className="px-4 py-2 rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#3b82f6' }}>
                  <Shield size={20} className="inline mr-1" />
                  Verwaltung
                </button>
              )}
              <button onClick={handleLogout} className="px-6 py-2 rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#f5a623' }}>
                <LogOut size={20} className="inline mr-2" />
                Logout
              </button>
            </div>
          </div>
        </div>

        {/* TAB-INHALT */}
        <div className="bg-white rounded-2xl shadow-xl p-8" style={{ marginBottom: '20px' }}>
          {activeTab === 'stempeluhr' ? (
            <>
              {hasCAssignments ? (
                <>
                  {/* Bie2 Stempeluhr - OHNE alte Oberfläche */}
                  <div className="text-center mb-4">
                    <div style={{ fontSize: '48px', fontWeight: 'bold', color: '#1e3a5f' }}>{currentTime.toLocaleTimeString('de-DE')}</div>
                    <div style={{ fontSize: '15px', color: '#666' }}>{currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
                  </div>
                  <Bie2Stempeluhr token={token} onStatusChange={() => { fetchTodayHours(); fetchWeekHours(); fetchMonthHours(); }} onLogout={handleLogout} />
                </>
              ) : (
                <>
                  {/* Alte Kat-C Stempeluhr mit GPS */}
                  <h2 style={{ textAlign: 'center', color: '#6c757d', fontSize: '16px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '16px' }}>Zeiterfassung</h2>
                  <div className="text-center mb-6">
                    <div style={{ fontSize: '60px', fontWeight: 'bold', color: '#1e3a5f' }}>{currentTime.toLocaleTimeString('de-DE')}</div>
                    <div style={{ fontSize: '16px', color: '#666' }}>{currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
                  </div>

                  {infoMessage && (
                    <div style={{ background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '8px', padding: '12px', marginBottom: '16px', textAlign: 'center' }}>
                      <Info size={20} className="inline mr-2" style={{ color: '#f59e0b' }} />
                      <span style={{ color: '#92400e' }}>{infoMessage}</span>
                    </div>
                  )}

                  {isWorking ? (
                    <>
                      <div style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #2c5f7c 100%)', borderRadius: '16px', padding: '24px', marginBottom: '24px', color: 'white', textAlign: 'center' }}>
                        <div style={{ fontSize: '20px', marginBottom: '8px' }}>ARBEITSZEIT LÄUFT</div>
                        <div style={{ fontSize: '48px', fontWeight: 'bold', fontFamily: 'monospace' }}>{calculateWorkTime()}</div>
                        <div style={{marginTop: '16px', padding: '16px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '8px'}}>
                          <div style={{fontWeight: 'bold'}}>
                            <Building size={16} className="inline mr-2" />
                            Objekt: {scheduledObjects.find(o => o.id === selectedObject)?.name || 'Unbekannt'}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                        <button onClick={handleCheckOut} style={{ flex: '2', padding: '14px', background: '#dc2626', color: 'white', fontSize: '16px', fontWeight: 'bold', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><Square size={24} /> ARBEIT BEENDEN</button>
                        {!isPaused ? (
                          <button onClick={handlePauseStart} style={{ flex: '1', background: '#6c757d', color: 'white', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><Pause size={24} /> PAUSE</button>
                        ) : (
                          <button onClick={handlePauseEnd} style={{ flex: '1', background: '#10b981', color: 'white', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><PlayCircle size={24} /> WEITER</button>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="mb-4">
                        <label style={{fontSize: '14px', color: '#666', display: 'block', marginBottom: '8px'}}>
                          Objekt wählen:
                        </label>
                        <select
                          value={selectedObject || ''}
                          onChange={(e) => setSelectedObject(parseInt(e.target.value))}
                          style={{
                            width: '100%',
                            padding: '12px',
                            fontSize: '16px',
                            border: '2px solid #e0e0e0',
                            borderRadius: '8px'
                          }}
                        >
                          {scheduledObjects.map((obj) => (
                            <option key={obj.id} value={obj.id}>
                              {obj.name.split('(')[0].trim()}
                            </option>
                          ))}
                        </select>
                        {currentObject?.start_time && (
                          <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                            Geplante Zeit: {currentObject.start_time} - {currentObject.end_time}
                          </div>
                        )}
                      </div>

                      <button onClick={handleCheckIn} style={{ width: '100%', padding: '16px', background: '#1e3a5f', color: 'white', fontSize: '18px', fontWeight: 'bold', borderRadius: '16px', border: 'none' }}>
                        <Play size={24} className="inline mr-3" /> ARBEIT BEGINNEN
                      </button>
                    </>
                  )}
                </>
              )}
              <div style={{marginTop: '32px', paddingTop: '24px', borderTop: '2px solid #e0e0e0'}}>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px'}}>
                  <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}><span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#e0f2fe' }}><Clock size={18} color="#0ea5e9" /></span><span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Heute</span></div>
                    <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(todayHours)}</div>
                  </div>
                  <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}><span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#dcfce7' }}><Calendar size={18} color="#22c55e" /></span><span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Diese Woche</span></div>
                    <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(weekHours)}</div>
                  </div>
                  <div style={{ background: '#f8f9fa', padding: '16px', borderRadius: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}><span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', borderRadius: '50%', backgroundColor: '#ffedd5' }}><Building size={18} color="#f97316" /></span><span style={{ fontSize: '14px', color: '#666', fontWeight: '500' }}>Dieser Monat</span></div>
                    <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#1e3a5f' }}>{formatHours(monthHours)}</div>
                  </div>
                  <div style={{ background: 'linear-gradient(135deg, #f5a623 0%, #f7b733 100%)', padding: '16px', borderRadius: '12px', color: 'white', textAlign: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}><span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', borderRadius: '50%', backgroundColor: 'rgba(255, 255, 255, 0.2)' }}><Gauge size={18} color="white" /></span><span style={{ fontSize: '14px', fontWeight: '500' }}>Seit Beginn</span></div>
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
				{(() => {
				  if (employeeTachoData && employeeTachoData.total_hours_since_start) {
					const total = employeeTachoData.total_hours_since_start;
					const h = Math.floor(total);
					const m = Math.round((total % 1) * 60);
					return `${h} Std ${m} Min`;
				  }
				  return '0 Std 0 Min';
				})()}
					</div>
                  </div>
                </div>
              </div>
            </>
          ) : activeTab === 'historie' ? (
            <HistoryTab />
          ) : activeTab === 'kilometer' ? (
            <KilometerTab />
          ) : activeTab === 'dienstplan' ? (
            <DienstplanTab token={token} />
          ) : activeTab === 'urlaub' ? (
            <VacationTab token={token} />
          ) : activeTab === 'schichtaenderung' ? (
            <ShiftChangeForm />
          ) : activeTab === 'nachrichten' ? (
            <NachrichtenTab />
          ) : activeTab === 'selbstbuchung' ? (
            <SelbstbuchungTab />
          ) : null}

        </div>

        {/* BOTTOM NAVIGATION */}
        <BottomNav categoryLabel="Stempel" />
      </div>

      {/* SCHICHT-MODAL (Kat C) */}
      {showShiftModal && selectedShift && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', zIndex: 9999,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '16px',
        }} onClick={() => setShowShiftModal(false)}>
          <div style={{
            background: 'white', borderRadius: '16px', width: '100%', maxWidth: '400px',
            padding: '24px', position: 'relative', maxHeight: '90vh', overflowY: 'auto',
          }} onClick={e => e.stopPropagation()}>
            <button onClick={() => setShowShiftModal(false)} style={{
              position: 'absolute', top: '12px', right: '12px', background: 'none',
              border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '4px',
            }}><CloseIcon size={20} /></button>

            <div style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '4px' }}>
                {selectedShift.object_name}
              </div>
              <div style={{ fontSize: '15px', color: '#374151' }}>
                {new Date(selectedShift.date).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
              </div>
              <div style={{ fontSize: '15px', color: '#6b7280', marginTop: '2px' }}>
                {selectedShift.start_time} - {selectedShift.end_time} Uhr ({selectedShift.planned_hours}h)
              </div>
            </div>

            {shiftRequestSent && (
              <div style={{
                background: cancelReason === 'Krank' ? '#fef2f2' : '#dcfce7',
                color: cancelReason === 'Krank' ? '#991b1b' : '#166534',
                padding: '12px 16px', borderRadius: '10px', marginBottom: '16px', fontSize: '14px',
                display: 'flex', alignItems: 'flex-start', gap: '8px',
              }}>
                <span style={{ fontSize: '18px', flexShrink: 0 }}>
                  {cancelReason === 'Krank' ? '\u{1F3E5}' : '\u2705'}
                </span>
                <span>{confirmationMessage}</span>
              </div>
            )}

            {!shiftRequestSent && !showCancelReasons && !showSwapFlow && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button onClick={() => { setShowSwapFlow(true); loadShiftColleagues(selectedShift.object_id); }} style={{
                  background: '#3b82f6', color: 'white', border: 'none', borderRadius: '10px',
                  padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                }}>{'\u{1F504}'} Schicht tauschen</button>
                <button onClick={() => setShowCancelReasons(true)} style={{
                  background: '#ef4444', color: 'white', border: 'none', borderRadius: '10px',
                  padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                }}>{'\u274C'} Kann nicht kommen</button>
                <button onClick={() => setShowShiftModal(false)} style={{
                  background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: '10px',
                  padding: '14px', fontSize: '15px', fontWeight: '500', cursor: 'pointer',
                }}>OK</button>
              </div>
            )}

            {!shiftRequestSent && showSwapFlow && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>Mit wem tauschen?</div>
                {loadingColleagues ? (
                  <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>Lade Kollegen...</div>
                ) : (
                  <>
                    {swapColleagues.map(c => (
                      <button key={c.id} disabled={sendingRequest} onClick={async () => {
                        setSendingRequest(true);
                        try {
                          const r = await axios.post(`${API_URL}/time-entries/shift-request`, {
                            schedule_id: selectedShift.schedule_id, request_type: 'swap', swap_with_employee_id: c.id,
                          }, { headers: { Authorization: `Bearer ${token}` } });
                          setConfirmationMessage(r.data.message || 'Tauschanfrage gesendet!'); setShiftRequestSent(true);
                        } catch (e) { console.error(e); }
                        setSendingRequest(false);
                      }} style={{ background: '#eff6ff', color: '#1e40af', border: '1px solid #bfdbfe', borderRadius: '10px',
                        padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center' }}>
                        {'\u{1F464}'} {c.name}
                      </button>
                    ))}
                    {swapColleagues.length === 0 && <div style={{ textAlign: 'center', padding: '12px', color: '#6b7280', fontSize: '14px' }}>Keine Kollegen an diesem Objekt gefunden</div>}
                    <button disabled={sendingRequest} onClick={async () => {
                      setSendingRequest(true);
                      try {
                        const r = await axios.post(`${API_URL}/time-entries/shift-request`, {
                          schedule_id: selectedShift.schedule_id, request_type: 'swap', swap_with_employee_id: null,
                        }, { headers: { Authorization: `Bearer ${token}` } });
                        setConfirmationMessage(r.data.message || 'Tauschanfrage gesendet!'); setShiftRequestSent(true);
                      } catch (e) { console.error(e); }
                      setSendingRequest(false);
                    }} style={{ background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a', borderRadius: '10px',
                      padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer' }}>
                      {'\u{1F4E2}'} Admin soll Vertretung organisieren
                    </button>
                    <button onClick={() => setShowSwapFlow(false)} style={{ background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px', padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px' }}>Zurueck</button>
                  </>
                )}
              </div>
            )}

            {!shiftRequestSent && showCancelReasons && !showSickDuration && !showCustomReason && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>Grund angeben:</div>
                <button onClick={() => { setCancelReason('Krank'); setShowSickDuration(true); }} style={{ background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center' }}>{'\u{1F912}'} Krank</button>
                <button disabled={sendingRequest} onClick={async () => {
                  setSendingRequest(true); setCancelReason('Privat');
                  try { const r = await axios.post(`${API_URL}/time-entries/shift-request`, { schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Privat' }, { headers: { Authorization: `Bearer ${token}` } }); setConfirmationMessage(r.data.message); setShiftRequestSent(true); } catch (e) { console.error(e); }
                  setSendingRequest(false);
                }} style={{ background: '#fffbeb', color: '#d97706', border: '1px solid #fde68a', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center' }}>{'\u{1F3E0}'} Privat</button>
                <button onClick={() => { setCancelReason('Sonstiges'); setShowCustomReason(true); }} style={{ background: '#f0f9ff', color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer', textAlign: 'center' }}>{'\u{1F4DD}'} Sonstiges</button>
                <button onClick={() => setShowCancelReasons(false)} style={{ background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px', padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px' }}>Zurueck</button>
              </div>
            )}

            {!shiftRequestSent && showSickDuration && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>{'\u{1F912}'} Wie lange krank?</div>
                <button disabled={sendingRequest} onClick={async () => { setSendingRequest(true); try { const r = await axios.post(`${API_URL}/time-entries/shift-request`, { schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank', sick_from: selectedShift.date, sick_until: selectedShift.date }, { headers: { Authorization: `Bearer ${token}` } }); setConfirmationMessage(r.data.message); setShiftRequestSent(true); } catch (e) { console.error(e); } setSendingRequest(false); }} style={{ background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer' }}>Nur diesen Tag</button>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '13px', color: '#374151', fontWeight: '500' }}>Ab heute bis:</label>
                  <input type="date" value={sickUntilDate} onChange={(e) => setSickUntilDate(e.target.value)} min={selectedShift.date} style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box' }} />
                  {sickUntilDate && <button disabled={sendingRequest} onClick={async () => { setSendingRequest(true); try { const r = await axios.post(`${API_URL}/time-entries/shift-request`, { schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank', sick_from: selectedShift.date, sick_until: sickUntilDate }, { headers: { Authorization: `Bearer ${token}` } }); setConfirmationMessage(r.data.message); setShiftRequestSent(true); } catch (e) { console.error(e); } setSendingRequest(false); }} style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer' }}>Krankmeldung senden</button>}
                </div>
                <button disabled={sendingRequest} onClick={async () => { setSendingRequest(true); try { const r = await axios.post(`${API_URL}/time-entries/shift-request`, { schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Krank', sick_from: selectedShift.date, sick_until: null }, { headers: { Authorization: `Bearer ${token}` } }); setConfirmationMessage(r.data.message); setShiftRequestSent(true); } catch (e) { console.error(e); } setSendingRequest(false); }} style={{ background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer' }}>Weiss noch nicht</button>
                <button onClick={() => setShowSickDuration(false)} style={{ background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px', padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px' }}>Zurueck</button>
              </div>
            )}

            {!shiftRequestSent && showCustomReason && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ fontSize: '14px', fontWeight: '600', color: '#374151', marginBottom: '4px' }}>{'\u{1F4DD}'} Grund angeben:</div>
                <textarea value={customReasonText} onChange={(e) => setCustomReasonText(e.target.value)} placeholder="Beschreibe kurz den Grund..." style={{ width: '100%', padding: '12px', borderRadius: '10px', border: '1px solid #d1d5db', fontSize: '15px', minHeight: '80px', resize: 'vertical', fontFamily: 'inherit', boxSizing: 'border-box' }} />
                <button disabled={sendingRequest || !customReasonText.trim()} onClick={async () => { setSendingRequest(true); try { const r = await axios.post(`${API_URL}/time-entries/shift-request`, { schedule_id: selectedShift.schedule_id, request_type: 'cancel', reason: 'Sonstiges', custom_reason: customReasonText }, { headers: { Authorization: `Bearer ${token}` } }); setConfirmationMessage(r.data.message); setShiftRequestSent(true); } catch (e) { console.error(e); } setSendingRequest(false); }} style={{ background: !customReasonText.trim() ? '#9ca3af' : '#2563eb', color: 'white', border: 'none', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '600', cursor: 'pointer' }}>Nachricht senden</button>
                <button onClick={() => { setShowCustomReason(false); setCustomReasonText(''); }} style={{ background: '#f3f4f6', color: '#6b7280', border: 'none', borderRadius: '10px', padding: '12px', fontSize: '14px', cursor: 'pointer', marginTop: '4px' }}>Zurueck</button>
              </div>
            )}

            {shiftRequestSent && (
              <button onClick={() => setShowShiftModal(false)} style={{ background: '#f3f4f6', color: '#374151', border: 'none', borderRadius: '10px', padding: '14px', fontSize: '15px', fontWeight: '500', cursor: 'pointer', width: '100%' }}>Schliessen</button>
            )}
          </div>
        </div>
      )}

      {/* Cap-Decision Dialog — nicht schließbar */}
      {showCapDialog && capDialogData && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}>
          <div style={{ background: 'white', borderRadius: '20px', padding: '28px', maxWidth: '400px', width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <AlertCircle size={48} color="#f59e0b" style={{ marginBottom: '12px' }} />
              <h3 style={{ margin: 0, fontSize: '18px', color: '#1e3a5f' }}>Arbeitszeit-Hinweis</h3>
            </div>
            <div style={{ background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '12px', padding: '16px', marginBottom: '20px', textAlign: 'center' }}>
              <div style={{ fontSize: '15px', color: '#92400e', lineHeight: '1.5' }}>
                Du hast <strong>{capDialogData.excess_minutes} Minuten</strong> laenger gearbeitet als im Dienstplan vorgesehen.
              </div>
              <div style={{ fontSize: '13px', color: '#b45309', marginTop: '8px' }}>
                Schicht: {capDialogData.schedule_str}
              </div>
            </div>

            {/* Button 1: Passt so */}
            <button
              disabled={capSubmitting}
              onClick={() => handleCapDecision('accept_cap')}
              style={{
                width: '100%', padding: '14px', marginBottom: '10px',
                background: capSubmitting ? '#9ca3af' : '#1e3a5f', color: 'white',
                fontSize: '15px', fontWeight: '600', borderRadius: '12px', border: 'none', cursor: 'pointer'
              }}
            >
              {capDialogData.planned_h != null
                ? `Passt so \u2013 ${capDialogData.planned_h} Std ${String(capDialogData.planned_m || 0).padStart(2, '0')} Min buchen`
                : 'Passt so \u2013 Dienstplan-Zeit buchen'}
            </button>

            {/* Button 2: Laenger gearbeitet */}
            <button
              disabled={capSubmitting}
              onClick={() => setCapOvertimeReason(capOvertimeReason || ' ')}
              style={{
                width: '100%', padding: '14px', marginBottom: '10px',
                background: 'white', color: '#dc2626',
                fontSize: '15px', fontWeight: '600', borderRadius: '12px',
                border: '2px solid #dc2626', cursor: 'pointer',
                display: capOvertimeReason ? 'none' : 'block'
              }}
            >
              Ich habe laenger gearbeitet
            </button>

            {/* Grund-Eingabe (erscheint nach Klick auf Button 2) */}
            {capOvertimeReason !== '' && (
              <div style={{ marginTop: '4px' }}>
                <label style={{ fontSize: '14px', fontWeight: '600', color: '#374151', display: 'block', marginBottom: '6px' }}>
                  Bitte Grund angeben (mind. 10 Zeichen):
                </label>
                <textarea
                  value={capOvertimeReason.trim() === '' ? '' : capOvertimeReason}
                  onChange={(e) => setCapOvertimeReason(e.target.value)}
                  placeholder="z.B. Kunde brauchte laengere Reinigung..."
                  style={{
                    width: '100%', padding: '12px', borderRadius: '10px',
                    border: '1px solid #d1d5db', fontSize: '15px',
                    minHeight: '80px', resize: 'vertical', fontFamily: 'inherit',
                    boxSizing: 'border-box'
                  }}
                />
                <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
                  <button
                    disabled={capSubmitting || capOvertimeReason.trim().length < 10}
                    onClick={() => handleCapDecision('request_overtime')}
                    style={{
                      flex: 1, padding: '14px',
                      background: capOvertimeReason.trim().length < 10 ? '#9ca3af' : '#dc2626',
                      color: 'white', fontSize: '15px', fontWeight: '600',
                      borderRadius: '12px', border: 'none', cursor: 'pointer'
                    }}
                  >
                    {capSubmitting ? 'Wird gesendet...' : 'Mehrzeit anfragen'}
                  </button>
                  <button
                    disabled={capSubmitting}
                    onClick={() => setCapOvertimeReason('')}
                    style={{
                      padding: '14px 20px', background: '#f3f4f6', color: '#6b7280',
                      fontSize: '14px', borderRadius: '12px', border: 'none', cursor: 'pointer'
                    }}
                  >
                    Zurueck
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;