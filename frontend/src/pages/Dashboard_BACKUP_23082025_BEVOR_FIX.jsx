import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LogOut, Play, Square, Pause, PlayCircle, MapPin, AlertCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const Dashboard = () => {
  const [currentTime, setCurrentTime] = useState(new Date());
  const [isWorking, setIsWorking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [pauseId, setPauseId] = useState(null);
  const [workStartTime, setWorkStartTime] = useState(null);
  const [pauseStartTime, setPauseStartTime] = useState(null);
  const [totalPauseTime, setTotalPauseTime] = useState(0);
  const [todayHours, setTodayHours] = useState(0);
  const [weekHours, setWeekHours] = useState(0);
  const [monthHours, setMonthHours] = useState(0);
  const [overtimeHours, setOvertimeHours] = useState(0);
  const [selectedObject, setSelectedObject] = useState(1);

  // GPS-States
  const [userLocation, setUserLocation] = useState(null);
  const [locationError, setLocationError] = useState(null);
  const [isLoadingLocation, setIsLoadingLocation] = useState(false);
  const [autoPauseTriggered, setAutoPauseTriggered] = useState(false);
  
  // PWA States - NEU HINZUGEFÜGT
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstallable, setIsInstallable] = useState(false);

  const navigate = useNavigate();

  const API_URL = 'https://192.168.178.87:8001/api/v1';
  const token = localStorage.getItem('token');

  // ECHTE Objekt-Koordinaten für Gaggenau - AKTUALISIERT
const objectLocations = {
  1: { name: 'SEDA24 Zentrale', lat: 48.794968, lng: 8.310615 },
  3: { name: 'Lidl Muggensturmer Str', lat: 48.8888214774413, lng: 8.26481250682591 },
  4: { name: 'Lidl Wochenende', lat: 48.8888214774413, lng: 8.26481250682591 },
  5: { name: 'Enfido Sonnenschein', lat: 48.9090646883034, lng: 8.26101850482367 },
  6: { name: 'Metalicone Muggensturm', lat: 48.8797133935092, lng: 8.28035636486564 },
  7: { name: 'JU_RA Baden-Baden', lat: 48.7612319749530, lng: 8.25051555347136 },
  8: { name: 'Huber Iffezheim', lat: 48.8167103890530, lng: 8.15985572143728 },
  9: { name: 'BAD-Treppen', lat: 48.7576771385761, lng: 8.24505946642259 },
  11: { name: 'Leible Rheinmünster', lat: 48.7498572046747, lng: 8.03728945082595 },
  12: { name: 'Zinsfabrik Baden-Baden', lat: 48.7664297331785, lng: 8.23475597645378 },
  13: { name: 'Polytec Rastatt', lat: 48.8657781551626, lng: 8.22110284976376 },
  14: { name: 'Steuerberater Baden-Baden', lat: 48.7611535126502, lng: 8.24928112428465 },
  15: { name: 'Geiger Malsch', lat: 48.8894361838853, lng: 8.31018689424884 },
  16: { name: 'Rytec Baden-Baden', lat: 48.7783217330924, lng: 8.20291705679789 }
};
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    checkStatus();
    fetchTodayHours();
    fetchWeekHours();
    fetchMonthHours();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      checkStatus();
      fetchTodayHours();
      fetchWeekHours();
      fetchMonthHours();
    }, 300000); // 5 Minuten
    return () => clearInterval(interval);
  }, []);

  // Auto-Pause nach 6 Stunden
  useEffect(() => {
    if (isWorking && !isPaused && workStartTime) {
      const checkAutoPause = setInterval(() => {
        const workSeconds = (new Date() - workStartTime) / 1000 - totalPauseTime;
        const workHours = workSeconds / 3600;

        if (workHours >= 6 && !autoPauseTriggered) {
          setAutoPauseTriggered(true);
          handleAutoPause();
        }
      }, 60000); // Jede Minute prüfen

      return () => clearInterval(checkAutoPause);
    }
  }, [isWorking, isPaused, workStartTime, totalPauseTime, autoPauseTriggered]);

  // PWA Event Listeners - NEU HINZUGEFÜGT
  useEffect(() => {
    const handleBeforeInstallPrompt = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsInstallable(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    // Online/Offline Detection
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // GPS-Position abrufen

// GPS-Position abrufen
  const getCurrentLocation = () => {
    return new Promise((resolve, reject) => {
      setIsLoadingLocation(true);
      setLocationError(null);

      console.log("GPS: Starte Standortabfrage..."); // NEU

      if (!navigator.geolocation) {
        console.error("GPS: Browser unterstützt kein GPS"); // NEU
        setLocationError('GPS wird von diesem Browser nicht unterstützt');
        setIsLoadingLocation(false);
        reject('Geolocation not supported');
        return;
      }

      navigator.geolocation.getCurrentPosition(
        (position) => {
          console.log("GPS ERFOLG:", position.coords); // NEU
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
          console.error("GPS FEHLER:", error); // NEU
          let errorMsg = 'GPS-Fehler: ';
          switch(error.code) {
            case error.PERMISSION_DENIED:
              errorMsg += 'Bitte GPS-Berechtigung erteilen';
              break;
            case error.POSITION_UNAVAILABLE:
              errorMsg += 'Position nicht verfügbar';
              break;
            case error.TIMEOUT:
              errorMsg += 'Zeitüberschreitung bei GPS-Abfrage';
              break;
            default:
              errorMsg += 'Unbekannter Fehler';
          }
          setLocationError(errorMsg);
          setIsLoadingLocation(false);
          reject(errorMsg);
        },
        {
          enableHighAccuracy: false,
          timeout: 30000,
          maximumAge: 10000
        }
      );
    });
  };

  // Distanz berechnen (Haversine-Formel)
  const calculateDistance = (lat1, lon1, lat2, lon2) => {
    const R = 6371e3; // Erdradius in Metern
    const φ1 = lat1 * Math.PI/180;
    const φ2 = lat2 * Math.PI/180;
    const Δφ = (lat2-lat1) * Math.PI/180;
    const Δλ = (lon2-lon1) * Math.PI/180;

    const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
              Math.cos(φ1) * Math.cos(φ2) *
              Math.sin(Δλ/2) * Math.sin(Δλ/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

    return R * c; // Distanz in Metern
  };

  // GPS-Validierung mit besserer Anzeige - KOMPLETT NEU
  const validateLocation = async (objectId) => {
    try {
      const location = await getCurrentLocation();
      const object = objectLocations[parseInt(objectId)];

      if (!object) {
        console.error('Objekt nicht gefunden');
        return true;
      }

      const distance = calculateDistance(
        location.lat,
        location.lng,
        object.lat,
        object.lng
      );

      console.log(`Distanz zu ${object.name}: ${Math.round(distance)}m`);

      if (distance > 100) {
        // Zeige Warnung aber blockiere nicht
        const warningMsg = `⚠️ Du bist ${Math.round(distance)}m vom ${object.name} entfernt (max. 100m erlaubt).\nStempelung wird trotzdem durchgeführt.`;
        setLocationError(warningMsg);
        setTimeout(() => setLocationError(null), 8000);
        
        // Optional: In Konsole für Admin sichtbar
        console.warn(`GPS-WARNUNG: ${Math.round(distance)}m Entfernung bei ${object.name}`);
      } else {
        // Zeige Erfolg
        setLocationError(`✅ GPS OK: ${Math.round(distance)}m vom ${object.name}`);
        setTimeout(() => setLocationError(null), 3000);
      }

      return true; // Immer erlauben

    } catch (error) {
      console.error('GPS-Fehler:', error);
      setLocationError('⚠️ GPS nicht verfügbar. Stempelung wird trotzdem durchgeführt.');
      setTimeout(() => setLocationError(null), 5000);
      return true;
    }
  };

  // Auto-Pause Handler
  const handleAutoPause = async () => {
    try {
      const response = await axios.post(
        `${API_URL}/breaks/start`,
        {
          is_paid: false,
          notes: "Automatische Pause nach 6 Stunden"
        },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      setIsPaused(true);
      setPauseId(response.data.id);
      setPauseStartTime(new Date());

      if ("Notification" in window && Notification.permission === "granted") {
        new Notification("⏸️ Automatische Pause", {
          body: "Nach 6 Stunden Arbeit wurde automatisch eine 30-minütige Pause gestartet.",
          icon: "/icon-192.png"
        });
      }

      alert('⏸️ Automatische Pause nach 6 Stunden!\nBitte 30 Minuten Pause machen.');

      setTimeout(() => {
        if (isPaused) {
          alert('📢 Deine 30-minütige Pause ist um. Du kannst wieder arbeiten!');
        }
      }, 30 * 60 * 1000);

    } catch (error) {
      console.error('Auto-Pause Fehler:', error);
    }
  };

  const checkStatus = async () => {
    try {
      const response = await axios.get(`${API_URL}/time-entries/current`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.data.is_working && !isWorking) {
        setIsWorking(true);
        setWorkStartTime(new Date(response.data.check_in));

        const workSeconds = (new Date() - new Date(response.data.check_in)) / 1000;
        const workHours = workSeconds / 3600;
        if (workHours >= 6) {
          setAutoPauseTriggered(true);
        }
      } else if (!response.data.is_working) {
        setIsWorking(false);
        setWorkStartTime(null);
        setAutoPauseTriggered(false);
      }

      const breakResponse = await axios.get(`${API_URL}/breaks/current`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (breakResponse.data.active_break) {
        setIsPaused(true);
        setPauseId(breakResponse.data.active_break.id);
        setPauseStartTime(new Date(breakResponse.data.active_break.start_time));
      } else {
        setIsPaused(false);
        setPauseId(null);
        setPauseStartTime(null);
      }
    } catch (error) {
      console.error('Status-Fehler:', error);
    }
  };

  const fetchTodayHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/today`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTodayHours(response.data.total_hours);
    } catch (error) {
      console.error('Stunden-Fehler:', error);
    }
  };

  const fetchWeekHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/week`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setWeekHours(response.data.total_hours);
    } catch (error) {
      console.error('Wochenstunden-Fehler:', error);
    }
  };

  const fetchMonthHours = async () => {
    try {
      const response = await axios.get(`${API_URL}/reports/my/month`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setMonthHours(response.data.total_hours);
      const sollStunden = 160;
      setOvertimeHours(response.data.total_hours - sollStunden);
    } catch (error) {
      console.error('Monatsstunden-Fehler:', error);
    }
  };

  const handleCheckIn = async () => {
    setLocationError(null);

    // GPS-Check (warnt nur, blockiert nicht)
    await validateLocation(selectedObject);

    try {
      const response = await axios.post(
        `${API_URL}/time-entries/check-in`,
        {
          object_id: parseInt(selectedObject),
          notes: "Arbeitsbeginn"
        },
        { headers: { Authorization: `Bearer ${token}` }}
      );

      setIsWorking(true);
      setWorkStartTime(new Date());
      setTotalPauseTime(0);
      setAutoPauseTriggered(false);
      fetchTodayHours();

      if ("Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
      }
    } catch (error) {
      console.error('Fehler beim Einstempeln:', error);
      alert('Fehler beim Einstempeln: ' + (error.response?.data?.detail || 'Unbekannter Fehler'));
    }
  };

  const handleObjectSwitch = async () => {
    setLocationError(null);

    await validateLocation(selectedObject);

    try {
      await axios.post(
        `${API_URL}/time-entries/switch-object`,
        {
          object_id: parseInt(selectedObject),
          notes: "Objektwechsel"
        },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      alert('Objektwechsel erfolgreich!');
      fetchTodayHours();
    } catch (error) {
      alert('Fehler beim Objektwechsel');
    }
  };

  const handleCheckOut = async () => {
    if (isPaused) {
      alert('Bitte erst die Pause beenden!');
      return;
    }

    try {
      await axios.post(
        `${API_URL}/time-entries/check-out`,
        {},
        { headers: { Authorization: `Bearer ${token}` }}
      );
      setIsWorking(false);
      setWorkStartTime(null);
      setTotalPauseTime(0);
      setAutoPauseTriggered(false);
      fetchTodayHours();
      fetchWeekHours();
      fetchMonthHours();
    } catch (error) {
      alert('Fehler beim Ausstempeln');
    }
  };

  const handlePauseStart = async () => {
    try {
      const response = await axios.post(
        `${API_URL}/breaks/start`,
        { is_paid: false },
        { headers: { Authorization: `Bearer ${token}` }}
      );
      setIsPaused(true);
      setPauseId(response.data.id);
      setPauseStartTime(new Date());
    } catch (error) {
      alert('Fehler beim Pause starten');
    }
  };

  const handlePauseEnd = async () => {
    try {
      await axios.post(
        `${API_URL}/breaks/end`,
        { break_id: pauseId },
        { headers: { Authorization: `Bearer ${token}` }}
      );

      if (pauseStartTime) {
        const pauseDuration = (new Date() - pauseStartTime) / 1000;
        setTotalPauseTime(prev => prev + pauseDuration);
      }

      setIsPaused(false);
      setPauseId(null);
      setPauseStartTime(null);
    } catch (error) {
      alert('Fehler beim Pause beenden');
    }
  };

  const calculateWorkTime = () => {
    if (!workStartTime) return '00:00:00';

    let totalSeconds = (currentTime - workStartTime) / 1000;

    if (isPaused && pauseStartTime) {
      const currentPause = (currentTime - pauseStartTime) / 1000;
      totalSeconds -= (totalPauseTime + currentPause);
    } else {
      totalSeconds -= totalPauseTime;
    }

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = Math.floor(totalSeconds % 60);

    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  const calculatePauseTime = () => {
    if (!pauseStartTime) return '00:00';

    const pauseSeconds = (currentTime - pauseStartTime) / 1000;
    const minutes = Math.floor(pauseSeconds / 60);
    const seconds = Math.floor(pauseSeconds % 60);

    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };

  const formatHours = (hours) => {
    if (hours < 1) {
      return `${Math.round(hours * 60)} Min`;
    }
    const h = Math.floor(hours);
    const m = Math.round((hours % 1) * 60);
    return `${h}:${m.toString().padStart(2, '0')} Std`;
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('userRole');
    navigate('/login');
  };

  // PWA Install Handler - NEU HINZUGEFÜGT
  const handleInstallPWA = async () => {
    if (!deferredPrompt) return;
    
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    
    if (outcome === 'accepted') {
      console.log('PWA wurde installiert');
      setIsInstallable(false);
    }
    setDeferredPrompt(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
          <div className="flex justify-between items-center">
            <h1 className="text-3xl font-bold text-gray-800">SEDA24 Zeiterfassung</h1>
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600"
            >
              <LogOut size={20} />
              Logout
            </button>
          </div>
          
          {/* Online/Offline Status - NEU */}
          {!isOnline && (
            <div className="mt-2 text-center text-orange-600 font-semibold">
              ⚠️ Offline-Modus
            </div>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8">
          <div className="text-center mb-8">
            <div className="text-6xl font-bold text-gray-800">
              {currentTime.toLocaleTimeString('de-DE')}
            </div>
            <div className="text-xl text-gray-600 mt-2">
              {currentTime.toLocaleDateString('de-DE', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
                year: 'numeric'
              })}
            </div>
          </div>

          {/* GPS-Status & Fehler */}
          {locationError && (
            <div className={`border rounded-lg p-4 mb-6 ${
              locationError.includes('✅') 
                ? 'bg-green-50 border-green-200' 
                : 'bg-red-50 border-red-200'
            }`}>
              <div className="flex items-start gap-2">
                {locationError.includes('✅') ? (
                  <span className="text-green-500">✅</span>
                ) : (
                  <AlertCircle className="text-red-500 mt-1" size={20} />
                )}
                <div className={
                  locationError.includes('✅') 
                    ? 'text-green-700' 
                    : 'text-red-700'
                }>
                  {locationError}
                </div>
              </div>
            </div>
          )}

          {isLoadingLocation && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <div className="flex items-center gap-2">
                <MapPin className="text-blue-500 animate-pulse" size={20} />
                <div className="text-blue-700">GPS-Position wird ermittelt...</div>
              </div>
            </div>
          )}

          {isWorking && (
            <div className="bg-blue-50 rounded-lg p-6 mb-6">
              <div className="text-center">
                {isPaused ? (
                  <>
                    <div className="text-2xl font-semibold text-orange-600 mb-2">
                      ⏸️ PAUSE
                      {autoPauseTriggered && (
                        <span className="text-sm block mt-1">
                          (Automatische Pause nach 6 Stunden)
                        </span>
                      )}
                    </div>
                    <div className="text-3xl font-mono text-orange-600">
                      {calculatePauseTime()}
                    </div>
                    <div className="text-sm text-gray-600 mt-2">
                      Arbeitszeit läuft nicht
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-2xl font-semibold text-green-600 mb-2">
                      🏃 ARBEITSZEIT LÄUFT
                    </div>
                    <div className="text-4xl font-mono text-green-600">
                      {calculateWorkTime()}
                    </div>
                    {!autoPauseTriggered && parseFloat(calculateWorkTime()) >= 5.5 && (
                      <div className="text-sm text-orange-600 mt-2">
                        ⚠️ Automatische Pause in {Math.round((6 - parseFloat(calculateWorkTime())) * 60)} Minuten
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {!isWorking && (
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Objekt wählen:
              </label>
              <select
                value={selectedObject}
                onChange={(e) => setSelectedObject(parseInt(e.target.value))}
                className="w-full px-4 py-3 border rounded-lg text-lg"
              >
               <option value="1">SEDA24 Zentrale</option>
               <option value="3">Lidl Muggensturmer Str</option>
               <option value="4">Lidl Wochenende</option>
               <option value="5">Enfido Sonnenschein</option>
               <option value="6">Metalicone Muggensturm</option>
               <option value="7">JU_RA Baden-Baden</option>
               <option value="8">Huber Iffezheim</option>
               <option value="9">BAD-Treppen</option>
               <option value="11">Leible Rheinmünster</option>
               <option value="12">Zinsfabrik Baden-Baden</option>
               <option value="13">Polytec Rastatt</option>
               <option value="14">Steuerberater Baden-Baden</option>
               <option value="15">Geiger Malsch</option>
               <option value="16">Rytec Baden-Baden</option>
              </select>
            </div>
          )}

          <div className="space-y-4">
            {!isWorking ? (
              <button
                onClick={handleCheckIn}
                disabled={isLoadingLocation}
                className="w-full py-6 bg-green-500 text-white rounded-xl text-2xl font-bold hover:bg-green-600 flex items-center justify-center gap-3 disabled:bg-gray-400"
              >
                <Play size={32} />
                ARBEIT BEGINNEN
              </button>
            ) : (
              <>
                {!isPaused ? (
                  <button
                    onClick={handlePauseStart}
                    className="w-full py-4 bg-orange-500 text-white rounded-xl text-xl font-bold hover:bg-orange-600 flex items-center justify-center gap-3"
                  >
                    <Pause size={28} />
                    PAUSE MACHEN
                  </button>
                ) : (
                  <button
                    onClick={handlePauseEnd}
                    className="w-full py-4 bg-green-500 text-white rounded-xl text-xl font-bold hover:bg-green-600 flex items-center justify-center gap-3 animate-pulse"
                  >
                    <PlayCircle size={28} />
                    PAUSE BEENDEN
                  </button>
                )}

                {!isPaused && (
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Zu anderem Objekt wechseln:
                    </label>
<select
  value={selectedObject}
  onChange={(e) => setSelectedObject(parseInt(e.target.value))}
  className="w-full px-4 py-2 border rounded-lg text-lg mb-2"
>
  <option value="1">SEDA24 Zentrale</option>
  <option value="3">Lidl Muggensturmer Str</option>
  <option value="4">Lidl Wochenende</option>
  <option value="5">Enfido Sonnenschein</option>
  <option value="6">Metalicone Muggensturm</option>
  <option value="7">JU_RA Baden-Baden</option>
  <option value="8">Huber Iffezheim</option>
  <option value="9">BAD-Treppen</option>
  <option value="11">Leible Rheinmünster</option>
  <option value="12">Zinsfabrik Baden-Baden</option>
  <option value="13">Polytec Rastatt</option>
  <option value="14">Steuerberater Baden-Baden</option>
  <option value="15">Geiger Malsch</option>
  <option value="16">Rytec Baden-Baden</option>
</select>                    <button
                      onClick={handleObjectSwitch}
                      disabled={isLoadingLocation}
                      className="w-full py-2 bg-blue-500 text-white rounded-lg font-bold hover:bg-blue-600 disabled:bg-gray-400"
                    >
                      OBJEKT WECHSELN
                    </button>
                  </div>
                )}

                <button
                  onClick={handleCheckOut}
                  disabled={isPaused}
                  className={`w-full py-6 rounded-xl text-2xl font-bold flex items-center justify-center gap-3 ${
                    isPaused
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : 'bg-red-500 text-white hover:bg-red-600'
                  }`}
                >
                  <Square size={32} />
                  ARBEIT BEENDEN
                </button>
              </>
            )}
          </div>

          <div className="mt-8 pt-6 border-t">
            
            {/* PWA Install Button - NEU HINZUGEFÜGT */}
            {isInstallable && !window.matchMedia('(display-mode: standalone)').matches && (
              <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                <button
                  onClick={handleInstallPWA}
                  className="w-full py-3 bg-blue-600 text-white rounded-lg font-bold hover:bg-blue-700 flex items-center justify-center gap-2"
                >
                  📱 App installieren
                </button>
              </div>
            )}
            
            <div className="flex justify-between items-center">
              <span className="text-lg text-gray-600">Heute gearbeitet:</span>
              <span className="text-2xl font-bold text-blue-600">
                {formatHours(todayHours)}
              </span>
            </div>

            <div className="flex justify-between items-center mt-4">
              <span className="text-lg text-gray-600">Diese Woche:</span>
              <span className="text-2xl font-bold text-blue-600">
                {formatHours(weekHours)}
              </span>
            </div>

            <div className="flex justify-between items-center mt-4">
              <span className="text-lg text-gray-600">Dieser Monat:</span>
              <span className="text-2xl font-bold text-blue-600">
                {formatHours(monthHours)}
              </span>
            </div>

            <div className="flex justify-between items-center mt-4">
              <span className="text-lg text-gray-600">Überstunden:</span>
              <span className={`text-2xl font-bold ${overtimeHours >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {overtimeHours >= 0 ? '+' : ''}{formatHours(Math.abs(overtimeHours))}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
