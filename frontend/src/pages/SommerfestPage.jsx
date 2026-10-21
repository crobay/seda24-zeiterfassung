import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { API_URL } from '../config.js';

const SommerfestPage = () => {
  const [searchParams] = useSearchParams();
  const personalNr = searchParams.get('id');
  const [firstName, setFirstName] = useState('');
  const [terminWahl, setTerminWahl] = useState('');
  const [begleitung, setBegleitung] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');
  const [hasExisting, setHasExisting] = useState(false);

  useEffect(() => {
    if (!personalNr) { setLoading(false); return; }
    axios.get(`${API_URL}/fest/info/${personalNr}`)
      .then(res => {
        setFirstName(res.data.first_name);
        if (res.data.existing_answer) {
          setTerminWahl(res.data.existing_answer.termin_wahl);
          setBegleitung(res.data.existing_answer.begleitung);
          setHasExisting(true);
        }
      })
      .catch(() => setError('Link ungültig oder Mitarbeiter nicht gefunden.'))
      .finally(() => setLoading(false));
  }, [personalNr]);

  const handleSubmit = async () => {
    if (!terminWahl || !begleitung) { setError('Bitte beantworte beide Fragen.'); return; }
    setError('');
    try {
      await axios.post(`${API_URL}/fest/antwort`, {
        personal_nr: personalNr,
        termin_wahl: terminWahl,
        begleitung: begleitung
      });
      setSubmitted(true);
    } catch (e) {
      setError('Fehler beim Speichern. Bitte versuche es nochmal.');
    }
  };

  if (loading) return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 50%, #d97706 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 48, height: 48, border: '4px solid white', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
    </div>
  );

  if (!personalNr) return (
    <div style={{ minHeight: '100vh', background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: 'white', borderRadius: 16, padding: 32, maxWidth: 400, textAlign: 'center', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}>
        <p style={{ fontSize: 48 }}>&#127946;</p>
        <h2 style={{ color: '#92400e' }}>Kein Zugang</h2>
        <p style={{ color: '#78716c' }}>Bitte benutze den persönlichen Link aus deiner Einladungs-E-Mail.</p>
      </div>
    </div>
  );

  if (error && !firstName) return (
    <div style={{ minHeight: '100vh', background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: 'white', borderRadius: 16, padding: 32, maxWidth: 400, textAlign: 'center', boxShadow: '0 10px 40px rgba(0,0,0,0.1)' }}>
        <p style={{ fontSize: 48 }}>&#128533;</p>
        <p style={{ color: '#dc2626' }}>{error}</p>
      </div>
    </div>
  );

  if (submitted) return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #34d399 0%, #10b981 50%, #059669 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: 'white', borderRadius: 20, padding: 40, maxWidth: 440, textAlign: 'center', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
        <p style={{ fontSize: 64 }}>&#127881;</p>
        <h2 style={{ color: '#059669', marginBottom: 12 }}>Danke, {firstName}!</h2>
        <p style={{ color: '#6b7280', lineHeight: 1.6 }}>
          Deine Antwort wurde gespeichert. Du kannst diesen Link jederzeit erneut öffnen, falls du deine Auswahl ändern möchtest.
        </p>
        <p style={{ color: '#9ca3af', fontSize: 13, marginTop: 24 }}>SEDA24 GmbH</p>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 50%, #d97706 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: 'white', borderRadius: 20, padding: 32, maxWidth: 480, width: '100%', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>

        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <p style={{ fontSize: 56 }}>&#9728;&#65039;&#127866;</p>
          <h1 style={{ color: '#92400e', fontSize: 24, marginBottom: 4 }}>SEDA24 Sommerfest</h1>
          <p style={{ color: '#b45309', fontSize: 15 }}>Du bist eingeladen!</p>
        </div>

        <div style={{ background: '#fffbeb', borderRadius: 12, padding: 20, marginBottom: 24, borderLeft: '4px solid #f59e0b' }}>
          <p style={{ color: '#92400e', lineHeight: 1.7, margin: 0, fontSize: 15 }}>
            Hallo <strong>{firstName}</strong>,<br /><br />
            es ist wieder so weit – wir schmeißen ein Sommerfest, und du gehörst dazu!
            Der Garten der Firmenzentrale wird zur Festwiese: Grill, frische Salate, kühle
            Getränke und gute Gesellschaft. Bring gerne deinen Partner oder deine Partnerin mit!
            <br /><br />
            Es geht am späten Nachmittag los (ca. 17–18 Uhr) – open end.
            Sag uns kurz Bescheid, welcher Samstag dir passt:
          </p>
        </div>

        {hasExisting && (
          <div style={{ background: '#dbeafe', borderRadius: 8, padding: 12, marginBottom: 16, textAlign: 'center', fontSize: 13, color: '#1e40af' }}>
            Du hast bereits geantwortet. Du kannst deine Auswahl hier ändern.
          </div>
        )}

        {/* Frage 1: Termin */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontWeight: 'bold', color: '#374151', fontSize: 15, display: 'block', marginBottom: 10 }}>
            Welcher Termin passt dir?
          </label>
          {[
            { value: '25_07', label: 'Samstag, 25. Juli 2026', emoji: '&#128197;' },
            { value: '01_08', label: 'Samstag, 1. August 2026', emoji: '&#128197;' },
            { value: 'beide', label: 'Beide Termine passen mir', emoji: '&#128077;' },
            { value: 'keiner', label: 'Leider keiner', emoji: '&#128532;' },
          ].map(opt => (
            <button
              key={opt.value}
              onClick={() => setTerminWahl(opt.value)}
              style={{
                display: 'block', width: '100%', padding: '12px 16px', marginBottom: 8,
                borderRadius: 10, border: terminWahl === opt.value ? '2px solid #f59e0b' : '2px solid #e5e7eb',
                background: terminWahl === opt.value ? '#fffbeb' : 'white',
                textAlign: 'left', cursor: 'pointer', fontSize: 15, color: '#374151',
                transition: 'all 0.15s'
              }}
            >
              <span dangerouslySetInnerHTML={{ __html: opt.emoji }} /> {opt.label}
            </button>
          ))}
        </div>

        {/* Frage 2: Begleitung */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontWeight: 'bold', color: '#374151', fontSize: 15, display: 'block', marginBottom: 10 }}>
            Kommst du allein oder zu zweit?
          </label>
          {[
            { value: 'allein', label: 'Ich komme allein', emoji: '&#128587;' },
            { value: 'zu_zweit', label: 'Zu zweit (mit Partner/in)', emoji: '&#128107;' },
          ].map(opt => (
            <button
              key={opt.value}
              onClick={() => setBegleitung(opt.value)}
              style={{
                display: 'block', width: '100%', padding: '12px 16px', marginBottom: 8,
                borderRadius: 10, border: begleitung === opt.value ? '2px solid #f59e0b' : '2px solid #e5e7eb',
                background: begleitung === opt.value ? '#fffbeb' : 'white',
                textAlign: 'left', cursor: 'pointer', fontSize: 15, color: '#374151',
                transition: 'all 0.15s'
              }}
            >
              <span dangerouslySetInnerHTML={{ __html: opt.emoji }} /> {opt.label}
            </button>
          ))}
        </div>

        {error && <p style={{ color: '#dc2626', textAlign: 'center', marginBottom: 12, fontSize: 14 }}>{error}</p>}

        <button
          onClick={handleSubmit}
          disabled={!terminWahl || !begleitung}
          style={{
            width: '100%', padding: '14px', borderRadius: 12, border: 'none',
            background: (!terminWahl || !begleitung) ? '#d1d5db' : 'linear-gradient(135deg, #f59e0b, #d97706)',
            color: 'white', fontSize: 17, fontWeight: 'bold', cursor: (!terminWahl || !begleitung) ? 'default' : 'pointer',
            transition: 'all 0.2s', boxShadow: (!terminWahl || !begleitung) ? 'none' : '0 4px 15px rgba(245,158,11,0.4)'
          }}
        >
          {hasExisting ? 'Antwort aktualisieren' : 'Absenden'}
        </button>

        <p style={{ color: '#9ca3af', fontSize: 12, textAlign: 'center', marginTop: 20 }}>SEDA24 GmbH - Sommerfest 2026</p>
      </div>
    </div>
  );
};

export default SommerfestPage;
