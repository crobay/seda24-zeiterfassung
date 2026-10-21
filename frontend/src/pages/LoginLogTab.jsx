import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import api from '../services/api';

const ROLE_LABELS = {
  admin: 'Admin',
  objektleiter: 'Objektleitung',
  mitarbeiter: 'Mitarbeiter',
};

export default function LoginLogTab() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/auth-log?limit=500');
      setEntries(res.data);
    } catch (e) {
      console.error('Auth-Log laden fehlgeschlagen', e);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const filtered = entries.filter(e =>
    filter === 'all' ? true : filter === 'success' ? e.success : !e.success
  );

  const failedCount = entries.filter(e => !e.success).length;
  const successCount = entries.filter(e => e.success).length;

  return (
    <div style={{ padding: '0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>Login-Protokoll</h2>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '4px', background: '#f3f4f6', borderRadius: '8px', padding: '3px' }}>
            {[
              { key: 'all', label: `Alle (${entries.length})` },
              { key: 'success', label: `OK (${successCount})` },
              { key: 'failed', label: `Fehlgeschlagen (${failedCount})` },
            ].map(f => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                style={{
                  padding: '6px 12px', border: 'none', borderRadius: '6px', fontSize: '13px', cursor: 'pointer', fontWeight: 'bold',
                  background: filter === f.key ? (f.key === 'failed' ? '#fecaca' : '#dbeafe') : 'transparent',
                  color: filter === f.key ? (f.key === 'failed' ? '#dc2626' : '#2563eb') : '#666',
                }}>
                {f.label}
              </button>
            ))}
          </div>
          <button onClick={load}
            style={{ padding: '6px 12px', border: '1px solid #ddd', borderRadius: '8px', background: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '13px' }}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>Laden...</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#999' }}>Noch keine Login-Eintraege vorhanden.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {filtered.map((entry, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 14px',
              background: entry.success ? '#f0fdf4' : '#fef2f2',
              border: `1px solid ${entry.success ? '#bbf7d0' : '#fecaca'}`,
              borderRadius: '10px', fontSize: '14px', flexWrap: 'wrap',
            }}>
              {entry.success
                ? <CheckCircle size={18} color="#16a34a" />
                : <XCircle size={18} color="#dc2626" />
              }
              <span style={{ fontWeight: 'bold', color: entry.success ? '#166534' : '#991b1b', minWidth: '80px' }}>
                {entry.success ? 'Erfolgreich' : 'Fehlgeschlagen'}
              </span>
              <span style={{ color: '#374151', fontWeight: '500' }}>
                {entry.email}
              </span>
              {entry.name && (
                <span style={{ color: '#6b7280' }}>
                  ({entry.name}{entry.personal_nr ? `, ${entry.personal_nr}` : ''})
                </span>
              )}
              {entry.role && (
                <span style={{
                  padding: '2px 8px', borderRadius: '8px', fontSize: '11px', fontWeight: 'bold',
                  background: entry.role === 'admin' ? '#ede9fe' : entry.role === 'objektleiter' ? '#dbeafe' : '#f3f4f6',
                  color: entry.role === 'admin' ? '#7c3aed' : entry.role === 'objektleiter' ? '#2563eb' : '#666',
                }}>
                  {ROLE_LABELS[entry.role] || entry.role}
                </span>
              )}
              <span style={{ marginLeft: 'auto', color: '#9ca3af', fontSize: '12px', whiteSpace: 'nowrap' }}>
                {entry.ip}
              </span>
              <span style={{ color: '#9ca3af', fontSize: '12px', whiteSpace: 'nowrap' }}>
                {entry.timestamp}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
