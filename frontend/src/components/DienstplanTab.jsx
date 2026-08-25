import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { API_URL } from '../config.js';
import { ChevronLeft, ChevronRight, Calendar, MapPin, Clock, Car } from 'lucide-react';

const DienstplanTab = ({ token }) => {
  const [weekOffset, setWeekOffset] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const headers = { Authorization: `Bearer ${token}` };

  const load = async (offset) => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_URL}/schedule/my-week?week_offset=${offset}`, { headers });
      setData(res.data);
    } catch (e) {
      console.error('Dienstplan load error:', e);
      setData({ days: [], week_start: null, week_end: null });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(weekOffset); }, [weekOffset]);

  const formatDate = (isoStr) => {
    if (!isoStr) return '';
    const d = new Date(isoStr + 'T00:00:00');
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
  };

  const formatDateFull = (isoStr) => {
    if (!isoStr) return '';
    const d = new Date(isoStr + 'T00:00:00');
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  };

  const isToday = (isoStr) => {
    if (!isoStr) return false;
    return isoStr === new Date().toISOString().split('T')[0];
  };

  const weekLabel = data?.week_start && data?.week_end
    ? `${formatDateFull(data.week_start)} - ${formatDateFull(data.week_end)}`
    : '';

  return (
    <div style={{ padding: '16px', paddingBottom: '100px' }}>
      {/* Header mit Wochenwechsel */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16, background: '#f0f4ff', borderRadius: 12, padding: '12px 8px'
      }}>
        <button onClick={() => setWeekOffset(weekOffset - 1)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8, borderRadius: 8, display: 'flex', alignItems: 'center' }}>
          <ChevronLeft size={28} color="#1e3a5f" />
        </button>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: '#6b7280', fontWeight: 500 }}>
            {weekOffset === 0 ? 'Aktuelle Woche' : weekOffset === 1 ? 'Nächste Woche' : weekOffset === -1 ? 'Letzte Woche' : `${weekOffset > 0 ? '+' : ''}${weekOffset} Wochen`}
          </div>
          <div style={{ fontSize: 15, fontWeight: 'bold', color: '#1e3a5f' }}>{weekLabel}</div>
        </div>
        <button onClick={() => setWeekOffset(weekOffset + 1)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8, borderRadius: 8, display: 'flex', alignItems: 'center' }}>
          <ChevronRight size={28} color="#1e3a5f" />
        </button>
      </div>

      {/* Heute-Button wenn nicht aktuelle Woche */}
      {weekOffset !== 0 && (
        <button onClick={() => setWeekOffset(0)}
          style={{
            display: 'block', margin: '0 auto 16px', padding: '6px 20px',
            background: '#1e3a5f', color: 'white', border: 'none', borderRadius: 20,
            fontSize: 13, fontWeight: 'bold', cursor: 'pointer'
          }}>
          Zur aktuellen Woche
        </button>
      )}

      {/* Inhalt */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ width: 36, height: 36, border: '3px solid #ddd', borderTopColor: '#1e3a5f', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto' }} />
        </div>
      ) : data?.days?.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '48px 20px', background: '#f9fafb',
          borderRadius: 16, color: '#9ca3af'
        }}>
          <Calendar size={48} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
          <p style={{ fontSize: 16, fontWeight: 600, color: '#6b7280', margin: '0 0 4px' }}>Keine Schichten diese Woche geplant</p>
          <p style={{ fontSize: 13, margin: 0 }}>Wechsle die Woche mit den Pfeilen oben.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {data.days.map((d, i) => {
            const today = isToday(d.date);
            return (
              <div key={i} style={{
                background: today ? '#eff6ff' : 'white',
                border: today ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                borderRadius: 14, padding: '14px 16px',
                boxShadow: today ? '0 2px 8px rgba(59,130,246,0.15)' : '0 1px 3px rgba(0,0,0,0.04)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      background: today ? '#3b82f6' : '#e5e7eb',
                      color: today ? 'white' : '#374151',
                      padding: '3px 10px', borderRadius: 8, fontSize: 13, fontWeight: 700
                    }}>
                      {d.weekday_short}
                    </span>
                    <span style={{ fontSize: 14, color: '#6b7280' }}>{formatDate(d.date)}</span>
                    {today && <span style={{ fontSize: 11, color: '#3b82f6', fontWeight: 600 }}>HEUTE</span>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {d.is_driver && <Car size={16} color="#f59e0b" title="Fahrer" />}
                    {d.status === 'vertretung' && (
                      <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '2px 8px', borderRadius: 10, fontWeight: 600 }}>Vertretung</span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <MapPin size={16} color="#6b7280" />
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#1e3a5f' }}>{d.object_name}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Clock size={16} color="#6b7280" />
                  <span style={{ fontSize: 14, color: '#374151' }}>
                    {d.start_time && d.end_time ? `${d.start_time} - ${d.end_time}` : '\u2014'}
                    {d.planned_hours > 0 && <span style={{ color: '#9ca3af', marginLeft: 8 }}>({d.planned_hours} Std.)</span>}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default DienstplanTab;
