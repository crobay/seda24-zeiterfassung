import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LogOut, Play, Square, Pause, Building, User, Clock, Calendar, Star, CheckCircle, AlertCircle, Gauge, Users, PlayCircle, ChevronsRight, Shield, UserCheck, Info } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import HistoryTab from "../components/HistoryTab";

const Dashboard = () => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [activeTab, setActiveTab] = useState('stempeluhr');
  const [isWorking, setIsWorking] = useState(false);
  const [workStartTime, setWorkStartTime] = useState(null);
  const [todayHours, setTodayHours] = useState(0);
  const [weekHours, setWeekHours] = useState(0);
  const [monthHours, setMonthHours] = useState(0);
  const [totalHours, setTotalHours] = useState(0);
  const [selectedObject, setSelectedObject] = useState(null);
  const [workingWithColleague, setWorkingWithColleague] = useState(false);
  const [selectedColleague, setSelectedColleague] = useState('');
  const [serviceType, setServiceType] = useState('Unterhaltsreinigung');
  const [buttonText, setButtonText] = useState('ICH WAR HEUTE ANWESEND');
  
  // NEU: Geplante Objekte aus Dienstplan
  const [scheduledObjects, setScheduledObjects] = useState([]);
  const [hasWorkToday, setHasWorkToday] = useState(false);
  const [infoMessage, setInfoMessage] = useState('');
  
  // Kategorie des Mitarbeiters
  const [employeeCategory, setEmployeeCategory] = useState('C');
  const [employeeData, setEmployeeData] = useState(null);
  const [loadingCategory, setLoadingCategory] = useState(true);
  
  // States für die Pause
  const [isPaused, setIsPaused] = useState(false);
  const [pauseId, setPauseId] = useState(null);
  const [pauseStartTime, setPauseStartTime] = useState(null);
  const [totalPauseTime, setTotalPauseTime] = useState(0);

  const navigate = useNavigate();
  const API_URL = 'https://192.168.178.87:8001/api/v1';
  const token = localStorage.getItem('token');

  // Fallback Objekte falls Dienstplan nicht lädt
  const fallbackObjects = {
    1: { name: 'SEDA24 Zentrale' },
    3: { name: 'Lidl Muggensturmer Str' },
    4: { name: 'Lidl Wochenende' },
    5: { name: 'Enfido Sonnenschein' },
    6: { name: 'Metalicone Muggensturm' },
    7: { name: 'JU_RA Baden-Baden' },
    8: { name: 'Huber Iffezheim' },
    9: { name: 'BAD-Treppen' },
    11: { name: 'Leible Rheinmünster' },
    12: { name: 'Zinsfabrik Baden-Baden' },
    13: { name: 'Polytec Rastatt' },
    14: { name: 'Steuerberater Baden-Baden' },
    15: { name: 'Geiger Malsch' },
    16: { name: 'Rytec Baden-Baden' }
  };

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    fetchEmployeeCategory();
    loadScheduledObjects();
    checkStatus();
    fetchTodayHours();
    fetchWeekHours();
    fetchMonthHours();
  }, []);

  useEffect(() => {
    const baseHours = 2856;
    setTotalHours(baseHours + monthHours);
  }, [monthHours]);

  const fetchEmployeeCategory = async () => {
    try {
      setLoadingCategory(true);
      const response = await axios.get(`${API_URL}/employees/my-category`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      setEmployeeCategory(response.data.tracking_mode || 'C');
      setEmployeeData(response.data);
      console.log('Mitarbeiter-Kategorie:', response.data.tracking_mode);
    } catch (error) {
      console.error('Fehler beim Abrufen der Kategorie:', error);
      setEmployeeCategory('C');
    } finally {
      setLoadingCategory(false);
    }
  };

  // NEU: Lade nur geplante Objekte aus Dienstplan
  const loadScheduledObjects = async () => {
    try {
      // Versuche Dienstplan-Objekte zu laden
      const response = await axios.get(`${API_URL}/time-entries/my-objects-today`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.data && response.data.length > 0) {
        setScheduledObjects(response.data);
        // Setze erstes Objekt als Standard
        if (!selectedObject && response.data.length > 0) {
          setSelectedObject(response.data[0].id);
        }
        setInfoMessage('');
      } else {
        // Prüfe ob heute überhaupt Arbeitstag ist
        const workCheck = await axios.get(`${API_URL}/time-entries/has-work-today`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        
        if (!workCheck.data.has_work) {
          setInfoMessage('Heute ist kein Arbeitstag laut Dienstplan');
        } else {
          setInfoMessage('Keine Objekte für heute geplant');
        }
        
        // Fallback zu allen Objekten
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
      // Fallback wenn Endpoint nicht existiert
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

  const handleWarAnwesend = async () => {
  try {
    console.log('Sende Leistungsart:', serviceType); // DEBUG-ZEILE
    
    const response = await axios.post(
      `${API_URL}/time-entries/war-anwesend`,
      { 
        object_id: parseInt(selectedObject), 
        service_type: serviceType 
      },
      { headers: { Authorization: `Bearer ${token}` }}
    );
    
    console.log('Antwort vom Server:', response.data); // DEBUG-ZEILE
    
    setButtonText(`✅ ${response.data.scheduled_hours}h gebucht!`);
    setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 3000);
    
    fetchTodayHours();
    fetchWeekHours();
    fetchMonthHours();
  } catch (error) {
    if (error.response?.status === 400 && error.response?.data?.detail?.includes('bereits Stunden')) {
      setButtonText('❌ Bereits gebucht!');
      setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 3000);
    } else {
      console.error('Fehler:', error); // DEBUG-ZEILE
      setButtonText('❌ Fehler!');
      setTimeout(() => setButtonText('ICH WAR HEUTE ANWESEND'), 3000);
    }
  }
};

  const handleCheckIn = async () => {
    try {
      const notes = workingWithColleague ? `Arbeitsbeginn (zu zweit mit ${selectedColleague})` : "Arbeitsbeginn";
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
      await axios.post(`${API_URL}/time-entries/check-out`, {}, { 
        headers: { Authorization: `Bearer ${token}` }
      });
      checkStatus();
      fetchTodayHours();
      fetchWeekHours();
      fetchMonthHours();
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
    navigate('/login');
  };

  // Finde aktuell gewähltes Objekt
  const currentObject = scheduledObjects.find(obj => obj.id === selectedObject);

  // Lade-Zustand
  if (loadingCategory) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: '#1e3a5f' }}>
        <div className="text-white text-xl">Lade Mitarbeiterdaten...</div>
      </div>
    );
  }

  // KATEGORIE A: Vollautomatisch
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
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end' }}>
                <button onClick={handleLogout} className="px-6 py-2 rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#f5a623' }}>
                  <LogOut size={20} className="inline mr-2" />
                  Logout
                </button>
              </div>
            </div>
          </div>

          {/* TAB-NAVIGATION */}
          <div className="bg-white rounded-t-2xl shadow-xl p-4">
            <div className="flex gap-2">
              <button onClick={() => setActiveTab('stempeluhr')} 
                style={{padding: '10px 20px', borderRadius: '8px', border: 'none',
                  backgroundColor: activeTab === 'stempeluhr' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'stempeluhr' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
                Übersicht
              </button>
              <button onClick={() => setActiveTab('historie')}
                style={{padding: '10px 20px', borderRadius: '8px', border: 'none', 
                  backgroundColor: activeTab === 'historie' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'historie' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
                Historie
              </button>
            </div>
          </div>

          {/* TAB-INHALT */}
          <div className="bg-white rounded-b-2xl shadow-xl p-8">
            {activeTab === 'stempeluhr' ? (
              <>
                <div className="text-center mb-6">
                  <div style={{ fontSize: '60px', fontWeight: 'bold', color: '#1e3a5f' }}>
                    {currentTime.toLocaleTimeString('de-DE')}
                  </div>
                  <div style={{ fontSize: '18px', color: '#666' }}>
                    {currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </div>
                </div>

                {/* INFO BOX */}
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

                {/* STUNDEN-ÜBERSICHT */}
                <div style={{marginTop: '32px', paddingTop: '24px', borderTop: '2px solid #e0e0e0'}}>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px'}}>
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
                      <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{formatTotalHours(totalHours)}</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <HistoryTab />
            )}
          </div>
        </div>
      </div>
    );
  }

  // KATEGORIE B: War-Anwesend Button
  if (employeeCategory === 'B') {
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
              <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end' }}>
                <button onClick={handleLogout} className="px-6 py-2 rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#f5a623' }}>
                  <LogOut size={20} className="inline mr-2" />
                  Logout
                </button>
              </div>
            </div>
          </div>

          {/* TAB-NAVIGATION */}
          <div className="bg-white rounded-t-2xl shadow-xl p-4">
            <div className="flex gap-2">
              <button onClick={() => setActiveTab('stempeluhr')} 
                style={{padding: '10px 20px', borderRadius: '8px', border: 'none',
                  backgroundColor: activeTab === 'stempeluhr' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'stempeluhr' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
                Stempeluhr
              </button>
              <button onClick={() => setActiveTab('historie')}
                style={{padding: '10px 20px', borderRadius: '8px', border: 'none', 
                  backgroundColor: activeTab === 'historie' ? '#1e3a5f' : '#f8f9fa',
                  color: activeTab === 'historie' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
                Historie
              </button>
            </div>
          </div>

          {/* TAB-INHALT */}
          <div className="bg-white rounded-b-2xl shadow-xl p-8">
            {activeTab === 'stempeluhr' ? (
              <>
                <div className="text-center mb-6">
                  <div style={{ fontSize: '60px', fontWeight: 'bold', color: '#1e3a5f' }}>
                    {currentTime.toLocaleTimeString('de-DE')}
                  </div>
                  <div style={{ fontSize: '18px', color: '#666' }}>
                    {currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </div>
                </div>

                {/* Info-Nachricht wenn keine Arbeit heute */}
                {infoMessage && (
                  <div style={{ background: '#fef3c7', border: '1px solid #fbbf24', borderRadius: '8px', padding: '12px', marginBottom: '16px', textAlign: 'center' }}>
                    <Info size={20} className="inline mr-2" style={{ color: '#f59e0b' }} />
                    <span style={{ color: '#92400e' }}>{infoMessage}</span>
                  </div>
                )}

                {/* OBJEKT-AUSWAHL - Nur geplante Objekte */}
                <div className="mb-6">
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
                        {obj.name}
                        {obj.is_scheduled_today && ' ⭐ HEUTE'}
                        {obj.planned_hours && ` (${obj.planned_hours}h geplant)`}
                      </option>
                    ))}
                  </select>
                  {currentObject?.start_time && (
                    <div style={{ fontSize: '12px', color: '#666', marginTop: '4px' }}>
                      Geplante Zeit: {currentObject.start_time} - {currentObject.end_time}
                    </div>
                  )}
                </div>

                {/* Zu zweit arbeiten */}
                <div style={{ background: '#f8f9fa', borderRadius: '8px', padding: '16px', marginBottom: '24px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                    <input type="checkbox" checked={workingWithColleague} onChange={(e) => setWorkingWithColleague(e.target.checked)} 
                      style={{ marginRight: '12px', width: '20px', height: '20px' }} />
                    <span style={{ fontSize: '16px', color: '#333' }}>
                      <Users size={20} className="inline mr-2" /> Zu zweit arbeiten
                    </span>
                  </label>
                  {workingWithColleague && (
                    <select value={selectedColleague} onChange={(e) => setSelectedColleague(e.target.value)} 
                      style={{ width: '100%', marginTop: '12px', padding: '10px', fontSize: '16px', border: '1px solid #e0e0e0', borderRadius: '6px' }}>
                      <option value="">Kollegen wählen...</option>
                      <option value="Ruza (D0002)">Ruza Sertic</option>
                      <option value="Ljubica (D0004)">Ljubica Stjepic</option>
                      <option value="Matej (D0021)">Matej Stjepic</option>
                    </select>
                  )}
                </div>

                {/* WAR ANWESEND BUTTON */}
                <button 
                  onClick={handleWarAnwesend}
                  style={{ 
                    width: '100%', 
                    padding: '32px', 
                    background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)', 
                    color: 'white', 
                    fontSize: '24px', 
                    fontWeight: 'bold', 
                    borderRadius: '16px', 
                    border: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '12px'
                  }}
                >
                  <UserCheck size={32} />
                  {buttonText}
                </button>

                {/* Leistungsart dezent mit Dropdown */}
                <div style={{ marginTop: '8px', textAlign: 'center', fontSize: '12px', color: '#666' }}>
                  <span>Leistung: </span>
                  <select 
                    value={serviceType} 
                    onChange={(e) => setServiceType(e.target.value)}
                    style={{ 
                      fontSize: '12px', 
                      padding: '2px 4px', 
                      border: '1px solid #e0e0e0', 
                      borderRadius: '4px',
                      background: serviceType === 'Unterhaltsreinigung' ? 'white' : '#fef3c7'
                    }}
                  >
                    <option value="Unterhaltsreinigung">Unterhaltsreinigung (15€/Std)</option>
                    <option value="Fensterreinigung">Fensterreinigung (20€/Std)</option>
                    <option value="Grundreinigung">Grundreinigung (20€/Std)</option>
                  </select>
                </div>

                <div style={{ 
                  marginTop: '16px', 
                  padding: '16px', 
                  background: '#f0f9ff', 
                  borderRadius: '8px',
                  border: '1px solid #bfdbfe'
                }}>
                  <div style={{ fontSize: '14px', color: '#1e40af', textAlign: 'center' }}>
                    💡 <strong>Hinweis:</strong> Ein Klick bucht deine kompletten Sollstunden für heute.
                    Du kannst jedes Objekt einmal pro Tag buchen.
                  </div>
                </div>

                {/* STUNDEN-ÜBERSICHT */}
                <div style={{marginTop: '32px', paddingTop: '24px', borderTop: '2px solid #e0e0e0'}}>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px'}}>
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
                      <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{formatTotalHours(totalHours)}</div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <HistoryTab />
            )}
          </div>
        </div>
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
            <div style={{ flex: '1', display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={handleLogout} className="px-6 py-2 rounded-lg text-white transition-all hover:scale-105" style={{ backgroundColor: '#f5a623' }}>
                <LogOut size={20} className="inline mr-2" />
                Logout
              </button>
            </div>
          </div>
        </div>

        {/* TAB-NAVIGATION */}
        <div className="bg-white rounded-t-2xl shadow-xl p-4">
          <div className="flex gap-2">
            <button onClick={() => setActiveTab('stempeluhr')} 
              style={{padding: '10px 20px', borderRadius: '8px', border: 'none',
                backgroundColor: activeTab === 'stempeluhr' ? '#1e3a5f' : '#f8f9fa',
                color: activeTab === 'stempeluhr' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
              Stempeluhr
            </button>
            <button onClick={() => setActiveTab('historie')}
              style={{padding: '10px 20px', borderRadius: '8px', border: 'none', 
                backgroundColor: activeTab === 'historie' ? '#1e3a5f' : '#f8f9fa',
                color: activeTab === 'historie' ? 'white' : '#666', fontWeight: 'bold', cursor: 'pointer'}}>
              Historie
            </button>
          </div>
        </div>

        {/* TAB-INHALT */}
        <div className="bg-white rounded-b-2xl shadow-xl p-8">
          {activeTab === 'stempeluhr' ? (
            <>
              <h2 style={{ textAlign: 'center', color: '#6c757d', fontSize: '16px', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '16px' }}>Zeiterfassung</h2>
              <div className="text-center mb-6">
                <div style={{ fontSize: '60px', fontWeight: 'bold', color: '#1e3a5f' }}>{currentTime.toLocaleTimeString('de-DE')}</div>
                <div style={{ fontSize: '18px', color: '#666' }}>{currentTime.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</div>
              </div>

              {/* Info-Nachricht wenn keine Arbeit heute */}
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
                      {workingWithColleague && selectedColleague && (<div style={{ fontSize: '14px', marginTop: '8px' }}><Users size={16} className="inline mr-2" /> Mit: {selectedColleague}</div>)}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
                    <button onClick={handleCheckOut} style={{ flex: '2', padding: '20px', background: '#f5a623', color: 'white', fontSize: '18px', fontWeight: 'bold', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><Square size={24} /> ARBEIT BEENDEN</button>
                    {!isPaused ? (
                      <button onClick={handlePauseStart} style={{ flex: '1', background: '#6c757d', color: 'white', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><Pause size={24} /> PAUSE</button>
                    ) : (
                      <button onClick={handlePauseEnd} style={{ flex: '1', background: '#10b981', color: 'white', borderRadius: '12px', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}><PlayCircle size={24} /> WEITER</button>
                    )}
                  </div>
                </>
              ) : (
                <>
                  {/* OBJEKT-AUSWAHL - Nur geplante Objekte */}
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

                  <div style={{ background: '#f8f9fa', borderRadius: '8px', padding: '16px', marginBottom: '24px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
                      <input type="checkbox" checked={workingWithColleague} onChange={(e) => setWorkingWithColleague(e.target.checked)} style={{ marginRight: '12px', width: '20px', height: '20px' }} />
                      <span style={{ fontSize: '16px', color: '#333' }}><Users size={20} className="inline mr-2" /> Zu zweit arbeiten</span>
                    </label>
                    {workingWithColleague && (
                      <select value={selectedColleague} onChange={(e) => setSelectedColleague(e.target.value)} style={{ width: '100%', marginTop: '12px', padding: '10px', fontSize: '16px', border: '1px solid #e0e0e0', borderRadius: '6px' }}>
                        <option value="">Kollegen wählen...</option>
                        <option value="Ruza (D0002)">Ruza Sertic</option>
                        <option value="Ljubica (D0004)">Ljubica Stjepic</option>
                        <option value="Matej (D0021)">Matej Stjepic</option>
                        <option value="Eldina (D0005)">Eldina Mustafic</option>
                        <option value="Jana (D0022)">Jana Bojko</option>
                        <option value="Eliane (D0031)">Eliane DaSilvaTodaro</option>
                        <option value="Andy (D0032)">Andreas Frosch</option>
                        <option value="Sonja (D0034)">Sonja Mullak</option>
                      </select>
                    )}
                  </div>
                  <button onClick={handleCheckIn} style={{ width: '100%', padding: '32px', background: '#1e3a5f', color: 'white', fontSize: '24px', fontWeight: 'bold', borderRadius: '16px', border: 'none' }}>
                    <Play size={32} className="inline mr-3" /> ARBEIT BEGINNEN
                  </button>
                </>
              )}
              <div style={{marginTop: '32px', paddingTop: '24px', borderTop: '2px solid #e0e0e0'}}>
                <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px'}}>
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
                    <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{formatTotalHours(totalHours)}</div>
                  </div>
                </div>
              </div>
            </>
          ) : (
            <HistoryTab />
          )}
        </div>
      </div>
    </div>
  );
};

export default Dashboard;