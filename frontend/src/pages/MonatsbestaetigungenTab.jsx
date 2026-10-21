import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { CheckCircle, Clock, AlertTriangle, Send, RotateCcw, Calendar, ChevronLeft, ChevronRight, Users, Bell, ShieldCheck } from 'lucide-react';

const MONTH_NAMES = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
];

const STATUS_CONFIG = {
  not_sent:  { label: 'Nicht gesendet', bg: '#f3f4f6', color: '#6b7280', icon: Clock },
  sent:      { label: 'Gesendet',       bg: '#dbeafe', color: '#2563eb', icon: Send },
  confirmed: { label: 'Bestätigt',      bg: '#d1fae5', color: '#059669', icon: CheckCircle },
  disputed:  { label: 'Korrektur',      bg: '#fee2e2', color: '#dc2626', icon: AlertTriangle },
};

const MonatsbestaetigungenTab = ({ showToast }) => {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [overrideModal, setOverrideModal] = useState(null);
  const [overrideDate, setOverrideDate] = useState('');

  useEffect(() => { loadData(); }, [year, month]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/confirmations/admin/pending-confirmations?year=${year}&month=${month}`);
      setData(res.data);
    } catch (err) {
      showToast('Fehler beim Laden', 'error');
    }
    setLoading(false);
  };

  const navigate = (dir) => {
    let m = month + dir;
    let y = year;
    if (m > 12) { m = 1; y++; }
    if (m < 1) { m = 12; y--; }
    setMonth(m);
    setYear(y);
  };

  const handleReset = async (empId) => {
    if (!confirm('Bestätigung wirklich zurücksetzen?')) return;
    try {
      await api.post(`/confirmations/admin/confirmation-reset/${empId}/${year}/${month}`);
      showToast('Zurückgesetzt', 'success');
      loadData();
    } catch (err) {
      showToast('Fehler', 'error');
    }
  };

  const handleRemind = async (empId) => {
    try {
      await api.post(`/confirmations/admin/confirmation-remind/${empId}/${year}/${month}`);
      showToast('Erinnerung gesendet', 'success');
      loadData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Fehler', 'error');
    }
  };

  const handleOverrideSave = async () => {
    if (!overrideModal) return;
    try {
      await api.put(`/confirmations/admin/confirmation-override/${overrideModal}/${year}/${month}`, {
        last_shift_override: overrideDate || null,
      });
      showToast('Gespeichert', 'success');
      setOverrideModal(null);
      loadData();
    } catch (err) {
      showToast('Fehler', 'error');
    }
  };

  const handleTriggerAll = async () => {
    if (!confirm('Bestätigungen an alle unbestätigten MAs senden?')) return;
    try {
      const res = await api.post(`/confirmations/admin/trigger-confirmations/${year}/${month}`);
      showToast(`${res.data.sent_count} Bestätigungen gesendet`, 'success');
      loadData();
    } catch (err) {
      showToast('Fehler', 'error');
    }
  };

  const handleAdminConfirm = async (empId, name) => {
    if (!confirm(`Monat ${MONTH_NAMES[month - 1]} ${year} für ${name} als Admin bestätigen?`)) return;
    try {
      await api.post(`/confirmations/admin/confirm-by-admin/${empId}/${year}/${month}`);
      showToast('Admin-Bestätigung gespeichert', 'success');
      loadData();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Fehler', 'error');
    }
  };

  const confirmations = data?.confirmations || [];
  const counts = {
    total: confirmations.length,
    confirmed: confirmations.filter(c => c.status === 'confirmed').length,
    sent: confirmations.filter(c => c.status === 'sent').length,
    disputed: confirmations.filter(c => c.status === 'disputed').length,
    not_sent: confirmations.filter(c => c.status === 'not_sent').length,
  };

  const fmtDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };
  const fmtDateTime = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div style={{ padding: '20px' }}>
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #059669 0%, #047857 100%)',
        borderRadius: '15px', padding: '30px', marginBottom: '20px', color: 'white'
      }}>
        <h2 style={{ fontSize: '28px', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <CheckCircle size={32} />
          Monatsbestätigungen
        </h2>
        <p style={{ opacity: 0.9 }}>Übersicht der Monatsbestätigungen aller Mitarbeiter (Kat. B/C)</p>
      </div>

      {/* Navigation + Summary */}
      <div style={{ display: 'flex', gap: '15px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {/* Month Nav */}
        <div style={{
          background: 'white', borderRadius: '12px', padding: '15px 20px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.08)', display: 'flex', alignItems: 'center', gap: '12px'
        }}>
          <button onClick={() => navigate(-1)} style={{ border: 'none', background: 'none', cursor: 'pointer', padding: '4px' }}>
            <ChevronLeft size={20} />
          </button>
          <span style={{ fontWeight: '700', fontSize: '16px', minWidth: '140px', textAlign: 'center' }}>
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button onClick={() => navigate(1)} style={{ border: 'none', background: 'none', cursor: 'pointer', padding: '4px' }}>
            <ChevronRight size={20} />
          </button>
        </div>

        {/* Summary Badges */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          {[
            { label: 'Bestätigt', count: counts.confirmed, bg: '#d1fae5', color: '#059669' },
            { label: 'Gesendet', count: counts.sent, bg: '#dbeafe', color: '#2563eb' },
            { label: 'Korrektur', count: counts.disputed, bg: '#fee2e2', color: '#dc2626' },
            { label: 'Offen', count: counts.not_sent, bg: '#f3f4f6', color: '#6b7280' },
          ].map(b => (
            <span key={b.label} style={{
              background: b.bg, color: b.color, padding: '8px 14px', borderRadius: '20px',
              fontSize: '13px', fontWeight: '600'
            }}>
              {b.count} {b.label}
            </span>
          ))}
        </div>

        {/* Trigger All */}
        <button
          onClick={handleTriggerAll}
          style={{
            marginLeft: 'auto', padding: '10px 20px', background: '#2563eb', color: 'white',
            border: 'none', borderRadius: '10px', cursor: 'pointer', fontWeight: '600',
            fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px'
          }}
        >
          <Send size={16} /> Alle auslösen
        </button>
      </div>

      {/* Table */}
      <div style={{
        background: 'white', borderRadius: '15px', boxShadow: '0 4px 15px rgba(0,0,0,0.1)', overflow: 'hidden'
      }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#999' }}>Lade...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ background: '#f9fafb', borderBottom: '2px solid #e5e7eb' }}>
              <tr>
                <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', fontSize: '13px' }}>Pers.Nr</th>
                <th style={{ padding: '14px 16px', textAlign: 'left', fontWeight: '600', fontSize: '13px' }}>Name</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Kat.</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Schichten</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Stunden</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Letzte Schicht</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Status</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Gesendet</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Bestätigt</th>
                <th style={{ padding: '14px 16px', textAlign: 'center', fontWeight: '600', fontSize: '13px' }}>Aktionen</th>
              </tr>
            </thead>
            <tbody>
              {confirmations.map(c => {
                const sc = STATUS_CONFIG[c.status] || STATUS_CONFIG.not_sent;
                const StatusIcon = sc.icon;
                const effectiveLastShift = c.last_shift_override || c.last_shift_date;
                return (
                  <tr key={c.employee_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <td style={{ padding: '12px 16px', fontWeight: '600', fontSize: '13px' }}>{c.personal_nr}</td>
                    <td style={{ padding: '12px 16px', fontSize: '14px' }}>{c.name}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{
                        background: c.tracking_mode === 'B' ? '#dbeafe' : '#fef3c7',
                        color: c.tracking_mode === 'B' ? '#2563eb' : '#d97706',
                        padding: '2px 10px', borderRadius: '12px', fontSize: '12px', fontWeight: '600'
                      }}>{c.tracking_mode}</span>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontWeight: '500' }}>{c.shift_count}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontWeight: '500' }}>
                      {c.total_hours}h
                      {(c.vacation_days > 0 || c.sick_days > 0) && (
                        <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '2px' }}>
                          {c.vacation_days > 0 && <span style={{ color: '#2563eb' }}>+{c.vacation_days}U </span>}
                          {c.sick_days > 0 && <span style={{ color: '#dc2626' }}>+{c.sick_days}K</span>}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontSize: '13px' }}>
                      {effectiveLastShift ? fmtDate(effectiveLastShift) : '-'}
                      {c.last_shift_override && (
                        <span style={{ display: 'block', fontSize: '10px', color: '#d97706', fontWeight: '600' }}>Override</span>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                        background: sc.bg, color: sc.color,
                        padding: '4px 12px', borderRadius: '16px', fontSize: '12px', fontWeight: '600'
                      }}>
                        <StatusIcon size={13} /> {c.status === 'confirmed' && c.confirmed_by === 'admin' ? 'Bestätigt (Admin)' : sc.label}
                      </span>
                      {c.status === 'disputed' && c.dispute_reason && (
                        <div style={{ fontSize: '11px', color: '#dc2626', marginTop: '4px', maxWidth: '150px' }}
                          title={c.dispute_reason}>
                          {c.dispute_reason.length > 40 ? c.dispute_reason.substring(0, 40) + '...' : c.dispute_reason}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', color: '#666' }}>
                      {fmtDateTime(c.sent_at)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', fontSize: '12px', color: '#666' }}>
                      {fmtDateTime(c.confirmed_at)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', flexWrap: 'wrap' }}>
                        {/* Admin bestätigt */}
                        {c.status !== 'confirmed' && (
                          <button
                            onClick={() => handleAdminConfirm(c.employee_id, c.name)}
                            title="Admin bestätigt"
                            style={{
                              padding: '6px 8px', background: '#d1fae5', border: '1px solid #6ee7b7',
                              borderRadius: '6px', cursor: 'pointer', color: '#059669'
                            }}
                          >
                            <ShieldCheck size={14} />
                          </button>
                        )}
                        {/* Reset */}
                        {(c.status === 'confirmed' || c.status === 'disputed' || c.status === 'sent') && (
                          <button
                            onClick={() => handleReset(c.employee_id)}
                            title="Zurücksetzen"
                            style={{
                              padding: '6px 8px', background: '#f3f4f6', border: '1px solid #d1d5db',
                              borderRadius: '6px', cursor: 'pointer', color: '#6b7280'
                            }}
                          >
                            <RotateCcw size={14} />
                          </button>
                        )}
                        {/* Remind */}
                        {c.status !== 'confirmed' && c.has_telegram && (
                          <button
                            onClick={() => handleRemind(c.employee_id)}
                            title="Erinnerung senden"
                            style={{
                              padding: '6px 8px', background: '#dbeafe', border: '1px solid #93c5fd',
                              borderRadius: '6px', cursor: 'pointer', color: '#2563eb'
                            }}
                          >
                            <Bell size={14} />
                          </button>
                        )}
                        {/* Override */}
                        <button
                          onClick={() => {
                            setOverrideDate(c.last_shift_override || '');
                            setOverrideModal(c.employee_id);
                          }}
                          title="Letzte Schicht überschreiben"
                          style={{
                            padding: '6px 8px', background: c.last_shift_override ? '#fef3c7' : '#f3f4f6',
                            border: c.last_shift_override ? '1px solid #fcd34d' : '1px solid #d1d5db',
                            borderRadius: '6px', cursor: 'pointer', color: c.last_shift_override ? '#d97706' : '#6b7280'
                          }}
                        >
                          <Calendar size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {confirmations.length === 0 && (
                <tr>
                  <td colSpan={10} style={{ padding: '40px', textAlign: 'center', color: '#999' }}>
                    Keine Mitarbeiter (Kat. B/C) gefunden
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* Override Modal */}
      {overrideModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
          <div style={{ background: 'white', borderRadius: '15px', padding: '25px', width: '400px', maxWidth: '90%' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '15px' }}>Letzte Schicht überschreiben</h3>
            <p style={{ fontSize: '13px', color: '#666', marginBottom: '15px' }}>
              Manuelles Datum setzen (z.B. wenn MA früher in Urlaub geht). Leer lassen = automatisch.
            </p>
            <input
              type="date"
              value={overrideDate}
              onChange={e => setOverrideDate(e.target.value)}
              style={{
                width: '100%', padding: '12px', border: '2px solid #e5e7eb',
                borderRadius: '8px', fontSize: '16px', marginBottom: '20px'
              }}
            />
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={() => setOverrideModal(null)}
                style={{ flex: 1, padding: '10px', background: '#f3f4f6', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}>
                Abbrechen
              </button>
              <button onClick={handleOverrideSave}
                style={{ flex: 1, padding: '10px', background: '#059669', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600' }}>
                Speichern
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MonatsbestaetigungenTab;
