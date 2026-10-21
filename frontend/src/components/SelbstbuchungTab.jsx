import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Send, CheckCircle, Clock, AlertCircle, Building, Calendar, ChevronDown } from 'lucide-react';
import { API_URL } from '../config.js';

const SelbstbuchungTab = () => {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');

  // Formular
  const [objects, setObjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null); // {type: 'success'|'error', text: '...'}

  const today = new Date().toISOString().split('T')[0];
  const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  const [formData, setFormData] = useState({
    object_id: '',
    date: today,
    start_time: '08:00',
    end_time: '16:00',
    service_type: 'Unterhaltsreinigung',
    is_driver: false,
    notes: '',
  });

  // Meine Buchungen
  const [myBookings, setMyBookings] = useState([]);

  useEffect(() => {
    loadObjects();
    loadMyBookings();
  }, []);

  const loadObjects = async () => {
    try {
      const res = await axios.get(`${API_URL}/self-booking/my-objects`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setObjects(res.data);
      // Fahrer-Status vom ersten Objekt uebernehmen
      if (res.data.length > 0) {
        setFormData(prev => ({
          ...prev,
          object_id: res.data[0].id,
          is_driver: res.data[0].is_driver || false,
        }));
      }
    } catch (e) {
      console.error('Fehler beim Laden der Objekte:', e);
    } finally {
      setLoading(false);
    }
  };

  const loadMyBookings = async () => {
    try {
      const res = await axios.get(`${API_URL}/self-booking/my-bookings`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setMyBookings(res.data);
    } catch (e) {
      console.error('Fehler beim Laden:', e);
    }
  };

  const handleObjectChange = (objId) => {
    const obj = objects.find(o => o.id === parseInt(objId));
    setFormData(prev => ({
      ...prev,
      object_id: objId,
      is_driver: obj?.is_driver || false,
    }));
  };

  const calcHours = () => {
    if (!formData.start_time || !formData.end_time) return 0;
    const [sh, sm] = formData.start_time.split(':').map(Number);
    const [eh, em] = formData.end_time.split(':').map(Number);
    const diff = (eh * 60 + em) - (sh * 60 + sm);
    return diff > 0 ? (diff / 60).toFixed(2) : 0;
  };

  const handleSubmit = async () => {
    if (!formData.object_id || !formData.date || !formData.start_time || !formData.end_time) {
      setMessage({ type: 'error', text: 'Bitte alle Felder ausfuellen' });
      return;
    }

    setSubmitting(true);
    setMessage(null);
    try {
      const res = await axios.post(`${API_URL}/self-booking/submit`, {
        object_id: parseInt(formData.object_id),
        date: formData.date,
        start_time: formData.start_time,
        end_time: formData.end_time,
        service_type: formData.service_type,
        is_driver: formData.is_driver,
        notes: formData.notes,
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setMessage({ type: 'success', text: `Buchung eingereicht (${res.data.hours}h). Warte auf Genehmigung.` });
      loadMyBookings();
      // Formular zuruecksetzen
      setFormData(prev => ({ ...prev, notes: '' }));
    } catch (e) {
      setMessage({ type: 'error', text: e.response?.data?.detail || 'Fehler beim Einreichen' });
    } finally {
      setSubmitting(false);
    }
  };

  const statusBadge = (status) => {
    const styles = {
      'offen': { bg: '#fef3c7', color: '#92400e', icon: Clock, label: 'Offen' },
      'genehmigt': { bg: '#d1fae5', color: '#065f46', icon: CheckCircle, label: 'Genehmigt' },
      'abgelehnt': { bg: '#fee2e2', color: '#991b1b', icon: AlertCircle, label: 'Abgelehnt' },
    };
    const s = styles[status] || styles['offen'];
    const Icon = s.icon;
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: '4px',
        background: s.bg, color: s.color, padding: '3px 8px',
        borderRadius: '6px', fontSize: '11px', fontWeight: '600'
      }}>
        <Icon size={12} /> {s.label}
      </span>
    );
  };

  if (loading) {
    return <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>Lade Objekte...</div>;
  }

  if (objects.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '40px' }}>
        <Building size={48} style={{ color: '#9ca3af', margin: '0 auto 12px' }} />
        <p style={{ color: '#6b7280', fontSize: '16px' }}>Dir sind noch keine Objekte zugewiesen.</p>
        <p style={{ color: '#9ca3af', fontSize: '13px', marginTop: '8px' }}>Bitte wende dich an den Admin.</p>
      </div>
    );
  }

  return (
    <div>
      <h3 style={{ fontSize: '18px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '16px' }}>
        Schicht buchen
      </h3>

      {/* Formular */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Objekt */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Objekt</label>
          <select
            value={formData.object_id}
            onChange={(e) => handleObjectChange(e.target.value)}
            style={{
              width: '100%', padding: '12px', borderRadius: '10px',
              border: '1px solid #d1d5db', fontSize: '15px', background: 'white'
            }}
          >
            <option value="">-- Objekt waehlen --</option>
            {objects.map(obj => (
              <option key={obj.id} value={obj.id}>{obj.name}</option>
            ))}
          </select>
        </div>

        {/* Datum */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Datum</label>
          <input
            type="date"
            value={formData.date}
            min={threeDaysAgo}
            max={today}
            onChange={(e) => setFormData({ ...formData, date: e.target.value })}
            style={{
              width: '100%', padding: '12px', borderRadius: '10px',
              border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box'
            }}
          />
        </div>

        {/* Von / Bis */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Von</label>
            <input
              type="time"
              value={formData.start_time}
              onChange={(e) => setFormData({ ...formData, start_time: e.target.value })}
              style={{
                width: '100%', padding: '12px', borderRadius: '10px',
                border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box'
              }}
            />
          </div>
          <div>
            <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Bis</label>
            <input
              type="time"
              value={formData.end_time}
              onChange={(e) => setFormData({ ...formData, end_time: e.target.value })}
              style={{
                width: '100%', padding: '12px', borderRadius: '10px',
                border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box'
              }}
            />
          </div>
        </div>

        {/* Berechnete Stunden */}
        <div style={{
          background: '#eff6ff', padding: '10px 14px', borderRadius: '10px',
          fontSize: '14px', color: '#1e40af', fontWeight: '600', textAlign: 'center'
        }}>
          = {(() => {
            const h = calcHours();
            if (!h || h <= 0) return "0 Min";
            const hrs = Math.floor(h);
            const mins = Math.round((h % 1) * 60);
            if (hrs === 0) return `${mins} Min`;
            if (mins === 0) return `${hrs} Std`;
            return `${hrs} Std ${mins} Min`;
          })()}
        </div>

        {/* Reinigungsart */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Reinigungsart</label>
          <select
            value={formData.service_type}
            onChange={(e) => setFormData({ ...formData, service_type: e.target.value })}
            style={{
              width: '100%', padding: '12px', borderRadius: '10px',
              border: '1px solid #d1d5db', fontSize: '15px', background: 'white'
            }}
          >
            <option value="Unterhaltsreinigung">Unterhaltsreinigung</option>
            <option value="Fensterreinigung">Fensterreinigung</option>
            <option value="Sonderreinigung">Sonderreinigung</option>
          </select>
        </div>

        {/* Fahrer */}
        <label style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '12px', background: '#f9fafb', borderRadius: '10px', cursor: 'pointer'
        }}>
          <input
            type="checkbox"
            checked={formData.is_driver}
            onChange={(e) => setFormData({ ...formData, is_driver: e.target.checked })}
            style={{ width: '20px', height: '20px', accentColor: '#1e3a5f' }}
          />
          <span style={{ fontSize: '15px', fontWeight: '500', color: '#374151' }}>
            Ich bin gefahren (KM-Anspruch)
          </span>
        </label>

        {/* Notiz */}
        <div>
          <label style={{ fontSize: '13px', fontWeight: '600', color: '#374151', marginBottom: '4px', display: 'block' }}>Notiz (optional)</label>
          <input
            type="text"
            value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            placeholder="z.B. Sondereinsatz"
            style={{
              width: '100%', padding: '12px', borderRadius: '10px',
              border: '1px solid #d1d5db', fontSize: '15px', boxSizing: 'border-box'
            }}
          />
        </div>

        {/* Nachricht */}
        {message && (
          <div style={{
            padding: '12px', borderRadius: '10px', fontSize: '14px', fontWeight: '500',
            background: message.type === 'success' ? '#d1fae5' : '#fee2e2',
            color: message.type === 'success' ? '#065f46' : '#991b1b',
          }}>
            {message.type === 'success' ? <CheckCircle size={16} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} /> : <AlertCircle size={16} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />}
            {message.text}
          </div>
        )}

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={submitting || !formData.object_id}
          style={{
            width: '100%', padding: '16px',
            background: submitting ? '#9ca3af' : 'linear-gradient(135deg, #1e3a5f 0%, #2c5f7c 100%)',
            color: 'white', border: 'none', borderRadius: '12px',
            fontSize: '16px', fontWeight: 'bold', cursor: submitting ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
          }}
        >
          <Send size={18} />
          {submitting ? 'Wird eingereicht...' : 'Buchung einreichen'}
        </button>
      </div>

      {/* Meine eingereichten Buchungen */}
      {myBookings.length > 0 && (
        <div style={{ marginTop: '28px' }}>
          <h4 style={{ fontSize: '16px', fontWeight: 'bold', color: '#1e3a5f', marginBottom: '12px' }}>
            Meine Buchungen
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {myBookings.map(b => (
              <div key={b.id} style={{
                background: '#f9fafb', borderRadius: '10px', padding: '12px',
                border: '1px solid #e5e7eb',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontWeight: '600', fontSize: '14px', color: '#1f2937' }}>
                    {b.object_name}
                  </span>
                  {statusBadge(b.status)}
                </div>
                <div style={{ fontSize: '13px', color: '#6b7280' }}>
                  {new Date(b.date).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })}
                  {' '}{b.start_time} - {b.end_time}
                  {' '}({b.requested_hours}h)
                  {b.service_type !== 'Unterhaltsreinigung' && (
                    <span style={{ marginLeft: '6px', color: '#7c3aed', fontWeight: '500' }}>{b.service_type}</span>
                  )}
                </div>
                {b.status === 'genehmigt' && b.approved_hours && b.approved_hours !== b.requested_hours && (
                  <div style={{ fontSize: '12px', color: '#065f46', marginTop: '4px' }}>
                    Genehmigt: {b.approved_hours}h
                  </div>
                )}
                {b.status === 'abgelehnt' && b.admin_notes && (
                  <div style={{ fontSize: '12px', color: '#991b1b', marginTop: '4px' }}>
                    Grund: {b.admin_notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SelbstbuchungTab;
