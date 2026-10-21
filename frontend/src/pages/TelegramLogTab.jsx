import React, { useState, useEffect } from 'react';
import { Send, AlertTriangle, MinusCircle, Clock, CheckCheck, Hourglass, ArrowRight, RefreshCw } from 'lucide-react';
import api from '../services/api';

const TYPE_LABELS = {
  shift_confirm: 'Schichtbestaetigung',
  reminder: 'Erinnerung',
  missing_stamp_ma: 'Fehlende Stempelung (MA)',
  missing_stamp_admin: 'Fehlende Stempelung (Admin)',
  overdue_ma: 'Ueberfaellig (MA)',
  overdue_admin: 'Ueberfaellig (Admin)',
  monthly_confirm: 'Monatsbestaetigung',
  correction_request: 'Korrekturanfrage',
};

const STATUS_CONFIG = {
  sent:         { label: 'Zugestellt',     icon: <Send size={14} />,           bg: 'bg-blue-100 text-blue-800', border: '' },
  failed:       { label: 'Fehlgeschlagen', icon: <AlertTriangle size={14} />,  bg: 'bg-red-100 text-red-800',   border: 'border-l-4 border-red-500' },
  no_chat_id:   { label: 'Kein Bot',       icon: <MinusCircle size={14} />,    bg: 'bg-gray-100 text-gray-600', border: '' },
  pending:      { label: 'Ausstehend',     icon: <Clock size={14} />,          bg: 'bg-yellow-100 text-yellow-800', border: 'border border-dashed border-yellow-400' },
  responded:    { label: 'Beantwortet',    icon: <CheckCheck size={14} />,     bg: 'bg-blue-100 text-blue-800', border: 'border-2 border-blue-500' },
  expired:      { label: 'Abgelaufen',     icon: <Hourglass size={14} />,      bg: 'bg-gray-100 text-gray-500', border: '' },
  skipped_cat_c:{ label: 'Uebersprungen',  icon: <ArrowRight size={14} />,     bg: 'bg-gray-100 text-gray-500', border: '' },
};

const formatDateTime = (iso) => {
  if (!iso) return '–';
  const d = new Date(iso);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' })
    + ' ' + d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
};

const formatTime = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
};

const TelegramLogTab = ({ employees }) => {
  const [stats, setStats] = useState(null);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedRow, setExpandedRow] = useState(null);

  // Filter state
  const today = new Date();
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(today.getDate() - 7);
  const toISO = (d) => d.toISOString().split('T')[0];

  const [dateFrom, setDateFrom] = useState(toISO(sevenDaysAgo));
  const [dateTo, setDateTo] = useState(toISO(today));
  const [filterEmployee, setFilterEmployee] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');

  const loadStats = async () => {
    try {
      const res = await api.get('/admin/telegram-log/stats');
      setStats(res.data);
    } catch (e) {
      console.error('Stats laden fehlgeschlagen:', e);
    }
  };

  const loadEntries = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      params.limit = 500;
      const res = await api.get('/admin/telegram-log', { params });
      setEntries(res.data.items || []);
    } catch (e) {
      console.error('Telegram-Log laden fehlgeschlagen:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
    loadEntries();
  }, []);

  // Reload when date range changes
  useEffect(() => {
    loadEntries();
  }, [dateFrom, dateTo]);

  // Client-side filtering
  const filtered = entries.filter(e => {
    if (filterEmployee !== 'all' && e.employee_id !== parseInt(filterEmployee)) return false;
    if (filterType !== 'all' && e.notification_type !== filterType) return false;
    if (filterStatus !== 'all') {
      if (filterStatus === 'responded') {
        if (!e.response_status) return false;
      } else if (e.status !== filterStatus) {
        return false;
      }
    }
    return true;
  });

  const getEffectiveStatus = (entry) => {
    if (entry.response_status) return 'responded';
    return entry.status || 'pending';
  };

  const renderStatusBadge = (entry) => {
    const effectiveStatus = getEffectiveStatus(entry);
    const cfg = STATUS_CONFIG[effectiveStatus] || STATUS_CONFIG.pending;
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cfg.bg} ${cfg.border}`}
        style={effectiveStatus === 'expired' ? { textDecoration: 'line-through' } : {}}>
        {cfg.icon} {cfg.label}
      </span>
    );
  };

  const renderReaction = (entry) => {
    if (entry.notification_type !== 'shift_confirm') return '–';
    if (entry.response_status === 'confirmed') {
      return <span className="text-green-700 font-medium">Bestaetigt {formatTime(entry.responded_at) && `um ${formatTime(entry.responded_at)}`}</span>;
    }
    if (entry.response_status === 'rejected') {
      return <span className="text-red-700 font-medium">Abgelehnt {formatTime(entry.responded_at) && `um ${formatTime(entry.responded_at)}`}</span>;
    }
    if (entry.status !== 'expired') {
      return <span className="text-gray-500">Keine Reaktion</span>;
    }
    return <span className="text-gray-400">Abgelaufen</span>;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg shadow p-6 text-white flex justify-between items-center">
        <h2 className="text-2xl font-bold">Telegram-Log</h2>
        <button onClick={() => { loadStats(); loadEntries(); }} className="px-4 py-2 bg-white bg-opacity-20 rounded-lg text-white font-medium flex items-center gap-2 hover:bg-opacity-30">
          <RefreshCw size={18} /> Aktualisieren
        </button>
      </div>

      {/* Statistik-Karten */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-600">Gesamt (7 Tage)</p>
            <p className="text-2xl font-bold text-indigo-600">{stats.total_7d}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-600"><Send size={14} className="inline mr-1" />Zugestellt</p>
            <p className="text-2xl font-bold text-blue-600">{stats.sent}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-600"><AlertTriangle size={14} className="inline mr-1" />Fehlgeschlagen</p>
            <p className="text-2xl font-bold text-red-600">{stats.failed}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-sm text-gray-600"><MinusCircle size={14} className="inline mr-1" />Ohne Bot</p>
            <p className="text-2xl font-bold text-gray-600">{stats.no_chat_id}</p>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="font-bold text-lg mb-4">Filter</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Von</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bis</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Mitarbeiter</label>
            <select value={filterEmployee} onChange={e => setFilterEmployee(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm">
              <option value="all">Alle</option>
              {(employees || []).map(emp => (
                <option key={emp.id} value={emp.id}>{emp.first_name} {emp.last_name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Typ</label>
              <select value={filterType} onChange={e => setFilterType(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm">
                <option value="all">Alle</option>
                {Object.entries(TYPE_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
              <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm">
                <option value="all">Alle</option>
                {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Tabelle */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-4 py-3 border-b flex justify-between items-center">
          <span className="text-sm text-gray-600">{filtered.length} Eintraege{entries.length !== filtered.length && ` (von ${entries.length})`}</span>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-500">Lade Daten...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Keine Eintraege gefunden</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Datum/Uhrzeit</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">MA</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Typ</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Kanal</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Reaktion</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(entry => (
                  <React.Fragment key={entry.id}>
                    <tr className={`hover:bg-gray-50 cursor-pointer ${entry.status === 'failed' ? 'bg-red-50' : ''}`}
                      onClick={() => setExpandedRow(expandedRow === entry.id ? null : entry.id)}>
                      <td className="px-3 py-2 whitespace-nowrap">{formatDateTime(entry.created_at)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="font-medium">{entry.employee_name}</span>
                        <span className="text-gray-400 text-xs ml-1">{entry.personal_nr}</span>
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{TYPE_LABELS[entry.notification_type] || entry.notification_type}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{entry.channel || 'telegram'}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{renderStatusBadge(entry)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{renderReaction(entry)}</td>
                      <td className="px-3 py-2">
                        <span className="text-gray-500 text-xs truncate block max-w-[200px]" title={entry.title}>
                          {entry.title}
                        </span>
                      </td>
                    </tr>
                    {/* Expanded row: show body + error details */}
                    {expandedRow === entry.id && (
                      <tr>
                        <td colSpan={7} className="px-4 py-3 bg-gray-50">
                          <div className="space-y-2">
                            {entry.body && (
                              <div className="text-sm text-gray-700">
                                <span className="font-medium">Nachricht:</span> {entry.body}
                              </div>
                            )}
                            {entry.sent_at && (
                              <div className="text-xs text-gray-500">Gesendet: {formatDateTime(entry.sent_at)}</div>
                            )}
                            {entry.status === 'failed' && entry.response_data && (
                              <div className="bg-red-100 border border-red-300 rounded p-2 text-sm text-red-800">
                                <span className="font-medium">Fehler:</span> {entry.response_data}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default TelegramLogTab;
