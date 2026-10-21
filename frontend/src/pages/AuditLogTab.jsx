import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Search, ChevronLeft, ChevronRight, Filter, User, Clock } from 'lucide-react';

const ACTION_LABELS = {
  'push_confirmed': { label: 'Push bestaetigt', color: 'bg-green-100 text-green-700', group: 'Stempeln' },
  'push_not_present': { label: 'Nicht anwesend', color: 'bg-red-100 text-red-700', group: 'Stempeln' },
  'push_confirmed_with_colleague': { label: 'Push mit Kollege', color: 'bg-green-100 text-green-700', group: 'Stempeln' },
  'booking_created': { label: 'Buchung erstellt', color: 'bg-blue-100 text-blue-700', group: 'Buchungen' },
  'booking_updated': { label: 'Buchung geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Buchungen' },
  'booking_deleted': { label: 'Buchung geloescht', color: 'bg-red-100 text-red-700', group: 'Buchungen' },
  'booking_approved': { label: 'Buchung genehmigt', color: 'bg-green-100 text-green-700', group: 'Genehmigungen' },
  'booking_rejected': { label: 'Buchung abgelehnt', color: 'bg-red-100 text-red-700', group: 'Genehmigungen' },
  'schedule_created': { label: 'Dienstplan erstellt', color: 'bg-indigo-100 text-indigo-700', group: 'Dienstplan' },
  'schedule_updated': { label: 'Dienstplan geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Dienstplan' },
  'schedule_deleted': { label: 'Dienstplan geloescht', color: 'bg-red-100 text-red-700', group: 'Dienstplan' },
  'hourly_rate_changed': { label: 'Stundensatz geaendert', color: 'bg-orange-100 text-orange-700', group: 'Finanzen' },
  'vacation_entitlement_updated': { label: 'Urlaubsanspruch', color: 'bg-purple-100 text-purple-700', group: 'Urlaub' },
  'vacation_request_created': { label: 'Urlaubsantrag', color: 'bg-blue-100 text-blue-700', group: 'Urlaub' },
  'vacation_request_updated': { label: 'Urlaub geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Urlaub' },
  'vacation_request_approved': { label: 'Urlaub genehmigt', color: 'bg-green-100 text-green-700', group: 'Urlaub' },
  'vacation_request_rejected': { label: 'Urlaub abgelehnt', color: 'bg-red-100 text-red-700', group: 'Urlaub' },
  'vacation_request_cancelled': { label: 'Urlaub storniert', color: 'bg-gray-100 text-gray-700', group: 'Urlaub' },
  'vacation_request_pending': { label: 'Urlaub beantragt', color: 'bg-blue-100 text-blue-700', group: 'Urlaub' },
  'vacation_urlaub_created': { label: 'Urlaub angelegt', color: 'bg-blue-100 text-blue-700', group: 'Urlaub' },
  'mark_sick': { label: 'Krank gemeldet', color: 'bg-orange-100 text-orange-700', group: 'Krankmeldungen' },
  'sick_note_created': { label: 'Krankmeldung erstellt', color: 'bg-red-100 text-red-700', group: 'Krankmeldungen' },
  'sick_note_edited': { label: 'Krankmeldung bearbeitet', color: 'bg-yellow-100 text-yellow-700', group: 'Krankmeldungen' },
  'sick_note_deleted': { label: 'Krankmeldung geloescht', color: 'bg-red-100 text-red-700', group: 'Krankmeldungen' },
  'sick_note_telegram': { label: 'Krankmeldung (Telegram)', color: 'bg-orange-100 text-orange-700', group: 'Krankmeldungen' },
  'sick_note_rejected': { label: 'Krankmeldung abgelehnt', color: 'bg-red-100 text-red-700', group: 'Krankmeldungen' },
  'month_confirmed': { label: 'Monat bestaetigt', color: 'bg-green-100 text-green-700', group: 'Monatsbestaetigung' },
  'month_confirmed_by_admin': { label: 'Monat bestaetigt (Admin)', color: 'bg-green-100 text-green-700', group: 'Monatsbestaetigung' },
  'month_disputed': { label: 'Monat widersprochen', color: 'bg-orange-100 text-orange-700', group: 'Monatsbestaetigung' },
  'monthly_confirmations_triggered': { label: 'Bestaetigung ausgeloest', color: 'bg-blue-100 text-blue-700', group: 'Monatsbestaetigung' },
  'confirmation_reset': { label: 'Bestaetigung zurueckgesetzt', color: 'bg-yellow-100 text-yellow-700', group: 'Monatsbestaetigung' },
  'last_shift_override': { label: 'Letzte-Schicht ueberschrieben', color: 'bg-yellow-100 text-yellow-700', group: 'Monatsbestaetigung' },
  'employee_created': { label: 'Mitarbeiter angelegt', color: 'bg-green-100 text-green-700', group: 'Mitarbeiter' },
  'employee_updated': { label: 'Mitarbeiter geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Mitarbeiter' },
  'password_reset': { label: 'Passwort zurueckgesetzt', color: 'bg-orange-100 text-orange-700', group: 'Mitarbeiter' },
  'customer_created': { label: 'Kunde angelegt', color: 'bg-green-100 text-green-700', group: 'Kunden/Objekte' },
  'customer_updated': { label: 'Kunde geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Kunden/Objekte' },
  'object_created': { label: 'Objekt angelegt', color: 'bg-green-100 text-green-700', group: 'Kunden/Objekte' },
  'object_updated': { label: 'Objekt geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'Kunden/Objekte' },
  'km_entry_created': { label: 'KM-Eintrag angelegt', color: 'bg-blue-100 text-blue-700', group: 'KM-Journal' },
  'km_entry_updated': { label: 'KM-Eintrag geaendert', color: 'bg-yellow-100 text-yellow-700', group: 'KM-Journal' },
  'km_entry_deleted': { label: 'KM-Eintrag geloescht', color: 'bg-red-100 text-red-700', group: 'KM-Journal' },
  'km_entries_bulk_deleted': { label: 'KM-Eintraege geloescht', color: 'bg-red-100 text-red-700', group: 'KM-Journal' },
  'vacation_rate_corrected': { label: 'Urlaubssatz korrigiert', color: 'bg-orange-100 text-orange-700', group: 'Urlaub' },
  'correction_requested': { label: 'Korrektur beantragt', color: 'bg-yellow-100 text-yellow-700', group: 'Sonstiges' },
  'telegram_registration': { label: 'Telegram registriert', color: 'bg-blue-100 text-blue-700', group: 'Sonstiges' },
};

const ROLE_LABELS = {
  'admin': 'Admin',
  'objektleiter': 'Objektleitung',
  'mitarbeiter': 'Mitarbeiter',
};

const formatValue = (val) => {
  if (!val || typeof val !== 'object') return null;
  return Object.entries(val).map(([k, v]) => {
    const label = {
      stundensatz: 'Stundensatz',
      stunden: 'Stunden',
      datum: 'Datum',
      zeit: 'Zeit',
      objekt: 'Objekt',
      typ: 'Typ',
      status: 'Status',
      objekt_id: 'Objekt-ID',
      anspruch_tage: 'Anspruch (Tage)',
      jahr: 'Jahr',
      name: 'Name',
      personal_nr: 'Personal-Nr',
      email: 'E-Mail',
      adresse: 'Adresse',
      kunde_id: 'Kunden-ID',
      km: 'Kilometer',
      anzahl: 'Anzahl',
      first_name: 'Vorname',
      last_name: 'Nachname',
      tracking_mode: 'Kategorie',
      is_active: 'Aktiv',
      address: 'Adresse',
      kuerzel: 'Kuerzel',
      employment_type: 'Beschaeftigungsart',
      gps_required: 'GPS erforderlich',
      billing_type: 'Abrechnungsart',
      monthly_rate: 'Monatspauschale',
      cleaning_type: 'Reinigungsart',
    }[k] || k;
    const display = (k === 'stundensatz' && v !== null) ? `${v} EUR` :
                    (k === 'stunden' && v !== null) ? `${v}h` : String(v ?? '-');
    return `${label}: ${display}`;
  }).join(', ');
};

const AuditLogTab = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    startDate: '',
    endDate: '',
    action: '',
    employeeId: '',
    userId: '',
  });
  const [page, setPage] = useState(0);
  const [employees, setEmployees] = useState([]);
  const [adminUsers, setAdminUsers] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const LIMIT = 50;

  useEffect(() => {
    fetchLogs();
    fetchEmployees();
    fetchAdminUsers();
  }, [page]);

  const fetchEmployees = async () => {
    try {
      const res = await api.get('/admin/employees-with-categories');
      setEmployees(res.data || []);
    } catch (e) {}
  };

  const fetchAdminUsers = async () => {
    try {
      // Aus den Audit-Logs die unique changed_by extrahieren
      const res = await api.get('/admin/audit-log?limit=500');
      const users = {};
      (res.data || []).forEach(log => {
        if (log.user_id && log.changed_by) {
          users[log.user_id] = { id: log.user_id, name: log.changed_by, role: log.changed_by_role };
        }
      });
      setAdminUsers(Object.values(users));
    } catch (e) {}
  };

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('limit', LIMIT);
      params.set('offset', page * LIMIT);
      if (filters.startDate) params.set('start_date', filters.startDate);
      if (filters.endDate) params.set('end_date', filters.endDate);
      if (filters.action) params.set('action', filters.action);
      if (filters.employeeId) params.set('employee_id', filters.employeeId);
      if (filters.userId) params.set('user_id', filters.userId);

      const res = await api.get(`/admin/audit-log?${params.toString()}`);
      setLogs(res.data || []);
    } catch (error) {
      console.error('Audit-Log Fehler:', error);
      setLogs([]);
    }
    setLoading(false);
  };

  const handleSearch = () => {
    setPage(0);
    fetchLogs();
  };

  const formatAction = (action) => {
    const info = ACTION_LABELS[action] || { label: action, color: 'bg-gray-100 text-gray-600' };
    return <span className={`text-xs px-2 py-1 rounded font-medium ${info.color}`}>{info.label}</span>;
  };

  // Gruppen fuer Action-Filter
  const actionGroups = {};
  Object.entries(ACTION_LABELS).forEach(([key, val]) => {
    const g = val.group || 'Sonstiges';
    if (!actionGroups[g]) actionGroups[g] = [];
    actionGroups[g].push({ key, label: val.label });
  });

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold flex items-center gap-2">
        <Filter size={20} /> Aenderungsprotokoll
      </h2>

      {/* Filter */}
      <div className="bg-white p-4 rounded-lg shadow">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Von</label>
            <input
              type="date"
              value={filters.startDate}
              onChange={(e) => setFilters(f => ({ ...f, startDate: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Bis</label>
            <input
              type="date"
              value={filters.endDate}
              onChange={(e) => setFilters(f => ({ ...f, endDate: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Geaendert von</label>
            <select
              value={filters.userId}
              onChange={(e) => setFilters(f => ({ ...f, userId: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            >
              <option value="">Alle</option>
              {adminUsers.map(u => (
                <option key={u.id} value={u.id}>
                  {u.name} ({ROLE_LABELS[u.role] || u.role})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Betroffener MA</label>
            <select
              value={filters.employeeId}
              onChange={(e) => setFilters(f => ({ ...f, employeeId: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            >
              <option value="">Alle</option>
              {employees.filter(e => e.is_active !== false).map(emp => (
                <option key={emp.id} value={emp.id}>{emp.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Aktion</label>
            <select
              value={filters.action}
              onChange={(e) => setFilters(f => ({ ...f, action: e.target.value }))}
              className="w-full border rounded p-2 text-sm"
            >
              <option value="">Alle</option>
              {Object.entries(actionGroups).map(([group, actions]) => (
                <optgroup key={group} label={group}>
                  {actions.map(a => (
                    <option key={a.key} value={a.key}>{a.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleSearch}
              className="w-full bg-blue-500 text-white rounded p-2 flex items-center justify-center gap-1 hover:bg-blue-600"
            >
              <Search size={16} /> Suchen
            </button>
          </div>
        </div>
      </div>

      {/* Log-Eintraege */}
      {loading ? (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="space-y-1">
          {logs.map((log, idx) => (
            <div
              key={log.id || idx}
              className={`bg-white rounded p-3 shadow-sm border-l-4 ${
                log.action?.includes('deleted') || log.action?.includes('rejected') ? 'border-red-300' :
                log.action?.includes('created') || log.action?.includes('approved') || log.action?.includes('confirmed') ? 'border-green-300' :
                log.action?.includes('updated') || log.action?.includes('changed') ? 'border-yellow-300' :
                'border-blue-200'
              } cursor-pointer hover:bg-gray-50`}
              onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    {formatAction(log.action)}
                    {log.employee_name && (
                      <span className="text-sm font-medium">{log.employee_name}</span>
                    )}
                  </div>
                  {log.details && (
                    <p className="text-xs text-gray-600 mt-1">{log.details}</p>
                  )}
                  {/* Wer hat geaendert */}
                  {log.changed_by && (
                    <div className="flex items-center gap-1 mt-1">
                      <User size={12} className="text-gray-400" />
                      <span className="text-xs text-gray-500">
                        {log.changed_by}
                        {log.changed_by_role && (
                          <span className={`ml-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            log.changed_by_role === 'admin' ? 'bg-purple-100 text-purple-600' :
                            log.changed_by_role === 'objektleiter' ? 'bg-blue-100 text-blue-600' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {ROLE_LABELS[log.changed_by_role] || log.changed_by_role}
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                  {/* Erweiterte Details */}
                  {expandedId === log.id && (
                    <div className="mt-2 p-3 bg-gray-50 rounded text-xs space-y-2">
                      {log.old_value && (
                        <div>
                          <span className="font-medium text-red-600">Vorher:</span>{' '}
                          <span className="text-gray-700">{typeof log.old_value === 'object' ? formatValue(log.old_value) : String(log.old_value)}</span>
                        </div>
                      )}
                      {log.new_value && (
                        <div>
                          <span className="font-medium text-green-600">Nachher:</span>{' '}
                          <span className="text-gray-700">{typeof log.new_value === 'object' ? formatValue(log.new_value) : String(log.new_value)}</span>
                        </div>
                      )}
                      {log.entity_type && <p><span className="font-medium">Typ:</span> {log.entity_type}</p>}
                      {log.entity_id && <p><span className="font-medium">ID:</span> {log.entity_id}</p>}
                      <p><span className="font-medium">Log-ID:</span> {log.id}</p>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 text-xs text-gray-400 whitespace-nowrap ml-2">
                  <Clock size={12} />
                  {log.created_at ? new Date(log.created_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}
                </div>
              </div>
            </div>
          ))}
          {logs.length === 0 && (
            <p className="text-gray-500 text-center py-8">Keine Eintraege gefunden</p>
          )}
        </div>
      )}

      {/* Pagination */}
      <div className="flex justify-between items-center">
        <button
          onClick={() => setPage(p => Math.max(0, p - 1))}
          disabled={page === 0}
          className="flex items-center gap-1 text-sm text-blue-500 disabled:text-gray-300"
        >
          <ChevronLeft size={16} /> Zurueck
        </button>
        <span className="text-sm text-gray-500">Seite {page + 1} ({logs.length} Eintraege)</span>
        <button
          onClick={() => setPage(p => p + 1)}
          disabled={logs.length < LIMIT}
          className="flex items-center gap-1 text-sm text-blue-500 disabled:text-gray-300"
        >
          Weiter <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

export default AuditLogTab;
